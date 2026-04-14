from flask import Blueprint, jsonify, request, current_app
from flask_login import login_required, current_user

from app.decorators import admin_required
from app.models import User, db
from app.services.invitations import InvitationService, ALLOWED_ROLES
from app.services.audit import AuditService
from app.extensions import limiter, csrf, jwt_required


api_admin_bp = Blueprint('api_admin', __name__, url_prefix='/api/admin')


def _serialize_user(user):
    return {
        'id': user.id,
        'email': user.email,
        'role': user.role,
        'status': user.status,
        'invitedAt': user.invited_at.isoformat() if user.invited_at else None,
    }


@api_admin_bp.route('/invite', methods=['POST'])
@csrf.exempt  # Only this endpoint is exempt — called from frontend JS with fetch()
@login_required
@admin_required
@jwt_required
@limiter.limit(lambda: current_app.config.get('INVITE_RATE_LIMIT', '5 per minute'))
def invite():
    data = request.get_json(silent=True) or request.form
    email = (data.get('email') or '').strip().lower()
    role = (data.get('role') or 'viewer').strip().lower()

    if not email or '@' not in email:
        return jsonify({'error': 'Valid email is required.'}), 400
    if role not in ALLOWED_ROLES:
        return jsonify({'error': 'Invalid role.'}), 400

    try:
        user = InvitationService.invite_user(email, role)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify({'message': 'Invitation sent.', 'user': _serialize_user(user)}), 201


@api_admin_bp.route('/users', methods=['GET'])
@login_required
@admin_required
@jwt_required
def list_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({'users': [_serialize_user(user) for user in users]})


@api_admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@login_required
@admin_required
@jwt_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if current_user.id == user.id:
        return jsonify({'error': 'You cannot delete your own account.'}), 400
    if user.is_admin() and User.query.filter_by(role='admin').count() <= 1:
        return jsonify({'error': 'Cannot delete the last admin user.'}), 400

    AuditService.log('Delete', 'User', user.id, f"Deleted user {user.username} ({user.email})")
    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': 'User deleted.'})


@api_admin_bp.route('/resend-invite/<int:user_id>', methods=['POST'])
@login_required
@admin_required
@jwt_required
def resend_invite(user_id):
    user = User.query.get_or_404(user_id)
    InvitationService.resend_invite(user)
    return jsonify({'message': 'Invitation resent.', 'user': _serialize_user(user)})
