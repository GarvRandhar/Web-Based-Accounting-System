from datetime import date, datetime, timedelta, timezone

from app import create_app, db
from app.models import (
    Account,
    BankStatement,
    BankTransaction,
    CompanySettings,
    CostCenter,
    Currency,
    Customer,
    Employee,
    ExchangeRate,
    FixedAsset,
    JournalEntry,
    Product,
    SalaryComponent,
    SalaryStructure,
    SalaryStructureDetail,
    Tax,
    TaxGroup,
    User,
    Vendor,
    Warehouse,
)
from app.services.accounting import AccountingService
from app.services.ap import AccountsPayableService
from app.services.ar import AccountsReceivableService
from app.services.assets import AssetService
from app.services.currency import CurrencyService
from app.services.inventory import InventoryService
from app.services.payroll import PayrollService

app = create_app("development")


def _now():
    return datetime.now(timezone.utc)


def _get_account(code):
    acc = Account.query.filter_by(code=code).first()
    if not acc:
        raise RuntimeError(f"Required account with code {code} not found.")
    return acc


def _ensure_admin():
    admin = User.query.filter_by(username="admin").first()
    if not admin:
        admin = User(
            username="admin",
            email="admin@demo.com",
            role="admin",
            status="active",
            invited_at=_now(),
            password_changed_at=_now(),
        )
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.commit()
        print("  - created admin user (admin/admin123)")


def _ensure_company_settings():
    settings = CompanySettings.query.first()
    if not settings:
        settings = CompanySettings(
            company_name="Demo Accounting Co",
            address="42 Demo Street, Example City",
            tax_id="TAX-DEMO-001",
            currency_symbol="$",
            base_currency="USD",
            fiscal_year_start=date(date.today().year, 1, 1),
        )
        db.session.add(settings)
        db.session.commit()
        print("  - created company settings")


def _ensure_currencies_and_rates():
    CurrencyService.seed_default_currencies()
    for from_code, to_code, rate in [
        ("USD", "EUR", 0.92),
        ("USD", "GBP", 0.78),
        ("USD", "INR", 83.10),
        ("EUR", "USD", 1.09),
    ]:
        existing = ExchangeRate.query.filter_by(
            from_currency=from_code, to_currency=to_code
        ).first()
        if not existing:
            CurrencyService.add_exchange_rate(
                from_currency=from_code,
                to_currency=to_code,
                rate=rate,
                effective_date=date.today() - timedelta(days=7),
            )
    print("  - ensured currencies and exchange rates")


def _ensure_tax_setup():
    gst = Tax.query.filter_by(name="GST 10%").first()
    if not gst:
        gst = Tax(
            name="GST 10%",
            rate=10.0,
            sales_tax_account_id=_get_account("2200").id,
            purchase_tax_account_id=_get_account("2200").id,
            is_active=True,
        )
        db.session.add(gst)
        db.session.commit()

    tax_group = TaxGroup.query.filter_by(name="Standard GST").first()
    if not tax_group:
        from app.services.taxation import TaxationService

        TaxationService.create_tax_group(
            name="Standard GST",
            tax_ids=[gst.id],
            description="Default GST group for demo transactions",
        )
    print("  - ensured tax and tax group")


def _ensure_cost_centers():
    for code, name in [
        ("OPS", "Operations"),
        ("SAL", "Sales"),
        ("ADM", "Administration"),
    ]:
        if not CostCenter.query.filter_by(code=code).first():
            db.session.add(CostCenter(code=code, name=name, is_active=True))
    db.session.commit()
    print("  - ensured cost centers")


def _ensure_customers_vendors():
    for data in [
        ("Acme Corp", "contact@acme.com", "555-0100", "USD"),
        ("Globex Inc", "info@globex.com", "555-0101", "EUR"),
        ("Soylent Corp", "sales@soylent.com", "555-0102", "GBP"),
    ]:
        if not Customer.query.filter_by(name=data[0]).first():
            db.session.add(
                Customer(name=data[0], email=data[1], phone=data[2], currency=data[3])
            )

    for name, email in [
        ("Office Depot", "sales@officedepot.com"),
        ("Power Co", "billing@powerco.com"),
        ("Landlord LLC", "rent@landlord.com"),
    ]:
        if not Vendor.query.filter_by(name=name).first():
            db.session.add(Vendor(name=name, email=email, currency="USD"))
    db.session.commit()
    print("  - ensured customers and vendors")


def _ensure_capital_entry():
    if not JournalEntry.query.filter_by(description="Initial Capital Investment").first():
        AccountingService.create_journal_entry(
            date=date.today() - timedelta(days=60),
            description="Initial Capital Investment",
            items=[
                {"account_id": _get_account("1010").id, "debit": 50000, "credit": 0},
                {"account_id": _get_account("3010").id, "debit": 0, "credit": 50000},
            ],
        )
        print("  - created initial capital journal")


def _ensure_ar_ap_data():
    if not JournalEntry.query.filter(JournalEntry.reference.like("INV-%")).first():
        sales = _get_account("4010")
        service = _get_account("4020")
        bank = _get_account("1020")
        gst = Tax.query.filter_by(name="GST 10%").first()
        for idx, customer in enumerate(Customer.query.order_by(Customer.name).limit(3).all(), start=1):
            invoice = AccountsReceivableService.create_invoice(
                customer_id=customer.id,
                due_date=date.today() + timedelta(days=20 + idx),
                items=[
                    {
                        "description": f"Consulting package {idx}",
                        "quantity": 5 * idx,
                        "unit_price": 120,
                        "account_id": sales.id,
                        "tax_id": gst.id if gst else None,
                    },
                    {
                        "description": f"Support retainer {idx}",
                        "quantity": 2,
                        "unit_price": 180,
                        "account_id": service.id,
                        "tax_id": gst.id if gst else None,
                    },
                ],
            )
            AccountsReceivableService.post_invoice(invoice.id)
            if idx == 1:
                AccountsReceivableService.record_payment(
                    invoice_id=invoice.id,
                    amount=float(invoice.total_amount) / 2,
                    payment_date=date.today(),
                    bank_account_id=bank.id,
                    notes="Demo partial payment",
                )
        print("  - created AR demo invoices/payments")

    if not JournalEntry.query.filter(JournalEntry.reference.like("BILL-%")).first():
        supplies = _get_account("5040")
        utilities = _get_account("5020")
        rent = _get_account("5010")
        bank = _get_account("1020")
        gst = Tax.query.filter_by(name="GST 10%").first()
        expense_accounts = [supplies, utilities, rent]
        for idx, vendor in enumerate(Vendor.query.order_by(Vendor.name).limit(3).all(), start=1):
            bill = AccountsPayableService.create_bill(
                vendor_id=vendor.id,
                due_date=date.today() + timedelta(days=10 + idx),
                items=[
                    {
                        "description": f"Monthly charge {idx}",
                        "quantity": 1,
                        "unit_price": 250 * idx,
                        "account_id": expense_accounts[idx - 1].id,
                        "tax_id": gst.id if gst else None,
                    }
                ],
            )
            AccountsPayableService.post_bill(bill.id)
            if idx == 1:
                AccountsPayableService.record_payment(
                    bill_id=bill.id,
                    amount=float(bill.total_amount) / 2,
                    payment_date=date.today(),
                    bank_account_id=bank.id,
                    notes="Demo partial payment",
                )
        print("  - created AP demo bills/payments")


def _ensure_inventory_data():
    inv_acc = _get_account("1500")
    exp_acc = _get_account("5040")
    rev_acc = _get_account("4010")

    main_wh = Warehouse.query.filter_by(name="Main Warehouse").first()
    if not main_wh:
        main_wh = InventoryService.create_warehouse("Main Warehouse", "HQ")
    outlet_wh = Warehouse.query.filter_by(name="Outlet Warehouse").first()
    if not outlet_wh:
        outlet_wh = InventoryService.create_warehouse("Outlet Warehouse", "Retail")

    products_data = [
        ("SKU-LAP-001", "Laptop", 850, 1200, "AVG"),
        ("SKU-MOU-002", "Mouse", 15, 30, "FIFO"),
        ("SKU-KEY-003", "Keyboard", 25, 50, "AVG"),
    ]
    products = []
    for sku, name, buy, sell, method in products_data:
        product = Product.query.filter_by(sku=sku).first()
        if not product:
            product = InventoryService.create_product(
                sku=sku,
                name=name,
                purchase_price=buy,
                selling_price=sell,
                valuation_method=method,
                inventory_account_id=inv_acc.id,
                expense_account_id=exp_acc.id,
                revenue_account_id=rev_acc.id,
            )
        products.append(product)

    if not JournalEntry.query.filter(JournalEntry.reference.like("SE-%")).first():
        InventoryService.process_stock_entry(
            entry_type="Receipt",
            date=date.today() - timedelta(days=12),
            items=[
                {"product_id": products[0].id, "quantity": 15, "rate": 840},
                {"product_id": products[1].id, "quantity": 80, "rate": 14},
                {"product_id": products[2].id, "quantity": 50, "rate": 24},
            ],
            target_warehouse_id=main_wh.id,
            reference="SEED-RECEIPT-1",
            notes="Initial stock for demo",
        )
        InventoryService.process_stock_entry(
            entry_type="Issue",
            date=date.today() - timedelta(days=8),
            items=[{"product_id": products[1].id, "quantity": 5}],
            source_warehouse_id=main_wh.id,
            reference="SEED-ISSUE-1",
            notes="Sample issue movement",
        )
        InventoryService.process_stock_entry(
            entry_type="Transfer",
            date=date.today() - timedelta(days=6),
            items=[{"product_id": products[2].id, "quantity": 10}],
            source_warehouse_id=main_wh.id,
            target_warehouse_id=outlet_wh.id,
            reference="SEED-TRANSFER-1",
            notes="Move stock to outlet",
        )
        print("  - created inventory stock movements")


def _ensure_payroll_data():
    salary_exp = _get_account("5030")
    ap = _get_account("2010")
    bank = _get_account("1020")
    _ = bank  # kept for readability of mapped accounts

    basic = SalaryComponent.query.filter_by(name="Basic Pay").first()
    if not basic:
        basic = PayrollService.create_salary_component(
            name="Basic Pay", component_type="Earning", account_id=salary_exp.id
        )
    hra = SalaryComponent.query.filter_by(name="HRA").first()
    if not hra:
        hra = PayrollService.create_salary_component(
            name="HRA", component_type="Earning", account_id=salary_exp.id
        )
    pf = SalaryComponent.query.filter_by(name="PF Deduction").first()
    if not pf:
        pf = PayrollService.create_salary_component(
            name="PF Deduction", component_type="Deduction", is_statutory=True, account_id=ap.id
        )

    structure = SalaryStructure.query.filter_by(name="Demo Standard Structure").first()
    if not structure:
        structure = PayrollService.create_salary_structure(
            name="Demo Standard Structure",
            description="Demo payroll structure",
            details=[
                {"component_id": basic.id, "amount": 3000, "percentage": 0, "base_component_id": None},
                {"component_id": hra.id, "amount": 1200, "percentage": 0, "base_component_id": None},
                {"component_id": pf.id, "amount": 500, "percentage": 0, "base_component_id": None},
            ],
        )

    employees_data = [
        ("EMP-001", "Alice Johnson", "Finance", "Accountant"),
        ("EMP-002", "Bob Smith", "Sales", "Manager"),
    ]
    for code, name, dept, role in employees_data:
        if not Employee.query.filter_by(employee_code=code).first():
            PayrollService.create_employee(
                employee_code=code,
                name=name,
                department=dept,
                designation=role,
                email=f"{code.lower()}@demo.com",
                salary_structure_id=structure.id,
            )

    period = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    if not JournalEntry.query.filter(JournalEntry.reference.like("PAYROLL-%")).first():
        payroll = PayrollService.process_payroll(period=period)
        PayrollService.post_payroll(payroll.id)
        print("  - created payroll run and GL posting")


def _ensure_assets_data():
    if not FixedAsset.query.filter_by(asset_code="AST-LAPTOP-01").first():
        AssetService.create_asset(
            asset_code="AST-LAPTOP-01",
            name="Office Laptop Set",
            purchase_date=date.today() - timedelta(days=180),
            purchase_price=6000,
            useful_life_years=3,
            depreciation_method="SLM",
            salvage_value=600,
            description="Demo fixed asset",
            asset_account_id=_get_account("1500").id,
            depreciation_account_id=_get_account("5030").id,
            accumulated_dep_account_id=_get_account("2010").id,
        )
        print("  - created fixed asset and schedule")


def _ensure_reconciliation_data():
    bank_account = _get_account("1020")
    existing = BankStatement.query.join(Account).filter(Account.code == "1020").first()
    if not existing:
        stmt = BankStatement(
            account_id=bank_account.id,
            start_date=date.today() - timedelta(days=30),
            end_date=date.today(),
            starting_balance=25000,
            ending_balance=26800,
        )
        db.session.add(stmt)
        db.session.flush()
        db.session.add(
            BankTransaction(
                statement_id=stmt.id,
                date=date.today() - timedelta(days=5),
                description="Customer transfer receipt",
                amount=800,
            )
        )
        db.session.commit()
        print("  - created bank statement and transaction")


def seed():
    with app.app_context():
        print("Seeding demo database...")
        db.create_all()
        AccountingService.seed_chart_of_accounts()
        _ensure_admin()
        _ensure_company_settings()
        _ensure_currencies_and_rates()
        _ensure_tax_setup()
        _ensure_cost_centers()
        _ensure_customers_vendors()
        _ensure_capital_entry()
        _ensure_ar_ap_data()
        _ensure_inventory_data()
        _ensure_payroll_data()
        _ensure_assets_data()
        _ensure_reconciliation_data()
        print("Seeding complete.")


if __name__ == "__main__":
    seed()
