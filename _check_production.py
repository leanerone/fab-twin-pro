"""
Production Database Status Checker
- READ ONLY: does NOT modify any data
- Checks: Machine data, MachineModelConfig, DT_EVENT_RAW data, model mapping
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
sys.path.insert(0, BACKEND_DIR)

from database import SessionLocal, DB_IS_SQLITE
from models import Machine, MachineModelConfig, DT_EVENT_RAW
from config import DB_TYPE, ORACLE_HOST, ORACLE_SERVICE, ORACLE_DSN_TYPE

db = SessionLocal()

print("=" * 70)
print("FabTwin Production Database Status Check")
print("=" * 70)
print(f"DB Type: {DB_TYPE.upper()}")
print(f"DB Connection: {ORACLE_HOST}:{ORACLE_SERVICE} (DSN_TYPE={ORACLE_DSN_TYPE})")
print(f"Is SQLite: {DB_IS_SQLITE}")
print()

# 1. Machine table
print("--- 1. Machine Table ---")
machines = db.query(Machine).all()
print(f"Total machines: {len(machines)}")
if machines:
    for m in machines:
        print(f"  - id={m.id}, model={m.model}, state={m.state}, name={m.name or 'N/A'}")

# 2. MachineModelConfig table
print("\n--- 2. MachineModelConfig Table ---")
models = db.query(MachineModelConfig).all()
print(f"Total model configs: {len(models)}")
if models:
    for m in models:
        print(f"  - model_id={m.model_id}, name={m.model_name}, view_mode={m.view_mode}, vendor={m.vendor}")
else:
    print("  WARNING: NO MODEL CONFIGS FOUND! VPO views won't work")

# 3. Model mapping check
print("\n--- 3. Machine -> Model Mapping ---")
if machines and models:
    model_ids = {m.model_id for m in models}
    for machine in machines:
        if machine.model in model_ids:
            mc = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == machine.model).first()
            status = "OK" if mc and mc.view_mode else "NO VIEW_MODE"
            print(f"  {machine.id} -> {machine.model}: {status}")
        else:
            print(f"  {machine.id} -> {machine.model}: MISSING!")

# 4. DT_EVENT_RAW data
print("\n--- 4. DT_EVENT_RAW Data ---")
total_events = db.query(DT_EVENT_RAW).count()
print(f"Total records: {total_events}")

if total_events > 0:
    # Time range
    min_ts = db.query(DT_EVENT_RAW.event_ts_utc).order_by(DT_EVENT_RAW.event_ts_utc.asc()).first()
    max_ts = db.query(DT_EVENT_RAW.event_ts_utc).order_by(DT_EVENT_RAW.event_ts_utc.desc()).first()
    print(f"\nTime range:")
    print(f"  Min: {min_ts[0]}")
    print(f"  Max: {max_ts[0]}")

    # Timestamp format sample
    samples = db.query(DT_EVENT_RAW.event_ts_utc).limit(10).all()
    print(f"\nTimestamp format sample (first 10):")
    for ts in samples:
        t = str(ts[0]) if ts[0] else ""
        fmt = "T-sep" if 'T' in t else ("space-sep" if ' ' in t else "unknown")
        print(f"  {t[:30]}... [{fmt}]")

    # Tool IDs with data
    tools = db.query(DT_EVENT_RAW.tool_id).distinct().limit(20).all()
    tool_list = [t[0] for t in tools if t[0]]
    print(f"\nDistinct tool_ids (first 20):")
    for t in tool_list:
        cnt = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id == t).count()
        print(f"  {t}: {cnt} records")

    # Check if machines have data
    print("\n--- 5. Machine Data Coverage ---")
    if machines:
        for m in machines:
            cnt = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id == m.id).count()
            print(f"  {m.id}: {cnt} events in DT_EVENT_RAW")

# 5. VPO specific check
print("\n--- 6. VPO Model Check ---")
vpo_models = db.query(MachineModelConfig).filter(MachineModelConfig.view_mode == "vpo").all()
print(f"VPO models (view_mode='vpo'): {len(vpo_models)}")
if vpo_models:
    for vm in vpo_models:
        print(f"  - {vm.model_id}: {vm.model_name}")

    # Check which machines use VPO models
    vpo_model_ids = {vm.model_id for vm in vpo_models}
    vpo_machines = [m for m in machines if m.model in vpo_model_ids]
    print(f"\nMachines using VPO models: {len(vpo_machines)}")
    for m in vpo_machines:
        print(f"  - {m.id} (model={m.model})")

db.close()

print("\n" + "=" * 70)
print("Check Complete. No data was modified.")
print("\nIssues to fix (if any):")
print("1. If 'NO MODEL CONFIGS FOUND': Need to add MachineModelConfig for VPO")
print("2. If 'MISSING!' in mapping: Machine.model doesn't match any model_id")
print("3. If machines have 0 events: Check tool_id matching between Machine and DT_EVENT_RAW")
