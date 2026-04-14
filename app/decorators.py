from functools import wraps
from flask import abort
from flask_login import current_user


def roles_required(*roles):
    allowed_roles = {role.strip().lower() for role in roles}

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(403)
            if (current_user.role or '').lower() not in allowed_roles:
                abort(403)
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def admin_required(f):
    return roles_required('admin')(f)


def accountant_or_admin_required(f):
    return roles_required('admin', 'accountant')(f)
