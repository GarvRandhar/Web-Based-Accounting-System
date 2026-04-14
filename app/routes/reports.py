import csv
import io
from flask import Blueprint, render_template, request, make_response, flash, redirect, url_for
from flask_login import login_required
from app.services.reports import ReportingService
from app.models import JournalEntry, JournalItem, Account, db
from datetime import datetime
import pdfkit

reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

@reports_bp.route('/')
@login_required
def index():
    return render_template('reports/index.html', now=datetime.now())

@reports_bp.route('/balance-sheet', methods=['GET'])
@login_required
def balance_sheet():
    date_str = request.args.get('date', datetime.today().strftime('%Y-%m-%d'))
    date = datetime.strptime(date_str, '%Y-%m-%d')
    
    data = ReportingService.get_balance_sheet(date)
    
    if request.args.get('export') == 'pdf':
        try:
            rendered = render_template('reports/balance_sheet_pdf.html', data=data)
            options = {'enable-local-file-access': ''}
            pdf = pdfkit.from_string(rendered, False, options=options)
            response = make_response(pdf)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename=balance_sheet_{date_str}.pdf'
            return response
        except Exception as e:
            from flask import flash, redirect, url_for
            flash(f"PDF export failed: wkhtmltopdf not installed. ({str(e)})", "error")
            return redirect(url_for('reports.balance_sheet', date=date_str))

    return render_template('reports/balance_sheet.html', data=data)

@reports_bp.route('/profit-loss', methods=['GET'])
@login_required
def profit_loss():
    start_str = request.args.get('start_date', datetime.today().replace(day=1).strftime('%Y-%m-%d'))
    end_str = request.args.get('end_date', datetime.today().strftime('%Y-%m-%d'))
    
    start_date = datetime.strptime(start_str, '%Y-%m-%d')
    end_date = datetime.strptime(end_str, '%Y-%m-%d')
    
    data = ReportingService.get_profit_loss(start_date, end_date)
    
    if request.args.get('export') == 'pdf':
        try:
            rendered = render_template('reports/profit_loss_pdf.html', data=data)
            options = {'enable-local-file-access': ''}
            pdf = pdfkit.from_string(rendered, False, options=options)
            response = make_response(pdf)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'attachment; filename=profit_loss_{start_str}_{end_str}.pdf'
            return response
        except Exception as e:
            from flask import flash, redirect, url_for
            flash(f"PDF export failed: wkhtmltopdf not installed. ({str(e)})", "error")
            return redirect(url_for('reports.profit_loss', start_date=start_str, end_date=end_str))

    return render_template('reports/profit_loss.html', data=data)

@reports_bp.route('/trial-balance')
@login_required
def trial_balance():
    date_str = request.args.get('date')
    if date_str:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        date = datetime.today().date()
        
    data = ReportingService.get_trial_balance(date)
    return render_template('reports/trial_balance.html', **data)

@reports_bp.route('/cash-flow')
@login_required
def cash_flow():
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    if start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        today = datetime.today()
        start_date = today.replace(day=1).date()
        end_date = today.date()

    data = ReportingService.get_cash_flow(start_date, end_date)
    return render_template('reports/cash_flow.html', **data)


# ───────────────────────────────────────────────────────────────────
# CSV EXPORTS  (no external dependency, always available)
# ───────────────────────────────────────────────────────────────────

def _csv_response(filename, header, rows):
    """Helper: build a CSV download response from header list and row list."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    output = make_response(buf.getvalue())
    output.headers['Content-Type'] = 'text/csv; charset=utf-8'
    output.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return output


@reports_bp.route('/trial-balance/export/csv')
@login_required
def trial_balance_csv():
    date_str = request.args.get('date', datetime.today().strftime('%Y-%m-%d'))
    date = datetime.strptime(date_str, '%Y-%m-%d').date()
    data = ReportingService.get_trial_balance(date)

    header = ['Account Code', 'Account Name', 'Account Type', 'Debit', 'Credit']
    rows = [
        [a['code'], a['name'], a.get('type', ''), a['debit'], a['credit']]
        for a in data['accounts']
    ]
    rows.append(['', 'TOTAL', '', data['total_debit'], data['total_credit']])
    return _csv_response(f'trial_balance_{date_str}.csv', header, rows)


@reports_bp.route('/profit-loss/export/csv')
@login_required
def profit_loss_csv():
    start_str = request.args.get('start_date', datetime.today().replace(day=1).strftime('%Y-%m-%d'))
    end_str   = request.args.get('end_date',   datetime.today().strftime('%Y-%m-%d'))
    start_date = datetime.strptime(start_str, '%Y-%m-%d')
    end_date   = datetime.strptime(end_str,   '%Y-%m-%d')
    data = ReportingService.get_profit_loss(start_date, end_date)

    header = ['Section', 'Account Code', 'Account Name', 'Amount']
    rows = []
    for a in data['revenue']['accounts']:
        rows.append(['Revenue', a['code'], a['name'], a['balance']])
    rows.append(['Revenue', '', 'Total Revenue', data['revenue']['total']])
    rows.append([])
    for a in data['expenses']['accounts']:
        rows.append(['Expenses', a['code'], a['name'], a['balance']])
    rows.append(['Expenses', '', 'Total Expenses', data['expenses']['total']])
    rows.append([])
    rows.append(['', '', 'Net Income / (Loss)', data['net_income']])
    return _csv_response(f'profit_loss_{start_str}_{end_str}.csv', header, rows)


@reports_bp.route('/balance-sheet/export/csv')
@login_required
def balance_sheet_csv():
    date_str = request.args.get('date', datetime.today().strftime('%Y-%m-%d'))
    date = datetime.strptime(date_str, '%Y-%m-%d')
    data = ReportingService.get_balance_sheet(date)

    header = ['Section', 'Account Code', 'Account Name', 'Balance']
    rows = []
    for section, label in [
        ('assets', 'Asset'), ('liabilities', 'Liability'), ('equity', 'Equity')
    ]:
        for a in data[section]['accounts']:
            rows.append([label, a['code'], a['name'], a['balance']])
        rows.append([label, '', f'Total {label}', data[section]['total']])
        rows.append([])
    return _csv_response(f'balance_sheet_{date_str}.csv', header, rows)


@reports_bp.route('/general-ledger/export/csv')
@login_required
def general_ledger_csv():
    """Exports the full general ledger (all non-voided journal items) as CSV."""
    start_str = request.args.get('start_date', datetime.today().replace(day=1).strftime('%Y-%m-%d'))
    end_str   = request.args.get('end_date',   datetime.today().strftime('%Y-%m-%d'))
    start_date = datetime.strptime(start_str, '%Y-%m-%d')
    end_date   = datetime.strptime(end_str,   '%Y-%m-%d')

    items = (
        db.session.query(JournalItem)
        .join(JournalEntry, JournalEntry.id == JournalItem.journal_entry_id)
        .filter(
            JournalEntry.date >= start_date,
            JournalEntry.date <= end_date,
            JournalEntry.voided == False,  # noqa
        )
        .order_by(JournalEntry.date, JournalEntry.id)
        .all()
    )

    header = ['Date', 'JE #', 'Reference', 'Description', 'Account Code', 'Account Name', 'Debit', 'Credit']
    rows = [
        [
            item.entry.date.strftime('%Y-%m-%d'),
            item.entry.id,
            item.entry.reference or '',
            item.entry.description,
            item.account.code if item.account else '',
            item.account.name if item.account else '',
            float(item.debit),
            float(item.credit),
        ]
        for item in items
    ]
    return _csv_response(f'general_ledger_{start_str}_{end_str}.csv', header, rows)
