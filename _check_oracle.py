"""
FabTwin Oracle Client Diagnostic Tool
Run via check_oracle.bat - all logic in Python to avoid cmd parsing issues

Key improvements:
- Detects actual lib_dir (oci.dll in bin\\ or root)
- Tests Thick mode in subprocess (avoid module state pollution)
- Checks oracledb version (4.x has DPI-1047 bug, recommend 2.4.0)
- Auto-detects TNS_ADMIN location
"""
import os
import sys
import struct
import subprocess
import glob

# Resolve BASE_DIR robustly (check_oracle.bat runs this via exec() without __file__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
if not BASE_DIR or not os.path.isdir(BASE_DIR):
    BASE_DIR = os.getcwd()
BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
REPORT = os.path.join(BASE_DIR, 'oracle_check_report.txt')
PY_EXE = os.path.join(BACKEND_DIR, 'venv', 'Scripts', 'python.exe')

errors = 0
fixed = 0


def log(msg):
    print(msg)
    with open(REPORT, 'a', encoding='utf-8') as f:
        f.write(msg + '\n')


# Clear report
with open(REPORT, 'w', encoding='utf-8') as f:
    f.write(f"FabTwin Oracle Diagnostic Report\n{'='*60}\n\n")

log("=" * 60)
log("FabTwin Oracle Client Diagnostic")
log("=" * 60)
log("")


# ---- Check 1: Python ----
log("[1/8] Checking Python venv...")
if not os.path.exists(PY_EXE):
    log(f"  ERROR: Python not found at {PY_EXE}")
    log("  Please run deploy.bat first to create venv.")
    sys.exit(1)
log(f"  OK: {PY_EXE}")


# ---- Check 2: Python bitness ----
log("")
log("[2/8] Checking Python architecture...")
py_bits = struct.calcsize('P') * 8
log(f"  Python is {py_bits}-bit")
if py_bits != 64:
    log("  ERROR: Python must be 64-bit to match 64-bit Oracle Client")
    errors += 1
else:
    log("  OK: Python is 64-bit")


# ---- Check 3: oracledb version ----
log("")
log("[3/8] Checking oracledb package version...")
try:
    import oracledb
    ver = oracledb.__version__
    log(f"  oracledb version: {ver}")
    major = int(ver.split('.')[0])
    if major >= 4:
        log("  WARNING: oracledb 4.x has known DPI-1047 issues with Oracle 11g")
        log("  RECOMMEND: pip install oracledb==2.4.0")
        errors += 1
    elif major == 2:
        log("  OK: oracledb 2.x is the recommended version")
    else:
        log(f"  INFO: oracledb {ver} (untested)")
except ImportError:
    log("  ERROR: oracledb package not installed")
    log("  Run: pip install oracledb==2.4.0")
    errors += 1


# ---- Check 4: Find Oracle Client root ----
log("")
log("[4/8] Searching for Oracle Client (oci.dll)...")

client_dir = os.environ.get('ORACLE_CLIENT_DIR', '')
client_found = False

if client_dir and (os.path.exists(os.path.join(client_dir, 'bin', 'oci.dll')) or
                   os.path.exists(os.path.join(client_dir, 'oci.dll'))):
    log(f"  Found from ORACLE_CLIENT_DIR: {client_dir}")
    client_found = True
else:
    if client_dir:
        log(f"  WARNING: ORACLE_CLIENT_DIR={client_dir} but oci.dll not found there")
        log(f"           Checked: {client_dir}\\oci.dll and {client_dir}\\bin\\oci.dll")

if not client_found:
    search_paths = [
        r'C:\oracle\product\19.0.0\client_1',
        r'C:\oracle\product\19.3.0\client_1',
        r'C:\oracle\product\19.0.0\dbhome_1',
        r'C:\oracle\instantclient_19_3',
        r'C:\oracle\instantclient_19_11',
        r'C:\app\oracle\product\19.0.0\client_1',
        r'C:\app\client\admin\product\19.0.0\client_1',
    ]
    for p in search_paths:
        if (os.path.exists(os.path.join(p, 'bin', 'oci.dll')) or
                os.path.exists(os.path.join(p, 'oci.dll'))):
            log(f"  Found Oracle Client: {p}")
            client_dir = p
            client_found = True
            break

if not client_found:
    for pattern in [
        r'C:\app\client\*\product\*\client_1',
        r'C:\app\*\product\*\client_1',
        r'C:\oracle\*\product\*\client_1',
        r'C:\oracle\*\product\*\dbhome_1',
        r'C:\oracle\instantclient_*',
    ]:
        for p in glob.glob(pattern):
            if (os.path.exists(os.path.join(p, 'bin', 'oci.dll')) or
                    os.path.exists(os.path.join(p, 'oci.dll'))):
                log(f"  Found Oracle Client: {p}")
                client_dir = p
                client_found = True
                break
        if client_found:
            break

if not client_found:
    for root in [r'C:\app', r'C:\oracle']:
        if not os.path.exists(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if 'oci.dll' not in filenames:
                continue
            if dirpath.endswith('\\bin'):
                client_dir = os.path.dirname(dirpath)
            else:
                client_dir = dirpath
            log(f"  Found Oracle Client (deep search): {client_dir}")
            client_found = True
            break
        if client_found:
            break

if not client_found:
    log("  ERROR: Oracle Client (oci.dll) not found in common paths.")
    log("  Please install Oracle 19c Client x64 and set ORACLE_CLIENT_DIR.")
    errors += 1
    sys.exit(1)

log(f"  CLIENT_ROOT={client_dir}")


# ---- Check 5: lib_dir (actual oci.dll location) ----
log("")
log("[5/8] Detecting lib_dir (directory containing oci.dll)...")
lib_dir = ''
bin_dir = os.path.join(client_dir, 'bin')
if os.path.exists(os.path.join(bin_dir, 'oci.dll')):
    lib_dir = bin_dir
    log(f"  OK: Full Client layout, lib_dir = {lib_dir}")
elif os.path.exists(os.path.join(client_dir, 'oci.dll')):
    lib_dir = client_dir
    log(f"  OK: Instant Client layout, lib_dir = {lib_dir}")
else:
    log(f"  ERROR: oci.dll not found in {client_dir} or {bin_dir}")
    errors += 1


# ---- Check 6: PATH ----
log("")
log("[6/8] Checking PATH contains Oracle bin...")
path_env = os.environ.get('PATH', '')
# Check both client_dir and lib_dir in PATH
in_path = False
if lib_dir and lib_dir.lower() in path_env.lower():
    in_path = True
if bin_dir.lower() in path_env.lower():
    in_path = True
if in_path:
    log("  OK: PATH contains Oracle bin/lib dir")
else:
    log(f"  WARNING: PATH does not contain {lib_dir or bin_dir}")
    log(f"  To fix (need admin):")
    log(f"    setx PATH \"%PATH%;{lib_dir}\"")


# ---- Check 7: TNS_ADMIN ----
log("")
log("[7/8] Checking TNS_ADMIN / tnsnames.ora location...")
tns_admin_env = os.environ.get('TNS_ADMIN', '')
tns_admin_detected = ''
if tns_admin_env and os.path.exists(tns_admin_env):
    tns_admin_detected = tns_admin_env
    log(f"  OK: TNS_ADMIN env var set: {tns_admin_env}")
else:
    # Try to find network\admin under client_dir or parent of lib_dir
    candidates = []
    if client_dir:
        candidates.append(os.path.join(client_dir, 'network', 'admin'))
    if lib_dir:
        candidates.append(os.path.join(os.path.dirname(lib_dir), 'network', 'admin'))
    for c in candidates:
        if os.path.exists(c):
            tns_admin_detected = c
            break
    if tns_admin_detected:
        log(f"  OK: Found tnsnames.ora dir (not in env): {tns_admin_detected}")
        log(f"  Recommend: setx TNS_ADMIN \"{tns_admin_detected}\"")
    else:
        log(f"  INFO: No TNS_ADMIN / network\\admin found")
        log(f"  (OK if using EZCONNECT/makedsn - no tnsnames.ora needed)")


# ---- Check 8: Test Thick mode (subprocess) ----
log("")
log("[8/8] Testing python-oracledb Thick mode (subprocess)...")

if not lib_dir:
    log("  SKIP: lib_dir not detected, cannot test Thick mode")
    errors += 1
else:
    log(f"  Using lib_dir: {lib_dir}")
    if tns_admin_detected:
        log(f"  Using TNS_ADMIN: {tns_admin_detected}")

    # Run in subprocess so we don't pollute this process's oracledb state
    thick_code = (
        "import sys, os\n"
        "import oracledb\n"
        "try:\n"
        "    lib_dir = sys.argv[1]\n"
        "    tns_admin = sys.argv[2] if len(sys.argv) > 2 else ''\n"
        "    if tns_admin and os.path.exists(tns_admin):\n"
        "        os.environ['TNS_ADMIN'] = tns_admin\n"
        "    oracledb.init_oracle_client(lib_dir=lib_dir)\n"
        "    ver = oracledb.clientversion()\n"
        "    print('OK:' + str(ver))\n"
        "except Exception as e:\n"
        "    import traceback\n"
        "    print('ERR:' + type(e).__name__ + ':' + str(e))\n"
        "    traceback.print_exc()\n"
        "    sys.exit(1)\n"
    )

    try:
        result = subprocess.run(
            [sys.executable, '-c', thick_code, lib_dir, tns_admin_detected],
            capture_output=True, text=True, timeout=30, encoding='utf-8', errors='replace'
        )
        out = (result.stdout or '').strip()
        err = (result.stderr or '').strip()
        if result.returncode == 0 and out.startswith('OK:'):
            log(f"  OK: Thick mode loaded, client version: {out[3:]}")
        else:
            for line in out.splitlines():
                if line.startswith('ERR:'):
                    log(f"  ERROR: Thick mode failed: {line[4:]}")
                    break
            else:
                log(f"  ERROR: Thick mode failed: {out or err or 'unknown'}")
            if err:
                log("  --- traceback ---")
                for line in err.splitlines()[-8:]:
                    log(f"  {line}")
            log("  Common fixes:")
            log("    1. Downgrade oracledb: pip install oracledb==2.4.0")
            log("    2. Install VC++ 2015-2022 Redistributable (x64)")
            log("       https://aka.ms/vs/17/release/vc_redist.x64.exe")
            log("    3. Verify lib_dir contains oci.dll")
            errors += 1
    except subprocess.TimeoutExpired:
        log("  ERROR: Thick mode test timeout (30s)")
        errors += 1
    except Exception as e:
        log(f"  ERROR: subprocess failed: {e}")
        errors += 1


# ---- Summary ----
log("")
log("=" * 60)
if errors == 0:
    log(f"  Result: ALL CHECKS PASSED ({fixed} auto-fixes applied)")
    log("")
    log("  Next steps:")
    log("    1. Run test_db_connection.bat to test DB connection")
    log("    2. Run deploy.bat to start services")
else:
    log(f"  Result: {errors} error(s) found, {fixed} auto-fix(es) applied")
log("=" * 60)
log("")
log(f"  Full report: {REPORT}")
