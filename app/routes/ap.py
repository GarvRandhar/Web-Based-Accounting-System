from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.models import Vendor, Bill, Account, Tax, db
from app.services.ap import AccountsPayableService
from app.services.audit import AuditService
from app.decorators import accountant_or_admin_required
from datetime import datetime

ap_bp = Blueprint('ap', __name__, url_prefix='/ap')

@ap_bp.route('/vendors', methods=['GET', 'POST'])
@login_required
@accountant_or_admin_required
def vendors():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        address = request.form.get('address')
        currency = request.form.get('currency', 'USD')
        
        try:
            AccountsPayableService.create_vendor(name, email, phone, address, currency)
            flash('Vendor created successfully!', 'success')
            return redirect(url_for('ap.vendors'))
        except Exception as e:
            flash(f'Error creating vendor: {e}', 'error')

    vendors = Vendor.query.order_by(Vendor.name).all()
    return render_template('ap/vendors.html', vendors=vendors)

@ap_bp.route('/vendors/<int:id>/edit', methods=['POST'])
@login_required
@accountant_or_admin_required
def edit_vendor(id):
    vendor = Vendor.query.get_or_404(id)
    vendor.name = request.form.get('name', vendor.name).strip()
    vendor.email = request.form.get('email', '').strip()
    vendor.phone = request.form.get('phone', '').strip()
    vendor.address = request.form.get('address', '').strip()
    vendor.currency = request.form.get('currency', vendor.currency).strip()
    
    db.session.commit()
    AuditService.log(action='UPDATE', model='Vendor', model_id=vendor.id, details=f"Updated vendor: {vendor.name}")
    flash(f'Vendor {vendor.name} updated.', 'success')
    return redirect(url_for('ap.vendors'))

@ap_bp.route('/vendors/<int:id>/delete', methods=['POST'])
@login_required
@accountant_or_admin_required
def delete_vendor(id):
    vendor = Vendor.query.get_or_404(id)
    if vendor.bills:
        flash(f'Cannot delete vendor {vendor.name} — they have existing bills.', 'error')
    else:
        AuditService.log(action='DELETE', model='Vendor', model_id=vendor.id, details=f"Deleted vendor: {vendor.name}")
        db.session.delete(vendor)
        db.session.commit()
        flash(f'Vendor {vendor.name} deleted.', 'success')
    return redirect(url_for('ap.vendors'))

@ap_bp.route('/bills')
@login_required
def bills():
    # Auto-update overdue statuses before displaying
    AccountsPayableService.refresh_overdue_statuses()
    bills = Bill.query.order_by(Bill.date.desc()).all()
    return render_template('ap/bills.html', bills=bills)

@ap_bp.route('/bills/new', methods=['GET', 'POST'])
@login_required
@accountant_or_admin_required
def new_bill():
    if request.method == 'POST':
        try:
            vendor_id = request.form.get('vendor_id')
            due_date = request.form.get('due_date')
            
            descriptions = request.form.getlist('description[]')
            quantities = request.form.getlist('quantity[]')
            prices = request.form.getlist('price[]')
            accounts = request.form.getlist('account_id[]')
            tax_ids = request.form.getlist('tax_id[]')
            
            items = []
            for i in range(len(descriptions)):
                if not descriptions[i].strip():
                    continue
                
                try:
                    qty_raw = quantities[i].strip() if i < len(quantities) else '1'
                    price_raw = prices[i].strip() if i < len(prices) else '0'
                    acc_id_raw = accounts[i].strip() if i < len(accounts) else ''
                    tax_id_raw = tax_ids[i].strip() if tax_ids and i < len(tax_ids) else ''

                    qty = float(qty_raw or '1')
                    price = float(price_raw or '0')
                    acc_id = int(acc_id_raw)
                    tax_id = int(tax_id_raw) if tax_id_raw else None

                    items.append({
                        'description': descriptions[i],
                        'quantity': qty,
                        'unit_price': price,
                        'account_id': acc_id,
                        'tax_id': tax_id
                    })
                except (ValueError, IndexError):
                    raise ValueError(f"Invalid numeric value or missing account on line {i + 1}.")
            
            bill = AccountsPayableService.create_bill(vendor_id, due_date, items)
            flash(f'Bill {bill.bill_number} created successfully.', 'success')
            return redirect(url_for('ap.view_bill', id=bill.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating bill: {e}', 'error')

    vendors = Vendor.query.order_by(Vendor.name).all()
    expense_accounts = Account.query.filter_by(type='Expense').all()
    taxes = Tax.query.filter_by(is_active=True).all()
    form_data = request.form if request.method == 'POST' else None
    return render_template('ap/bill_form.html', vendors=vendors, expense_accounts=expense_accounts, taxes=taxes, form_data=form_data)

@ap_bp.route('/bills/<int:id>')
@login_required
def view_bill(id):
    # Refresh overdue on view too
    AccountsPayableService.refresh_overdue_statuses()
    bill = Bill.query.get_or_404(id)
    return render_template('ap/bill_view.html', bill=bill, company=bill.vendor) 

@ap_bp.route('/bills/<int:id>/post', methods=['POST'])
@login_required
@accountant_or_admin_required
def post_bill(id):
    try:
        AccountsPayableService.post_bill(id)
        flash('Bill posted to General Ledger successfully.', 'success')
    except Exception as e:
        flash(f'Error posting bill: {e}', 'error')
    return redirect(url_for('ap.view_bill', id=id))

@ap_bp.route('/bills/<int:id>/cancel', methods=['POST'])
@login_required
@accountant_or_admin_required
def cancel_bill(id):
    try:
        AccountsPayableService.cancel_bill(id)
        flash(f'Bill #{id} has been cancelled.', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        flash(f'Error cancelling bill: {e}', 'error')
    return redirect(url_for('ap.view_bill', id=id))


@ap_bp.route('/bills/<int:id>/pay', methods=['GET', 'POST'])
@login_required
@accountant_or_admin_required
def pay_bill(id):
    """Record a cash disbursement against a posted bill."""
    AccountsPayableService.refresh_overdue_statuses()
    bill = Bill.query.get_or_404(id)

    if bill.status not in ('Posted', 'Overdue'):
        flash(f'Bill is not payable (status: {bill.status}).', 'error')
        return redirect(url_for('ap.view_bill', id=id))

    if request.method == 'POST':
        try:
            amount          = request.form.get('amount')
            payment_date    = request.form.get('payment_date')
            bank_account_id = request.form.get('bank_account_id')
            notes           = request.form.get('notes', '')

            if not amount or not payment_date or not bank_account_id:
                raise ValueError("Amount, payment date, and bank account are all required.")

            AccountsPayableService.record_payment(
                bill_id=id,
                amount=float(amount),
                payment_date=payment_date,
                bank_account_id=int(bank_account_id),
                notes=notes,
            )
            flash(f'Payment of {amount} recorded for Bill #{id}.', 'success')
            return redirect(url_for('ap.view_bill', id=id))
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash(f'Error recording payment: {e}', 'error')

    bank_accounts = Account.query.filter(
        Account.type == 'Asset',
        Account.name.in_(['Cash', 'Bank', 'Petty Cash'])
    ).order_by(Account.name).all()
    if not bank_accounts:
        bank_accounts = Account.query.filter_by(type='Asset').order_by(Account.code).all()

    return render_template('ap/pay_bill.html', bill=bill, bank_accounts=bank_accounts)


@ap_bp.route('/aging')
@login_required
def ap_aging():
    """Accounts Payable Aging Report."""
    date_str = request.args.get('as_of_date', datetime.today().strftime('%Y-%m-%d'))
    try:
        as_of_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        as_of_date = datetime.today().date()
        date_str = as_of_date.strftime('%Y-%m-%d')

    AccountsPayableService.refresh_overdue_statuses()
    data = AccountsPayableService.get_ap_aging(as_of_date)
    return render_template('ap/aging.html', data=data, as_of_date_str=date_str)
