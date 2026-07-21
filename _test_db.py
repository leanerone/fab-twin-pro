"""
FabTwin Oracle DB Connection Test
Tests 3 connection methods: Thin, Thick, Backend config
"""
import os
import sys
import glob

# ===== DB Config - modify if needed =====
DB_HOST = '10.30.8.119'
DB_PORT = 1521
DB_SID = 'APCDB'
DB_USER = 'emuuser'
DB_PASSWORD = 'apcuser'
DB_DSN_TYPE = 'sid'  # 'sid' for 10g/11g, 'service_name' for 12c+
# =========================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
REPORT = os.path.join(BASE_DIR, 'db_connection_report.txt')

def log(msg):
    print(msg)
    with open(REPORT, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')

with open(REPORT, 'w', encoding='utf-8') as f:
    f.write("FabTwin Oracle DB Connection Test Report\n")
    f.write(f"Target: {DB_USER}@{DB_HOST}:{DB_PORT} ({DB_DSN_TYPE}={DB_SID})\n")
    f.write("=" * 60 + "\n\n")

log("=" * 60)
log("FabTwin Oracle DB Connection Test")
log("=" * 60)
log(f"Target DB: {DB_USER}/{DB_PASSWORD}@{DB_HOST}:{DB_PORT}:{DB_SID}")
log(f"DSN Type:  {DB_DSN_TYPE}")
log("")

# Find Oracle Client
def find_oracle_client():
    env_dir = os.environ.get('ORACLE_CLIENT_DIR', '')
    if env_dir and os.path.exists(os.path.join(env_dir, 'bin', 'oci.dll')):
        return env_dir
    search_paths = [
        r'C:\oracle\product\19.0.0\client_1',
        r'C:\oracle\product\19.3.0\client_1',
        r'C:\app\oracle\product\19.0.0\client_1',
        r'C:\app\client\admin\product\19.0.0\client_1',
    ]
    for p in search_paths:
        if os.path.exists(os.path.join(p, 'bin', 'oci.dll')):
            return p
    for pattern in [r'C:\app\client\*\product\*\client_1', r'C:\oracle\*\product\*\client_1']:
        for p in glob.glob(pattern):
            if os.path.exists(os.path.join(p, 'bin', 'oci.dll')):
                return p
    for root in [r'C:\app', r'C:\oracle']:
        if not os.path.exists(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if 'oci.dll' in filenames and dirpath.endswith('\\bin'):
                return os.path.dirname(dirpath)
    return ''

# ---- Test 1: Thin mode ----
log("[1/3] Testing with python-oracledb Thin mode...")
try:
    import oracledb
    try:
        if DB_DSN_TYPE == 'sid':
            dsn = oracledb.makedsn(DB_HOST, DB_PORT, sid=DB_SID)
        else:
            dsn = oracledb.makedsn(DB_HOST, DB_PORT, service_name=DB_SID)
        conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=dsn)
        cur = conn.cursor()
        cur.execute('SELECT * FROM v$version')
        ver = cur.fetchone()[0]
        log(f"  OK: Thin mode connected: {ver}")
        conn.close()
    except Exception as e:
        log(f"  FAILED: Thin mode: {e}")
except ImportError:
    log("  ERROR: oracledb package not installed")

# ---- Test 2: Thick mode ----
log("")
log("[2/3] Testing with python-oracledb Thick mode...")
client_dir = find_oracle_client()
if not client_dir:
    log("  SKIP: Oracle Client not found, cannot test Thick mode")
else:
    log(f"  Using Oracle Client: {client_dir}")
    try:
        import importlib
        if 'oracledb' in sys.modules:
            importlib.reload(oracledb)
        try:
            oracledb.init_oracle_client(lib_dir=client_dir)
        except Exception:
            pass  # may already be initialized
        if DB_DSN_TYPE == 'sid':
            dsn = oracledb.makedsn(DB_HOST, DB_PORT, sid=DB_SID)
        else:
            dsn = oracledb.makedsn(DB_HOST, DB_PORT, service_name=DB_SID)
        conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=dsn)
        cur = conn.cursor()
        cur.execute('SELECT * FROM v$version')
        ver = cur.fetchone()[0]
        log(f"  OK: Thick mode connected: {ver}")
        conn.close()
    except Exception as e:
        log(f"  FAILED: Thick mode: {e}")

# ---- Test 3: Backend config ----
log("")
log("[3/3] Testing backend config.py / database.py connection...")
os.environ['DB_TYPE'] = 'oracle'
os.environ['ORACLE_HOST'] = DB_HOST
os.environ['ORACLE_PORT'] = str(DB_PORT)
os.environ['ORACLE_USER'] = DB_USER
os.environ['ORACLE_PASSWORD'] = DB_PASSWORD
os.environ['ORACLE_SERVICE'] = DB_SID
os.environ['ORACLE_DSN_TYPE'] = DB_DSN_TYPE
if client_dir:
    os.environ['ORACLE_CLIENT_DIR'] = client_dir
sys.path.insert(0, BACKEND_DIR)
try:
    from database import engine
    import sqlalchemy
    conn = engine.connect()
    result = conn.execute(sqlalchemy.text('SELECT * FROM v$version'))
    ver = result.scalar()
    log(f"  OK: Backend config connected: {ver}")
    conn.close()
except Exception as e:
    log(f"  FAILED: Backend config: {e}")

log("")
log("=" * 60)
log("Test Complete")
log("=" * 60)
log("")
log(f"Full report: {REPORT}")
