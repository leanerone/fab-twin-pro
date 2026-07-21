"""
FabTwin VPO Model & History Data Diagnostic Tool
Checks:
1. Oracle connection status
2. DT_EVENT_RAW table data count and time range
3. MachineModelConfig for VPO models (view_mode=vpo)
4. Machine -> Model mapping consistency
5. Timestamp format issues in DB
6. VPO model files existence
"""
import os
import sys
import json
import re
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
REPORT = os.path.join(BASE_DIR, 'vpo_history_check_report.txt')

sys.path.insert(0, BACKEND_DIR)


def log(msg):
    print(msg)
    with open(REPORT, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')


def _normalize_ts(ts: str) -> str:
    if not ts:
        return ""
    ts = str(ts).strip()
    ts = re.sub(r'(Z|[+-]\d{2}:\d{2})$', '', ts)
    ts = ts.replace('T', ' ')
    return ts


with open(REPORT, 'w', encoding='utf-8') as f:
    f.write(f"FabTwin VPO Model & History Diagnostic Report\n")
    f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write("=" * 70 + "\n\n")

log("=" * 70)
log("FabTwin VPO Model & History Data Diagnostic")
log("=" * 70)
log("")

errors = 0

# ---- Check 1: DB connection ----
log("[1/8] Checking database connection and type...")
try:
    from database import engine, SessionLocal, DB_IS_SQLITE
    from config import DB_TYPE, ORACLE_HOST, ORACLE_PORT, ORACLE_SERVICE

    db = SessionLocal()
    from sqlalchemy import text
    db.execute(text("SELECT 1 FROM DUAL" if not DB_IS_SQLITE else "SELECT 1"))
    log(f"  OK: Connected to {DB_TYPE.upper()}")
    if not DB_IS_SQLITE:
        log(f"  Oracle: {ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}")
    db.close()
except Exception as e:
    log(f"  ERROR: DB connection failed: {e}")
    errors += 1
    sys.exit(1)

# ---- Check 2: DT_EVENT_RAW data ----
log("")
log("[2/8] Checking DT_EVENT_RAW history data...")
try:
    from models import DT_EVENT_RAW
    db = SessionLocal()
    try:
        total = db.query(DT_EVENT_RAW).count()
        log(f"  Total records: {total}")

        if total > 0:
            min_ts = db.query(DT_EVENT_RAW.event_ts_utc).order_by(DT_EVENT_RAW.event_ts_utc.asc()).first()
            max_ts = db.query(DT_EVENT_RAW.event_ts_utc).order_by(DT_EVENT_RAW.event_ts_utc.desc()).first()
            log(f"  Time range: {min_ts[0]} ~ {max_ts[0]}")

            # Check timestamp format distribution
            sample_ts = db.query(DT_EVENT_RAW.event_ts_utc).limit(20).all()
            formats = {}
            for ts in sample_ts:
                t = str(ts[0]) if ts[0] else ""
                if 'T' in t:
                    formats['T_separator'] = formats.get('T_separator', 0) + 1
                elif ' ' in t:
                    formats['space_separator'] = formats.get('space_separator', 0) + 1
                if t.endswith('Z'):
                    formats['Z_suffix'] = formats.get('Z_suffix', 0) + 1
            log(f"  Timestamp formats in sample: {formats}")

            # Check VPO/PODOPENER specific data
            vpo_tools = [r[0] for r in db.query(DT_EVENT_RAW.tool_id).distinct().all() if r[0] and ('VPO' in r[0] or 'PODOPENER' in r[0])]
            log(f"  VPO/PODOPENER tools with data: {vpo_tools}")
            for tool in vpo_tools:
                cnt = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id == tool).count()
                log(f"    - {tool}: {cnt} records")

            # Check OXE tools
            oxe_tools = [r[0] for r in db.query(DT_EVENT_RAW.tool_id).distinct().all() if r[0] and 'OXE' in r[0]]
            log(f"  OXE tools with data (first 10): {oxe_tools[:10]}")

            # Check event types
            event_types = db.query(DT_EVENT_RAW.source_system).distinct().all()
            log(f"  Source systems: {[r[0] for r in event_types]}")

        else:
            log("  WARNING: DT_EVENT_RAW is empty - no history data")
            errors += 1
    finally:
        db.close()
except Exception as e:
    log(f"  ERROR: {e}")
    errors += 1

# ---- Check 3: MachineModelConfig ----
log("")
log("[3/8] Checking MachineModelConfig (view_mode=vpo)...")
try:
    from models import MachineModelConfig
    db = SessionLocal()
    try:
        all_models = db.query(MachineModelConfig).all()
        log(f"  Total model configs: {len(all_models)}")

        vpo_models = [m for m in all_models if m.view_mode == 'vpo']
        if vpo_models:
            log(f"  VPO models found: {len(vpo_models)}")
            for m in vpo_models:
                views = json.loads(m.views_config_json) if m.views_config_json else {}
                log(f"  - model_id={m.model_id}, view_mode={m.view_mode}")
                log(f"    views_config: {json.dumps(views, ensure_ascii=False)[:100]}...")
        else:
            log("  WARNING: No VPO model config found (view_mode=vpo)")
            errors += 1
            # List all models
            for m in all_models:
                log(f"    - model_id={m.model_id}, view_mode={m.view_mode}")

        # Check if PODOPENER-2200 model exists (used by PODOPENER-1 machine)
        pod_model = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == 'PODOPENER-2200').first()
        if pod_model:
            log(f"  OK: PODOPENER-2200 model config exists")
        else:
            log(f"  ERROR: PODOPENER-2200 model config NOT FOUND")
            log(f"         But VPO-2200 may exist - checking...")
            vpo2200 = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == 'VPO-2200').first()
            if vpo2200:
                log(f"         VPO-2200 exists but PODOPENER-2200 doesn't - model_id mismatch!")
            errors += 1
    finally:
        db.close()
except Exception as e:
    log(f"  ERROR: {e}")
    errors += 1

# ---- Check 4: Machine -> Model mapping ----
log("")
log("[4/8] Checking Machine -> Model mapping consistency...")
try:
    from models import Machine, MachineModelConfig
    db = SessionLocal()
    try:
        machines = db.query(Machine).all()
        log(f"  Total machines: {len(machines)}")

        vpo_machines = [m for m in machines if m.id.startswith('VPO') or m.process_type == 'PODOPENER']
        log(f"  VPO/PODOPENER machines: {len(vpo_machines)}")

        for m in vpo_machines:
            config = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == m.model).first()
            if config:
                log(f"  OK: {m.id} -> model={m.model} (view_mode={config.view_mode})")
            else:
                log(f"  ERROR: {m.id} -> model={m.model} NOT FOUND in MachineModelConfig")
                errors += 1

        # Check OXE machines
        oxe_machines = [m for m in machines if m.id.startswith('OXE')]
        log(f"  OXE machines: {len(oxe_machines)} (first 5)")
        for m in oxe_machines[:5]:
            config = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == m.model).first()
            status = "OK" if config else "NOT FOUND"
            vm = config.view_mode if config else "N/A"
            log(f"    {m.id} -> model={m.model} ({status}, view_mode={vm})")

    finally:
        db.close()
except Exception as e:
    log(f"  ERROR: {e}")
    errors += 1

# ---- Check 5: Model files existence ----
log("")
log("[5/8] Checking VPO model files...")
models_dir = os.path.join(BASE_DIR, 'frontend', 'public', 'models')
if os.path.exists(models_dir):
    log(f"  Models dir: {models_dir}")
    for f in os.listdir(models_dir):
        if 'podopener' in f.lower() or 'vpo' in f.lower():
            size = os.path.getsize(os.path.join(models_dir, f))
            log(f"  Found: {f} ({size} bytes)")
else:
    log(f"  WARNING: Models dir not found: {models_dir}")
    errors += 1

# ---- Check 6: API endpoint test ----
log("")
log("[6/8] Testing API endpoints...")
try:
    import urllib.request
    import urllib.error

    api_url = "http://localhost:8002/api/models"
    try:
        resp = urllib.request.urlopen(api_url, timeout=5)
        data = resp.read().decode('utf-8')
        log(f"  OK: GET /api/models ({resp.status})")
        import json as _json
        models_data = _json.loads(data)
        log(f"  Models count: {len(models_data)}")
        vpo_items = [m for m in models_data if m.get('view_mode') == 'vpo']
        log(f"  VPO models in API: {len(vpo_items)}")
    except urllib.error.URLError as e:
        log(f"  WARNING: API not reachable: {e}")
        log(f"  (May be OK if backend isn't running)")

    # Test history API
    api_history = "http://localhost:8002/api/history/PODOPENER-1?limit=5"
    try:
        resp = urllib.request.urlopen(api_history, timeout=5)
        data = resp.read().decode('utf-8')
        log(f"  OK: GET /api/history/PODOPENER-1 ({resp.status})")
        hist_data = _json.loads(data)
        log(f"  History events: {hist_data.get('total', 0)}")
    except urllib.error.URLError as e:
        log(f"  WARNING: History API not reachable: {e}")

except Exception as e:
    log(f"  ERROR: {e}")

# ---- Check 7: Timestamp format comparison ----
log("")
log("[7/8] Checking timestamp format compatibility...")
try:
    from models import DT_EVENT_RAW
    db = SessionLocal()
    try:
        # Get a sample of timestamps
        samples = db.query(DT_EVENT_RAW.event_ts_utc, DT_EVENT_RAW.received_ts_utc).limit(10).all()
        log(f"  Sample timestamp formats:")
        for i, (evt_ts, rec_ts) in enumerate(samples):
            evt_norm = _normalize_ts(evt_ts)
            rec_norm = _normalize_ts(rec_ts)
            log(f"    [{i}] event_ts_utc={evt_ts!r} -> normalized={evt_norm!r}")
            log(f"         received_ts_utc={rec_ts!r} -> normalized={rec_norm!r}")

        # Test if current date would find data
        today = datetime.now().strftime("%Y-%m-%d")
        today_start = f"{today} 00:00:00"
        today_end = f"{today} 23:59:59"
        today_count = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.event_ts_utc >= today_start).filter(DT_EVENT_RAW.event_ts_utc <= today_end).count()
        log(f"  Today's data ({today}): {today_count} records")

        # Check last 7 days
        for days_ago in [1, 3, 7, 14, 30]:
            start_date = (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d 00:00:00")
            cnt = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.event_ts_utc >= start_date).count()
            log(f"  Last {days_ago} days: {cnt} records")

    finally:
        db.close()
except Exception as e:
    log(f"  ERROR: {e}")
    errors += 1

# ---- Check 8: Seed data generation status ----
log("")
log("[8/8] Checking seed data generation status...")
try:
    from models import DT_EVENT_RAW, MachineModelConfig, Machine
    db = SessionLocal()
    try:
        raw_count = db.query(DT_EVENT_RAW).count()
        model_count = db.query(MachineModelConfig).count()
        machine_count = db.query(Machine).count()

        log(f"  DT_EVENT_RAW: {raw_count} records")
        log(f"  MachineModelConfig: {model_count} records")
        log(f"  Machines: {machine_count} records")

        # Check if seed data is from the default sample (base_time=2026-06-14)
        if raw_count > 0:
            early_count = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.event_ts_utc < '2026-07-01').count()
            late_count = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.event_ts_utc >= '2026-07-01').count()
            log(f"  Data before 2026-07-01: {early_count}")
            log(f"  Data from 2026-07-01 onwards: {late_count}")

            if late_count == 0 and early_count > 0:
                log("  WARNING: All data is older than July 2026 - history may not show recent dates")
                log("  This is expected if seed_data.py generated sample data (base_time=2026-06-14)")

        # Check if Oracle has real RV data vs seed data
        if not DB_IS_SQLITE:
            # Real RV data typically has tool_ids like VPO-01, PODOPENER-1, etc.
            # Check for VPO patterns that might be missing
            vpo_patterns = ['VPO-', 'PODOPENER-']
            for pattern in vpo_patterns:
                cnt = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id.like(f'{pattern}%')).count()
                log(f"  {pattern}* tools in DT_EVENT_RAW: {cnt} records")

    finally:
        db.close()
except Exception as e:
    log(f"  ERROR: {e}")
    errors += 1

# ---- Summary ----
log("")
log("=" * 70)
if errors == 0:
    log("  Result: ALL CHECKS PASSED")
else:
    log(f"  Result: {errors} error(s) found")
log("=" * 70)
log("")
log("Common fixes:")
log("  1. If VPO model not loading: Check MachineModelConfig view_mode='vpo'")
log("  2. If model_id mismatch: Machine.model='PODOPENER-2200' must match MachineModelConfig.model_id")
log("  3. If history empty: Check DT_EVENT_RAW has data, or run seed_data.py")
log("  4. If timestamp mismatch: Oracle uses space separator 'YYYY-MM-DD HH:MM:SS'")
log("  5. If seed data old: The default sample starts from 2026-06-14")
log("")
log(f"Full report: {REPORT}")
