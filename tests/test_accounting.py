import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from app.services.accounting import AccountingService
from app.services.inventory import InventoryService
from app.services.ar import AccountsReceivableService
from app.services.ap import AccountsPayableService
import app.services.ar as ar_module
import app.services.ap as ap_module
from app.models import (
    Account,
    JournalEntry,
    JournalItem,
    Product,
    Warehouse,
    StockEntryItem,
    Customer,
    Invoice,
    Vendor,
    Bill,
    Tax,
)


def _utc_now():
    return datetime.now(timezone.utc)

def test_create_journal_entry_balanced(session):
    # Setup test accounts
    asset_acc = Account(code='1010', name='Cash', type='Asset')
    rev_acc = Account(code='4010', name='Sales', type='Revenue')
    session.add(asset_acc)
    session.add(rev_acc)
    session.commit()

    # Valid balanced entry
    items = [
        {'account_id': asset_acc.id, 'debit': Decimal('100.50'), 'credit': Decimal('0')},
        {'account_id': rev_acc.id, 'debit': Decimal('0'), 'credit': Decimal('100.50')}
    ]
    
    entry = AccountingService.create_journal_entry(
        date=_utc_now(),
        description='Test Sale', 
        items=items
    )
    
    assert entry.id is not None
    assert len(entry.items) == 2
    assert entry.is_balanced is True
    assert entry.total_debit == entry.total_credit

def test_create_journal_entry_unbalanced(session):
    # Setup test accounts
    asset_acc = Account(code='1010', name='Cash', type='Asset')
    rev_acc = Account(code='4010', name='Sales', type='Revenue')
    session.add(asset_acc)
    session.add(rev_acc)
    session.commit()

    # Invalid unbalanced entry
    items = [
        {'account_id': asset_acc.id, 'debit': float(100.50), 'credit': float(0)},
        {'account_id': rev_acc.id, 'debit': float(0), 'credit': float(100.51)}
    ]
    
    with pytest.raises(ValueError, match="Transaction is not balanced"):
        AccountingService.create_journal_entry(
            date=_utc_now(),
            description='Test Unbalanced', 
            items=items
        )

def test_get_summary_metrics(session):
    AccountingService.seed_chart_of_accounts()
    
    cash_acc = Account.query.filter_by(code='1010').first()
    sales_acc = Account.query.filter_by(code='4010').first()
    
    AccountingService.create_journal_entry(
        date=_utc_now(),
        description='Initial Capital',
        items=[
            {'account_id': cash_acc.id, 'debit': 500, 'credit': 0},
            {'account_id': sales_acc.id, 'debit': 0, 'credit': 500}
        ]
    )
    
    metrics = AccountingService.get_summary_metrics()
    assert metrics['assets'] == Decimal('500')
    assert metrics['net_income'] == Decimal('500')


def test_inventory_fifo_issue_uses_valuation_rate(session):
    inv_acc = Account(code='1501', name='Inventory A', type='Asset')
    exp_acc = Account(code='5001', name='COGS A', type='Expense')
    session.add_all([inv_acc, exp_acc])
    session.commit()

    product = InventoryService.create_product(
        sku='SKU-FIFO',
        name='FIFO Product',
        valuation_method='FIFO',
        inventory_account_id=inv_acc.id,
        expense_account_id=exp_acc.id,
    )
    warehouse = InventoryService.create_warehouse(name='Main WH')

    InventoryService.process_stock_entry(
        entry_type='Receipt',
        date=_utc_now().date(),
        items=[{'product_id': product.id, 'quantity': 10, 'rate': 12.5}],
        target_warehouse_id=warehouse.id,
    )
    issue = InventoryService.process_stock_entry(
        entry_type='Issue',
        date=_utc_now().date(),
        items=[{'product_id': product.id, 'quantity': 4}],
        source_warehouse_id=warehouse.id,
    )

    issued_line = StockEntryItem.query.filter_by(stock_entry_id=issue.id).first()
    assert issued_line is not None
    assert float(issued_line.rate) == pytest.approx(12.5, abs=0.01)


def test_inventory_multi_item_gl_posts_per_product_accounts(session):
    inv_a = Account(code='1511', name='Inventory B', type='Asset')
    exp_a = Account(code='5011', name='Expense B', type='Expense')
    inv_b = Account(code='1512', name='Inventory C', type='Asset')
    exp_b = Account(code='5012', name='Expense C', type='Expense')
    session.add_all([inv_a, exp_a, inv_b, exp_b])
    session.commit()

    p1 = InventoryService.create_product(
        sku='SKU-1', name='P1', inventory_account_id=inv_a.id, expense_account_id=exp_a.id
    )
    p2 = InventoryService.create_product(
        sku='SKU-2', name='P2', inventory_account_id=inv_b.id, expense_account_id=exp_b.id
    )
    wh = InventoryService.create_warehouse(name='GL WH')

    entry = InventoryService.process_stock_entry(
        entry_type='Receipt',
        date=_utc_now().date(),
        items=[
            {'product_id': p1.id, 'quantity': 2, 'rate': 10},
            {'product_id': p2.id, 'quantity': 3, 'rate': 20},
        ],
        target_warehouse_id=wh.id,
    )

    je = session.get(JournalEntry, entry.journal_entry_id)
    by_account = {item.account_id: (float(item.debit), float(item.credit)) for item in je.items}
    assert by_account[inv_a.id][0] == pytest.approx(20.0, abs=0.01)
    assert by_account[inv_b.id][0] == pytest.approx(60.0, abs=0.01)
    assert by_account[exp_a.id][1] == pytest.approx(20.0, abs=0.01)
    assert by_account[exp_b.id][1] == pytest.approx(60.0, abs=0.01)


def test_invoice_number_retries_after_conflict(session, monkeypatch):
    ar_acc = Account(code='1200', name='Accounts Receivable', type='Asset')
    rev_acc = Account(code='4100', name='Sales Revenue', type='Revenue')
    session.add_all([ar_acc, rev_acc])
    session.commit()
    customer = Customer(name='Retry Customer', currency='USD')
    session.add(customer)
    session.commit()

    existing = Invoice(
        invoice_number='INV-2026-00001',
        customer_id=customer.id,
        date=_utc_now().date(),
        due_date=_utc_now().date(),
        status='Draft',
        currency='USD',
    )
    session.add(existing)
    session.commit()

    seq = iter(['INV-2026-00001', 'INV-2026-00002'])
    monkeypatch.setattr(ar_module, '_generate_invoice_number', lambda: next(seq))

    invoice = AccountsReceivableService.create_invoice(
        customer_id=customer.id,
        due_date=_utc_now().date(),
        items=[{'description': 'Line', 'quantity': 1, 'unit_price': 25, 'account_id': rev_acc.id}],
    )
    assert invoice.invoice_number == 'INV-2026-00002'


def test_bill_number_retries_after_conflict(session, monkeypatch):
    ap_acc = Account(code='2010', name='Accounts Payable', type='Liability')
    exp_acc = Account(code='5200', name='Office Expense', type='Expense')
    session.add_all([ap_acc, exp_acc])
    session.commit()
    vendor = Vendor(name='Retry Vendor', currency='USD')
    session.add(vendor)
    session.commit()

    existing = Bill(
        bill_number='BILL-2026-00001',
        vendor_id=vendor.id,
        date=_utc_now().date(),
        due_date=_utc_now().date(),
        status='Open',
        currency='USD',
    )
    session.add(existing)
    session.commit()

    seq = iter(['BILL-2026-00001', 'BILL-2026-00002'])
    monkeypatch.setattr(ap_module, '_generate_bill_number', lambda: next(seq))

    bill = AccountsPayableService.create_bill(
        vendor_id=vendor.id,
        due_date=_utc_now().date(),
        items=[{'description': 'Line', 'quantity': 1, 'unit_price': 30, 'account_id': exp_acc.id}],
    )
    assert bill.bill_number == 'BILL-2026-00002'


def test_ar_rounding_and_set_based_overdue_refresh(session):
    rev_acc = Account(code='4300', name='Services Revenue', type='Revenue')
    tax_liab = Account(code='2200', name='GST Payable', type='Liability')
    session.add_all([rev_acc, tax_liab])
    session.commit()
    tax = Tax(name='GST 7.25', rate=Decimal('7.25'), sales_tax_account_id=tax_liab.id)
    customer = Customer(name='Precision Customer', currency='USD')
    session.add_all([tax, customer])
    session.commit()

    invoice = AccountsReceivableService.create_invoice(
        customer_id=customer.id,
        due_date=(_utc_now() - timedelta(days=2)).date(),
        items=[{'description': 'Service', 'quantity': '1', 'unit_price': '10.015', 'account_id': rev_acc.id, 'tax_id': tax.id}],
    )
    assert float(invoice.total_amount) == pytest.approx(10.75, abs=0.01)
    assert float(invoice.tax_amount) == pytest.approx(0.73, abs=0.01)

    invoice.status = 'Sent'
    session.commit()
    updated_count = AccountsReceivableService.refresh_overdue_statuses()
    session.refresh(invoice)
    assert updated_count >= 1
    assert invoice.status == 'Overdue'
