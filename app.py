import csv
from collections import defaultdict
from datetime import datetime, timedelta
from io import StringIO
import pdfkit
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
from functools import wraps
from models import db, User, Account, Transaction

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.secret_key = 'bacASadbfjsLnswQWhwvqhebfqkfbqhe' 
app.permanent_session_lifetime = timedelta(minutes=5)
db.init_app(app)

with app.app_context():
    db.create_all()

@app.before_request
def manage_session():
    session.permanent = True
    session.modified = True

    # Manual timeout check
    timeout_seconds = 300  # 1 minute for testing, set higher in production
    login_time = session.get('login_time')

    if login_time:
        now = datetime.utcnow().timestamp()
        if now - login_time > timeout_seconds:
            session.clear()
            flash('Session expired due to inactivity.', 'warning')
            return redirect(url_for('login'))

# Template context processor to add current date to all templates
@app.context_processor
def inject_now():
    return {'now': datetime.now()}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/register', methods=['POST'])
def register():
    username = request.form['username']
    email = request.form['email']
    password = request.form['password']
    confirm_password = request.form['confirm_password']

    if password != confirm_password:
        flash("Passwords do not match.", "error")
        # Use request.form to refill username and email in the form
        return render_template('auth.html', form_type='register', request=request)

    if User.query.filter_by(username=username).first():
        flash('Username already exists', 'error')
        return render_template('auth.html', form_type='register', request=request)

    if User.query.filter_by(email=email).first():
        flash('An account with this email already exists.', 'error')
        return render_template('auth.html', form_type='register', request=request)

    new_user = User(username=username, email=email)
    new_user.set_password(password)
    db.session.add(new_user)
    db.session.commit()

    flash('Registration successful. Please log in.', 'success')
    return redirect(url_for('auth'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('dashboard'))  # Already logged in

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session['username'] = user.username
            session.permanent = True
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'error')

    return render_template('auth.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/')
def home():
    return redirect(url_for('auth'))

@app.route('/auth')
def auth():
    return render_template('auth.html')


@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.filter_by(username=session['username']).first()
    accounts = Account.query.filter_by(user_id=user.id).all()
    account_ids = [a.id for a in accounts]

    transactions = Transaction.query.filter(Transaction.account_id.in_(account_ids)).all()

    # ✅ Only include Asset and Income accounts in total_balance
    total_balance = sum(acc.balance for acc in accounts if acc.type in ['Asset', 'Income'])

    total_income = sum(txn.amount for txn in transactions if txn.transaction_type == 'Income')
    total_expenses = sum(txn.amount for txn in transactions if txn.transaction_type == 'Expense')

    recent_transactions = sorted(transactions, key=lambda x: x.date, reverse=True)[:5]

    # Current month summary
    now = datetime.now()
    monthly_income = monthly_expenses = 0
    for txn in transactions:
        if txn.date.month == now.month and txn.date.year == now.year:
            if txn.transaction_type == 'Income':
                monthly_income += txn.amount
            elif txn.transaction_type == 'Expense':
                monthly_expenses += txn.amount

    # Monthly chart data (only Income & Expense types)
    monthly_data = defaultdict(lambda: {'Income': 0, 'Expense': 0})
    for txn in transactions:
        if txn.transaction_type in ['Income', 'Expense']:
            key = txn.date.strftime('%Y-%m')
            monthly_data[key][txn.transaction_type] += txn.amount

    sorted_months = sorted(monthly_data.keys())
    income_chart = [monthly_data[m]['Income'] for m in sorted_months]
    expense_chart = [monthly_data[m]['Expense'] for m in sorted_months]

    # Balance distribution (all accounts)
    balance_labels = [acc.type for acc in accounts]
    balance_values = [acc.balance for acc in accounts]

    # GST Summary
    income_gst = sum(t.gst_amount for t in transactions if t.transaction_type == 'Income')
    expense_gst = sum(t.gst_amount for t in transactions if t.transaction_type == 'Expense')
    gst_summary = {
        'output_gst': income_gst,
        'input_gst': expense_gst,
        'net_gst': income_gst - expense_gst
    }

    return render_template('dashboard.html',
        username=user.username,
        accounts=accounts,
        total_balance=total_balance,
        total_income=total_income,
        total_expenses=total_expenses,
        monthly_income=monthly_income,
        monthly_expenses=monthly_expenses,
        recent_transactions=recent_transactions,
        income_chart=income_chart,
        expense_chart=expense_chart,
        months=sorted_months,
        balance_labels=balance_labels,
        balance_values=balance_values,
        gst_summary=gst_summary
    )


@app.route('/accounts')
@login_required
def accounts():
    user = User.query.filter_by(username=session['username']).first()
    accounts = Account.query.filter_by(user_id=user.id).all()
    return render_template('accounts.html', accounts=accounts)


@app.route('/transactions')
@login_required
def transactions():
    user = User.query.filter_by(username=session['username']).first()
    user_accounts = Account.query.filter_by(user_id=user.id).all()
    account_ids = [acc.id for acc in user_accounts]

    # Correct query with proper parentheses and method chaining
    transactions = Transaction.query.filter(
        Transaction.account_id.in_(account_ids)
    ).order_by(
        Transaction.date.desc()
    ).all()

    formatted_transactions = []
    for transaction in transactions:
        account = Account.query.get(transaction.account_id)
        formatted_transactions.append({
            'id': transaction.id,
            'date': transaction.date.strftime('%Y-%m-%d'),
            'account': account.name if account else 'Unknown',
            'type': transaction.transaction_type,  # Use actual transaction type
            'description': transaction.description,
            'amount': transaction.amount,
            'transaction_type': transaction.transaction_type
        })

    return render_template('transactions.html',
                           transactions=formatted_transactions,
                           accounts=user_accounts)

@app.route('/add_transaction', methods=['POST'])
@login_required
def add_transaction():
    account_id = int(request.form['account_id'])
    amount = float(request.form['amount'])
    description = request.form['description']
    date_str = request.form['date']
    transaction_type = request.form['transaction_type']

    # Parse date
    if date_str:
        date = datetime.strptime(date_str, '%Y-%m-%d')
    else:
        date = datetime.now()

    # GST only for Income & Expense
    if transaction_type == 'Income':
        gst_rate = 18.0
    elif transaction_type == 'Expense':
        gst_rate = 5.0
    else:
        gst_rate = 0.0
    gst_amount = amount * gst_rate / 100

    # Create new transaction
    new_transaction = Transaction(
        account_id=account_id,
        amount=amount,
        description=description,
        date=date,
        transaction_type=transaction_type,
        gst_rate=gst_rate,
        gst_amount=gst_amount
    )

    # Update account balance for all types
    account = Account.query.get(account_id)
    if transaction_type in ['Income', 'Asset Sale', 'Loan Taken']:
        account.balance += amount
    elif transaction_type in ['Expense', 'Asset Purchase', 'Loan Repayment']:
        account.balance -= amount

    db.session.add(new_transaction)
    db.session.commit()

    flash('Transaction added successfully!', 'success')
    return redirect(url_for('transactions'))
@app.route('/delete_transaction/<int:transaction_id>', methods=['POST'])
@login_required
def delete_transaction(transaction_id):
    transaction = Transaction.query.get_or_404(transaction_id)
    account = Account.query.get(transaction.account_id)

    # Reverse the transaction's effect on account balance
    if transaction.transaction_type in ['Income', 'Asset Sale', 'Loan Taken']:
        account.balance -= transaction.amount
    elif transaction.transaction_type in ['Expense', 'Asset Purchase', 'Loan Repayment']:
        account.balance += transaction.amount

    db.session.delete(transaction)
    db.session.commit()

    flash('Transaction deleted successfully.', 'info')
    return redirect(url_for('transactions'))


@app.route('/reports', methods=['GET', 'POST'])
@login_required
def reports():
    user = User.query.filter_by(username=session['username']).first()
    user_accounts = Account.query.filter_by(user_id=user.id).all()
    account_ids = [a.id for a in user_accounts]

    # Default: full year
    current_year = datetime.now().year
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')

    if start_date and end_date:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
    else:
        start = datetime(current_year, 1, 1)
        end = datetime(current_year, 12, 31)

    # Balance Sheet
    balance_sheet = {acc.name: acc.balance for acc in user_accounts}

    # Profit & Loss (only Income and Expense)
    report = {"Income": 0.0, "Expense": 0.0}
    rows = db.session.query(Transaction.transaction_type, db.func.sum(Transaction.amount)) \
        .filter(Transaction.account_id.in_(account_ids)) \
        .filter(Transaction.transaction_type.in_(['Income', 'Expense'])) \
        .filter(Transaction.date.between(start, end)) \
        .group_by(Transaction.transaction_type).all()

    for row in rows:
        report[row[0]] = float(row[1])

    # ✅ GST Summary
    gst_rows = db.session.query(Transaction.transaction_type, db.func.sum(Transaction.gst_amount)) \
        .filter(Transaction.account_id.in_(account_ids)) \
        .filter(Transaction.transaction_type.in_(['Income', 'Expense'])) \
        .filter(Transaction.date.between(start, end)) \
        .group_by(Transaction.transaction_type).all()

    gst_summary = {'output_gst': 0.0, 'input_gst': 0.0}
    for row in gst_rows:
        if row[0] == 'Income':
            gst_summary['output_gst'] = float(row[1])
        elif row[0] == 'Expense':
            gst_summary['input_gst'] = float(row[1])
    gst_summary['net_gst'] = gst_summary['output_gst'] - gst_summary['input_gst']

    return render_template('reports.html',
                           balance=balance_sheet,
                           profit=report,
                           gst_summary=gst_summary,
                           start_date=start.strftime('%Y-%m-%d'),
                           end_date=end.strftime('%Y-%m-%d'),
                           current_year=current_year)

@app.route('/add_account', methods=['POST'])
@login_required
def add_account():
    user = User.query.filter_by(username=session['username']).first()
    name = request.form['name']
    type_ = request.form['type']
    balance = float(request.form['balance'])

    new_account = Account(name=name, type=type_, balance=balance, user_id=user.id)
    db.session.add(new_account)
    db.session.commit()
    flash('Account added successfully!', 'success')
    return redirect(url_for('accounts'))

@app.route('/delete_account/<int:account_id>', methods=['POST'])
@login_required
def delete_account(account_id):
    account = Account.query.get_or_404(account_id)
    
    # First delete all transactions related to this account
    Transaction.query.filter_by(account_id=account.id).delete()
    
    db.session.delete(account)
    db.session.commit()
    flash('Account deleted successfully.', 'info')
    return redirect(url_for('accounts'))


@app.route('/ledger', methods=['GET'])
@login_required
def ledger():
    user = User.query.filter_by(username=session['username']).first()
    user_accounts = Account.query.filter_by(user_id=user.id).all()

    selected_account_id = request.args.get('account_id', type=int)

    if selected_account_id:
        account = Account.query.filter_by(id=selected_account_id, user_id=user.id).first_or_404()
        transactions = Transaction.query.filter_by(account_id=selected_account_id).order_by(Transaction.date).all()

        running_balance = account.balance
        ledger_entries = []

        # Reverse process to calculate running balance
        for transaction in reversed(transactions):
            if transaction.transaction_type in ['Income', 'Asset Sale', 'Loan Taken']:
                running_balance -= transaction.amount
            elif transaction.transaction_type in ['Expense', 'Asset Purchase', 'Loan Repayment']:
                running_balance += transaction.amount
            else:
                continue  # Ignore unknown types for safety

            ledger_entries.insert(0, {
                'id': transaction.id,
                'date': transaction.date.strftime('%Y-%m-%d'),
                'description': transaction.description,
                'amount': transaction.amount if transaction.transaction_type in ['Income', 'Asset Sale', 'Loan Taken'] else -transaction.amount,
                'running_balance': running_balance,
                'gst_rate': transaction.gst_rate,
                'gst_amount': transaction.gst_amount
            })

        return render_template('ledger.html',
                               accounts=user_accounts,
                               selected_account=account,
                               ledger_entries=ledger_entries)
    else:
        return render_template('ledger.html', accounts=user_accounts, selected_account=None)


@app.route('/import', methods=['GET', 'POST'])
@login_required
def import_transactions():
    user = User.query.filter_by(username=session['username']).first()
    accounts = Account.query.filter_by(user_id=user.id).all()

    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(request.url)

        if file and file.filename.endswith('.csv'):
            import csv
            import io

            account_id = int(request.form['account_id'])
            transaction_type = request.form['transaction_type']
            date_format = request.form['date_format']
            account = Account.query.get_or_404(account_id)

            # Ensure account belongs to user
            if account.user_id != user.id:
                flash('Unauthorized account access', 'error')
                return redirect(url_for('import_transactions'))

            # ✅ Validate transaction type
            valid_types = [
                'Income', 'Expense',
                'Asset Purchase', 'Asset Sale',
                'Loan Taken', 'Loan Repayment'
            ]
            if transaction_type not in valid_types:
                flash('Invalid transaction type selected.', 'error')
                return redirect(url_for('import_transactions'))

            # Read and process CSV
            try:
                stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
                csv_data = csv.DictReader(stream)

                row_count = 0
                import_errors = 0

                for row in csv_data:
                    try:
                        # Validate required fields
                        if 'amount' not in row or 'date' not in row or 'description' not in row:
                            import_errors += 1
                            continue

                        date_str = row['date'].strip()
                        try:
                            date = datetime.strptime(date_str, date_format)
                        except ValueError:
                            import_errors += 1
                            continue

                        try:
                            amount = float(row['amount'].strip())
                        except ValueError:
                            import_errors += 1
                            continue

                        description = row['description'].strip()

                        # ✅ Determine GST
                        if transaction_type == 'Income':
                            gst_rate = 18.0
                        elif transaction_type == 'Expense':
                            gst_rate = 5.0
                        else:
                            gst_rate = 0.0

                        gst_amount = amount * gst_rate / 100

                        new_transaction = Transaction(
                            account_id=account_id,
                            amount=amount,
                            description=description,
                            date=date,
                            transaction_type=transaction_type,
                            gst_rate=gst_rate,
                            gst_amount=gst_amount
                        )

                        # ✅ Update balance logic for all types
                        if transaction_type in ['Income', 'Asset Sale', 'Loan Taken']:
                            account.balance += amount
                        elif transaction_type in ['Expense', 'Asset Purchase', 'Loan Repayment']:
                            account.balance -= amount

                        db.session.add(new_transaction)
                        row_count += 1

                    except Exception:
                        import_errors += 1

                db.session.commit()

                if import_errors > 0:
                    flash(f'Imported {row_count} transactions with {import_errors} errors', 'warning')
                else:
                    flash(f'Successfully imported {row_count} transactions', 'success')

                return redirect(url_for('transactions'))

            except Exception as e:
                flash(f'Error processing CSV file: {str(e)}', 'error')
                return redirect(request.url)
        else:
            flash('Invalid file format. Please upload a CSV file.', 'error')
            return redirect(request.url)

    return render_template('import.html', accounts=accounts)

@app.route('/export_report')
@login_required
def export_report():
    user = User.query.filter_by(username=session['username']).first()
    user_accounts = Account.query.filter_by(user_id=user.id).all()
    account_ids = [a.id for a in user_accounts]

    # Try to get date range from query params
    start = request.args.get('start_date')
    end = request.args.get('end_date')

    try:
        start_date = datetime.strptime(start, '%Y-%m-%d') if start else datetime(datetime.now().year, 1, 1)
        end_date = datetime.strptime(end, '%Y-%m-%d') if end else datetime(datetime.now().year, 12, 31)
    except ValueError:
        flash("Invalid date format for export.", "error")
        return redirect(url_for('reports'))

    # Query user-specific transactions in range
    transactions = Transaction.query.filter(
        Transaction.account_id.in_(account_ids),
        Transaction.date.between(start_date, end_date)
    ).order_by(Transaction.date).all()

    # Create CSV
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Date', 'Account', 'Transaction Type', 'Description', 'Amount'])

    for txn in transactions:
        writer.writerow([
            txn.date.strftime('%Y-%m-%d %H:%M'),  # <-- Proper readable datetime
            txn.account.name,
            txn.transaction_type,
            txn.description,
            f"{txn.amount:.2f}"
        ])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=report_{start or 'start'}_to_{end or 'end'}.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@app.route('/export_summary')
@login_required
def export_summary():
    user = User.query.filter_by(username=session['username']).first()
    user_accounts = Account.query.filter_by(user_id=user.id).all()
    account_ids = [a.id for a in user_accounts]

    start = request.args.get('start_date')
    end = request.args.get('end_date')

    try:
        start_date = datetime.strptime(start, '%Y-%m-%d') if start else datetime(datetime.now().year, 1, 1)
        end_date = datetime.strptime(end, '%Y-%m-%d') if end else datetime(datetime.now().year, 12, 31)
    except ValueError:
        flash("Invalid date format.", "error")
        return redirect(url_for('reports'))

    # Totals
    totals = {
        "Income": 0,
        "Expense": 0,
        "Asset Purchase": 0,
        "Asset Sale": 0,
        "Loan Taken": 0,
        "Loan Repayment": 0
    }
    rows = db.session.query(Transaction.transaction_type, db.func.sum(Transaction.amount))\
        .filter(Transaction.account_id.in_(account_ids))\
        .filter(Transaction.date.between(start_date, end_date))\
        .group_by(Transaction.transaction_type).all()

    for type_, sum_ in rows:
        totals[type_] = float(sum_)

    net = totals.get('Income', 0) - totals.get('Expense', 0)
    total_sum = totals.get('Income', 0) + totals.get('Expense', 0)

    # Account balances
    balances = [(acc.name, acc.type, acc.balance) for acc in user_accounts]
    total_balance = sum(bal for _, _, bal in balances)

    si = StringIO()
    writer = csv.writer(si)

    writer.writerow(['Summary Report'])
    writer.writerow(['Date Range', f'{start_date.date()} to {end_date.date()}'])
    writer.writerow([])

    # Main totals
    writer.writerow(['Income', f"{totals['Income']:.2f}"])
    writer.writerow(['Expense', f"{totals['Expense']:.2f}"])
    writer.writerow(['Net Profit/Loss', f"{net:.2f}"])
    writer.writerow([])

    # Percent breakdown
    writer.writerow(['Income %', f"{(totals['Income'] / total_sum * 100):.2f}%" if total_sum else '0%'])
    writer.writerow(['Expense %', f"{(totals['Expense'] / total_sum * 100):.2f}%" if total_sum else '0%'])
    writer.writerow([])

    # Other transaction types
    writer.writerow(['Other Transaction Types'])
    writer.writerow(['Type', 'Total'])
    for type_ in ['Asset Purchase', 'Asset Sale', 'Loan Taken', 'Loan Repayment']:
        writer.writerow([type_, f"{totals[type_]:.2f}"])
    writer.writerow([])

    # Account balances
    writer.writerow(['Account Name', 'Account Type', 'Current Balance', 'Balance %'])
    for name, type_, bal in balances:
        percent = f"{(bal / total_balance * 100):.2f}%" if total_balance else "0%"
        writer.writerow([name, type_, f"{bal:.2f}", percent])

    writer.writerow([])
    writer.writerow(['Note:', 'For visual breakdown, see the web dashboard.'])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename=summary_{start or 'start'}_to_{end or 'end'}.csv"
    output.headers["Content-type"] = "text/csv"
    return output


@app.route('/export_dashboard_pdf', methods=['POST'])
@login_required
def export_dashboard_pdf():
    user = User.query.filter_by(username=session['username']).first()

    # Collect data like dashboard
    accounts = Account.query.filter_by(user_id=user.id).all()
    account_ids = [a.id for a in accounts]
    transactions = Transaction.query.filter(Transaction.account_id.in_(account_ids)).all()

    total_balance = sum(acc.balance for acc in accounts)
    total_income = sum(txn.amount for txn in transactions if txn.transaction_type == 'Income')
    total_expenses = sum(txn.amount for txn in transactions if txn.transaction_type == 'Expense')

    # GST Summary Calculation
    income_gst = sum(t.gst_amount for t in transactions if t.transaction_type == 'Income')
    expense_gst = sum(t.gst_amount for t in transactions if t.transaction_type == 'Expense')
    gst_summary = {
        'output_gst': income_gst,
        'input_gst': expense_gst,
        'net_gst': income_gst - expense_gst
    }

    # Other Transaction Totals
    additional_types = ['Asset Purchase', 'Asset Sale', 'Loan Taken', 'Loan Repayment']
    additional_totals = {t: 0.0 for t in additional_types}
    for t in additional_types:
        additional_totals[t] = sum(txn.amount for txn in transactions if txn.transaction_type == t)

    # Charts from form
    balance_chart = request.form.get('balance_chart')
    profit_chart = request.form.get('profit_chart')

    rendered = render_template('dashboard_pdf.html',
        username=user.username,
        current_date=datetime.now().strftime("%d %B %Y"),
        balance_chart=balance_chart,
        profit_chart=profit_chart,
        total_balance=total_balance,
        total_income=total_income,
        total_expenses=total_expenses,
        gst_summary=gst_summary,
        additional_totals=additional_totals
    )
    options = {
        'enable-local-file-access': '',
        'load-error-handling': 'ignore',
        'load-media-error-handling': 'ignore',
        'quiet': ''
    }
    config = pdfkit.configuration(wkhtmltopdf=r'C:\\Program Files\\wkhtmltopdf\\bin\\wkhtmltopdf.exe')
    pdf = pdfkit.from_string(rendered, False, configuration=config , options  = options)
    # pdf = HTML(string=rendered).write_pdf()

    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=dashboard_summary.pdf'
    return response

@app.route('/income_statement', methods=['GET', 'POST'])
@login_required
def income_statement():
    user = User.query.filter_by(username=session['username']).first()
    accounts = Account.query.filter_by(user_id=user.id).all()
    account_ids = [a.id for a in accounts]

    # Date filter: custom or this month
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')

    if start_date and end_date:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
    else:
        today = datetime.today()
        start = today.replace(day=1)
        end = today

    transactions = Transaction.query.filter(
        Transaction.account_id.in_(account_ids),
        Transaction.date.between(start, end)
    ).all()

    income_total = sum(t.amount for t in transactions if t.transaction_type == 'Income')
    expense_total = sum(t.amount for t in transactions if t.transaction_type == 'Expense')
    net_income = income_total - expense_total

    return render_template('income_statement.html',
                           start_date=start.strftime('%Y-%m-%d'),
                           end_date=end.strftime('%Y-%m-%d'),
                           income_total=income_total,
                           expense_total=expense_total,
                           net_income=net_income)
@app.route('/balance_sheet')
@login_required
def balance_sheet():
    user = User.query.filter_by(username=session['username']).first()
    accounts = Account.query.filter_by(user_id=user.id).all()

    # Classify accounts
    assets = [acc for acc in accounts if acc.type.lower() == 'asset']
    liabilities = [acc for acc in accounts if acc.type.lower() == 'liability']

    # Calculate totals
    total_assets = sum(a.balance for a in assets)
    total_liabilities = sum(l.balance for l in liabilities)
    equity = total_assets - total_liabilities

    return render_template('balance_sheet.html',
                           assets=assets,
                           liabilities=liabilities,
                           total_assets=total_assets,
                           total_liabilities=total_liabilities,
                           equity=equity)
@app.route('/cashflow_statement', methods=['GET', 'POST'])
@login_required
def cashflow_statement():
    user = User.query.filter_by(username=session['username']).first()
    accounts = Account.query.filter_by(user_id=user.id).all()

    # Optional date range for form UI
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')

    if start_date and end_date:
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
    else:
        today = datetime.today()
        start = today.replace(day=1)
        end = today

    # ✅ Split by account type
    income_total = sum(acc.balance for acc in accounts if acc.type == 'Income')
    expense_total = sum(acc.balance for acc in accounts if acc.type == 'Expense')
    asset_total = sum(acc.balance for acc in accounts if acc.type == 'Asset')
    liability_total = sum(acc.balance for acc in accounts if acc.type == 'Liability')

    # ✅ Calculate cash flows
    operating_cash = income_total - expense_total
    investing_cash = asset_total
    financing_cash = -liability_total  # Liabilities reduce cash position

    net_cash_flow = operating_cash + investing_cash + financing_cash

    return render_template('cashflow_statement.html',
                           start_date=start.strftime('%Y-%m-%d'),
                           end_date=end.strftime('%Y-%m-%d'),
                           operating_cash=operating_cash,
                           investing_cash=investing_cash,
                           financing_cash=financing_cash,
                           net_cash_flow=net_cash_flow)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = User.query.filter_by(username=session['username']).first()

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_name':
            new_name = request.form.get('name')
            if new_name:
                user.name = new_name
                db.session.commit()
                flash('Name updated successfully.', 'success')
            else:
                flash('Name cannot be empty.', 'error')

        elif action == 'change_password':
            old_password = request.form.get('old_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')

            if not user.check_password(old_password):
                flash('Old password is incorrect.', 'error')
            elif new_password != confirm_password:
                flash('New passwords do not match.', 'error')
            else:
                user.set_password(new_password)
                db.session.commit()
                flash('Password changed successfully.', 'success')

        return redirect(url_for('profile'))

    return render_template('profile.html', user=user)



if __name__ == '__main__':
    app.run(debug=True)