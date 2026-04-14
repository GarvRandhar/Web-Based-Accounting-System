from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory
from flask_login import login_required
from app.models import Account, Tax, db, JournalEntry, JournalItem, Attachment
from app.services.accounting import AccountingService
from app.services.audit import AuditService
from app.decorators import accountant_or_admin_required
from datetime import datetime, timezone
import os
from werkzeug.utils import secure_filename

accounting_bp = Blueprint('accounting', __name__, url_prefix='/accounting')

# === ACCOUNTS ===

@accounting_bp.route('/accounts')
@login_required
def list_accounts():
    page = request.args.get('page', 1, type=int)
    pagination = Account.query.filter_by(is_active=True).order_by(Account.code).paginate(page=page, per_page=50, error_out=False)
    all_accounts = Account.query.filter_by(is_active=True).order_by(Account.code).all()
    return render_template('accounting/accounts.html', pagination=pagination, accounts=pagination.items, all_accounts=all_accounts)

@accounting_bp.route('/accounts/new', methods=['POST'])
@login_required
@accountant_or_admin_required
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
@accountant_or_admin_required
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
@accountant_or_admin_required
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
    page = request.args.get('page', 1, type=int)
    pagination = JournalEntry.query.order_by(JournalEntry.date.desc()).paginate(page=page, per_page=50, error_out=False)
    return render_template('accounting/journals.html', pagination=pagination)

@accounting_bp.route('/journal/new', methods=['GET', 'POST'])
@login_required
@accountant_or_admin_required
def create_journal_entry():
    if request.method == 'POST':
        try:
            date_str = request.form.get('date')
            description = request.form.get('description', '').strip()
            reference = request.form.get('reference', '').strip()

            if not description:
                raise ValueError("Description is required.")
            if not date_str:
                raise ValueError("Date is required.")

            # ── Robust multi-row parsing using getlist ──────────────────
            # Frontend sends: account_id[], debit[], credit[]
            account_ids = request.form.getlist('account_id[]')
            debits      = request.form.getlist('debit[]')
            credits_    = request.form.getlist('credit[]')

            items = []
            for i in range(len(account_ids)):
                acc_id_raw = account_ids[i].strip() if i < len(account_ids) else ''
                if not acc_id_raw:
                    continue  # skip blank rows

                try:
                    acc_id = int(acc_id_raw)
                    debit_str = debits[i].strip() if i < len(debits) else '0'
                    credit_str = credits_[i].strip() if i < len(credits_) else '0'
                    
                    debit  = float(debit_str or '0')
                    credit = float(credit_str or '0')
                except (ValueError, IndexError):
                    raise ValueError(f"Invalid numeric value on line {i + 1}.")

                if debit < 0 or credit < 0:
                    raise ValueError(f"Debit and credit amounts must be non-negative (line {i + 1}).")
                if debit > 0 or credit > 0:
                    items.append({'account_id': acc_id, 'debit': debit, 'credit': credit})

            if not items:
                raise ValueError("Journal Entry must have at least one line item with a non-zero amount.")

            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            AccountingService.create_journal_entry(date_obj, description, items, reference)
            flash('Journal Entry successfully posted.', 'success')
            return redirect(url_for('accounting.list_journals'))

        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'error')

    accounts = Account.query.filter_by(is_active=True).order_by(Account.code).all()
    return render_template('accounting/journal_form.html', accounts=accounts,
                           today=datetime.today().strftime('%Y-%m-%d'))

@accounting_bp.route('/journal/<int:id>/void', methods=['POST'])
@login_required
@accountant_or_admin_required
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
@accountant_or_admin_required
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
        unique_filename = f"{entry.id}_{int(datetime.now(timezone.utc).timestamp())}_{filename}"
        
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
