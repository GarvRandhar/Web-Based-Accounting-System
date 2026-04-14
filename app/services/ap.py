from app.models import db, Vendor, Bill, BillItem, Account, Tax, CompanySettings
from app.services.accounting import AccountingService
from app.services.currency import CurrencyService
from app.services.audit import AuditService
from datetime import datetime, timezone, date as date_type
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError


def _now():
    return datetime.now(timezone.utc)


def _generate_bill_number():
    """Returns a formatted bill number like BILL-2026-00001."""
    year = _now().year
    prefix = f"BILL-{year}-"
    like_pattern = f"{prefix}%"
    last = (
        db.session.query(func.max(Bill.bill_number))
        .filter(Bill.bill_number.like(like_pattern))
        .scalar()
    )
    if last:
        try:
            seq = int(last.split('-')[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:05d}"


_MONEY_PLACES = Decimal('0.01')


def _to_decimal(value, field_name):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid numeric value for {field_name}: {value}") from exc


def _money(value):
    return value.quantize(_MONEY_PLACES, rounding=ROUND_HALF_UP)


class AccountsPayableService:

    @staticmethod
    def refresh_overdue_statuses():
        """
        Updates Bill status from 'Posted' → 'Overdue' when due_date has passed.
        Called at the start of list/view routes so statuses are always current.
        """
        today = date_type.today()
        updated_count = (
            db.session.query(Bill)
            .filter(Bill.status.in_(['Posted']))
            .filter(Bill.due_date < today)
            .update({Bill.status: 'Overdue'}, synchronize_session=False)
        )
        if updated_count:
            db.session.commit()
        return updated_count

    @staticmethod
    def create_vendor(name, email=None, phone=None, address=None, currency='USD'):
        vendor = Vendor(name=name, email=email, phone=phone, address=address, currency=currency)
        db.session.add(vendor)
        db.session.commit()
        AuditService.log(action='CREATE', model='Vendor', model_id=vendor.id,
                         details=f"Created vendor: {name}")
        return vendor

    @staticmethod
    def create_bill(vendor_id, due_date, items):
        """
        Creates a new bill with optional tax per item.
        items: list of dicts {'description', 'quantity', 'unit_price', 'account_id', 'tax_id'}
        """
        if not items:
            raise ValueError("Bill must contain at least one line item.")

        if isinstance(due_date, str):
            due_date = datetime.strptime(due_date, '%Y-%m-%d').date()

        vendor = db.session.get(Vendor, vendor_id)
        if not vendor:
            raise ValueError("Vendor not found.")

        tax_ids = {item.get('tax_id') for item in items if item.get('tax_id')}
        taxes = Tax.query.filter(Tax.id.in_(tax_ids)).all() if tax_ids else []
        tax_by_id = {tax.id: tax for tax in taxes}

        bill = None
        max_attempts = 3
        for _ in range(max_attempts):
            try:
                bill = Bill(
                    bill_number=_generate_bill_number(),
                    vendor_id=vendor_id,
                    due_date=due_date,
                    date=_now().date(),
                    status='Open',
                    currency=vendor.currency,
                    amount_paid=Decimal('0.00'),
                )
                db.session.add(bill)
                db.session.flush()

                subtotal = Decimal('0.00')
                total_tax = Decimal('0.00')
                for idx, item in enumerate(items, start=1):
                    qty = _to_decimal(item['quantity'], f"quantity line {idx}")
                    price = _to_decimal(item['unit_price'], f"unit_price line {idx}")

                    if qty <= 0:
                        raise ValueError(f"Quantity on line {idx} must be greater than zero (got {qty}).")
                    if price < 0:
                        raise ValueError(f"Unit price on line {idx} cannot be negative (got {price}).")
                    if not item.get('account_id'):
                        raise ValueError(f"Expense account is required on line {idx}.")

                    amount = _money(qty * price)
                    tax_amount = Decimal('0.00')
                    tax_id = item.get('tax_id')
                    if tax_id:
                        tax = tax_by_id.get(tax_id)
                        if tax:
                            tax_amount = _money(amount * _to_decimal(tax.rate, f"tax rate line {idx}") / Decimal('100'))

                    bill_item = BillItem(
                        bill_id=bill.id,
                        description=item['description'],
                        quantity=qty,
                        unit_price=price,
                        amount=amount,
                        account_id=item['account_id'],
                        tax_id=tax_id,
                        tax_amount=tax_amount,
                    )
                    db.session.add(bill_item)
                    subtotal += amount
                    total_tax += tax_amount

                if subtotal <= 0:
                    raise ValueError("Bill total must be greater than zero.")

                bill.total_amount = _money(subtotal + total_tax)
                bill.tax_amount = _money(total_tax)
                db.session.commit()
                break
            except IntegrityError:
                db.session.rollback()
        else:
            raise ValueError("Unable to generate a unique bill number. Please retry.")

        AuditService.log(action='CREATE', model='Bill', model_id=bill.id,
                         details=f"Bill {bill.bill_number} created for {vendor.name}, total: {bill.total_amount}")
        return bill

    @staticmethod
    def post_bill(bill_id):
        """
        Posts a bill to the General Ledger.
        Journal Entry:
          Debit:  Expense Account(s)     (subtotal per account)
          Debit:  Tax Receivable         (input tax, if any)
          Credit: Accounts Payable       (total incl tax)
        """
        bill = Bill.query.get_or_404(bill_id)
        if bill.journal_entry_id:
            raise ValueError("Bill is already posted to the GL.")

        ap_account = Account.query.filter_by(code='2010').first()
        if not ap_account:
            raise ValueError("Accounts Payable account (Code 2010) not found.")

        verified_total = _money(sum(
            _to_decimal(i.amount or 0, "bill item amount") + _to_decimal(i.tax_amount or 0, "bill item tax")
            for i in bill.items
        ))
        bill_total = _money(_to_decimal(bill.total_amount or 0, "bill total"))
        if abs(verified_total - bill_total) > Decimal('0.01'):
            raise ValueError(
                f"Bill total mismatch: stored {bill.total_amount} vs calculated {verified_total}. "
                "Please recreate the bill."
            )

        settings = CompanySettings.query.first()
        base_currency = settings.base_currency if settings else 'USD'
        rate = _to_decimal(CurrencyService.get_rate(bill.currency, base_currency, bill.date) or 1.0, "fx rate")

        je_items = [
            {'account_id': ap_account.id, 'debit': 0, 'credit': float(_money(verified_total * rate))}
        ]

        expense_map: dict[int, Decimal] = {}
        for item in bill.items:
            expense_map[item.account_id] = expense_map.get(item.account_id, Decimal('0.00')) + _to_decimal(item.amount or 0, "expense amount")
        for acc_id, amount in expense_map.items():
            je_items.append({'account_id': acc_id, 'debit': float(_money(amount * rate)), 'credit': 0})

        if bill.tax_amount and _to_decimal(bill.tax_amount, "bill tax amount") > 0:
            gst = Account.query.filter_by(code='2200').first()
            bill_tax_ids = {i.tax_id for i in bill.items if i.tax_id and i.tax_amount}
            taxes = Tax.query.filter(Tax.id.in_(bill_tax_ids)).all() if bill_tax_ids else []
            tax_by_id = {tax.id: tax for tax in taxes}
            tax_map: dict[int, Decimal] = {}
            for item in bill.items:
                if item.tax_id and item.tax_amount:
                    tax = tax_by_id.get(item.tax_id)
                    if tax and tax.purchase_tax_account_id:
                        acc_id = tax.purchase_tax_account_id
                    else:
                        acc_id = gst.id if gst else None
                    if acc_id:
                        tax_map[acc_id] = tax_map.get(acc_id, Decimal('0.00')) + _to_decimal(item.tax_amount, "item tax")
            for acc_id, amount in tax_map.items():
                je_items.append({'account_id': acc_id, 'debit': float(_money(amount * rate)), 'credit': 0})

        desc = f"Bill {bill.bill_number} — {bill.vendor.name}"
        if rate != Decimal('1'):
            desc += f" [FX Rate: {rate}]"

        entry = AccountingService.create_journal_entry(
            date=bill.date,
            description=desc,
            items=je_items,
            reference=f"BILL-{bill.id}",
        )

        bill.status = 'Posted'
        bill.journal_entry_id = entry.id
        db.session.commit()

        AuditService.log(
            action='POST',
            model='Bill',
            model_id=bill.id,
            details=f"Bill {bill.bill_number} posted to GL (JE #{entry.id}), total: {verified_total}",
        )
        return bill

    @staticmethod
    def record_payment(bill_id, amount, payment_date, bank_account_id, notes=''):
        """
        Records a cash disbursement against a posted bill.
        Tracks partial payments via amount_paid. Prevents overpayment.
        Journal Entry:
          Debit:  Accounts Payable   (reduces AP balance)
          Credit: Bank / Cash        (payment made)
        Marks bill as 'Paid' only when fully settled.
        """
        bill = Bill.query.get_or_404(bill_id)

        if bill.status not in ('Posted', 'Overdue'):
            raise ValueError(
                f"Cannot record payment: bill status is '{bill.status}'. "
                "Only posted bills can be paid."
            )

        amount = _money(_to_decimal(amount, "payment amount"))
        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero.")

        # Overpayment guard
        balance = bill.balance_due
        if amount > _to_decimal(balance, "bill balance") + Decimal('0.005'):
            raise ValueError(
                f"Payment of {amount} exceeds the outstanding balance of {balance:.2f}. "
                "Use a debit note for overpayments."
            )

        ap_account = Account.query.filter_by(code='2010').first()
        if not ap_account:
            raise ValueError("Accounts Payable account (Code 2010) not found.")

        bank_account = db.session.get(Account, bank_account_id)
        if not bank_account:
            raise ValueError("Bank/Cash account not found.")

        if isinstance(payment_date, str):
            payment_date = datetime.strptime(payment_date, '%Y-%m-%d').date()

        entry = AccountingService.create_journal_entry(
            date=payment_date,
            description=f"Payment made — Bill {bill.bill_number} ({bill.vendor.name})",
            items=[
                {'account_id': ap_account.id,   'debit': amount, 'credit': 0},
                {'account_id': bank_account.id, 'debit': 0,      'credit': amount},
            ],
            reference=f"PMT-BILL-{bill.id}",
        )

        # Update running total and mark paid if fully settled
        bill.amount_paid = _money(_to_decimal(bill.amount_paid or 0, "amount_paid") + amount)
        if bill.balance_due <= 0.005:
            bill.status = 'Paid'

        db.session.commit()

        AuditService.log(
            action='PAYMENT',
            model='Bill',
            model_id=bill.id,
            details=f"Payment of {amount} recorded for Bill {bill.bill_number} via JE #{entry.id}. "
                    f"Balance remaining: {bill.balance_due:.2f}. Notes: {notes}",
        )
        return entry

    @staticmethod
    def cancel_bill(bill_id):
        """Cancels a bill. If posted, creates a reversing JE."""
        bill = db.session.get(Bill, bill_id)
        if not bill:
            raise ValueError("Bill not found.")
        if bill.status == 'Cancelled':
            raise ValueError("Bill is already cancelled.")
        if bill.status == 'Paid':
            raise ValueError("Cannot cancel a paid bill. Please issue a debit note.")

        if bill.journal_entry_id:
            AccountingService.void_journal_entry(bill.journal_entry_id)

        bill.status = 'Cancelled'
        db.session.commit()

        AuditService.log(
            action='CANCEL',
            model='Bill',
            model_id=bill.id,
            details=f"Cancelled bill {bill.bill_number or bill.id}",
        )
        return bill

    @staticmethod
    def get_ap_aging(as_of_date=None):
        """
        Generates AP Aging Report grouped by vendor.
        Buckets: Current, 1-30, 31-60, 61-90, 90+ days overdue.
        Only includes Posted/Overdue bills (unpaid/partial).
        """
        if as_of_date is None:
            as_of_date = date_type.today()

        bills = Bill.query.filter(
            Bill.status.in_(['Posted', 'Overdue'])
        ).order_by(Bill.vendor_id, Bill.due_date).all()

        vendors: dict[int, dict] = {}
        totals = {'current': 0.0, 'days_1_30': 0.0, 'days_31_60': 0.0,
                  'days_61_90': 0.0, 'days_91_plus': 0.0, 'total': 0.0}

        for bill in bills:
            balance = bill.balance_due
            if balance <= 0.005:
                continue

            days_overdue = (as_of_date - bill.due_date).days

            if bill.vendor_id not in vendors:
                vendors[bill.vendor_id] = {
                    'vendor': bill.vendor,
                    'current': 0.0,
                    'days_1_30': 0.0,
                    'days_31_60': 0.0,
                    'days_61_90': 0.0,
                    'days_91_plus': 0.0,
                    'total': 0.0,
                    'bills': [],
                }

            bucket = _aging_bucket(days_overdue)
            vendors[bill.vendor_id][bucket] += balance
            vendors[bill.vendor_id]['total'] += balance
            totals[bucket] += balance
            totals['total'] += balance

            vendors[bill.vendor_id]['bills'].append({
                'bill_number': bill.bill_number or f"#{bill.id}",
                'due_date': bill.due_date,
                'balance': balance,
                'days_overdue': max(0, days_overdue),
                'bucket': bucket,
            })

        return {
            'rows': list(vendors.values()),
            'totals': totals,
            'as_of_date': as_of_date,
        }


def _aging_bucket(days_overdue: int) -> str:
    if days_overdue <= 0:
        return 'current'
    elif days_overdue <= 30:
        return 'days_1_30'
    elif days_overdue <= 60:
        return 'days_31_60'
    elif days_overdue <= 90:
        return 'days_61_90'
    else:
        return 'days_91_plus'
