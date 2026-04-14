from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.models import FixedAsset, DepreciationSchedule, Account, db
from app.services.assets import AssetService

assets_bp = Blueprint('assets', __name__, url_prefix='/assets')


@assets_bp.route('/')
@login_required
def index():
    status = request.args.get('status', 'Active')
    assets = FixedAsset.query.filter_by(status=status).order_by(FixedAsset.asset_code).all()
    return render_template('assets/index.html', assets=assets, current_status=status)


@assets_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_asset():
    if request.method == 'POST':
        try:
            AssetService.create_asset(
                asset_code=request.form['asset_code'],
                name=request.form['name'],
                purchase_date=request.form['purchase_date'],
                purchase_price=float(request.form['purchase_price']),
                useful_life_years=int(request.form['useful_life_years']),
                depreciation_method=request.form.get('depreciation_method', 'SLM'),
                salvage_value=float(request.form.get('salvage_value', 0)),
                description=request.form.get('description'),
                asset_account_id=request.form.get('asset_account_id') or None,
                depreciation_account_id=request.form.get('depreciation_account_id') or None,
                accumulated_dep_account_id=request.form.get('accumulated_dep_account_id') or None
            )
            flash('Fixed asset created and depreciation schedule generated.', 'success')
            return redirect(url_for('assets.index'))
        except Exception as e:
            flash(f'Error: {e}', 'error')

    asset_accounts = Account.query.filter_by(type='Asset').order_by(Account.code).all()
    expense_accounts = Account.query.filter_by(type='Expense').order_by(Account.code).all()
    liability_accounts = Account.query.filter(Account.type.in_(['Liability', 'Asset'])).order_by(Account.code).all()
    return render_template('assets/new.html',
                           asset_accounts=asset_accounts,
                           expense_accounts=expense_accounts,
                           liability_accounts=liability_accounts)


@assets_bp.route('/<int:id>')
@login_required
def detail(id):
    asset = FixedAsset.query.get_or_404(id)
    return render_template('assets/detail.html', asset=asset)


@assets_bp.route('/<int:id>/depreciate', methods=['POST'])
@login_required
def post_depreciation(id):
    schedule_id = request.form.get('schedule_id')
    try:
        AssetService.post_depreciation(int(schedule_id))
        flash('Depreciation posted to GL.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('assets.detail', id=id))


@assets_bp.route('/<int:id>/depreciate-all', methods=['POST'])
@login_required
def post_all_depreciation(id):
    """Post all un-posted depreciation schedules up to today."""
    from datetime import datetime, timezone
    asset = FixedAsset.query.get_or_404(id)
    today = datetime.now(timezone.utc).date()
    count = 0
    for schedule in asset.schedules:
        if not schedule.journal_entry_id and schedule.schedule_date <= today:
            try:
                AssetService.post_depreciation(schedule.id)
                count += 1
            except Exception:
                break
    flash(f'{count} depreciation entries posted.', 'success')
    return redirect(url_for('assets.detail', id=id))


@assets_bp.route('/<int:id>/dispose', methods=['POST'])
@login_required
def dispose(id):
    try:
        AssetService.dispose_asset(
            id,
            disposed_date=request.form.get('disposed_date'),
            disposed_amount=float(request.form.get('disposed_amount', 0))
        )
        flash('Asset disposed successfully.', 'success')
    except Exception as e:
        flash(f'Error: {e}', 'error')
    return redirect(url_for('assets.detail', id=id))
