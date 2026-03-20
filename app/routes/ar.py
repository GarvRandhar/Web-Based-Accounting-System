from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.models import Customer, Invoice, Account, Tax, db
from app.services.ar import AccountsReceivableService
from app.services.audit import AuditService

ar_bp = Blueprint('ar', __name__, url_prefix='/ar')

@ar_bp.route('/customers', methods=['GET', 'POST'])
@login_required
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
    invoices = Invoice.query.order_by(Invoice.date.desc()).all()
    return render_template('ar/invoices.html', invoices=invoices)

@ar_bp.route('/invoices/new', methods=['GET', 'POST'])
@login_required
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
                if descriptions[i]:
                    items.append({
                        'description': descriptions[i],
                        'quantity': float(quantities[i]),
                        'unit_price': float(prices[i]),
                        'account_id': int(accounts[i]),
                        'tax_id': int(tax_ids[i]) if tax_ids and tax_ids[i] else None
                    })
            
            invoice = AccountsReceivableService.create_invoice(customer_id, due_date, items)
            flash(f'Invoice #{invoice.id} created successfully as Draft.', 'success')
            return redirect(url_for('ar.view_invoice', id=invoice.id))
            
        except Exception as e:
            flash(f'Error creating invoice: {e}', 'error')

    customers = Customer.query.order_by(Customer.name).all()
    revenue_accounts = Account.query.filter_by(type='Revenue').all()
    taxes = Tax.query.filter_by(is_active=True).all()
    return render_template('ar/invoice_form.html', customers=customers, revenue_accounts=revenue_accounts, taxes=taxes)

@ar_bp.route('/invoices/<int:id>')
@login_required
def view_invoice(id):
    invoice = Invoice.query.get_or_404(id)
    return render_template('ar/invoice_view.html', invoice=invoice, company=invoice.customer)

@ar_bp.route('/invoices/<int:id>/post', methods=['POST'])
@login_required
def post_invoice(id):
    try:
        AccountsReceivableService.post_invoice(id)
        flash('Invoice posted to General Ledger successfully.', 'success')
    except Exception as e:
        flash(f'Error posting invoice: {e}', 'error')
    return redirect(url_for('ar.view_invoice', id=id))

@ar_bp.route('/invoices/<int:id>/cancel', methods=['POST'])
@login_required
def cancel_invoice(id):
    try:
        AccountsReceivableService.cancel_invoice(id)
        flash(f'Invoice #{id} has been cancelled.', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        flash(f'Error cancelling invoice: {e}', 'error')
    return redirect(url_for('ar.view_invoice', id=id))
