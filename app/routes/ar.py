from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.models import Customer, Invoice, Account, Tax, db
from app.services.ar import AccountsReceivableService
from app.services.audit import AuditService
from app.decorators import accountant_or_admin_required
from datetime import datetime

ar_bp = Blueprint('ar', __name__, url_prefix='/ar')

@ar_bp.route('/customers', methods=['GET', 'POST'])
@login_required
@accountant_or_admin_required
def customers():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        address = request.form.get('address')
        currency = request.form.get('currency', 'USD')
        
        try:
            AccountsReceivableService.create_customer(name, email, phone, address, currency)
            flash('Customer created successfully!', 'success')
            return redirect(url_for('ar.customers'))
        except Exception as e:
            flash(f'Error creating customer: {e}', 'error')

    customers = Customer.query.order_by(Customer.name).all()
    return render_template('ar/customers.html', customers=customers)

@ar_bp.route('/customers/<int:id>/edit', methods=['POST'])
@login_required
@accountant_or_admin_required
def edit_customer(id):
    customer = Customer.query.get_or_404(id)
    customer.name = request.form.get('name', customer.name).strip()
    customer.email = request.form.get('email', '').strip()
    customer.phone = request.form.get('phone', '').strip()
    customer.address = request.form.get('address', '').strip()
    customer.currency = request.form.get('currency', customer.currency).strip()
    
    db.session.commit()
    AuditService.log(action='UPDATE', model='Customer', model_id=customer.id, details=f"Updated customer: {customer.name}")
    flash(f'Customer {customer.name} updated.', 'success')
    return redirect(url_for('ar.customers'))

@ar_bp.route('/customers/<int:id>/delete', methods=['POST'])
@login_required
@accountant_or_admin_required
def delete_customer(id):
    customer = Customer.query.get_or_404(id)
    if customer.invoices:
        flash(f'Cannot delete customer {customer.name} — they have existing invoices.', 'error')
    else:
        AuditService.log(action='DELETE', model='Customer', model_id=customer.id, details=f"Deleted customer: {customer.name}")
        db.session.delete(customer)
        db.session.commit()
        flash(f'Customer {customer.name} deleted.', 'success')
    return redirect(url_for('ar.customers'))

@ar_bp.route('/invoices')
@login_required
def invoices():
    # Auto-update overdue statuses before displaying
    AccountsReceivableService.refresh_overdue_statuses()
    invoices = Invoice.query.order_by(Invoice.date.desc()).all()
    return render_template('ar/invoices.html', invoices=invoices)

@ar_bp.route('/invoices/new', methods=['GET', 'POST'])
@login_required
@accountant_or_admin_required
def new_invoice():
    if request.method == 'POST':
        try:
            customer_id = request.form.get('customer_id')
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
            
            invoice = AccountsReceivableService.create_invoice(customer_id, due_date, items)
            flash(f'Invoice {invoice.invoice_number} created successfully as Draft.', 'success')
            return redirect(url_for('ar.view_invoice', id=invoice.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating invoice: {e}', 'error')

    customers = Customer.query.order_by(Customer.name).all()
    revenue_accounts = Account.query.filter_by(type='Revenue').all()
    taxes = Tax.query.filter_by(is_active=True).all()
    return render_template('ar/invoice_form.html', customers=customers, revenue_accounts=revenue_accounts, taxes=taxes)

@ar_bp.route('/invoices/<int:id>')
@login_required
def view_invoice(id):
    # Refresh overdue on view too
    AccountsReceivableService.refresh_overdue_statuses()
    invoice = Invoice.query.get_or_404(id)
    return render_template('ar/invoice_view.html', invoice=invoice, company=invoice.customer)

@ar_bp.route('/invoices/<int:id>/post', methods=['POST'])
@login_required
@accountant_or_admin_required
def post_invoice(id):
    try:
        AccountsReceivableService.post_invoice(id)
        flash('Invoice posted to General Ledger successfully.', 'success')
    except Exception as e:
        flash(f'Error posting invoice: {e}', 'error')
    return redirect(url_for('ar.view_invoice', id=id))

@ar_bp.route('/invoices/<int:id>/cancel', methods=['POST'])
@login_required
@accountant_or_admin_required
def cancel_invoice(id):
    try:
        AccountsReceivableService.cancel_invoice(id)
        flash(f'Invoice #{id} has been cancelled.', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        flash(f'Error cancelling invoice: {e}', 'error')
    return redirect(url_for('ar.view_invoice', id=id))


@ar_bp.route('/invoices/<int:id>/pay', methods=['GET', 'POST'])
@login_required
@accountant_or_admin_required
def pay_invoice(id):
    """Record a cash receipt against a posted invoice."""
    AccountsReceivableService.refresh_overdue_statuses()
    invoice = Invoice.query.get_or_404(id)

    if invoice.status not in ('Sent', 'Overdue'):
        flash(f'Invoice is not payable (status: {invoice.status}).', 'error')
        return redirect(url_for('ar.view_invoice', id=id))

    if request.method == 'POST':
        try:
            amount          = request.form.get('amount')
            payment_date    = request.form.get('payment_date')
            bank_account_id = request.form.get('bank_account_id')
            notes           = request.form.get('notes', '')

            if not amount or not payment_date or not bank_account_id:
                raise ValueError("Amount, payment date, and bank account are all required.")

            AccountsReceivableService.record_payment(
                invoice_id=id,
                amount=float(amount),
                payment_date=payment_date,
                bank_account_id=int(bank_account_id),
                notes=notes,
            )
            flash(f'Payment of {amount} recorded for Invoice #{id}.', 'success')
            return redirect(url_for('ar.view_invoice', id=id))
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

    return render_template('ar/pay_invoice.html', invoice=invoice, bank_accounts=bank_accounts)


@ar_bp.route('/aging')
@login_required
def ar_aging():
    """Accounts Receivable Aging Report."""
    date_str = request.args.get('as_of_date', datetime.today().strftime('%Y-%m-%d'))
    try:
        as_of_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        as_of_date = datetime.today().date()
        date_str = as_of_date.strftime('%Y-%m-%d')

    AccountsReceivableService.refresh_overdue_statuses()
    data = AccountsReceivableService.get_ar_aging(as_of_date)
    return render_template('ar/aging.html', data=data, as_of_date_str=date_str)
