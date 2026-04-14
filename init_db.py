from app import create_app, db
from app.models import User, Account
from app.services.accounting import AccountingService
from datetime import datetime, timezone
from sqlalchemy import inspect, text

app = create_app('development')

with app.app_context():
    print("Creating database tables...")
    db.create_all()

    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())

    def table_column_names(table):
        if table not in table_names:
            return set()
        return {col['name'] for col in inspector.get_columns(table)}

    user_columns = table_column_names('user')

    alter_statements = []
    if 'invited_at' not in user_columns:
        alter_statements.append("ALTER TABLE user ADD COLUMN invited_at DATETIME")
    if 'password_changed_at' not in user_columns:
        alter_statements.append("ALTER TABLE user ADD COLUMN password_changed_at DATETIME")
    if 'status' not in user_columns:
        alter_statements.append("ALTER TABLE user ADD COLUMN status VARCHAR(20) DEFAULT 'pending'")

    # Invoice updates
    invoice_columns = table_column_names('invoice')
    if 'invoice_number' not in invoice_columns:
        alter_statements.append("ALTER TABLE invoice ADD COLUMN invoice_number VARCHAR(30)")
    if 'amount_paid' not in invoice_columns:
        alter_statements.append("ALTER TABLE invoice ADD COLUMN amount_paid NUMERIC(12, 2) DEFAULT 0.0")

    # Bill updates
    bill_columns = table_column_names('bill')
    if 'bill_number' not in bill_columns:
        alter_statements.append("ALTER TABLE bill ADD COLUMN bill_number VARCHAR(30)")
    if 'amount_paid' not in bill_columns:
        alter_statements.append("ALTER TABLE bill ADD COLUMN amount_paid NUMERIC(12, 2) DEFAULT 0.0")

    for stmt in alter_statements:
        db.session.execute(text(stmt))

    if alter_statements:
        db.session.commit()
        print("Applied user table compatibility updates.")
    
    print("Seeding Chart of Accounts...")
    try:
        AccountingService.seed_chart_of_accounts()
        
        # Ensure at least one admin user exists
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            print("Creating default admin user (admin / admin123)...")
            admin_user = User(
                username='admin',
                email='admin@example.com',
                role='admin',
                status='active',
                invited_at=datetime.now(timezone.utc),
                password_changed_at=datetime.now(timezone.utc)
            )
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            db.session.commit()
        else:
            # Update role to lowercase and ensure it's admin, and reset password to ensure bcrypt
            print("Updating existing admin user to ensure compatible password hash...")
            admin_user.role = 'admin'
            admin_user.set_password('admin123')
            db.session.commit()
            
        print("Success!")
    except Exception as e:
        print(f"Error seeding database: {e}")
        db.session.rollback()
