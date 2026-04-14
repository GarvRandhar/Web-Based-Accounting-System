from datetime import datetime, timezone


def _now():
    """Timezone-aware UTC timestamp helper."""
    return datetime.now(timezone.utc)

def _today():
    """Returns today's date."""
    return datetime.now(timezone.utc).date()
from flask_login import UserMixin
from .extensions import db
from .extensions import bcrypt

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    name = db.Column(db.String(100))
    role = db.Column(db.String(20), nullable=False, default='viewer')  # admin, accountant, viewer
    invited_at = db.Column(db.DateTime)
    password_changed_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, active
    created_at = db.Column(db.DateTime, default=_now)

    ALLOWED_ROLES = {'admin', 'accountant', 'viewer'}
    ALLOWED_STATUSES = {'pending', 'active'}

    def normalize_role(self):
        if self.role:
            self.role = self.role.strip().lower()

    def normalize_status(self):
        if self.status:
            self.status = self.status.strip().lower()

    def is_admin(self):
        return (self.role or '').lower() == 'admin'

    def requires_password_change(self):
        return (self.status or '').lower() == 'pending' or self.password_changed_at is None

    def activate(self):
        self.status = 'active'
        self.password_changed_at = _now()

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)


@db.event.listens_for(User, 'before_insert')
def normalize_user_before_insert(mapper, connection, target):
    target.normalize_role()
    target.normalize_status()
    if target.role not in User.ALLOWED_ROLES:
        target.role = 'viewer'
    if target.status not in User.ALLOWED_STATUSES:
        target.status = 'pending'


@db.event.listens_for(User, 'before_update')
def normalize_user_before_update(mapper, connection, target):
    target.normalize_role()
    target.normalize_status()

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False) # e.g. "1001"
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False) # Asset, Liability, Equity, Revenue, Expense
    description = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=_now)
    
    # Hierarchy
    parent_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    children = db.relationship('Account', backref=db.backref('parent', remote_side=[id]))

    def __repr__(self):
        return f'<Account {self.code} - {self.name}>'

class JournalEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=_today, index=True)  # idx: reports filter by date
    description = db.Column(db.String(255), nullable=False)
    reference = db.Column(db.String(100), index=True)  # idx: FY-CLOSE lookup
    posted = db.Column(db.Boolean, default=False)
    voided = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=_now)
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)

    items = db.relationship('JournalItem', backref='entry', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<JournalEntry {self.id} {self.date}>'

    @property
    def total_debit(self):
        return sum(item.debit for item in self.items)

    @property
    def total_credit(self):
        return sum(item.credit for item in self.items)
    
    @property
    def is_balanced(self):
        return abs(self.total_debit - self.total_credit) < 0.01

class JournalItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entry.id'), nullable=False, index=True)  # idx: parent JE lookup
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False, index=True)  # idx: all reports group/filter by account
    debit = db.Column(db.Numeric(12, 2), default=0.0)
    credit = db.Column(db.Numeric(12, 2), default=0.0)
    cost_center_id = db.Column(db.Integer, db.ForeignKey('cost_center.id'), nullable=True)

    account = db.relationship('Account', backref='journal_items')
    cost_center = db.relationship('CostCenter', backref='journal_items')

    def __repr__(self):
        return f'<JournalItem {self.account.name} Dr:{self.debit} Cr:{self.credit}>'

class Tax(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    rate = db.Column(db.Numeric(5, 2), nullable=False) # e.g. 18.0
    is_active = db.Column(db.Boolean, default=True)
    
    # GL accounts for tax posting
    sales_tax_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    purchase_tax_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    
    sales_tax_account = db.relationship('Account', foreign_keys=[sales_tax_account_id])
    purchase_tax_account = db.relationship('Account', foreign_keys=[purchase_tax_account_id])

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    action = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(50), nullable=False)
    model_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=_now, index=True)  # idx: audit log ordered by time

    user = db.relationship('User', backref='audit_logs')

class BankStatement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False) # The Cash/Bank account
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    starting_balance = db.Column(db.Numeric(12, 2), default=0.0)
    ending_balance = db.Column(db.Numeric(12, 2), default=0.0)
    created_at = db.Column(db.DateTime, default=_now)
    
    account = db.relationship('Account', backref='bank_statements')
    transactions = db.relationship('BankTransaction', backref='statement', cascade="all, delete-orphan")

class BankTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    statement_id = db.Column(db.Integer, db.ForeignKey('bank_statement.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False) # + for Deposit, - for Withdrawal
    
    # Matching
    matched_journal_item_id = db.Column(db.Integer, db.ForeignKey('journal_item.id'), nullable=True)
    matched_item = db.relationship('JournalItem', backref='bank_match')
    
    @property
    def is_reconciled(self):
        return self.matched_journal_item_id is not None

class CompanySettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company_name = db.Column(db.String(100), default="My Company")
    address = db.Column(db.Text)
    tax_id = db.Column(db.String(50))
    currency_symbol = db.Column(db.String(5), default="$")
    base_currency = db.Column(db.String(3), default="USD")
    fiscal_year_start = db.Column(db.Date)
    
    updated_at = db.Column(db.DateTime, default=_now, onupdate=_now)


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    currency = db.Column(db.String(3), default="USD")
    created_at = db.Column(db.DateTime, default=_now)
    
    invoices = db.relationship('Invoice', backref='customer', lazy=True)

    def __repr__(self):
        return f'<Customer {self.name}>'

class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(30), unique=True, nullable=True, index=True)  # e.g. INV-2026-00001
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False, index=True)  # idx: customer invoice lookups
    date = db.Column(db.Date, nullable=False, default=lambda: _now().date(), index=True)
    due_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='Draft', index=True)  # Draft/Sent/Overdue/Paid/Cancelled
    total_amount = db.Column(db.Numeric(12, 2), default=0.0)
    tax_amount = db.Column(db.Numeric(12, 2), default=0.0)
    amount_paid = db.Column(db.Numeric(12, 2), default=0.0)  # Running total of payments received
    currency = db.Column(db.String(3), default="USD")

    # Link to GL
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entry.id'), nullable=True)
    journal_entry = db.relationship('JournalEntry')

    created_at = db.Column(db.DateTime, default=_now)

    items = db.relationship('InvoiceItem', backref='invoice', lazy=True, cascade="all, delete-orphan")

    @property
    def balance_due(self):
        """Remaining unpaid amount."""
        return round(float(self.total_amount or 0) - float(self.amount_paid or 0), 2)

    @property
    def is_overdue(self):
        from datetime import date as date_type
        return (
            self.status in ('Sent', 'Overdue')
            and self.due_date is not None
            and self.due_date < date_type.today()
        )

    def __repr__(self):
        return f'<Invoice {self.invoice_number or self.id} - {self.status}>'

class InvoiceItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), default=1.0)
    unit_price = db.Column(db.Numeric(12, 2), default=0.0)
    amount = db.Column(db.Numeric(12, 2), default=0.0)
    
    # Tax
    tax_id = db.Column(db.Integer, db.ForeignKey('tax.id'), nullable=True)
    tax_amount = db.Column(db.Numeric(12, 2), default=0.0)
    tax = db.relationship('Tax')
    
    # Revenue Account (Credit)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    account = db.relationship('Account')

    def __repr__(self):
        return f'<InvoiceItem {self.description} - {self.amount}>'

class Vendor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    currency = db.Column(db.String(3), default="USD")
    created_at = db.Column(db.DateTime, default=_now)
    
    bills = db.relationship('Bill', backref='vendor', lazy=True)

    def __repr__(self):
        return f'<Vendor {self.name}>'

class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_number = db.Column(db.String(30), unique=True, nullable=True, index=True)  # e.g. BILL-2026-00001
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False, index=True)   # idx: vendor bill lookups
    date = db.Column(db.Date, nullable=False, default=lambda: _now().date(), index=True)
    due_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='Open', index=True)  # Open/Posted/Overdue/Paid/Cancelled
    total_amount = db.Column(db.Numeric(12, 2), default=0.0)
    tax_amount = db.Column(db.Numeric(12, 2), default=0.0)
    amount_paid = db.Column(db.Numeric(12, 2), default=0.0)  # Running total of payments made
    currency = db.Column(db.String(3), default="USD")

    # Link to GL (Accounts Payable)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entry.id'), nullable=True)
    journal_entry = db.relationship('JournalEntry')

    created_at = db.Column(db.DateTime, default=_now)

    items = db.relationship('BillItem', backref='bill', lazy=True, cascade="all, delete-orphan")

    @property
    def balance_due(self):
        """Remaining unpaid amount."""
        return round(float(self.total_amount or 0) - float(self.amount_paid or 0), 2)

    @property
    def is_overdue(self):
        from datetime import date as date_type
        return (
            self.status in ('Posted', 'Overdue')
            and self.due_date is not None
            and self.due_date < date_type.today()
        )

    def __repr__(self):
        return f'<Bill {self.bill_number or self.id} - {self.status}>'

class BillItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), default=1.0)
    unit_price = db.Column(db.Numeric(12, 2), default=0.0)
    amount = db.Column(db.Numeric(12, 2), default=0.0)
    
    # Tax
    tax_id = db.Column(db.Integer, db.ForeignKey('tax.id'), nullable=True)
    tax_amount = db.Column(db.Numeric(12, 2), default=0.0)
    tax = db.relationship('Tax')
    
    # Expense Account (Debit)
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    account = db.relationship('Account')

    def __repr__(self):
        return f'<BillItem {self.description} - {self.amount}>'

class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entry.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(512), nullable=False)
    upload_date = db.Column(db.DateTime, default=_now)
    
    # Link back to JournalEntry
    journal_entry = db.relationship('JournalEntry', backref=db.backref('attachments', lazy=True, cascade="all, delete-orphan"))

    def __repr__(self):
        return f'<Attachment {self.filename}>'


# =====================================================
# MODULE: Cost Centers / Profit Centers
# =====================================================

class CostCenter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('cost_center.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_now)

    children = db.relationship('CostCenter', backref=db.backref('parent', remote_side='CostCenter.id'))

    def __repr__(self):
        return f'<CostCenter {self.code} - {self.name}>'


# =====================================================
# MODULE: Taxation — Tax Groups (Composite Taxes)
# =====================================================

class TaxGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)  # e.g. "GST 18%"
    description = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=_now)

    items = db.relationship('TaxGroupItem', backref='group', lazy=True, cascade="all, delete-orphan",
                            order_by='TaxGroupItem.sequence')

    @property
    def total_rate(self):
        return sum(float(item.tax.rate) for item in self.items if item.tax)

    def __repr__(self):
        return f'<TaxGroup {self.name}>'

class TaxGroupItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tax_group_id = db.Column(db.Integer, db.ForeignKey('tax_group.id'), nullable=False)
    tax_id = db.Column(db.Integer, db.ForeignKey('tax.id'), nullable=False)
    sequence = db.Column(db.Integer, default=0)

    tax = db.relationship('Tax')

    def __repr__(self):
        return f'<TaxGroupItem {self.tax.name} in group {self.tax_group_id}>'


# =====================================================
# MODULE: Multi-Currency Processing
# =====================================================

class Currency(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(3), unique=True, nullable=False)  # ISO 4217: USD, EUR, INR
    name = db.Column(db.String(50), nullable=False)
    symbol = db.Column(db.String(5), default='')
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f'<Currency {self.code}>'

class ExchangeRate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    from_currency = db.Column(db.String(3), nullable=False)
    to_currency = db.Column(db.String(3), nullable=False)
    rate = db.Column(db.Numeric(18, 8), nullable=False)  # e.g. 1 USD = 83.12 INR
    effective_date = db.Column(db.Date, nullable=False, default=_now)
    created_at = db.Column(db.DateTime, default=_now)

    def __repr__(self):
        return f'<ExchangeRate {self.from_currency}->{self.to_currency} @ {self.rate}>'


# =====================================================
# MODULE: Inventory & Stock Management
# =====================================================

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    unit = db.Column(db.String(20), default='Nos')  # Nos, Kg, Ltr, etc.
    purchase_price = db.Column(db.Numeric(12, 2), default=0.0)
    selling_price = db.Column(db.Numeric(12, 2), default=0.0)
    valuation_method = db.Column(db.String(10), default='AVG')  # FIFO or AVG (Weighted Average)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=_now)

    # GL Accounts
    inventory_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    expense_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    revenue_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)

    inventory_account = db.relationship('Account', foreign_keys=[inventory_account_id])
    expense_account = db.relationship('Account', foreign_keys=[expense_account_id])
    revenue_account = db.relationship('Account', foreign_keys=[revenue_account_id])

    def __repr__(self):
        return f'<Product {self.sku} - {self.name}>'

class Warehouse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    location = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=_now)

    def __repr__(self):
        return f'<Warehouse {self.name}>'

class StockEntry(db.Model):
    """Header for stock movements (Receipt, Issue, Transfer)."""
    id = db.Column(db.Integer, primary_key=True)
    entry_type = db.Column(db.String(20), nullable=False)  # Receipt, Issue, Transfer
    date = db.Column(db.Date, nullable=False, default=_today)
    reference = db.Column(db.String(100))
    notes = db.Column(db.Text)
    source_warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.id'), nullable=True)
    target_warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.id'), nullable=True)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entry.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_now)

    source_warehouse = db.relationship('Warehouse', foreign_keys=[source_warehouse_id])
    target_warehouse = db.relationship('Warehouse', foreign_keys=[target_warehouse_id])
    journal_entry = db.relationship('JournalEntry')
    items = db.relationship('StockEntryItem', backref='stock_entry', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<StockEntry {self.entry_type} #{self.id}>'

class StockEntryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stock_entry_id = db.Column(db.Integer, db.ForeignKey('stock_entry.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Numeric(12, 3), nullable=False)
    rate = db.Column(db.Numeric(12, 2), default=0.0)  # Unit cost
    amount = db.Column(db.Numeric(14, 2), default=0.0)

    product = db.relationship('Product')

    def __repr__(self):
        return f'<StockEntryItem {self.product.name} x{self.quantity}>'

class StockLedgerEntry(db.Model):
    """Perpetual inventory ledger — one row per stock movement per product per warehouse."""
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False, index=True)    # idx: stock balance queries
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouse.id'), nullable=False, index=True) # idx: per-warehouse balance
    posting_date = db.Column(db.Date, nullable=False, default=_today, index=True)      # idx: date-range stock queries
    qty_change = db.Column(db.Numeric(12, 3), nullable=False)
    valuation_rate = db.Column(db.Numeric(12, 2), default=0.0)
    balance_qty = db.Column(db.Numeric(12, 3), default=0.0)
    balance_value = db.Column(db.Numeric(14, 2), default=0.0)
    stock_entry_id = db.Column(db.Integer, db.ForeignKey('stock_entry.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_now)

    product = db.relationship('Product', backref='stock_ledger_entries')
    warehouse = db.relationship('Warehouse', backref='stock_ledger_entries')
    stock_entry = db.relationship('StockEntry')

    def __repr__(self):
        return f'<SLE {self.product.name} {self.qty_change} @ {self.valuation_rate}>'


# =====================================================
# MODULE: Payroll & HR
# =====================================================

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    department = db.Column(db.String(50))
    designation = db.Column(db.String(50))
    date_of_joining = db.Column(db.Date)
    bank_account = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True)
    salary_structure_id = db.Column(db.Integer, db.ForeignKey('salary_structure.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_now)

    salary_structure = db.relationship('SalaryStructure', backref='employees')

    def __repr__(self):
        return f'<Employee {self.employee_code} - {self.name}>'

class SalaryComponent(db.Model):
    """Individual earning or deduction component (e.g., Basic Pay, HRA, PF, Tax)."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    component_type = db.Column(db.String(10), nullable=False)  # Earning or Deduction
    is_statutory = db.Column(db.Boolean, default=False)  # PF, ESI, Tax etc.
    account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)  # GL posting account

    account = db.relationship('Account')

    def __repr__(self):
        return f'<SalaryComponent {self.name} ({self.component_type})>'

class SalaryStructure(db.Model):
    """A template defining component-wise salary breakdown."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=_now)

    details = db.relationship('SalaryStructureDetail', backref='structure', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<SalaryStructure {self.name}>'

class SalaryStructureDetail(db.Model):
    """One row per component in a salary structure, with fixed amount or % of base."""
    id = db.Column(db.Integer, primary_key=True)
    salary_structure_id = db.Column(db.Integer, db.ForeignKey('salary_structure.id'), nullable=False)
    component_id = db.Column(db.Integer, db.ForeignKey('salary_component.id'), nullable=False)
    amount = db.Column(db.Numeric(12, 2), default=0.0)  # Fixed amount
    percentage = db.Column(db.Numeric(5, 2), default=0.0)  # % of base (if amount=0)
    base_component_id = db.Column(db.Integer, db.ForeignKey('salary_component.id'), nullable=True)  # % of which component

    component = db.relationship('SalaryComponent', foreign_keys=[component_id])
    base_component = db.relationship('SalaryComponent', foreign_keys=[base_component_id])

    def __repr__(self):
        return f'<SalaryStructureDetail {self.component.name}>'

class PayrollEntry(db.Model):
    """A payroll run for a given period."""
    id = db.Column(db.Integer, primary_key=True)
    period = db.Column(db.String(20), nullable=False)  # e.g. "2026-03"
    run_date = db.Column(db.Date, nullable=False, default=_now)
    total_gross = db.Column(db.Numeric(14, 2), default=0.0)
    total_deductions = db.Column(db.Numeric(14, 2), default=0.0)
    total_net = db.Column(db.Numeric(14, 2), default=0.0)
    status = db.Column(db.String(20), default='Draft')  # Draft, Posted
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entry.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_now)

    journal_entry = db.relationship('JournalEntry')
    payroll_items = db.relationship('PayrollItem', backref='payroll_entry', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<PayrollEntry {self.period} - {self.status}>'

class PayrollItem(db.Model):
    """One row per employee in a payroll run."""
    id = db.Column(db.Integer, primary_key=True)
    payroll_entry_id = db.Column(db.Integer, db.ForeignKey('payroll_entry.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    gross_pay = db.Column(db.Numeric(12, 2), default=0.0)
    total_deductions = db.Column(db.Numeric(12, 2), default=0.0)
    net_pay = db.Column(db.Numeric(12, 2), default=0.0)
    components_json = db.Column(db.Text)  # JSON string of component-wise breakdown

    employee = db.relationship('Employee')

    def __repr__(self):
        return f'<PayrollItem {self.employee.name} Net:{self.net_pay}>'


# =====================================================
# MODULE: Fixed Asset Management
# =====================================================

class FixedAsset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    purchase_date = db.Column(db.Date, nullable=False)
    purchase_price = db.Column(db.Numeric(14, 2), nullable=False)
    salvage_value = db.Column(db.Numeric(14, 2), default=0.0)
    useful_life_years = db.Column(db.Integer, nullable=False)
    depreciation_method = db.Column(db.String(5), default='SLM')  # SLM (Straight Line) or WDV (Written Down Value)
    status = db.Column(db.String(20), default='Active')  # Active, Disposed, Sold
    disposed_date = db.Column(db.Date, nullable=True)
    disposed_amount = db.Column(db.Numeric(14, 2), default=0.0)
    created_at = db.Column(db.DateTime, default=_now)

    # GL Accounts
    asset_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    depreciation_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    accumulated_dep_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)

    asset_account = db.relationship('Account', foreign_keys=[asset_account_id])
    depreciation_account = db.relationship('Account', foreign_keys=[depreciation_account_id])
    accumulated_dep_account = db.relationship('Account', foreign_keys=[accumulated_dep_account_id])

    schedules = db.relationship('DepreciationSchedule', backref='asset', lazy=True, cascade="all, delete-orphan",
                                order_by='DepreciationSchedule.schedule_date')

    @property
    def depreciable_amount(self):
        return float(self.purchase_price) - float(self.salvage_value)

    @property
    def total_depreciated(self):
        return sum(float(s.depreciation_amount) for s in self.schedules if s.journal_entry_id)

    @property
    def book_value(self):
        return float(self.purchase_price) - self.total_depreciated

    def __repr__(self):
        return f'<FixedAsset {self.asset_code} - {self.name}>'

class DepreciationSchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('fixed_asset.id'), nullable=False)
    schedule_date = db.Column(db.Date, nullable=False)
    depreciation_amount = db.Column(db.Numeric(14, 2), nullable=False)
    accumulated_depreciation = db.Column(db.Numeric(14, 2), default=0.0)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey('journal_entry.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=_now)

    journal_entry = db.relationship('JournalEntry')

    @property
    def is_posted(self):
        return self.journal_entry_id is not None

    def __repr__(self):
        return f'<DepSchedule {self.schedule_date} - {self.depreciation_amount}>'
