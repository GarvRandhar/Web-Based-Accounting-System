from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.models import Vendor, Bill, Account, Tax, db
from app.services.ap import AccountsPayableService
from app.services.audit import AuditService

ap_bp = Blueprint('ap', __name__, url_prefix='/ap')

@ap_bp.route('/vendors', methods=['GET', 'POST'])
@login_required
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
    bills = Bill.query.order_by(Bill.date.desc()).all()
    return render_template('ap/bills.html', bills=bills)

@ap_bp.route('/bills/new', methods=['GET', 'POST'])
@login_required
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
                if descriptions[i]: 
                    items.append({
                        'description': descriptions[i],
                        'quantity': float(quantities[i]),
                        'unit_price': float(prices[i]),
                        'account_id': int(accounts[i]),
                        'tax_id': int(tax_ids[i]) if tax_ids and tax_ids[i] else None
                    })
            
            bill = AccountsPayableService.create_bill(vendor_id, due_date, items)
            flash(f'Bill #{bill.id} created successfully.', 'success')
            return redirect(url_for('ap.view_bill', id=bill.id))
            
        except Exception as e:
            flash(f'Error creating bill: {e}', 'error')

    vendors = Vendor.query.order_by(Vendor.name).all()
    expense_accounts = Account.query.filter_by(type='Expense').all()
    taxes = Tax.query.filter_by(is_active=True).all()
    return render_template('ap/bill_form.html', vendors=vendors, expense_accounts=expense_accounts, taxes=taxes)

@ap_bp.route('/bills/<int:id>')
@login_required
def view_bill(id):
    bill = Bill.query.get_or_404(id)
    return render_template('ap/bill_view.html', bill=bill, company=bill.vendor) 

@ap_bp.route('/bills/<int:id>/post', methods=['POST'])
@login_required
def post_bill(id):
    try:
        AccountsPayableService.post_bill(id)
        flash('Bill posted to General Ledger successfully.', 'success')
    except Exception as e:
        flash(f'Error posting bill: {e}', 'error')
    return redirect(url_for('ap.view_bill', id=id))

@ap_bp.route('/bills/<int:id>/cancel', methods=['POST'])
@login_required
def cancel_bill(id):
    try:
        AccountsPayableService.cancel_bill(id)
        flash(f'Bill #{id} has been cancelled.', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        flash(f'Error cancelling bill: {e}', 'error')
    return redirect(url_for('ap.view_bill', id=id))
