from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import JournalEntry, Account, Invoice, Bill

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
@login_required
def index():
    from flask import redirect, url_for
    return redirect(url_for('main.dashboard'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    from app.services.accounting import AccountingService
    metrics = AccountingService.get_summary_metrics()
    charts = AccountingService.get_dashboard_charts_data()
    recent_entries = JournalEntry.query.order_by(JournalEntry.date.desc()).limit(5).all()
    recent_invoices = Invoice.query.order_by(Invoice.date.desc()).limit(5).all()
    bills_to_pay = Bill.query.filter_by(status='Open').order_by(Bill.due_date).limit(5).all()
    
    return render_template('dashboard.html', 
                           recent_entries=recent_entries, 
                           metrics=metrics, 
                           charts=charts,
                           recent_invoices=recent_invoices,
                           bills_to_pay=bills_to_pay)
