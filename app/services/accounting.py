from app.extensions import db
from app.models import Account, JournalEntry, JournalItem, Tax
from app.services.audit import AuditService
from sqlalchemy import func, text
from datetime import datetime, timedelta

class AccountingService:
    @staticmethod
    def create_journal_entry(date, description, items, reference=None):
        """
        Creates a new Journal Entry with multiple items.
        items: list of dicts {'account_id': int, 'debit': float, 'credit': float}
        """
        # Validate balance
        total_debit = sum(item.get('debit', 0) for item in items)
        total_credit = sum(item.get('credit', 0) for item in items)
        
        if abs(total_debit - total_credit) > 0.01:
            raise ValueError(f"Transaction is not balanced: Debits {total_debit} != Credits {total_credit}")

        entry = JournalEntry(
            date=date,
            description=description,
            reference=reference,
            posted=True # Auto-post for now
        )
        db.session.add(entry)
        db.session.flush() # Get ID

        for item in items:
            j_item = JournalItem(
                journal_entry_id=entry.id,
                account_id=item['account_id'],
                debit=item.get('debit', 0),
                credit=item.get('credit', 0)
            )
            db.session.add(j_item)
        
        db.session.commit()
        
        AuditService.log(
            action='CREATE',
            model='JournalEntry',
            model_id=entry.id,
            details=f"Created entry: {description} ({date})"
        )

        return entry

    @staticmethod
    def get_summary_metrics():
        """Calculates totals for Assets, Liabilities, Equity, and Income."""
        
        def get_type_balance(acc_type):
            # For Asset/Expense: Dr - Cr
            # For Liability/Equity/Revenue: Cr - Dr
            # But here we just sum Dr and Cr and calculate based on type.
            
            # Simple query: Join Account and JournalItem
            # This is not optimized but works for small app.
            
            accounts = Account.query.filter_by(type=acc_type).all()
            total = 0
            for acc in accounts:
                debits = db.session.query(func.sum(JournalItem.debit)).filter_by(account_id=acc.id).scalar() or 0
                credits = db.session.query(func.sum(JournalItem.credit)).filter_by(account_id=acc.id).scalar() or 0
                
                if acc_type in ['Asset', 'Expense']:
                    total += (debits - credits)
                else:
                    total += (credits - debits)
            return total

        assets = get_type_balance('Asset')
        liabilities = get_type_balance('Liability')
        equity = get_type_balance('Equity')
        revenue = get_type_balance('Revenue')
        expense = get_type_balance('Expense')
        
        net_income = revenue - expense
        
        # Real Equity = Stored Equity + Net Income (Retained Earnings)
        total_equity = equity + net_income
        
        return {
            'assets': assets,
            'liabilities': liabilities,
            'equity': total_equity,
            'net_income': net_income
        }

    @staticmethod
    def seed_chart_of_accounts():
        """Creates a standard chart of accounts if empty."""
        if Account.query.first():
            return

        # Simplified Standard COA
        accounts = [
            # Assets (1000-1999)
            {'code': '1000', 'name': 'Assets', 'type': 'Asset', 'parent': None},
            {'code': '1010', 'name': 'Cash', 'type': 'Asset', 'parent': '1000'},
            {'code': '1020', 'name': 'Bank', 'type': 'Asset', 'parent': '1000'},
            {'code': '1200', 'name': 'Accounts Receivable', 'type': 'Asset', 'parent': '1000'},
            {'code': '1500', 'name': 'Inventory', 'type': 'Asset', 'parent': '1000'},
            
            # Liabilities (2000-2999)
            {'code': '2000', 'name': 'Liabilities', 'type': 'Liability', 'parent': None},
            {'code': '2010', 'name': 'Accounts Payable', 'type': 'Liability', 'parent': '2000'},
            {'code': '2200', 'name': 'GST Payable', 'type': 'Liability', 'parent': '2000'},
            
            # Equity (3000-3999)
            {'code': '3000', 'name': 'Equity', 'type': 'Equity', 'parent': None},
            {'code': '3010', 'name': 'Owner Capital', 'type': 'Equity', 'parent': '3000'},
            {'code': '3020', 'name': 'Retained Earnings', 'type': 'Equity', 'parent': '3000'},
            
            # Revenue (4000-4999)
            {'code': '4000', 'name': 'Revenue', 'type': 'Revenue', 'parent': None},
            {'code': '4010', 'name': 'Sales', 'type': 'Revenue', 'parent': '4000'},
            {'code': '4020', 'name': 'Service Income', 'type': 'Revenue', 'parent': '4000'},
            
            # Expenses (5000-5999)
            {'code': '5000', 'name': 'Expenses', 'type': 'Expense', 'parent': None},
            {'code': '5010', 'name': 'Rent Expense', 'type': 'Expense', 'parent': '5000'},
            {'code': '5020', 'name': 'Utilities', 'type': 'Expense', 'parent': '5000'},
            {'code': '5030', 'name': 'Salaries', 'type': 'Expense', 'parent': '5000'},
             {'code': '5040', 'name': 'Office Supplies', 'type': 'Expense', 'parent': '5000'},
        ]

        parent_map = {} # Code -> ID
        
        # Pass 1: Roots
        for acc_data in accounts:
            if not acc_data['parent']:
                acc = Account(
                    code=acc_data['code'],
                    name=acc_data['name'],
                    type=acc_data['type']
                )
                db.session.add(acc)
                db.session.flush()
                parent_map[acc_data['code']] = acc.id
        
        # Pass 2: Children
        for acc_data in accounts:
             if acc_data['parent']:
                 parent_id = parent_map.get(acc_data['parent'])
                 if parent_id:
                     acc = Account(
                        code=acc_data['code'],
                        name=acc_data['name'],
                        type=acc_data['type'],
                        parent_id=parent_id
                    )
                     db.session.add(acc)
                     db.session.flush() # Ensure ID is generated
                     parent_map[acc_data['code']] = acc.id
        
        db.session.commit()

    @staticmethod
    def get_dashboard_charts_data():
        """
        Returns data for dashboard charts:
        1. Monthly Revenue vs Expenses (Last 6 months)
        2. Expense Breakdown (by category/account)
        """
        end_date = datetime.today()
        start_date = end_date - timedelta(days=180) # Approx 6 months
        
        # 1. Monthly Revenue vs Expenses
        monthly_data = {} # 'YYYY-MM': {'revenue': 0, 'expense': 0}
        
        # Initialize last 6 months
        curr = start_date
        while curr <= end_date:
            key = curr.strftime('%Y-%m')
            monthly_data[key] = {'revenue': 0, 'expense': 0}
            # Increment month
            if curr.month == 12:
                curr = curr.replace(year=curr.year+1, month=1)
            else:
                curr = curr.replace(month=curr.month+1)
        
        # Query items
        # Join JournalEntry to filter by date
        # Join Account to filter by type
        items = db.session.query(
            JournalEntry.date,
            Account.type,
            JournalItem.debit,
            JournalItem.credit
        ).join(JournalEntry).join(Account)\
         .filter(JournalEntry.date >= start_date)\
         .filter(Account.type.in_(['Revenue', 'Expense']))\
         .all()
         
        for date, type, debit, credit in items:
            key = date.strftime('%Y-%m')
            if key in monthly_data:
                # For Revenue: Credit is increase. For Expense: Debit is increase.
                amount = (credit - debit) if type == 'Revenue' else (debit - credit)
                if type == 'Revenue':
                    monthly_data[key]['revenue'] += amount
                else:
                    monthly_data[key]['expense'] += amount

        # Fill missing keys if any (from query result) to ensure sorted labels
        labels = sorted(monthly_data.keys())
        revenue_series = [monthly_data[k]['revenue'] for k in labels]
        expense_series = [monthly_data[k]['expense'] for k in labels]

        # 2. Expense Breakdown (Top 5 expenses)
        expense_breakdown = db.session.query(
            Account.name,
            func.sum(JournalItem.debit - JournalItem.credit).label('total')
        ).join(JournalEntry).join(Account)\
         .filter(Account.type == 'Expense')\
         .group_by(Account.name)\
         .order_by(text('total DESC'))\
         .limit(5)\
         .all()
         
        expense_labels = [r[0] for r in expense_breakdown]
        expense_values = [r[1] for r in expense_breakdown]

        return {
            'monthly': {
                'labels': labels,
                'datasets': [
                    {'label': 'Revenue', 'data': revenue_series, 'borderColor': '#10b981', 'backgroundColor': 'rgba(16, 185, 129, 0.1)'},
                    {'label': 'Expenses', 'data': expense_series, 'borderColor': '#ef4444', 'backgroundColor': 'rgba(239, 68, 68, 0.1)'}
                ]
            },
            'expenses': {
                'labels': expense_labels,
                'datasets': [{
                    'data': expense_values,
                    'backgroundColor': ['#ef4444', '#f59e0b', '#3b82f6', '#8b5cf6', '#64748b']
                }]
            }
        }

    @staticmethod
    def void_journal_entry(entry_id):
        """Voids a posted journal entry by creating a reversing entry."""
        entry = JournalEntry.query.get(entry_id)
        if not entry:
            raise ValueError("Journal entry not found.")
        if entry.voided:
            raise ValueError("Journal entry is already voided.")
        
        # Create reversing entry (swap debits and credits)
        reversing_items = []
        for item in entry.items:
            reversing_items.append({
                'account_id': item.account_id,
                'debit': float(item.credit),
                'credit': float(item.debit)
            })
        
        reversing_entry = JournalEntry(
            date=datetime.utcnow(),
            description=f"VOID: {entry.description}",
            reference=f"VOID-{entry.id}",
            posted=True,
            voided=False
        )
        db.session.add(reversing_entry)
        db.session.flush()
        
        for item in reversing_items:
            j_item = JournalItem(
                journal_entry_id=reversing_entry.id,
                account_id=item['account_id'],
                debit=item['debit'],
                credit=item['credit']
            )
            db.session.add(j_item)
        
        # Mark original as voided
        entry.voided = True
        db.session.commit()
        
        AuditService.log(
            action='VOID',
            model='JournalEntry',
            model_id=entry.id,
            details=f"Voided entry #{entry.id}, reversing entry #{reversing_entry.id}"
        )
        
        return reversing_entry

    @staticmethod
    def close_fiscal_year(year_end_date):
        """
        Closes the fiscal year by zeroing Revenue and Expense accounts
        into Retained Earnings via a closing journal entry.
        """
        retained_earnings = Account.query.filter_by(code='3020').first()
        if not retained_earnings:
            raise ValueError("Retained Earnings account (3020) not found. Cannot close fiscal year.")
        
        closing_items = []
        net_income = 0
        
        # Zero out Revenue accounts (normal credit balance → debit to close)
        revenue_accounts = Account.query.filter_by(type='Revenue').all()
        for acc in revenue_accounts:
            debits = db.session.query(func.sum(JournalItem.debit)).filter_by(account_id=acc.id).scalar() or 0
            credits = db.session.query(func.sum(JournalItem.credit)).filter_by(account_id=acc.id).scalar() or 0
            balance = float(credits) - float(debits)
            if abs(balance) > 0.01:
                closing_items.append({
                    'account_id': acc.id,
                    'debit': balance if balance > 0 else 0,
                    'credit': abs(balance) if balance < 0 else 0
                })
                net_income += balance
        
        # Zero out Expense accounts (normal debit balance → credit to close)
        expense_accounts = Account.query.filter_by(type='Expense').all()
        for acc in expense_accounts:
            debits = db.session.query(func.sum(JournalItem.debit)).filter_by(account_id=acc.id).scalar() or 0
            credits = db.session.query(func.sum(JournalItem.credit)).filter_by(account_id=acc.id).scalar() or 0
            balance = float(debits) - float(credits)
            if abs(balance) > 0.01:
                closing_items.append({
                    'account_id': acc.id,
                    'debit': 0,
                    'credit': balance if balance > 0 else 0
                })
                net_income -= balance
        
        if not closing_items:
            raise ValueError("No revenue or expense balances to close.")
        
        # Net income → Retained Earnings
        # If net_income > 0 (profit): Credit Retained Earnings
        # If net_income < 0 (loss): Debit Retained Earnings
        closing_items.append({
            'account_id': retained_earnings.id,
            'debit': abs(net_income) if net_income < 0 else 0,
            'credit': net_income if net_income > 0 else 0
        })
        
        entry = JournalEntry(
            date=year_end_date,
            description=f"Fiscal Year Closing - {year_end_date.strftime('%Y-%m-%d')}",
            reference="FY-CLOSE",
            posted=True
        )
        db.session.add(entry)
        db.session.flush()
        
        for item in closing_items:
            j_item = JournalItem(
                journal_entry_id=entry.id,
                account_id=item['account_id'],
                debit=item['debit'],
                credit=item['credit']
            )
            db.session.add(j_item)
        
        db.session.commit()
        
        AuditService.log(
            action='CREATE',
            model='JournalEntry',
            model_id=entry.id,
            details=f"Fiscal year closing entry. Net income: {net_income:.2f}"
        )
        
        return entry

