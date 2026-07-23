import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from sqlalchemy import text
    from database import SessionLocal
    db = SessionLocal()
    db.execute(text('SELECT 1 FROM DUAL'))
    print('Database connection: OK')
    db.close()
except Exception as e:
    print(f'Database connection test failed: {e}')
    sys.exit(1)
