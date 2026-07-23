import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from config import DB_TYPE, ORACLE_HOST, ORACLE_PORT, ORACLE_SERVICE, ORACLE_USER

print(f"DB_TYPE: {DB_TYPE}")
print(f"DB: {ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE} ({ORACLE_USER})")

if DB_TYPE == 'sqlite':
    print("[OK] SQLite mode - no external connection needed")
    sys.exit(0)

try:
    import oracledb
    client_dir = os.environ.get("ORACLE_CLIENT_DIR", "")
    if client_dir:
        lib_dir = os.path.join(client_dir, 'bin')
        if os.path.exists(os.path.join(lib_dir, 'oci.dll')):
            oracledb.init_oracle_client(lib_dir=lib_dir)
            print(f"[OK] Thick mode with lib_dir={lib_dir}")
        else:
            print("[WARN] oci.dll not found, using Thin mode")
    else:
        print("[INFO] ORACLE_CLIENT_DIR not set, using Thin mode")

    dsn = oracledb.makedsn(ORACLE_HOST, ORACLE_PORT, service_name=ORACLE_SERVICE)
    with oracledb.connect(user=ORACLE_USER, password=os.environ.get('ORACLE_PASSWORD', ''), dsn=dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM DUAL")
            print(f"[OK] Oracle connection successful")
except Exception as e:
    print(f"[ERROR] Oracle connection failed: {e}")
    sys.exit(1)
