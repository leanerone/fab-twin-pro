"""
FabTwin Oracle DB Connection Test
Tests 3 connection methods: Thin, Thick (subprocess), Backend config

Key fixes:
- Thick mode test runs in subprocess (Thin -> Thick cannot switch in same process)
- lib_dir detection handles both Instant Client (oci.dll in root) and Full Client (oci.dll in bin\\)
- Adds oracledb version check
- Sets TNS_ADMIN for backend test if network\\admin exists
"""
import os
import sys
import glob
import subprocess
import traceback

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
log(f"Target DB: {DB_USER}/****@{DB_HOST}:{DB_PORT}:{DB_SID}")
log(f"DSN Type:  {DB_DSN_TYPE}")
log("")


# ---- Helpers ----
def find_oracle_client_root():
    """Find Oracle Client root directory (parent of bin). Returns '' if not found."""
    env_dir = os.environ.get('ORACLE_CLIENT_DIR', '')
    if env_dir and os.path.exists(os.path.join(env_dir, 'bin', 'oci.dll')):
        return env_dir
    if env_dir and os.path.exists(os.path.join(env_dir, 'oci.dll')):
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
        if os.path.exists(os.path.join(p, 'oci.dll')):
            return p
    for pattern in [r'C:\app\client\*\product\*\client_1', r'C:\oracle\*\product\*\client_1']:
        for p in glob.glob(pattern):
            if os.path.exists(os.path.join(p, 'bin', 'oci.dll')):
                return p
            if os.path.exists(os.path.join(p, 'oci.dll')):
                return p
    for root in [r'C:\app', r'C:\oracle']:
        if not os.path.exists(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if 'oci.dll' not in filenames:
                continue
            # If oci.dll is in a bin dir, root is parent
            if dirpath.endswith('\\bin'):
                return os.path.dirname(dirpath)
            # Otherwise oci.dll is in the dir itself (Instant Client layout)
            return dirpath
    return ''


def find_lib_dir(client_root):
    """Return the directory that directly contains oci.dll. '' if not found.

    - Full Client install: client_root\\bin\\oci.dll  -> returns client_root\\bin
    - Instant Client:      client_root\\oci.dll        -> returns client_root
    """
    if not client_root:
        return ''
    bin_dir = os.path.join(client_root, 'bin')
    if os.path.exists(os.path.join(bin_dir, 'oci.dll')):
        return bin_dir
    if os.path.exists(os.path.join(client_root, 'oci.dll')):
        return client_root
    return ''


def find_tns_admin(client_root, lib_dir):
    """Find tnsnames.ora directory. Returns '' if not found."""
    candidates = []
    if client_root:
        candidates.append(os.path.join(client_root, 'network', 'admin'))
    if lib_dir:
        candidates.append(os.path.join(os.path.dirname(lib_dir), 'network', 'admin'))
    # TNS_ADMIN env var takes priority
    env_tns = os.environ.get('TNS_ADMIN', '')
    if env_tns and os.path.exists(env_tns):
        return env_tns
    for c in candidates:
        if os.path.exists(c):
            return c
    return ''


# ---- Check oracledb version ----
log("[0/3] Checking oracledb version...")
try:
    import oracledb
    log(f"  oracledb version: {oracledb.__version__}")
    ver_parts = oracledb.__version__.split('.')
    major = int(ver_parts[0])
    if major >= 4:
        log("  WARNING: oracledb 4.x has known DPI-1047 issues. Recommend: pip install oracledb==2.4.0")
    elif major == 2:
        log("  OK: oracledb 2.x is the recommended version for Oracle 11g")
    else:
        log(f"  INFO: oracledb {oracledb.__version__} (untested)")
except ImportError:
    log("  ERROR: oracledb package not installed")
    sys.exit(1)
log("")


# ---- Test 1: Thin mode ----
log("[1/3] Testing with python-oracledb Thin mode (no Oracle Client needed)...")
try:
    if DB_DSN_TYPE == 'sid':
        dsn = oracledb.makedsn(DB_HOST, DB_PORT, sid=DB_SID)
    else:
        dsn = oracledb.makedsn(DB_HOST, DB_PORT, service_name=DB_SID)
    conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=dsn)
    cur = conn.cursor()
    cur.execute('SELECT banner FROM v$version WHERE ROWNUM = 1')
    ver = cur.fetchone()[0]
    log(f"  OK: Thin mode connected")
    log(f"  DB Version: {ver}")
    conn.close()
except Exception as e:
    log(f"  FAILED: Thin mode: {type(e).__name__}: {e}")
    log("  (Thin mode only supports Oracle 12.1+. For 10g/11g, use Thick mode.)")


# ---- Test 2: Thick mode (subprocess) ----
log("")
log("[2/3] Testing with python-oracledb Thick mode (subprocess, requires Oracle Client)...")
client_root = find_oracle_client_root()
lib_dir = find_lib_dir(client_root) if client_root else ''
tns_admin = find_tns_admin(client_root, lib_dir)

if not client_root:
    log("  SKIP: Oracle Client (oci.dll) not found, cannot test Thick mode")
elif not lib_dir:
    log(f"  SKIP: client_root found but oci.dll missing: {client_root}")
else:
    log(f"  Oracle Client root: {client_root}")
    log(f"  Library dir (oci.dll): {lib_dir}")
    if tns_admin:
        log(f"  TNS admin dir: {tns_admin}")
    else:
        log("  TNS admin dir: not found (will use EZCONNECT via makedsn)")

    # Thick mode must run in a fresh subprocess because Thin mode (Test 1)
    # already initialized oracledb in this process and cannot be switched.
    thick_code = (
        "import sys, os\n"
        "import oracledb\n"
        "try:\n"
        "    lib_dir = sys.argv[1]\n"
        "    host = sys.argv[2]\n"
        "    port = int(sys.argv[3])\n"
        "    sid = sys.argv[4]\n"
        "    user = sys.argv[5]\n"
        "    pwd = sys.argv[6]\n"
        "    dsn_type = sys.argv[7]\n"
        "    tns_admin = sys.argv[8] if len(sys.argv) > 8 else ''\n"
        "    if tns_admin and os.path.exists(tns_admin):\n"
        "        os.environ['TNS_ADMIN'] = tns_admin\n"
        "    oracledb.init_oracle_client(lib_dir=lib_dir)\n"
        "    if dsn_type == 'sid':\n"
        "        dsn = oracledb.makedsn(host, port, sid=sid)\n"
        "    else:\n"
        "        dsn = oracledb.makedsn(host, port, service_name=sid)\n"
        "    conn = oracledb.connect(user=user, password=pwd, dsn=dsn)\n"
        "    cur = conn.cursor()\n"
        "    cur.execute('SELECT banner FROM v$version WHERE ROWNUM = 1')\n"
        "    ver = cur.fetchone()[0]\n"
        "    print('OK:' + ver)\n"
        "    conn.close()\n"
        "except Exception as e:\n"
        "    import traceback\n"
        "    print('ERR:' + type(e).__name__ + ':' + str(e))\n"
        "    traceback.print_exc()\n"
        "    sys.exit(1)\n"
    )

    try:
        result = subprocess.run(
            [sys.executable, '-c', thick_code, lib_dir, DB_HOST, str(DB_PORT),
             DB_SID, DB_USER, DB_PASSWORD, DB_DSN_TYPE, tns_admin],
            capture_output=True, text=True, timeout=60, encoding='utf-8', errors='replace'
        )
        out = (result.stdout or '').strip()
        err = (result.stderr or '').strip()
        if result.returncode == 0 and out.startswith('OK:'):
            log(f"  OK: Thick mode connected")
            log(f"  DB Version: {out[3:]}")
        else:
            # Extract the ERR: line if present
            for line in out.splitlines():
                if line.startswith('ERR:'):
                    log(f"  FAILED: Thick mode: {line[4:]}")
                    break
            else:
                log(f"  FAILED: Thick mode: {out or err or 'unknown error'}")
            if err:
                log("  --- traceback ---")
                for line in err.splitlines()[-8:]:
                    log(f"  {line}")
    except subprocess.TimeoutExpired:
        log("  FAILED: Thick mode timeout (60s)")
    except Exception as e:
        log(f"  FAILED: subprocess error: {e}")


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
if client_root:
    os.environ['ORACLE_CLIENT_DIR'] = client_root
if tns_admin:
    os.environ['TNS_ADMIN'] = tns_admin

# Run backend test in subprocess too, so it starts fresh (Thick mode init is process-global)
backend_code = (
    "import sys, os\n"
    "sys.path.insert(0, " + repr(BACKEND_DIR) + ")\n"
    "os.environ.update({k: v for k, v in {\n"
    "    'DB_TYPE': 'oracle',\n"
    "    'ORACLE_HOST': " + repr(DB_HOST) + ",\n"
    "    'ORACLE_PORT': " + repr(str(DB_PORT)) + ",\n"
    "    'ORACLE_USER': " + repr(DB_USER) + ",\n"
    "    'ORACLE_PASSWORD': " + repr(DB_PASSWORD) + ",\n"
    "    'ORACLE_SERVICE': " + repr(DB_SID) + ",\n"
    "    'ORACLE_DSN_TYPE': " + repr(DB_DSN_TYPE) + ",\n"
    "}.items() if v})\n"
    "if " + repr(client_root) + ":\n"
    "    os.environ['ORACLE_CLIENT_DIR'] = " + repr(client_root) + "\n"
    "if " + repr(tns_admin) + ":\n"
    "    os.environ['TNS_ADMIN'] = " + repr(tns_admin) + "\n"
    "try:\n"
    "    from database import engine\n"
    "    import sqlalchemy\n"
    "    conn = engine.connect()\n"
    "    result = conn.execute(sqlalchemy.text('SELECT banner FROM v$version WHERE ROWNUM = 1'))\n"
    "    ver = result.scalar()\n"
    "    print('OK:' + str(ver))\n"
    "    conn.close()\n"
    "except Exception as e:\n"
    "    import traceback\n"
    "    print('ERR:' + type(e).__name__ + ':' + str(e))\n"
    "    traceback.print_exc()\n"
    "    sys.exit(1)\n"
)

try:
    result = subprocess.run(
        [sys.executable, '-c', backend_code],
        capture_output=True, text=True, timeout=60, encoding='utf-8', errors='replace',
        cwd=BACKEND_DIR
    )
    out = (result.stdout or '').strip()
    err = (result.stderr or '').strip()
    if result.returncode == 0 and out.startswith('OK:'):
        log(f"  OK: Backend config connected")
        log(f"  DB Version: {out[3:]}")
    else:
        for line in out.splitlines():
            if line.startswith('ERR:'):
                log(f"  FAILED: Backend config: {line[4:]}")
                break
        else:
            log(f"  FAILED: Backend config: {out or err or 'unknown error'}")
        if err:
            log("  --- traceback (last 10 lines) ---")
            for line in err.splitlines()[-10:]:
                log(f"  {line}")
except subprocess.TimeoutExpired:
    log("  FAILED: Backend config timeout (60s)")
except Exception as e:
    log(f"  FAILED: subprocess error: {e}")


# ---- Summary ----
log("")
log("=" * 60)
log("Test Complete")
log("=" * 60)
log("")
log("Tips:")
log("  - Thin mode (Test 1) works only for Oracle 12.1+")
log("  - Thick mode (Test 2) is required for Oracle 10g/11g")
log("  - If Thick fails with DPI-1047: downgrade oracledb to 2.4.0")
log("    command: pip install oracledb==2.4.0")
log("  - If Thick fails with lib_dir error: ensure ORACLE_CLIENT_DIR points to")
log("    the directory containing oci.dll (e.g. client_1\\bin for Full Client)")
log("")
log(f"Full report: {REPORT}")
