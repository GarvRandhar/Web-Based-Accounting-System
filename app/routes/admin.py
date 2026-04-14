import csv
import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from flask_login import login_required, current_user
from app.models import User, AuditLog, db
from app.decorators import admin_required
from datetime import datetime

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/audit-log')
@login_required
@admin_required
def audit_log():
    # Filters
    action_filter = request.args.get('action', '').strip()
    model_filter = request.args.get('model', '').strip()
    user_filter = request.args.get('user_id', '', type=int)
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 50

    query = AuditLog.query

    if action_filter:
        query = query.filter_by(action=action_filter)
    if model_filter:
        query = query.filter_by(model=model_filter)
    if user_filter:
        query = query.filter_by(user_id=user_filter)
    if date_from:
        try:
            df = datetime.strptime(date_from, '%Y-%m-%d')
            query = query.filter(AuditLog.timestamp >= df)
        except ValueError:
            pass
    if date_to:
        try:
            dt = datetime.strptime(date_to, '%Y-%m-%d')
            # include the entire end date by adding a day or just let it match to midnight
            query = query.filter(AuditLog.timestamp <= dt.replace(hour=23, minute=59, second=59))
        except ValueError:
            pass

    query = query.order_by(AuditLog.timestamp.desc())

    if request.args.get('export') == 'csv':
        logs = query.all()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Timestamp', 'User ID', 'Username', 'Action', 'Model', 'Model ID', 'Details'])
        for log in logs:
            username = log.user.username if log.user else 'System'
            writer.writerow([
                log.id,
                log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                log.user_id or '',
                username,
                log.action,
                log.model,
                log.model_id or '',
                log.details or ''
            ])
        
        response = Response(output.getvalue(), mimetype='text/csv')
        response.headers['Content-Disposition'] = f'attachment; filename=audit_log_{datetime.now().strftime("%Y%m%d%H%M")}.csv'
        return response

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    # Get distinct values for dropdowns
    actions = db.session.query(AuditLog.action).distinct().all()
    actions = [a[0] for a in actions if a[0]]
    models = db.session.query(AuditLog.model).distinct().all()
    models = [m[0] for m in models if m[0]]
    users = User.query.order_by(User.username).all()

    return render_template('admin/audit_log.html', 
                           pagination=pagination, 
                           actions=actions, 
                           models=models, 
                           users=users)

@admin_bp.route('/users')
@login_required
@admin_required
def users_panel():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users)
