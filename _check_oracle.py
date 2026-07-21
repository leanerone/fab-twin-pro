"""
FabTwin Oracle Client Diagnostic Tool
Run via check_oracle.bat - all logic in Python to avoid cmd parsing issues
"""
import os
import sys
import struct
import subprocess
import glob

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
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
    f.write(f"FabTwin Oracle Diagnostic Report\nGenerated: {os.popen('echo %date% %time%').read().strip()}\n{'='*60}\n\n")

log("=" * 60)
log("FabTwin Oracle Client Diagnostic")
log("=" * 60)
log("")

# ---- Check 1: Python ----
log("[1/7] Checking Python venv...")
if not os.path.exists(PY_EXE):
    log(f"  ERROR: Python not found at {PY_EXE}")
    log("  Please run deploy.bat first to create venv.")
    sys.exit(1)
log(f"  OK: {PY_EXE}")

# ---- Check 2: Python bitness ----
log("")
log("[2/7] Checking Python architecture...")
py_bits = struct.calcsize('P') * 8
log(f"  Python is {py_bits}-bit")
if py_bits != 64:
    log("  ERROR: Python must be 64-bit to match 64-bit Oracle Client")
    errors += 1
else:
    log("  OK: Python is 64-bit")

# ---- Check 3: Find Oracle Client ----
log("")
log("[3/7] Searching for Oracle Client (oci.dll)...")

client_dir = os.environ.get('ORACLE_CLIENT_DIR', '')
client_found = False

if client_dir and os.path.exists(os.path.join(client_dir, 'bin', 'oci.dll')):
    log(f"  Found from ORACLE_CLIENT_DIR: {client_dir}")
    client_found = True
else:
    if client_dir:
        log(f"  WARNING: ORACLE_CLIENT_DIR={client_dir} but oci.dll not found")

if not client_found:
    # Search common paths
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
        if os.path.exists(os.path.join(p, 'bin', 'oci.dll')):
            log(f"  Found Oracle Client: {p}")
            client_dir = p
            client_found = True
            break

if not client_found:
    # Search with glob
    for pattern in [
        r'C:\app\client\*\product\*\client_1',
        r'C:\app\*\product\*\client_1',
        r'C:\oracle\*\product\*\client_1',
        r'C:\oracle\*\product\*\dbhome_1',
    ]:
        for p in glob.glob(pattern):
            if os.path.exists(os.path.join(p, 'bin', 'oci.dll')):
                log(f"  Found Oracle Client: {p}")
                client_dir = p
                client_found = True
                break
        if client_found:
            break

if not client_found:
    # Last resort: search whole C:\app and C:\oracle
    for root in [r'C:\app', r'C:\oracle']:
        if not os.path.exists(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            if 'oci.dll' in filenames and dirpath.endswith('\\bin'):
                client_dir = os.path.dirname(dirpath)
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

log(f"  CLIENT_DIR={client_dir}")

# ---- Check 4: PATH ----
log("")
log("[4/7] Checking PATH contains Oracle bin...")
bin_dir = os.path.join(client_dir, 'bin')
path_env = os.environ.get('PATH', '')
if bin_dir.lower() in path_env.lower():
    log("  OK: PATH contains Oracle bin")
else:
    log(f"  WARNING: PATH does not contain {bin_dir}")
    log(f"  To fix, run this command (need admin):")
    log(f"    setx PATH \"%PATH%;{bin_dir}\"")
    log(f"  Or manually add to System Environment Variables")

# ---- Check 5: ORACLE_CLIENT_DIR env var ----
log("")
log("[5/7] Checking ORACLE_CLIENT_DIR env var...")
env_client_dir = os.environ.get('ORACLE_CLIENT_DIR', '')
if env_client_dir == client_dir:
    log("  OK: ORACLE_CLIENT_DIR is set correctly")
else:
    log(f"  Recommended: set ORACLE_CLIENT_DIR={client_dir}")
    log(f"  Run this command (need admin):")
    log(f"    setx ORACLE_CLIENT_DIR \"{client_dir}\"")

# ---- Check 6: VC++ runtime DLLs ----
log("")
log("[6/7] Checking Visual C++ Redistributables...")
required_dlls = ['MSVCR120.dll', 'MSVCP120.dll', 'VCRUNTIME140.dll', 'MSVCP140.dll', 'VCRUNTIME140_1.dll']
missing = []
for dll in required_dlls:
    found = False
    # Check Oracle bin dir
    if os.path.exists(os.path.join(bin_dir, dll)):
        found = True
    # Check System32
    if not found and os.path.exists(os.path.join(r'C:\Windows\System32', dll)):
        found = True
    if not found:
        missing.append(dll)

if not missing:
    log("  OK: Required VC++ runtime DLLs found")
else:
    log(f"  WARNING: Missing VC++ DLLs: {', '.join(missing)}")
    log("  Please install:")
    log("    - Microsoft Visual C++ 2013 Redistributable (x64)")
    log("    - Microsoft Visual C++ 2015-2022 Redistributable (x64)")
    log("  Download: https://aka.ms/vs/17/release/vc_redist.x64.exe")
    errors += 1

# ---- Check 7: Test Thick mode ----
log("")
log("[7/7] Testing python-oracledb Thick mode...")
try:
    import oracledb
    try:
        oracledb.init_oracle_client(lib_dir=client_dir)
        client_ver = oracledb.clientversion()
        log(f"  OK: Thick mode loaded, client version: {client_ver}")
    except Exception as e:
        log(f"  ERROR: Thick mode failed: {e}")
        log("  Common fix: Install VC++ Redistributables, then restart cmd.")
        errors += 1
except ImportError:
    log("  ERROR: oracledb package not installed")
    log("  Run: pip install oracledb")
    errors += 1

# ---- Summary ----
log("")
log("=" * 60)
if errors == 0:
    log(f"  Result: ALL CHECKS PASSED ({fixed} auto-fixes applied)")
else:
    log(f"  Result: {errors} error(s) found, {fixed} auto-fix(es) applied")
log("=" * 60)
log("")
log(f"  Full report: {REPORT}")
