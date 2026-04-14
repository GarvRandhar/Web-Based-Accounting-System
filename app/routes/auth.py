from datetime import datetime, timedelta, timezone
import jwt
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, jsonify, make_response
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User, db
from app.extensions import csrf, limiter
from app.services.invitations import InvitationService

auth_bp = Blueprint('auth', __name__)


def _issue_auth_token(user):
    now = datetime.now(timezone.utc)
    payload = {
        'sub': user.id,
        'email': user.email,
        'role': user.role,
        'iat': int(now.timestamp()),
        'exp': int((now + timedelta(hours=current_app.config['JWT_EXP_HOURS'])).timestamp()),
    }
    return jwt.encode(
        payload,
        current_app.config['JWT_SECRET_KEY'],
        algorithm=current_app.config['JWT_ALGORITHM'],
    )

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        user = User.query.filter((User.username == username) | (User.email == username)).first()
        
        if user and user.check_password(password):
            login_user(user)

            token = _issue_auth_token(user)

            if user.requires_password_change():
                response = make_response(redirect(url_for('auth.change_password_page')))
            else:
                response = make_response(redirect(url_for('main.dashboard')))

            response.set_cookie(
                'access_token',
                token,
                httponly=True,
                samesite='Lax',
                secure=not current_app.debug,
            )
            return response
        else:
            flash('Invalid username or password', 'error')
            
    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    flash('Self-registration is disabled. Please contact an admin for an invitation.', 'error')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET'])
@login_required
def change_password_page():
    if not current_user.requires_password_change():
        return redirect(url_for('main.dashboard'))
    return render_template('auth/change_password.html')


@auth_bp.route('/api/auth/change-password', methods=['POST'])
@csrf.exempt
@login_required
def change_password():
    data = request.get_json(silent=True) or request.form

    current_password = data.get('currentPassword') or data.get('current_password')
    new_password = data.get('newPassword') or data.get('new_password')
    confirm_password = data.get('confirmPassword') or data.get('confirm_password')

    if not current_password or not new_password:
        return jsonify({'error': 'Current and new password are required.'}), 400

    if not current_user.check_password(current_password):
        return jsonify({'error': 'Current password is incorrect.'}), 400

    if len(new_password) < 8:
        return jsonify({'error': 'New password must be at least 8 characters.'}), 400

    if confirm_password is not None and confirm_password != new_password:
        return jsonify({'error': 'Password confirmation does not match.'}), 400

    current_user.set_password(new_password)
    current_user.activate()
    db.session.commit()

    if request.is_json:
        return jsonify({'message': 'Password changed successfully.'}), 200

    flash('Password changed successfully.', 'success')
    return redirect(url_for('main.dashboard'))


# ── Invitation Accept (token-based, no password in email) ──────────────

@auth_bp.route('/accept-invite', methods=['GET', 'POST'])
def accept_invite():
    """Validates a JWT invitation token and lets the user set their password."""
    token = request.args.get('token') or request.form.get('token')
    if not token:
        flash('Invalid or missing invitation token.', 'error')
        return redirect(url_for('auth.login'))

    try:
        payload = InvitationService.verify_invite_token(token)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('auth.login'))

    user = db.session.get(User, payload['sub'])
    if not user or user.email != payload['email']:
        flash('Invitation is no longer valid.', 'error')
        return redirect(url_for('auth.login'))

    if user.status == 'active':
        flash('This invitation has already been accepted. Please log in.', 'info')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        new_password     = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if len(new_password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('auth/accept_invite.html', token=token, email=user.email)
        if new_password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('auth/accept_invite.html', token=token, email=user.email)

        user.set_password(new_password)
        user.activate()  # sets status='active' and password_changed_at
        db.session.commit()

        login_user(user)
        flash('Welcome! Your account is now active.', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('auth/accept_invite.html', token=token, email=user.email)

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    response = make_response(redirect(url_for('auth.login')))
    response.delete_cookie('access_token')
    return response
