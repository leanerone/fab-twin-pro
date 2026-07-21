"""
Quick timestamp format checker for Oracle DT_EVENT_RAW
"""
import os
import sys
import re
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
sys.path.insert(0, BACKEND_DIR)

from database import SessionLocal, DB_IS_SQLITE
from models import DT_EVENT_RAW
from config import DB_TYPE

db = SessionLocal()

print("=" * 60)
print("DT_EVENT_RAW Timestamp Format Check")
print("=" * 60)
print(f"DB Type: {DB_TYPE.upper()}")
print()

total = db.query(DT_EVENT_RAW).count()
print(f"Total records: {total}")

if total == 0:
    print("No data in DT_EVENT_RAW")
    sys.exit(0)

from sqlalchemy import func
ts_col = func.coalesce(DT_EVENT_RAW.event_ts_utc, DT_EVENT_RAW.received_ts_utc)

min_ts = db.query(ts_col).order_by(ts_col.asc()).first()
max_ts = db.query(ts_col).order_by(ts_col.desc()).first()
print(f"\nTime range:")
print(f"  Min: {min_ts[0]}")
print(f"  Max: {max_ts[0]}")

samples = db.query(DT_EVENT_RAW.event_ts_utc, DT_EVENT_RAW.received_ts_utc).limit(50).all()
formats = {'T_sep': 0, 'space_sep': 0, 'Z_suffix': 0, 'no_sep': 0}
for evt_ts, rec_ts in samples:
    t = str(evt_ts) if evt_ts else str(rec_ts) if rec_ts else ""
    if 'T' in t:
        formats['T_sep'] += 1
    elif ' ' in t:
        formats['space_sep'] += 1
    else:
        formats['no_sep'] += 1
    if t.endswith('Z'):
        formats['Z_suffix'] += 1

print(f"\nTimestamp format distribution (sample 50):")
print(f"  T separator: {formats['T_sep']}")
print(f"  Space separator: {formats['space_sep']}")
print(f"  Z suffix: {formats['Z_suffix']}")

print("\n--- Query Test ---")

test_date = "2026-07-21"
test_dt = datetime.strptime(f"{test_date} 00:00:00", "%Y-%m-%d %H:%M:%S")
count = db.query(DT_EVENT_RAW).filter(ts_col >= test_dt).count()
print(f"  Query ts >= '{test_date} 00:00:00' (datetime): {count} records")

print("\n--- 7-16 ~ 7-21 Data Check ---")
for day in range(16, 22):
    start = datetime.strptime(f"2026-07-{day:02d} 00:00:00", "%Y-%m-%d %H:%M:%S")
    end = datetime.strptime(f"2026-07-{day:02d} 23:59:59", "%Y-%m-%d %H:%M:%S")
    cnt = db.query(DT_EVENT_RAW).filter(ts_col >= start).filter(ts_col <= end).count()
    print(f"  2026-07-{day:02d}: {cnt} records")

print("\n--- Tool IDs ---")
tools = db.query(DT_EVENT_RAW.tool_id).distinct().all()
tool_list = [t[0] for t in tools if t[0]]
print(f"Total distinct tools: {len(tool_list)}")
vpo_tools = [t for t in tool_list if 'VPO' in t or 'PODOPENER' in t]
oxe_tools = [t for t in tool_list if 'OXE' in t]
print(f"VPO/PODOPENER tools: {vpo_tools}")
print(f"OXE tools (first 10): {oxe_tools[:10]}")

print("\n--- PODOPENER-1 History ---")
pod_cnt = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id == 'PODOPENER-1').count()
print(f"PODOPENER-1 records: {pod_cnt}")
if pod_cnt > 0:
    pod_min = db.query(ts_col).filter(DT_EVENT_RAW.tool_id == 'PODOPENER-1').order_by(ts_col.asc()).first()
    pod_max = db.query(ts_col).filter(DT_EVENT_RAW.tool_id == 'PODOPENER-1').order_by(ts_col.desc()).first()
    print(f"  Time range: {pod_min[0]} ~ {pod_max[0]}")

db.close()

print("\n" + "=" * 60)
print("Done")
