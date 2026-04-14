from app.models import AuditLog, db
from flask_login import current_user

class AuditService:
    @staticmethod
    def log(action, model, model_id, details=None):
        try:
            user_id = current_user.id if current_user and current_user.is_authenticated else None
            log_entry = AuditLog(
                user_id=user_id,
                action=action,
                model=model,
                model_id=model_id,
                details=details
            )
            db.session.add(log_entry)
            # Don't commit here — let the caller's transaction handle it.
            # This prevents rollback from corrupting the caller's data.
        except Exception as e:
            print(f"Failed to create audit log: {e}")
            # Expunge the failed log entry instead of rolling back the whole session
            try:
                db.session.expunge(log_entry)
            except Exception:
                pass

