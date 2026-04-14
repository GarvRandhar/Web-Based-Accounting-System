import secrets
import smtplib
import string
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import jwt as pyjwt
from flask import current_app, url_for

from app.models import User, db


ALLOWED_ROLES = {'admin', 'accountant', 'viewer'}
_TOKEN_EXPIRY_HOURS = 48  # invitation link is valid for 48 hours


class InvitationService:

    # ── Token helpers ──────────────────────────────────────────────────

    @staticmethod
    def _generate_invite_token(user_id: int, email: str) -> str:
        """
        Creates a signed JWT containing the user ID and email.
        Token expires in 48 h.  No password is embedded.
        """
        now = datetime.now(timezone.utc)
        payload = {
            'sub':   user_id,
            'email': email,
            'type':  'invite',
            'iat':   int(now.timestamp()),
            'exp':   int((now + timedelta(hours=_TOKEN_EXPIRY_HOURS)).timestamp()),
        }
        return pyjwt.encode(
            payload,
            current_app.config['JWT_SECRET_KEY'],
            algorithm=current_app.config.get('JWT_ALGORITHM', 'HS256'),
        )

    @staticmethod
    def verify_invite_token(token: str) -> dict:
        """
        Decodes and validates an invitation token.
        Returns the payload dict or raises ValueError on failure.
        """
        try:
            payload = pyjwt.decode(
                token,
                current_app.config['JWT_SECRET_KEY'],
                algorithms=[current_app.config.get('JWT_ALGORITHM', 'HS256')],
            )
        except pyjwt.ExpiredSignatureError:
            raise ValueError('Invitation link has expired. Please ask an admin to resend.')
        except pyjwt.InvalidTokenError as e:
            raise ValueError(f'Invalid invitation token: {e}')

        if payload.get('type') != 'invite':
            raise ValueError('Token is not an invitation token.')
        return payload

    # ── Email ──────────────────────────────────────────────────────────

    @staticmethod
    def _send_invite_email(user_email: str, role: str, invite_link: str) -> bool:
        """
        Sends an invitation email containing only a secure link.
        No password is ever included in the email.
        """
        system_name = current_app.config.get('SYSTEM_NAME', 'Accounting Pro')

        msg = EmailMessage()
        msg['Subject'] = f"You have been invited to {system_name}"
        msg['From']    = current_app.config.get('MAIL_SENDER', 'no-reply@example.com')
        msg['To']      = user_email
        msg.set_content(f"""\
You have been invited to {system_name} as {role}.

Click the link below to accept your invitation and set your password.
This link will expire in {_TOKEN_EXPIRY_HOURS} hours.

{invite_link}

If you did not expect this invitation, you can safely ignore this email.
""")

        mail_server = current_app.config.get('MAIL_SERVER')
        if not mail_server:
            current_app.logger.warning(
                "MAIL_SERVER not configured — skipping email to %s. Invite link: %s",
                user_email, invite_link,
            )
            return False

        with smtplib.SMTP(mail_server, current_app.config.get('MAIL_PORT', 587)) as server:
            if current_app.config.get('MAIL_USE_TLS', True):
                server.starttls()
            username = current_app.config.get('MAIL_USERNAME')
            password = current_app.config.get('MAIL_PASSWORD')
            if username and password:
                server.login(username, password)
            server.send_message(msg)
        return True

    # ── Public API ─────────────────────────────────────────────────────

    @staticmethod
    def invite_user(email: str, role: str) -> User:
        """
        Creates a pending user and emails them a secure token link.
        No password is generated or transmitted.
        """
        normalized_role = (role or 'viewer').strip().lower()
        if normalized_role not in ALLOWED_ROLES:
            raise ValueError('Invalid role selected.')

        existing = User.query.filter_by(email=email).first()
        if existing:
            raise ValueError('A user with this email already exists.')

        # Create the account with a random placeholder hash (user will set
        # their real password when they accept the invite link).
        placeholder = secrets.token_hex(32)
        user = User(
            username=email,
            email=email,
            role=normalized_role,
            invited_at=datetime.now(timezone.utc),
            status='pending',
        )
        user.set_password(placeholder)   # placeholder — never revealed to anyone
        db.session.add(user)
        db.session.commit()

        # Build the token AFTER commit so user.id is available
        token       = InvitationService._generate_invite_token(user.id, email)
        invite_link = (
            current_app.config.get('APP_BASE_URL', '').rstrip('/')
            + url_for('auth.accept_invite', token=token)
        )
        InvitationService._send_invite_email(email, normalized_role, invite_link)
        return user

    @staticmethod
    def resend_invite(user: User) -> User:
        """
        Generates a fresh invitation token and resends the link email.
        Resets the user to 'pending' status.
        """
        if not user:
            raise ValueError('User not found.')

        # Reset status so they must complete onboarding again
        user.invited_at        = datetime.now(timezone.utc)
        user.status            = 'pending'
        user.password_changed_at = None
        db.session.commit()

        token       = InvitationService._generate_invite_token(user.id, user.email)
        invite_link = (
            current_app.config.get('APP_BASE_URL', '').rstrip('/')
            + url_for('auth.accept_invite', token=token)
        )
        InvitationService._send_invite_email(user.email, user.role, invite_link)
        return user
