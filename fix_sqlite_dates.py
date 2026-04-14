import sqlite3
import os

db_path = 'instance/accounting.db'

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# List of (table, column) pairs that are now Date but might have Time strings
targets = [
    ('journal_entry', 'date'),
    ('bank_statement', 'start_date'),
    ('bank_statement', 'end_date'),
    ('bank_transaction', 'date'),
    ('company_settings', 'fiscal_year_start'),
    ('invoice', 'date'),
    ('invoice', 'due_date'),
    ('bill', 'date'),
    ('bill', 'due_date'),
    ('stock_entry', 'date'),
    ('stock_ledger_entry', 'posting_date'),
    ('exchange_rate', 'effective_date'),
    ('employee', 'date_of_joining'),
    ('payroll_entry', 'run_date'),
    ('fixed_asset', 'purchase_date'),
    ('fixed_asset', 'disposed_date'),
    ('depreciation_schedule', 'schedule_date')
]

print("Starting SQLite date format cleanup...")

for table, column in targets:
    try:
        # Check if table and column exist
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [row[1] for row in cursor.fetchall()]
        if column not in columns:
            print(f"Skipping {table}.{column} (column not found)")
            continue
            
        print(f"Cleaning {table}.{column}...")
        # Update matching strings to just the date part (first 10 chars)
        # Only update if the string is longer than 10 chars and contains a space or T
        cursor.execute(f"""
            UPDATE {table} 
            SET {column} = substr({column}, 1, 10) 
            WHERE length({column}) > 10 
            AND ({column} LIKE '% %' OR {column} LIKE '%T%')
        """)
        print(f"  Rows updated: {cursor.rowcount}")
    except sqlite3.OperationalError as e:
        print(f"  Error accessing {table}: {e}")

conn.commit()
conn.close()
print("Cleanup complete!")
