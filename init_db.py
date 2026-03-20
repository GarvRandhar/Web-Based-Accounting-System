from app import create_app, db
from app.services.accounting import AccountingService

app = create_app('development')

with app.app_context():
    print("Creating database tables...")
    db.create_all()
    
    print("Seeding Chart of Accounts...")
    try:
        AccountingService.seed_chart_of_accounts()
        print("Success!")
    except Exception as e:
        print(f"Error seeding database: {e}")
