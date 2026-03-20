from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.models import CostCenter, db
from app.services.cost_centers import CostCenterService
from datetime import datetime

cost_centers_bp = Blueprint('cost_centers', __name__, url_prefix='/cost-centers')


@cost_centers_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        try:
            CostCenterService.create_cost_center(
                code=request.form['code'],
                name=request.form['name'],
                description=request.form.get('description'),
                parent_id=int(request.form['parent_id']) if request.form.get('parent_id') else None
            )
            flash('Cost center created successfully.', 'success')
        except Exception as e:
            flash(f'Error: {e}', 'error')
        return redirect(url_for('cost_centers.index'))

    centers = CostCenter.query.order_by(CostCenter.code).all()
    return render_template('cost_centers/index.html', centers=centers)


@cost_centers_bp.route('/<int:id>/edit', methods=['POST'])
@login_required
def edit(id):
    try:
        CostCenterService.update_cost_center(
            id,
            name=request.form.get('name'),
            description=request.form.get('description'),
            is_active='is_active' in request.form
        )
        flash('Cost center updated.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('cost_centers.index'))


@cost_centers_bp.route('/<int:id>/deactivate', methods=['POST'])
@login_required
def deactivate(id):
    CostCenterService.deactivate_cost_center(id)
    flash('Cost center deactivated.', 'success')
    return redirect(url_for('cost_centers.index'))


@cost_centers_bp.route('/report')
@login_required
def report():
    cc_id = request.args.get('cost_center_id', type=int)
    start = request.args.get('start_date')
    end = request.args.get('end_date')

    start_date = datetime.strptime(start, '%Y-%m-%d') if start else None
    end_date = datetime.strptime(end, '%Y-%m-%d') if end else None

    data = None
    if cc_id:
        data = CostCenterService.get_pl_by_cost_center(cc_id, start_date, end_date)

    centers = CostCenter.query.filter_by(is_active=True).order_by(CostCenter.code).all()
    selected_center = CostCenter.query.get(cc_id) if cc_id else None
    return render_template('cost_centers/report.html', data=data, centers=centers,
                           selected_center=selected_center,
                           start_date=start or '', end_date=end or '')
