from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.models import CompanySettings, Tax, Account, db
from app.decorators import admin_required
from app.services.accounting import AccountingService
from datetime import datetime

settings_bp = Blueprint('settings', __name__, url_prefix='/settings')

@settings_bp.route('/', methods=['GET', 'POST'])
@login_required
@admin_required
def index():
    settings = CompanySettings.query.first()
    if not settings:
        settings = CompanySettings()
        db.session.add(settings)
        db.session.commit()
        
    if request.method == 'POST':
        settings.company_name = request.form.get('company_name')
        settings.address = request.form.get('address')
        settings.tax_id = request.form.get('tax_id')
        settings.currency_symbol = request.form.get('currency_symbol')
        settings.base_currency = request.form.get('base_currency', 'USD')
        db.session.commit()
        flash('Settings updated successfully.', 'success')
        return redirect(url_for('settings.index'))
    
    taxes = Tax.query.all()
    liability_accounts = Account.query.filter(Account.type.in_(['Liability', 'Asset'])).order_by(Account.code).all()
    return render_template('settings/index.html', settings=settings, taxes=taxes, liability_accounts=liability_accounts)

# === TAX MANAGEMENT ===

@settings_bp.route('/taxes/new', methods=['POST'])
@login_required
@admin_required
def create_tax():
    name = request.form.get('name', '').strip()
    rate = request.form.get('rate', '0')
    sales_tax_account_id = request.form.get('sales_tax_account_id')
    purchase_tax_account_id = request.form.get('purchase_tax_account_id')
    
    if not name:
        flash('Tax name is required.', 'error')
        return redirect(url_for('settings.index'))
    
    tax = Tax(
        name=name,
        rate=float(rate),
        is_active=True,
        sales_tax_account_id=int(sales_tax_account_id) if sales_tax_account_id else None,
        purchase_tax_account_id=int(purchase_tax_account_id) if purchase_tax_account_id else None
    )
    db.session.add(tax)
    db.session.commit()
    flash(f'Tax rate "{name}" created.', 'success')
    return redirect(url_for('settings.index'))

@settings_bp.route('/taxes/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_tax(id):
    tax = Tax.query.get_or_404(id)
    tax.is_active = False
    db.session.commit()
    flash(f'Tax rate "{tax.name}" deactivated.', 'success')
    return redirect(url_for('settings.index'))

# === FISCAL YEAR CLOSE ===

@settings_bp.route('/close-year', methods=['POST'])
@login_required
@admin_required
def close_fiscal_year():
    year_end_str = request.form.get('year_end_date')
    if not year_end_str:
        flash('Please select a fiscal year end date.', 'error')
        return redirect(url_for('settings.index'))
    
    try:
        year_end_date = datetime.strptime(year_end_str, '%Y-%m-%d')
        entry = AccountingService.close_fiscal_year(year_end_date)
        flash(f'Fiscal year closed successfully. Closing entry #{entry.id} created.', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        flash(f'Error closing fiscal year: {e}', 'error')
    
    return redirect(url_for('settings.index'))
