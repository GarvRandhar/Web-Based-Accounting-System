from app import create_app, db
from app.models import User, Account, Customer, Vendor, Invoice, Bill, JournalEntry, JournalItem, InvoiceItem, BillItem
from app.services.accounting import AccountingService
from datetime import date, timedelta
import random

app = create_app('development')

def seed():
    with app.app_context():
        print("🌱 Seeding database with test data...")
        
        # 1. Ensure COA exists
        AccountingService.seed_chart_of_accounts()
        
        # 1b. Create admin user
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@demo.com', role='Admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("  - Created admin user (admin / admin123)")
        
        # Get Accounts
        cash = Account.query.filter_by(code='1010').first()
        ar = Account.query.filter_by(code='1200').first()
        ap = Account.query.filter_by(code='2010').first()
        sales = Account.query.filter_by(code='4010').first()
        service = Account.query.filter_by(code='4020').first()
        rent = Account.query.filter_by(code='5010').first()
        utilities = Account.query.filter_by(code='5020').first()
        supplies = Account.query.filter_by(code='5040').first()
        capital = Account.query.filter_by(code='3010').first()
        
        # 2. Customers
        customers = [
            Customer(name="Acme Corp", email="contact@acme.com", phone="555-0100", currency="USD"),
            Customer(name="Globex Inc", email="info@globex.com", phone="555-0101", currency="EUR"),
            Customer(name="Soylent Corp", email="sales@soylent.com", phone="555-0102", currency="GBP")
        ]
        for c in customers:
            if not Customer.query.filter_by(name=c.name).first():
                db.session.add(c)
        db.session.commit()
        
        # 3. Vendors
        vendors = [
            Vendor(name="Office Depot", email="sales@officedepot.com"),
            Vendor(name="Power Co", email="billing@powerco.com"),
            Vendor(name="Landlord LLC", email="rent@landlord.com")
        ]
        for v in vendors:
            if not Vendor.query.filter_by(name=v.name).first():
                db.session.add(v)
        db.session.commit()
        
        # Reload to get IDs
        cust_objs = Customer.query.all()
        vend_objs = Vendor.query.all()
        
        # 4. Initial Capital (Journal Entry)
        if not JournalEntry.query.filter_by(description="Initial Capital Investment").first():
            print("  - Creating Initial Capital...")
            items = [
                {'account_id': cash.id, 'debit': 50000, 'credit': 0},
                {'account_id': capital.id, 'debit': 0, 'credit': 50000}
            ]
            AccountingService.create_journal_entry(
                date=date.today() - timedelta(days=60),
                description="Initial Capital Investment",
                items=items
            )
            
        # 5. Invoices (AR)
        print("  - Creating Invoices...")
        for i, cust in enumerate(cust_objs):
            # Invoice 1: Past
            inv_date = date.today() - timedelta(days=30 + i*5)
            inv = Invoice(
                customer_id=cust.id,
                date=inv_date,
                due_date=inv_date + timedelta(days=30),
                status='Sent',
                total_amount=1500.0 * (i+1)
            )
            db.session.add(inv)
            db.session.flush()
            
            # Link to GL
            items = [
                {'account_id': ar.id, 'debit': inv.total_amount, 'credit': 0},
                {'account_id': sales.id, 'debit': 0, 'credit': inv.total_amount}
            ]
            je = AccountingService.create_journal_entry(
                date=inv_date,
                description=f"Invoice #{inv.id} for {cust.name}",
                items=items,
                reference=f"INV-{inv.id}"
            )
            inv.journal_entry_id = je.id
            
            # Invoice Item
            db.session.add(InvoiceItem(
                invoice_id=inv.id,
                description="Consulting Services",
                quantity=10 * (i+1),
                unit_price=150.0,
                amount=1500.0 * (i+1),
                account_id=sales.id
            ))

        # 6. Bills (AP)
        print("  - Creating Bills...")
        for i, vend in enumerate(vend_objs):
            bill_date = date.today() - timedelta(days=15 + i*3)
            amount = 200.0 * (i+1)
            expense_acc = supplies if i==0 else (utilities if i==1 else rent)
            
            bill = Bill(
                vendor_id=vend.id,
                date=bill_date,
                due_date=bill_date + timedelta(days=14),
                status='Open',
                total_amount=amount
            )
            db.session.add(bill)
            db.session.flush()
            
            # Link to GL
            items = [
                {'account_id': expense_acc.id, 'debit': amount, 'credit': 0},
                {'account_id': ap.id, 'debit': 0, 'credit': amount}
            ]
            je = AccountingService.create_journal_entry(
                date=bill_date,
                description=f"Bill #{bill.id} from {vend.name}",
                items=items,
                reference=f"BILL-{bill.id}"
            )
            bill.journal_entry_id = je.id
            
            # Bill Item
            db.session.add(BillItem(
                bill_id=bill.id,
                description="Monthly Service",
                quantity=1,
                unit_price=amount,
                amount=amount,
                account_id=expense_acc.id
            ))
            
        db.session.commit()
        print("✅ Seeding Complete!")

if __name__ == '__main__':
    seed()
