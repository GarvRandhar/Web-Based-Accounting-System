from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.models import Account, BankStatement, BankTransaction, JournalItem, JournalEntry, db
from app.services.reconciliation import ReconciliationService
from datetime import datetime
import csv
import io

reconciliation_bp = Blueprint('reconciliation', __name__, url_prefix='/reconciliation')

@reconciliation_bp.route('/')
@login_required
def index():
    statements = BankStatement.query.order_by(BankStatement.start_date.desc()).all()
    accounts = Account.query.filter_by(type='Asset').all() # Ideally filter for Bank/Cash accounts
    return render_template('reconciliation/index.html', statements=statements, accounts=accounts)

@reconciliation_bp.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'file' not in request.files:
        flash('No file part', 'error')
        return redirect(url_for('reconciliation.index'))
    
    file = request.files['file']
    account_id = request.form.get('account_id')
    
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(url_for('reconciliation.index'))

    if file:
        # Parse CSV: Date, Description, Amount
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.DictReader(stream)
        
        transactions = []
        dates = []
        
        for row in csv_input:
            # Basic validation
            try:
                date_str = row.get('Date')
                date = datetime.strptime(date_str, '%Y-%m-%d').date()
                amount = float(row.get('Amount'))
                description = row.get('Description')
                
                transactions.append({
                    'date': date,
                    'description': description,
                    'amount': amount
                })
                dates.append(date)
            except Exception as e:
                flash(f"Error parsing row: {row}. Error: {e}", 'error')
                return redirect(url_for('reconciliation.index'))

        if not transactions:
            flash("No valid transactions found in CSV", 'error')
            return redirect(url_for('reconciliation.index'))

        start_date = min(dates)
        end_date = max(dates)
        
        # Calculate balances (placeholder logic, usually user inputs this)
        start_bal = 0.0
        end_bal = sum(t['amount'] for t in transactions)
        
        stmt = ReconciliationService.create_statement(
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
            start_bal=start_bal,
            end_bal=end_bal,
            transactions_data=transactions
        )
        
        flash(f"Uploaded statement with {len(transactions)} transactions.", 'success')
        return redirect(url_for('reconciliation.view', id=stmt.id))

@reconciliation_bp.route('/<int:id>')
@login_required
def view(id):
    stmt = BankStatement.query.get_or_404(id)
    bank_txs = BankTransaction.query.filter_by(statement_id=id).all()
    
    # Get unreconciled ledger items for this account
    # Left Join with BankTransaction to find items that are NOT matched
    ledger_items = JournalItem.query.outerjoin(BankTransaction, BankTransaction.matched_journal_item_id == JournalItem.id)\
        .filter(
            JournalItem.account_id == stmt.account_id,
            BankTransaction.id == None
        ).all()

    return render_template('reconciliation/view.html', stmt=stmt, bank_txs=bank_txs, ledger_items=ledger_items)

@reconciliation_bp.route('/match', methods=['POST'])
@login_required
def match():
    bank_tx_id = request.form.get('bank_tx_id')
    journal_item_id = request.form.get('journal_item_id')
    
    try:
        ReconciliationService.match_transaction(bank_tx_id, journal_item_id)
        flash("Matched successfully", 'success')
    except Exception as e:
        flash(str(e), 'error')
        
    return redirect(request.referrer)
