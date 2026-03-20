from app.models import db, Customer, Invoice, InvoiceItem, Account, Tax
from app.services.accounting import AccountingService
from app.services.audit import AuditService
from datetime import datetime

class AccountsReceivableService:
    @staticmethod
    def create_customer(name, email=None, phone=None, address=None, currency='USD'):
        customer = Customer(name=name, email=email, phone=phone, address=address, currency=currency)
        db.session.add(customer)
        db.session.commit()
        return customer

    @staticmethod
    def create_invoice(customer_id, due_date, items):
        """
        Creates a draft invoice with optional tax per item.
        items: list of dicts {'description': str, 'quantity': float, 'unit_price': float, 'account_id': int, 'tax_id': int|None}
        """
        if isinstance(due_date, str):
            due_date = datetime.strptime(due_date, '%Y-%m-%d').date()

        customer = Customer.query.get(customer_id)
        
        invoice = Invoice(
            customer_id=customer_id,
            due_date=due_date,
            date=datetime.utcnow().date(),
            status='Draft',
            currency=customer.currency if customer else 'USD'
        )
        db.session.add(invoice)
        db.session.flush()

        total_amount = 0
        total_tax = 0
        for item in items:
            amount = float(item['quantity']) * float(item['unit_price'])
            
            # Calculate tax if specified
            tax_amount = 0
            tax_id = item.get('tax_id')
            if tax_id:
                tax = Tax.query.get(tax_id)
                if tax:
                    tax_amount = amount * float(tax.rate) / 100
            
            inv_item = InvoiceItem(
                invoice_id=invoice.id,
                description=item['description'],
                quantity=item['quantity'],
                unit_price=item['unit_price'],
                amount=amount,
                account_id=item['account_id'],
                tax_id=tax_id,
                tax_amount=tax_amount
            )
            db.session.add(inv_item)
            total_amount += amount
            total_tax += tax_amount
        
        invoice.total_amount = total_amount + total_tax
        invoice.tax_amount = total_tax
        db.session.commit()
        return invoice

    @staticmethod
    def post_invoice(invoice_id):
        """
        Posts an invoice to the General Ledger.
        Creates a Journal Entry:
          Debit: Accounts Receivable (total incl tax)
          Credit: Revenue Account(s) (subtotal)
          Credit: Tax Payable (tax amount, if any)
        """
        invoice = Invoice.query.get_or_404(invoice_id)
        if invoice.status != 'Draft':
            raise ValueError("Invoice is already posted or cancelled")
        
        ar_account = Account.query.filter_by(code='1200').first()
        if not ar_account:
            raise ValueError("Accounts Receivable account (Code 1200) not found")
            
        # Debit AR for total (including tax)
        je_items = [
            {'account_id': ar_account.id, 'debit': float(invoice.total_amount), 'credit': 0}
        ]
        
        # Credit Revenue Accounts (subtotal only)
        revenue_map = {}
        for item in invoice.items:
            if item.account_id not in revenue_map:
                revenue_map[item.account_id] = 0
            revenue_map[item.account_id] += float(item.amount)
            
        for acc_id, amount in revenue_map.items():
            je_items.append({
                'account_id': acc_id,
                'debit': 0,
                'credit': amount
            })
        
        # Credit Tax Payable (if tax exists)
        if invoice.tax_amount and float(invoice.tax_amount) > 0:
            # Collect tax by tax type
            tax_map = {}
            for item in invoice.items:
                if item.tax_id and item.tax_amount:
                    tax = Tax.query.get(item.tax_id)
                    if tax and tax.sales_tax_account_id:
                        acc_id = tax.sales_tax_account_id
                    else:
                        # Fallback to GST Payable
                        gst = Account.query.filter_by(code='2200').first()
                        acc_id = gst.id if gst else None
                    
                    if acc_id:
                        if acc_id not in tax_map:
                            tax_map[acc_id] = 0
                        tax_map[acc_id] += float(item.tax_amount)
            
            for acc_id, amount in tax_map.items():
                je_items.append({
                    'account_id': acc_id,
                    'debit': 0,
                    'credit': amount
                })
        
        entry = AccountingService.create_journal_entry(
            date=invoice.date,
            description=f"Invoice #{invoice.id} for {invoice.customer.name}",
            items=je_items,
            reference=f"INV-{invoice.id}"
        )
        
        invoice.status = 'Sent'
        invoice.journal_entry_id = entry.id
        db.session.commit()
        
        return invoice

    @staticmethod
    def cancel_invoice(invoice_id):
        """Cancels an invoice. If posted, creates a reversing JE."""
        invoice = Invoice.query.get(invoice_id)
        if not invoice:
            raise ValueError("Invoice not found.")
        if invoice.status == 'Cancelled':
            raise ValueError("Invoice is already cancelled.")
        
        if invoice.journal_entry_id:
            # Posted invoice — void the journal entry
            AccountingService.void_journal_entry(invoice.journal_entry_id)
        
        invoice.status = 'Cancelled'
        db.session.commit()
        
        AuditService.log(
            action='CANCEL',
            model='Invoice',
            model_id=invoice.id,
            details=f"Cancelled invoice #{invoice.id}"
        )
        
        return invoice
