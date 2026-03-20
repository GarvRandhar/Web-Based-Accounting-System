from app.models import Account, JournalItem, JournalEntry, db
from sqlalchemy import func
from datetime import datetime

class ReportingService:
    @staticmethod
    def get_balance_sheet(as_of_date):
        """
        Generates Balance Sheet data as of a specific date.
        Assets = Liabilities + Equity
        Equity includes current year Net Income (Retained Earnings).
        """
        def get_group_balance(acc_type):
            # Sum (Dr - Cr) for Assets, (Cr - Dr) for others
            # Filter by date <= as_of_date
            
            accounts = Account.query.filter_by(type=acc_type).all()
            total = 0
            details = []
            
            for acc in accounts:
                # Sum items up to date
                debits = db.session.query(func.sum(JournalItem.debit))\
                    .join(JournalItem.entry)\
                    .filter(JournalItem.account_id == acc.id)\
                    .filter(JournalItem.entry.has(JournalItem.entry.property.mapper.class_.date <= as_of_date))\
                    .scalar() or 0

                credits = db.session.query(func.sum(JournalItem.credit))\
                    .join(JournalItem.entry)\
                    .filter(JournalItem.account_id == acc.id)\
                    .filter(JournalItem.entry.has(JournalItem.entry.property.mapper.class_.date <= as_of_date))\
                    .scalar() or 0

                if acc_type == 'Asset':
                    bal = debits - credits
                else:
                    bal = credits - debits
                
                if bal != 0:
                    details.append({'code': acc.code, 'name': acc.name, 'balance': bal})
                    total += bal
            
            return {'total': total, 'accounts': details}

        assets = get_group_balance('Asset')
        liabilities = get_group_balance('Liability')
        equity = get_group_balance('Equity')
        
        # Calculate Retained Earnings (Net Income over all time up to date)
        # Revenue - Expenses
        revenue_total = 0
        expense_total = 0
        
        # We need to query ALL revenue/expense accounts up to this date to get correct Retained Earnings
        # This is simplified. Real systems close books at year end.
        # We'll just sum all Rev/Exp.
        
        rev_accounts = Account.query.filter_by(type='Revenue').all()
        for acc in rev_accounts:
            credits = db.session.query(func.sum(JournalItem.credit)).join(JournalItem.entry).filter(JournalItem.account_id==acc.id, JournalItem.entry.has(JournalItem.entry.property.mapper.class_.date <= as_of_date)).scalar() or 0
            debits = db.session.query(func.sum(JournalItem.debit)).join(JournalItem.entry).filter(JournalItem.account_id==acc.id, JournalItem.entry.has(JournalItem.entry.property.mapper.class_.date <= as_of_date)).scalar() or 0
            revenue_total += (credits - debits)

        exp_accounts = Account.query.filter_by(type='Expense').all()
        for acc in exp_accounts:
            debits = db.session.query(func.sum(JournalItem.debit)).join(JournalItem.entry).filter(JournalItem.account_id==acc.id, JournalItem.entry.has(JournalItem.entry.property.mapper.class_.date <= as_of_date)).scalar() or 0
            credits = db.session.query(func.sum(JournalItem.credit)).join(JournalItem.entry).filter(JournalItem.account_id==acc.id, JournalItem.entry.has(JournalItem.entry.property.mapper.class_.date <= as_of_date)).scalar() or 0
            expense_total += (debits - credits)

        net_income = revenue_total - expense_total
        
        # Add Net Income to Equity section as "Retained Earnings (Calculated)"
        if net_income != 0:
            equity['accounts'].append({'code': '9999', 'name': 'Retained Earnings (YTD)', 'balance': net_income})
            equity['total'] += net_income

        return {
            'assets': assets,
            'liabilities': liabilities,
            'equity': equity,
            'date': as_of_date
        }

    @staticmethod
    def get_profit_loss(start_date, end_date):
        """
        Generates P&L for a period.
        """
        def get_group_balance(acc_type):
            accounts = Account.query.filter_by(type=acc_type).all()
            total = 0
            details = []
            
            for acc in accounts:
                # Filter by date range
                debits = db.session.query(func.sum(JournalItem.debit))\
                    .join(JournalItem.entry)\
                    .filter(JournalItem.account_id == acc.id)\
                    .filter(JournalItem.entry.has(JournalItem.entry.property.mapper.class_.date >= start_date))\
                    .filter(JournalItem.entry.has(JournalItem.entry.property.mapper.class_.date <= end_date))\
                    .scalar() or 0
                    
                credits = db.session.query(func.sum(JournalItem.credit))\
                    .join(JournalItem.entry)\
                    .filter(JournalItem.account_id == acc.id)\
                    .filter(JournalItem.entry.has(JournalItem.entry.property.mapper.class_.date >= start_date))\
                    .filter(JournalItem.entry.has(JournalItem.entry.property.mapper.class_.date <= end_date))\
                    .scalar() or 0
                
                if acc_type == 'Revenue':
                    bal = credits - debits
                else: # Expense
                    bal = debits - credits
                
                if bal != 0:
                    details.append({'code': acc.code, 'name': acc.name, 'balance': bal})
                    total += bal
            
            return {'total': total, 'accounts': details}

        revenue = get_group_balance('Revenue')
        expenses = get_group_balance('Expense')
        
        net_income = revenue['total'] - expenses['total']
        
        return {
            'revenue': revenue,
            'expenses': expenses,
            'net_income': net_income,
            'start_date': start_date,
            'end_date': end_date
        }

    @staticmethod
    def get_trial_balance(as_of_date):
        """
        Generates Trial Balance: List of all accounts with their debit/credit balance.
        """
        # Query all accounts with their journal items up to the date
        accounts = Account.query.order_by(Account.code).all()
        data = []
        total_debit = 0
        total_credit = 0

        for acc in accounts:
            # Sum debits and credits
            debits = db.session.query(func.sum(JournalItem.debit))\
                .join(JournalEntry)\
                .filter(JournalItem.account_id == acc.id)\
                .filter(JournalEntry.date <= as_of_date).scalar() or 0
            
            credits = db.session.query(func.sum(JournalItem.credit))\
                .join(JournalEntry)\
                .filter(JournalItem.account_id == acc.id)\
                .filter(JournalEntry.date <= as_of_date).scalar() or 0
            
            # Net balance
            net = debits - credits
            
            if abs(net) < 0.01:
                continue # Skip zero balance accounts
            
            row = {'code': acc.code, 'name': acc.name, 'debit': 0, 'credit': 0}
            
            # Formatting for Trial Balance
            # Asset/Expense: Dr balance
            # Liability/Equity/Revenue: Cr balance
            if net > 0:
                row['debit'] = net
                total_debit += net
            else:
                row['credit'] = abs(net)
                total_credit += abs(net)
            
            data.append(row)

        return {
            'accounts': data,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'date': as_of_date
        }

    @staticmethod
    def get_cash_flow(start_date, end_date):
        """
        Generates Statement of Cash Flows (Simplified Indirect Method)
        """
        # 1. Operating Activities
        # Net Income
        pl = ReportingService.get_profit_loss(start_date, end_date)
        net_income = pl['net_income']
        
        # Adjustments would go here (Depreciation etc.)
        
        # Changes in Working Capital (Current Assets & Current Liabilities)
        # Increase in AR (Asset) -> Negative Cash Flow
        # Increase in AP (Liability) -> Positive Cash Flow
        
        # For this MVP, we will stick to a simpler "Direct-ish" view based on Bank Account movements
        # Or just return Net Income as Operating Cash Flow for now since we lack detailed classification
        
        # Let's try a diff approach: Analysis of Cash GL Accounts
        cash_accounts = Account.query.filter(Account.name.in_(['Cash', 'Bank'])).all()
        cash_ids = [acc.id for acc in cash_accounts]
        
        # Inflows (Debits to Cash)
        inflows = db.session.query(func.sum(JournalItem.debit))\
            .join(JournalEntry)\
            .filter(JournalItem.account_id.in_(cash_ids))\
            .filter(JournalEntry.date >= start_date)\
            .filter(JournalEntry.date <= end_date).scalar() or 0
            
        # Outflows (Credits to Cash)
        outflows = db.session.query(func.sum(JournalItem.credit))\
            .join(JournalEntry)\
            .filter(JournalItem.account_id.in_(cash_ids))\
            .filter(JournalEntry.date >= start_date)\
            .filter(JournalEntry.date <= end_date).scalar() or 0
            
        net_change = inflows - outflows
        
        # Get start balance
        start_bal_debit = db.session.query(func.sum(JournalItem.debit))\
            .join(JournalEntry)\
            .filter(JournalItem.account_id.in_(cash_ids))\
            .filter(JournalEntry.date < start_date).scalar() or 0
            
        start_bal_credit = db.session.query(func.sum(JournalItem.credit))\
            .join(JournalEntry)\
            .filter(JournalItem.account_id.in_(cash_ids))\
            .filter(JournalEntry.date < start_date).scalar() or 0
            
        starting_cash = start_bal_debit - start_bal_credit
        ending_cash = starting_cash + net_change
        
        return {
            'operating_activities': net_change, # Simplified: All cash entry is operating for now
            'net_change': net_change,
            'starting_balance': starting_cash,
            'ending_balance': ending_cash,
            'start_date': start_date,
            'end_date': end_date
        }

