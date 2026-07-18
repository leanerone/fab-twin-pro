import sys
sys.path.insert(0, ".")

from database import engine, SessionLocal
from models import Machine

print("Testing Oracle connection...")
try:
    db = SessionLocal()
    count = db.query(Machine).count()
    print(f"Connection OK! Machine count: {count}")
    db.close()
except Exception as e:
    print(f"Connection failed: {e}")
    import traceback
    traceback.print_exc()
