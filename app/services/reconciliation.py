from app.models import BankStatement, BankTransaction, JournalItem, Account, JournalEntry, db
from app.services.audit import AuditService

class ReconciliationService:
    @staticmethod
    def create_statement(account_id, start_date, end_date, start_bal, end_bal, transactions_data):
        """
        Creates a new bank statement and its transactions.
        transactions_data: list of dicts {'date': 'YYYY-MM-DD', 'description': str, 'amount': float}
        """
        stmt = BankStatement(
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
            starting_balance=start_bal,
            ending_balance=end_bal
        )
        db.session.add(stmt)
        db.session.flush()

        for t_data in transactions_data:
            bt = BankTransaction(
                statement_id=stmt.id,
                date=t_data['date'],
                description=t_data['description'],
                amount=t_data['amount']
            )
            db.session.add(bt)
        
        db.session.commit()
        
        AuditService.log('CREATE', 'BankStatement', stmt.id, f"Uploaded statement for Account #{account_id}")
        return stmt

    @staticmethod
    def get_unreconciled_items(account_id, start_date, end_date):
        """
        Get un-matched ledger items for the account within date range.
        We only match JournalItems that are NOT already matched.
        """
        return JournalItem.query.join(JournalEntry).filter(
            JournalItem.account_id == account_id,
            JournalEntry.date >= start_date,
            JournalEntry.date <= end_date,
        ).outerjoin(BankTransaction, BankTransaction.matched_journal_item_id == JournalItem.id)\
         .filter(BankTransaction.id == None)\
         .all()

    @staticmethod
    def match_transaction(bank_tx_id, journal_item_id):
        """Link a bank transaction to a journal item"""
        bt = BankTransaction.query.get(bank_tx_id)
        ji = JournalItem.query.get(journal_item_id)
        
        if not bt or not ji:
            raise ValueError("Invalid ID")
            
        # Validate amounts match (allowing for small difference if we wanted, but strict for now)
        # Bank amount: +Deposit, -Withdrawal
        # Ledger: Debit (Increase Asset), Credit (Decrease Asset)
        # So for Asset account:
        # Debit = Positive Bank Amount
        # Credit = Negative Bank Amount (as positive number)
        
        ledger_amount = ji.debit - ji.credit
        # Bank amount is signed.
        
        if abs(bt.amount - ledger_amount) > 0.01:
             raise ValueError(f"Amount mismatch: Bank {bt.amount} != Ledger {ledger_amount}")

        bt.matched_journal_item_id = ji.id
        db.session.commit()
        return True
