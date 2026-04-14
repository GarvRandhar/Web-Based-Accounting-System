from app.models import db, Customer, Invoice, InvoiceItem, Account, Tax, CompanySettings
from app.services.accounting import AccountingService
from app.services.currency import CurrencyService
from app.services.audit import AuditService
from datetime import datetime, timezone, date as date_type
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError


def _now():
    return datetime.now(timezone.utc)


def _generate_invoice_number():
    """Returns a formatted invoice number like INV-2026-00001."""
    year = _now().year
    prefix = f"INV-{year}-"
    # Find highest sequence number for this year
    like_pattern = f"{prefix}%"
    last = (
        db.session.query(func.max(Invoice.invoice_number))
        .filter(Invoice.invoice_number.like(like_pattern))
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


class AccountsReceivableService:

    @staticmethod
    def refresh_overdue_statuses():
        """
        Updates Invoice status from 'Sent' → 'Overdue' when due_date has passed.
        Called at the start of list/view routes so statuses are always current.
        """
        today = date_type.today()
        updated_count = (
            db.session.query(Invoice)
            .filter(Invoice.status.in_(['Sent']))
            .filter(Invoice.due_date < today)
            .update({Invoice.status: 'Overdue'}, synchronize_session=False)
        )
        if updated_count:
            db.session.commit()
        return updated_count

    @staticmethod
    def create_customer(name, email=None, phone=None, address=None, currency='USD'):
        customer = Customer(name=name, email=email, phone=phone, address=address, currency=currency)
        db.session.add(customer)
        db.session.commit()
        AuditService.log(action='CREATE', model='Customer', model_id=customer.id,
                         details=f"Created customer: {name}")
        return customer

    @staticmethod
    def create_invoice(customer_id, due_date, items):
        """
        Creates a draft invoice with optional tax per item.
        items: list of dicts {'description', 'quantity', 'unit_price', 'account_id', 'tax_id'}
        """
        if not items:
            raise ValueError("Invoice must contain at least one line item.")

        if isinstance(due_date, str):
            due_date = datetime.strptime(due_date, '%Y-%m-%d').date()

        customer = db.session.get(Customer, customer_id)
        if not customer:
            raise ValueError("Customer not found.")

        tax_ids = {item.get('tax_id') for item in items if item.get('tax_id')}
        taxes = Tax.query.filter(Tax.id.in_(tax_ids)).all() if tax_ids else []
        tax_by_id = {tax.id: tax for tax in taxes}

        invoice = None
        max_attempts = 3
        for _ in range(max_attempts):
            try:
                invoice = Invoice(
                    invoice_number=_generate_invoice_number(),
                    customer_id=customer_id,
                    due_date=due_date,
                    date=_now().date(),
                    status='Draft',
                    currency=customer.currency,
                    amount_paid=Decimal('0.00'),
                )
                db.session.add(invoice)
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
                        raise ValueError(f"Revenue account is required on line {idx}.")

                    amount = _money(qty * price)
                    tax_amount = Decimal('0.00')
                    tax_id = item.get('tax_id')
                    if tax_id:
                        tax = tax_by_id.get(tax_id)
                        if tax:
                            tax_amount = _money(amount * _to_decimal(tax.rate, f"tax rate line {idx}") / Decimal('100'))

                    inv_item = InvoiceItem(
                        invoice_id=invoice.id,
                        description=item['description'],
                        quantity=qty,
                        unit_price=price,
                        amount=amount,
                        account_id=item['account_id'],
                        tax_id=tax_id,
                        tax_amount=tax_amount,
                    )
                    db.session.add(inv_item)
                    subtotal += amount
                    total_tax += tax_amount

                if subtotal <= 0:
                    raise ValueError("Invoice total must be greater than zero.")

                invoice.total_amount = _money(subtotal + total_tax)
                invoice.tax_amount = _money(total_tax)
                db.session.commit()
                break
            except IntegrityError:
                db.session.rollback()
        else:
            raise ValueError("Unable to generate a unique invoice number. Please retry.")

        AuditService.log(action='CREATE', model='Invoice', model_id=invoice.id,
                         details=f"Draft invoice {invoice.invoice_number} created for {customer.name}, total: {invoice.total_amount}")
        return invoice

    @staticmethod
    def post_invoice(invoice_id):
        """
        Posts an invoice to the General Ledger.
        Journal Entry:
          Debit:  Accounts Receivable (total incl tax)
          Credit: Revenue Account(s)  (subtotal per account)
          Credit: Tax Payable          (tax amount, if any)
        """
        invoice = Invoice.query.get_or_404(invoice_id)
        if invoice.status != 'Draft':
            raise ValueError("Invoice is already posted or cancelled.")

        ar_account = Account.query.filter_by(code='1200').first()
        if not ar_account:
            raise ValueError("Accounts Receivable account (Code 1200) not found.")

        verified_total = _money(sum(
            _to_decimal(i.amount or 0, "invoice item amount") + _to_decimal(i.tax_amount or 0, "invoice item tax")
            for i in invoice.items
        ))
        invoice_total = _money(_to_decimal(invoice.total_amount or 0, "invoice total"))
        if abs(verified_total - invoice_total) > Decimal('0.01'):
            raise ValueError(
                f"Invoice total mismatch: stored {invoice.total_amount} vs calculated {verified_total}. "
                "Please recreate the invoice."
            )

        settings = CompanySettings.query.first()
        base_currency = settings.base_currency if settings else 'USD'
        rate = _to_decimal(CurrencyService.get_rate(invoice.currency, base_currency, invoice.date) or 1.0, "fx rate")

        je_items = [
            {'account_id': ar_account.id, 'debit': float(_money(verified_total * rate)), 'credit': 0}
        ]

        revenue_map: dict[int, Decimal] = {}
        for item in invoice.items:
            revenue_map[item.account_id] = revenue_map.get(item.account_id, Decimal('0.00')) + _to_decimal(item.amount or 0, "revenue amount")
        for acc_id, amount in revenue_map.items():
            je_items.append({'account_id': acc_id, 'debit': 0, 'credit': float(_money(amount * rate))})

        if invoice.tax_amount and _to_decimal(invoice.tax_amount, "invoice tax amount") > 0:
            gst = Account.query.filter_by(code='2200').first()
            invoice_tax_ids = {i.tax_id for i in invoice.items if i.tax_id and i.tax_amount}
            taxes = Tax.query.filter(Tax.id.in_(invoice_tax_ids)).all() if invoice_tax_ids else []
            tax_by_id = {tax.id: tax for tax in taxes}
            tax_map: dict[int, Decimal] = {}
            for item in invoice.items:
                if item.tax_id and item.tax_amount:
                    tax = tax_by_id.get(item.tax_id)
                    if tax and tax.sales_tax_account_id:
                        acc_id = tax.sales_tax_account_id
                    else:
                        acc_id = gst.id if gst else None
                    if acc_id:
                        tax_map[acc_id] = tax_map.get(acc_id, Decimal('0.00')) + _to_decimal(item.tax_amount, "item tax")
            for acc_id, amount in tax_map.items():
                je_items.append({'account_id': acc_id, 'debit': 0, 'credit': float(_money(amount * rate))})

        desc = f"Invoice {invoice.invoice_number} — {invoice.customer.name}"
        if rate != Decimal('1'):
            desc += f" [FX Rate: {rate}]"

        entry = AccountingService.create_journal_entry(
            date=invoice.date,
            description=desc,
            items=je_items,
            reference=f"INV-{invoice.id}",
        )

        invoice.status = 'Sent'
        invoice.journal_entry_id = entry.id
        db.session.commit()

        AuditService.log(
            action='POST',
            model='Invoice',
            model_id=invoice.id,
            details=f"Invoice {invoice.invoice_number} posted to GL (JE #{entry.id}), total: {verified_total}",
        )
        return invoice

    @staticmethod
    def record_payment(invoice_id, amount, payment_date, bank_account_id, notes=''):
        """
        Records a cash receipt against a posted invoice.
        Tracks partial payments via amount_paid. Prevents overpayment.
        Journal Entry:
          Debit:  Bank / Cash           (payment received)
          Credit: Accounts Receivable   (reduces AR balance)
        Marks invoice as 'Paid' only when fully settled.
        """
        invoice = Invoice.query.get_or_404(invoice_id)

        if invoice.status not in ('Sent', 'Overdue'):
            raise ValueError(
                f"Cannot record payment: invoice status is '{invoice.status}'. "
                "Only posted (Sent/Overdue) invoices can be paid."
            )

        amount = _money(_to_decimal(amount, "payment amount"))
        if amount <= 0:
            raise ValueError("Payment amount must be greater than zero.")

        # Overpayment guard
        balance = invoice.balance_due
        if amount > _to_decimal(balance, "invoice balance") + Decimal('0.005'):
            raise ValueError(
                f"Payment of {amount} exceeds the outstanding balance of {balance:.2f}. "
                "Use a credit note for overpayments."
            )

        ar_account = Account.query.filter_by(code='1200').first()
        if not ar_account:
            raise ValueError("Accounts Receivable account (Code 1200) not found.")

        bank_account = db.session.get(Account, bank_account_id)
        if not bank_account:
            raise ValueError("Bank/Cash account not found.")

        if isinstance(payment_date, str):
            payment_date = datetime.strptime(payment_date, '%Y-%m-%d').date()

        entry = AccountingService.create_journal_entry(
            date=payment_date,
            description=f"Payment received — Invoice {invoice.invoice_number} ({invoice.customer.name})",
            items=[
                {'account_id': bank_account.id, 'debit': amount, 'credit': 0},
                {'account_id': ar_account.id,   'debit': 0,      'credit': amount},
            ],
            reference=f"PMT-INV-{invoice.id}",
        )

        # Update running total and mark paid if fully settled
        invoice.amount_paid = _money(_to_decimal(invoice.amount_paid or 0, "amount_paid") + amount)
        if invoice.balance_due <= 0.005:
            invoice.status = 'Paid'

        db.session.commit()

        AuditService.log(
            action='PAYMENT',
            model='Invoice',
            model_id=invoice.id,
            details=f"Payment of {amount} recorded for Invoice {invoice.invoice_number} via JE #{entry.id}. "
                    f"Balance remaining: {invoice.balance_due:.2f}. Notes: {notes}",
        )
        return entry

    @staticmethod
    def cancel_invoice(invoice_id):
        """Cancels an invoice. If posted, creates a reversing JE."""
        invoice = db.session.get(Invoice, invoice_id)
        if not invoice:
            raise ValueError("Invoice not found.")
        if invoice.status == 'Cancelled':
            raise ValueError("Invoice is already cancelled.")
        if invoice.status == 'Paid':
            raise ValueError("Cannot cancel a paid invoice. Please issue a credit note.")

        if invoice.journal_entry_id:
            AccountingService.void_journal_entry(invoice.journal_entry_id)

        invoice.status = 'Cancelled'
        db.session.commit()

        AuditService.log(
            action='CANCEL',
            model='Invoice',
            model_id=invoice.id,
            details=f"Cancelled invoice {invoice.invoice_number or invoice.id}",
        )
        return invoice

    @staticmethod
    def get_ar_aging(as_of_date=None):
        """
        Generates AR Aging Report grouped by customer.
        Buckets: Current, 1-30, 31-60, 61-90, 90+ days overdue.
        Only includes Sent/Overdue invoices (unpaid/partial).
        """
        if as_of_date is None:
            as_of_date = date_type.today()

        invoices = Invoice.query.filter(
            Invoice.status.in_(['Sent', 'Overdue'])
        ).order_by(Invoice.customer_id, Invoice.due_date).all()

        # Group by customer
        customers: dict[int, dict] = {}
        totals = {'current': 0.0, 'days_1_30': 0.0, 'days_31_60': 0.0,
                  'days_61_90': 0.0, 'days_91_plus': 0.0, 'total': 0.0}

        for inv in invoices:
            balance = inv.balance_due
            if balance <= 0.005:
                continue  # fully paid

            days_overdue = (as_of_date - inv.due_date).days

            if inv.customer_id not in customers:
                customer_row = {
                    'customer': inv.customer,
                    'current': 0.0,
                    'days_1_30': 0.0,
                    'days_31_60': 0.0,
                    'days_61_90': 0.0,
                    'days_91_plus': 0.0,
                    'total': 0.0,
                    'invoices': [],
                }
                customers[inv.customer_id] = customer_row

            bucket = _aging_bucket(days_overdue)
            customers[inv.customer_id][bucket] += balance
            customers[inv.customer_id]['total'] += balance
            totals[bucket] += balance
            totals['total'] += balance

            customers[inv.customer_id]['invoices'].append({
                'invoice_number': inv.invoice_number or f"#{inv.id}",
                'due_date': inv.due_date,
                'balance': balance,
                'days_overdue': max(0, days_overdue),
                'bucket': bucket,
            })

        return {
            'rows': list(customers.values()),
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
