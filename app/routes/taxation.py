from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.models import Tax, TaxGroup, db
from app.services.taxation import TaxationService

taxation_bp = Blueprint('taxation', __name__, url_prefix='/taxation')


@taxation_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        try:
            name = request.form['name']
            description = request.form.get('description', '')
            tax_ids = request.form.getlist('tax_ids[]')
            if not tax_ids:
                flash('Please select at least one tax component.', 'error')
                return redirect(url_for('taxation.index'))

            TaxationService.create_tax_group(name, tax_ids, description)
            flash(f'Tax group "{name}" created successfully.', 'success')
        except Exception as e:
            flash(f'Error: {e}', 'error')
        return redirect(url_for('taxation.index'))

    tax_groups = TaxGroup.query.filter_by(is_active=True).order_by(TaxGroup.name).all()
    taxes = Tax.query.filter_by(is_active=True).order_by(Tax.name).all()
    return render_template('taxation/index.html', tax_groups=tax_groups, taxes=taxes)


@taxation_bp.route('/<int:id>/delete', methods=['POST'])
@login_required
def delete_group(id):
    TaxationService.delete_tax_group(id)
    flash('Tax group deactivated.', 'success')
    return redirect(url_for('taxation.index'))
