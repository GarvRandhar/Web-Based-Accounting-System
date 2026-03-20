from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.models import Currency, ExchangeRate, db
from app.services.currency import CurrencyService

currency_bp = Blueprint('currency', __name__, url_prefix='/currencies')


@currency_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'add_currency':
                CurrencyService.create_currency(
                    code=request.form['code'],
                    name=request.form['name'],
                    symbol=request.form.get('symbol', '')
                )
                flash('Currency added successfully.', 'success')
            elif action == 'add_rate':
                CurrencyService.add_exchange_rate(
                    from_currency=request.form['from_currency'],
                    to_currency=request.form['to_currency'],
                    rate=float(request.form['rate']),
                    effective_date=request.form.get('effective_date')
                )
                flash('Exchange rate added successfully.', 'success')
        except Exception as e:
            flash(f'Error: {e}', 'error')
        return redirect(url_for('currency.index'))

    currencies = Currency.query.filter_by(is_active=True).order_by(Currency.code).all()
    rates = ExchangeRate.query.order_by(ExchangeRate.effective_date.desc()).limit(50).all()
    return render_template('currency/index.html', currencies=currencies, rates=rates)


@currency_bp.route('/seed', methods=['POST'])
@login_required
def seed():
    CurrencyService.seed_default_currencies()
    flash('Default currencies seeded.', 'success')
    return redirect(url_for('currency.index'))
