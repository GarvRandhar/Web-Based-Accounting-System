from app.extensions import db
from app.models import Currency, ExchangeRate, CompanySettings
from app.services.audit import AuditService
from datetime import datetime


class CurrencyService:
    @staticmethod
    def create_currency(code, name, symbol=''):
        currency = Currency(code=code.upper(), name=name, symbol=symbol)
        db.session.add(currency)
        db.session.commit()
        return currency

    @staticmethod
    def add_exchange_rate(from_currency, to_currency, rate, effective_date=None):
        if effective_date and isinstance(effective_date, str):
            effective_date = datetime.strptime(effective_date, '%Y-%m-%d').date()
        er = ExchangeRate(
            from_currency=from_currency.upper(),
            to_currency=to_currency.upper(),
            rate=rate,
            effective_date=effective_date or datetime.utcnow().date()
        )
        db.session.add(er)
        db.session.commit()
        AuditService.log(action='CREATE', model='ExchangeRate', model_id=er.id,
                         details=f"Rate: 1 {from_currency} = {rate} {to_currency}")
        return er

    @staticmethod
    def get_rate(from_currency, to_currency, as_of_date=None):
        """
        Returns the most recent exchange rate for the given pair on or before as_of_date.
        """
        if from_currency == to_currency:
            return 1.0

        as_of = as_of_date or datetime.utcnow().date()
        rate = ExchangeRate.query.filter_by(
            from_currency=from_currency.upper(),
            to_currency=to_currency.upper()
        ).filter(
            ExchangeRate.effective_date <= as_of
        ).order_by(
            ExchangeRate.effective_date.desc()
        ).first()

        if rate:
            return float(rate.rate)

        # Try reverse pair
        reverse = ExchangeRate.query.filter_by(
            from_currency=to_currency.upper(),
            to_currency=from_currency.upper()
        ).filter(
            ExchangeRate.effective_date <= as_of
        ).order_by(
            ExchangeRate.effective_date.desc()
        ).first()

        if reverse and float(reverse.rate) != 0:
            return round(1 / float(reverse.rate), 8)

        return None

    @staticmethod
    def convert(amount, from_currency, to_currency, as_of_date=None):
        """Converts an amount from one currency to another."""
        rate = CurrencyService.get_rate(from_currency, to_currency, as_of_date)
        if rate is None:
            raise ValueError(f"No exchange rate found for {from_currency} → {to_currency}")
        return round(float(amount) * rate, 2)

    @staticmethod
    def calculate_forex_gain_loss(original_amount, original_currency,
                                  payment_amount, payment_currency,
                                  original_date, payment_date):
        """
        Calculates unrealised/realised forex gain or loss.
        Returns positive for gain, negative for loss.
        """
        settings = CompanySettings.query.first()
        base = settings.base_currency if settings else 'USD'

        original_in_base = CurrencyService.convert(
            original_amount, original_currency, base, original_date)
        payment_in_base = CurrencyService.convert(
            payment_amount, payment_currency, base, payment_date)

        return round(payment_in_base - original_in_base, 2)

    @staticmethod
    def seed_default_currencies():
        """Seed common world currencies if none exist."""
        if Currency.query.first():
            return

        defaults = [
            ('USD', 'US Dollar', '$'),
            ('EUR', 'Euro', '€'),
            ('GBP', 'British Pound', '£'),
            ('INR', 'Indian Rupee', '₹'),
            ('JPY', 'Japanese Yen', '¥'),
            ('AUD', 'Australian Dollar', 'A$'),
            ('CAD', 'Canadian Dollar', 'C$'),
        ]
        for code, name, symbol in defaults:
            db.session.add(Currency(code=code, name=name, symbol=symbol))
        db.session.commit()
