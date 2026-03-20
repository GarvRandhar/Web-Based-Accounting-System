from app.models import db, Vendor, Bill, BillItem, Account, Tax
from app.services.accounting import AccountingService
from app.services.audit import AuditService
from datetime import datetime

class AccountsPayableService:
    @staticmethod
    def create_vendor(name, email=None, phone=None, address=None, currency='USD'):
        vendor = Vendor(name=name, email=email, phone=phone, address=address, currency=currency)
        db.session.add(vendor)
        db.session.commit()
        return vendor

    @staticmethod
    def create_bill(vendor_id, due_date, items):
        """
        Creates a new bill with optional tax per item.
        items: list of dicts {'description': str, 'quantity': float, 'unit_price': float, 'account_id': int, 'tax_id': int|None}
        """
        if isinstance(due_date, str):
            due_date = datetime.strptime(due_date, '%Y-%m-%d').date()

        vendor = Vendor.query.get(vendor_id)

        bill = Bill(
            vendor_id=vendor_id,
            due_date=due_date,
            date=datetime.utcnow().date(),
            status='Open',
            currency=vendor.currency if vendor else 'USD'
        )
        db.session.add(bill)
        db.session.flush()

        total_amount = 0
        total_tax = 0
        for item in items:
            amount = float(item['quantity']) * float(item['unit_price'])
            
            tax_amount = 0
            tax_id = item.get('tax_id')
            if tax_id:
                tax = Tax.query.get(tax_id)
                if tax:
                    tax_amount = amount * float(tax.rate) / 100
            
            bill_item = BillItem(
                bill_id=bill.id,
                description=item['description'],
                quantity=item['quantity'],
                unit_price=item['unit_price'],
                amount=amount,
                account_id=item['account_id'],
                tax_id=tax_id,
                tax_amount=tax_amount
            )
            db.session.add(bill_item)
            total_amount += amount
            total_tax += tax_amount
        
        bill.total_amount = total_amount + total_tax
        bill.tax_amount = total_tax
        db.session.commit()
        return bill

    @staticmethod
    def post_bill(bill_id):
        """
        Posts a bill to the General Ledger.
        Creates a Journal Entry:
          Debit: Expense Account(s) (subtotal)
          Debit: Tax Receivable (tax amount, if any)
          Credit: Accounts Payable (total incl tax)
        """
        bill = Bill.query.get_or_404(bill_id)
        if bill.journal_entry_id:
            raise ValueError("Bill is already posted")
        
        ap_account = Account.query.filter_by(code='2010').first()
        if not ap_account:
            raise ValueError("Accounts Payable account (Code 2010) not found")
            
        # Credit AP for total (including tax)
        je_items = [
            {'account_id': ap_account.id, 'debit': 0, 'credit': float(bill.total_amount)}
        ]
        
        # Debit Expense Accounts (subtotal only)
        expense_map = {}
        for item in bill.items:
            if item.account_id not in expense_map:
                expense_map[item.account_id] = 0
            expense_map[item.account_id] += float(item.amount)
            
        for acc_id, amount in expense_map.items():
            je_items.append({
                'account_id': acc_id,
                'debit': amount,
                'credit': 0
            })
        
        # Debit Tax Receivable (if tax exists)
        if bill.tax_amount and float(bill.tax_amount) > 0:
            tax_map = {}
            for item in bill.items:
                if item.tax_id and item.tax_amount:
                    tax = Tax.query.get(item.tax_id)
                    if tax and tax.purchase_tax_account_id:
                        acc_id = tax.purchase_tax_account_id
                    else:
                        # Fallback to GST Payable (input tax)
                        gst = Account.query.filter_by(code='2200').first()
                        acc_id = gst.id if gst else None
                    
                    if acc_id:
                        if acc_id not in tax_map:
                            tax_map[acc_id] = 0
                        tax_map[acc_id] += float(item.tax_amount)
            
            for acc_id, amount in tax_map.items():
                je_items.append({
                    'account_id': acc_id,
                    'debit': amount,
                    'credit': 0
                })
            
        entry = AccountingService.create_journal_entry(
            date=bill.date,
            description=f"Bill #{bill.id} from {bill.vendor.name}",
            items=je_items,
            reference=f"BILL-{bill.id}"
        )
        
        bill.status = 'Paid'
        bill.journal_entry_id = entry.id
        db.session.commit()
        
        return bill

    @staticmethod
    def cancel_bill(bill_id):
        """Cancels a bill. If posted, creates a reversing JE."""
        bill = Bill.query.get(bill_id)
        if not bill:
            raise ValueError("Bill not found.")
        if bill.status == 'Cancelled':
            raise ValueError("Bill is already cancelled.")
        
        if bill.journal_entry_id:
            AccountingService.void_journal_entry(bill.journal_entry_id)
        
        bill.status = 'Cancelled'
        db.session.commit()
        
        AuditService.log(
            action='CANCEL',
            model='Bill',
            model_id=bill.id,
            details=f"Cancelled bill #{bill.id}"
        )
        
        return bill
