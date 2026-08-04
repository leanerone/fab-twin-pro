"""Add PODOPENER machines to database
Run: backend\venv\Scripts\python.exe add_podopener_machines.py
"""
import os
import sys

if '__file__' in globals():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
else:
    BASE_DIR = os.getcwd()
    BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
sys.path.insert(0, BACKEND_DIR)

from database import SessionLocal
from models import Machine
from datetime import datetime

print("=" * 60)
print("Add PODOPENER-2 ~ PODOPENER-7")
print("=" * 60)

db = SessionLocal()
try:
    new_machines = [
        {"id": "PODOPENER-2", "name": "POD開蓋机 PODOPENER-2", "model": "PODOPENER-2200", "state": "run", "floor_id": 3, "floor_x": 15, "floor_y": 25},
        {"id": "PODOPENER-3", "name": "POD開蓋机 PODOPENER-3", "model": "PODOPENER-2200", "state": "run", "floor_id": 3, "floor_x": 30, "floor_y": 25},
        {"id": "PODOPENER-4", "name": "POD開蓋机 PODOPENER-4", "model": "PODOPENER-2200", "state": "run", "floor_id": 3, "floor_x": 45, "floor_y": 25},
        {"id": "PODOPENER-5", "name": "POD開蓋机 PODOPENER-5", "model": "PODOPENER-2200", "state": "run", "floor_id": 3, "floor_x": 15, "floor_y": 45},
        {"id": "PODOPENER-6", "name": "POD開蓋机 PODOPENER-6", "model": "PODOPENER-2200", "state": "run", "floor_id": 3, "floor_x": 30, "floor_y": 45},
        {"id": "PODOPENER-7", "name": "POD開蓋机 PODOPENER-7", "model": "PODOPENER-2200", "state": "run", "floor_id": 3, "floor_x": 45, "floor_y": 45},
    ]

    added = 0
    skipped = 0
    for m in new_machines:
        existing = db.query(Machine).filter(Machine.id == m['id']).first()
        if existing:
            print(f"SKIP: {m['id']} already exists")
            skipped += 1
        else:
            machine = Machine(
                id=m['id'],
                name=m['name'],
                model=m['model'],
                state=m['state'],
                floor=m['floor_id'],
                floor_x=m.get('floor_x', 50),
                floor_y=m.get('floor_y', 50),
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            db.add(machine)
            added += 1
            print(f"ADD: {m['id']} -> model={m['model']}, floor={m['floor_id']}, pos=({m.get('floor_x', 50)}%, {m.get('floor_y', 50)}%)")

    if added > 0:
        db.commit()
        print(f"\nCommitted {added} new machines")

    print(f"\nTotal PODOPENER machines:")
    for m in db.query(Machine).filter(Machine.id.like('PODOPENER-%')).order_by(Machine.id).all():
        print(f"  {m.id}: model={m.model}, state={m.state}")

finally:
    db.close()

print("\n" + "=" * 60)
print("Done")
print("=" * 60)
