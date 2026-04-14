from flask import Flask
from config import config
from .extensions import db, csrf, bcrypt, limiter
import os

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt'}

def create_app(config_name='default'):
    if not config_name:
        config_name = 'default'
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Configure Upload Folder
    app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/uploads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file upload
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)
    bcrypt.init_app(app)
    limiter.init_app(app)

    # CSRF Protection
    csrf.init_app(app)
    
    from flask_login import LoginManager
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)
    
    from .models import User
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # Register Blueprints
    from .routes.main import main_bp
    app.register_blueprint(main_bp)
    
    from .routes.auth import auth_bp
    app.register_blueprint(auth_bp)
    
    from .routes.accounting import accounting_bp
    app.register_blueprint(accounting_bp)
    
    from .routes.reports import reports_bp
    app.register_blueprint(reports_bp)

    from .routes.admin import admin_bp
    app.register_blueprint(admin_bp)

    from .routes.api_admin import api_admin_bp
    app.register_blueprint(api_admin_bp)
    # NOTE: CSRF exemption is now applied per-route in api_admin.py, not blueprint-wide.

    from .routes.reconciliation import reconciliation_bp
    app.register_blueprint(reconciliation_bp)

    from .routes.settings import settings_bp
    app.register_blueprint(settings_bp)

    from .routes.ar import ar_bp
    app.register_blueprint(ar_bp)

    from .routes.ap import ap_bp
    app.register_blueprint(ap_bp)

    from .routes.inventory import inventory_bp
    app.register_blueprint(inventory_bp)

    from .routes.taxation import taxation_bp
    app.register_blueprint(taxation_bp)

    from .routes.cost_centers import cost_centers_bp
    app.register_blueprint(cost_centers_bp)

    from .routes.currency import currency_bp
    app.register_blueprint(currency_bp)

    from .routes.payroll import payroll_bp
    app.register_blueprint(payroll_bp)

    from .routes.assets import assets_bp
    app.register_blueprint(assets_bp)

    @app.before_request
    def enforce_viewer_readonly():
        from flask import request, abort
        from flask_login import current_user

        if not current_user.is_authenticated:
            return None

        role = (current_user.role or '').lower()
        if role != 'viewer':
            return None

        safe_methods = {'GET', 'HEAD', 'OPTIONS'}
        if request.method in safe_methods:
            return None

        allowed_viewer_write_endpoints = {
            'auth.logout',
            'auth.change_password',
            'auth.change_password_page',
        }
        if request.endpoint in allowed_viewer_write_endpoints:
            return None

        abort(403)

    @app.before_request
    def refresh_session():
        from flask import session
        session.permanent = True
        session.modified = True

    # Context Processor to make company settings available globally
    from .models import CompanySettings
    @app.context_processor
    def inject_company_settings():
        settings = CompanySettings.query.first()
        if not settings:
            # Fallback if no settings exist
            return dict(company_settings={'company_name': 'Accounting Pro', 'currency_symbol': '$', 'address': ''})
        return dict(company_settings=settings)

    # Add abs to jinja globals
    app.jinja_env.globals.update(abs=abs)

    # Error handlers
    @app.errorhandler(404)
    def page_not_found(e):
        from flask import render_template
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        from flask import render_template
        return render_template('errors/500.html'), 500

    return app
