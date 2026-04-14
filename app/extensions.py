from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps

db = SQLAlchemy()
csrf = CSRFProtect()
bcrypt = Bcrypt()
limiter = Limiter(key_func=get_remote_address)


def jwt_required(f):
    """Decorator that validates the JWT access_token cookie on API routes.
    Falls back to Flask-Login session for browser requests that have no JWT.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        import jwt as pyjwt
        from flask import request, jsonify, current_app, g
        from flask_login import current_user

        token = request.cookies.get('access_token')
        if not token:
            # No JWT — reject API requests; browser sessions are handled by @login_required
            return jsonify({'error': 'Missing authentication token. Please log in.'}), 401

        try:
            payload = pyjwt.decode(
                token,
                current_app.config['JWT_SECRET_KEY'],
                algorithms=[current_app.config['JWT_ALGORITHM']]
            )
            g.jwt_user_id = payload['sub']
            g.jwt_role = payload.get('role', 'viewer')
        except pyjwt.ExpiredSignatureError:
            return jsonify({'error': 'Session expired. Please log in again.'}), 401
        except pyjwt.InvalidTokenError as e:
            return jsonify({'error': f'Invalid token: {str(e)}'}), 401

        return f(*args, **kwargs)
    return decorated
