from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory
from flask_login import login_required
from app.models import Account, Tax, db, JournalEntry, JournalItem, Attachment
from app.services.accounting import AccountingService
from app.services.audit import AuditService
from datetime import datetime
import os
from werkzeug.utils import secure_filename

accounting_bp = Blueprint('accounting', __name__, url_prefix='/accounting')

# === ACCOUNTS ===

@accounting_bp.route('/accounts')
@login_required
def list_accounts():
    accounts = Account.query.filter_by(is_active=True).order_by(Account.code).all()
    all_accounts = Account.query.filter_by(is_active=True).order_by(Account.code).all()
    return render_template('accounting/accounts.html', accounts=accounts, all_accounts=all_accounts)

@accounting_bp.route('/accounts/new', methods=['POST'])
@login_required
def create_account():
    code = request.form.get('code', '').strip()
    name = request.form.get('name', '').strip()
    acc_type = request.form.get('type', '').strip()
    description = request.form.get('description', '').strip()
    parent_id = request.form.get('parent_id')
    
    if not code or not name or not acc_type:
        flash('Code, name, and type are required.', 'error')
        return redirect(url_for('accounting.list_accounts'))
    
    if Account.query.filter_by(code=code).first():
        flash(f'Account code {code} already exists.', 'error')
        return redirect(url_for('accounting.list_accounts'))
    
    account = Account(
        code=code,
        name=name,
        type=acc_type,
        description=description,
        parent_id=int(parent_id) if parent_id else None
    )
    db.session.add(account)
    db.session.commit()
    
    AuditService.log(action='CREATE', model='Account', model_id=account.id, details=f"Created account: {code} - {name}")
    flash(f'Account {code} - {name} created.', 'success')
    return redirect(url_for('accounting.list_accounts'))

@accounting_bp.route('/accounts/<int:id>/edit', methods=['POST'])
@login_required
def edit_account(id):
    account = Account.query.get_or_404(id)
    account.name = request.form.get('name', account.name).strip()
    account.description = request.form.get('description', '').strip()
    account.type = request.form.get('type', account.type).strip()
    parent_id = request.form.get('parent_id')
    account.parent_id = int(parent_id) if parent_id else None
    
    db.session.commit()
    AuditService.log(action='UPDATE', model='Account', model_id=account.id, details=f"Updated account: {account.code} - {account.name}")
    flash(f'Account {account.code} updated.', 'success')
    return redirect(url_for('accounting.list_accounts'))

@accounting_bp.route('/accounts/<int:id>/delete', methods=['POST'])
@login_required
def delete_account(id):
    account = Account.query.get_or_404(id)
    
    # Check if account has journal items
    if JournalItem.query.filter_by(account_id=id).first():
        flash(f'Cannot delete account {account.code} — it has journal entries. Deactivating instead.', 'warning')
        account.is_active = False
        db.session.commit()
    else:
        AuditService.log(action='DELETE', model='Account', model_id=account.id, details=f"Deleted account: {account.code} - {account.name}")
        db.session.delete(account)
        db.session.commit()
        flash(f'Account {account.code} deleted.', 'success')
    
    return redirect(url_for('accounting.list_accounts'))

# === JOURNAL ENTRIES ===

@accounting_bp.route('/journals')
@login_required
def list_journals():
    entries = JournalEntry.query.order_by(JournalEntry.date.desc()).all()
    return render_template('accounting/journals.html', entries=entries)

@accounting_bp.route('/journal/new', methods=['GET', 'POST'])
@login_required
def create_journal_entry():
    if request.method == 'POST':
        try:
            date_str = request.form.get('date')
            description = request.form.get('description')
            reference = request.form.get('reference')
            
            items = []
            index = 0
            while True:
                key_prefix = f'items[{index}]'
                acc_id = request.form.get(f'{key_prefix}[account_id]')
                
                if not acc_id:
                    if index > 50: break
                    if request.form.get(f'items[{index+1}][account_id]'):
                        index += 1
                        continue
                    break
                
                debit = float(request.form.get(f'{key_prefix}[debit]') or 0)
                credit = float(request.form.get(f'{key_prefix}[credit]') or 0)
                
                if debit > 0 or credit > 0:
                    items.append({
                        'account_id': int(acc_id),
                        'debit': debit,
                        'credit': credit
                    })
                index += 1
            
            if not items:
                 raise ValueError("Journal Entry must have at least one line item.")

            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            AccountingService.create_journal_entry(date_obj, description, items, reference)
            flash('Journal Entry successfully posted.', 'success')
            return redirect(url_for('accounting.list_journals'))
            
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'error')

    accounts = Account.query.filter_by(is_active=True).order_by(Account.code).all()
    return render_template('accounting/journal_form.html', accounts=accounts, today=datetime.today().strftime('%Y-%m-%d'))

@accounting_bp.route('/journal/<int:id>/void', methods=['POST'])
@login_required
def void_journal_entry(id):
    try:
        AccountingService.void_journal_entry(id)
        flash(f'Journal Entry #{id} has been voided.', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        flash(f'Error voiding entry: {str(e)}', 'error')
    return redirect(url_for('accounting.list_journals'))

# === ATTACHMENTS ===

@accounting_bp.route('/journal/<int:id>/upload', methods=['POST'])
@login_required
def upload_attachment(id):
    entry = JournalEntry.query.get_or_404(id)
    
    if 'file' not in request.files:
        flash('No file part', 'error')
        return redirect(request.referrer)
        
    file = request.files['file']
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(request.referrer)
    
    from app import ALLOWED_EXTENSIONS
    def allowed_file(filename):
        return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    
    if not allowed_file(file.filename):
        flash(f'File type not allowed. Allowed: {", ".join(ALLOWED_EXTENSIONS)}', 'error')
        return redirect(request.referrer)
        
    if file:
        filename = secure_filename(file.filename)
        unique_filename = f"{entry.id}_{int(datetime.utcnow().timestamp())}_{filename}"
        
        file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename))
        
        attachment = Attachment(
            journal_entry_id=entry.id,
            filename=filename,
            filepath=unique_filename
        )
        db.session.add(attachment)
        db.session.commit()
        
        flash('File uploaded successfully', 'success')
        
    return redirect(request.referrer)

@accounting_bp.route('/download/<int:id>')
@login_required
def download_attachment(id):
    attachment = Attachment.query.get_or_404(id)
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], attachment.filepath, as_attachment=True, download_name=attachment.filename)
