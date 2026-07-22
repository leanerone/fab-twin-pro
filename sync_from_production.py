"""从量产DB同步数据到本地Oracle/SQLite

用途：
1. 定时同步 DT_EVENT_RAW 最新数据到本地
2. 初始化时导入历史数据

运行：
    # 同步最近24小时数据
    backend\venv\Scripts\python.exe sync_from_production.py --hours 24
    
    # 同步最近7天数据
    backend\venv\Scripts\python.exe sync_from_production.py --days 7
    
    # 仅测试连接
    backend\venv\Scripts\python.exe sync_from_production.py --test
"""
import os
import sys
import argparse
import json
from datetime import datetime, timedelta

# 添加 backend 到路径
if '__file__' in globals():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
else:
    BASE_DIR = os.getcwd()
    BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
sys.path.insert(0, BACKEND_DIR)

# 设置环境变量：连接本地 Oracle
os.environ['DB_TYPE'] = 'oracle'
os.environ['ORACLE_HOST'] = os.environ.get('LOCAL_ORACLE_HOST', 'localhost')
os.environ['ORACLE_PORT'] = os.environ.get('LOCAL_ORACLE_PORT', '1521')
os.environ['ORACLE_SERVICE'] = os.environ.get('LOCAL_ORACLE_SERVICE', 'ORCL')
os.environ['ORACLE_USER'] = os.environ.get('LOCAL_ORACLE_USER', 'emuuser')
os.environ['ORACLE_PASSWORD'] = os.environ.get('LOCAL_ORACLE_PASSWORD', 'password')
os.environ['ORACLE_CLIENT_DIR'] = os.environ.get('ORACLE_CLIENT_DIR', '')
os.environ['ORACLE_DSN_TYPE'] = 'sid'

from database import SessionLocal, engine
from models import DT_EVENT_RAW, DT_EVENT_RAW_CUR, Machine, MachineModelConfig, Floor, FloorArea
from sqlalchemy import text, func
import oracledb

print("=" * 70)
print("Sync from Production DB to Local Oracle")
print("=" * 70)
print(f"Target: {os.environ['ORACLE_HOST']}:{os.environ['ORACLE_PORT']}/{os.environ['ORACLE_SERVICE']}")
print("=" * 70)


def get_production_connection():
    """创建量产DB连接（读取环境变量或使用默认值）"""
    prod_host = os.environ.get('PROD_ORACLE_HOST', '10.30.8.119')
    prod_port = os.environ.get('PROD_ORACLE_PORT', '1521')
    prod_service = os.environ.get('PROD_ORACLE_SERVICE', 'APCDB')
    prod_user = os.environ.get('PROD_ORACLE_USER', 'emuuser')
    prod_password = os.environ.get('PROD_ORACLE_PASSWORD', 'apcuser')
    
    # Thick mode if client dir is set
    client_dir = os.environ.get('ORACLE_CLIENT_DIR', '')
    if client_dir:
        oracledb.init_oracle_client(lib_dir=client_dir)
    
    dsn = oracledb.makedsn(prod_host, int(prod_port), sid=prod_service)
    conn = oracledb.connect(user=prod_user, password=prod_password, dsn=dsn)
    
    print(f"[PROD] Connected to {prod_host}:{prod_port}/{prod_service}")
    return conn


def sync_dt_event_raw(hours: int = 24, test_only: bool = False):
    """同步 DT_EVENT_RAW 表数据"""
    print(f"\n[SYNC] DT_EVENT_RAW (last {hours} hours)")
    
    prod_conn = get_production_connection()
    prod_cursor = prod_conn.cursor()
    
    # 查询量产DB最近数据
    start_time = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
    
    query = f"""
        SELECT raw_id, tool_id, source_system, source_message_id, 
               received_ts_utc, event_ts_utc, payload_json, parse_status, error_message
        FROM EMUUSER.DT_EVENT_RAW
        WHERE received_ts_utc >= TO_TIMESTAMP('{start_time}', 'YYYY-MM-DD HH24:MI:SS')
        ORDER BY received_ts_utc
    """
    
    print(f"[PROD] Querying events since {start_time}...")
    prod_cursor.execute(query)
    rows = prod_cursor.fetchall()
    print(f"[PROD] Found {len(rows)} records")
    
    if test_only:
        print("[SYNC] Test mode, skipping insert")
        prod_cursor.close()
        prod_conn.close()
        return
    
    # 插入本地DB
    local_db = SessionLocal()
    try:
        inserted = 0
        skipped = 0
        for row in rows:
            # 检查是否已存在
            existing = local_db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.raw_id == row[0]).first()
            if existing:
                skipped += 1
                continue
            
            # 插入新记录
            event = DT_EVENT_RAW(
                raw_id=row[0],
                tool_id=row[1],
                source_system=row[2],
                source_message_id=row[3],
                received_ts_utc=str(row[4]) if row[4] else None,
                event_ts_utc=str(row[5]) if row[5] else None,
                payload_json=row[6],
                parse_status=row[7] or 'NEW',
                error_message=row[8],
            )
            local_db.add(event)
            inserted += 1
            
            if inserted % 1000 == 0:
                local_db.commit()
                print(f"[SYNC] Inserted {inserted} records...")
        
        local_db.commit()
        print(f"[SYNC] Done: {inserted} inserted, {skipped} skipped")
        
    finally:
        local_db.close()
    
    prod_cursor.close()
    prod_conn.close()


def sync_dt_event_raw_cur():
    """同步 DT_EVENT_RAW_CUR 表（每台机台最新一条）"""
    print(f"\n[SYNC] DT_EVENT_RAW_CUR")
    
    prod_conn = get_production_connection()
    prod_cursor = prod_conn.cursor()
    
    query = """
        SELECT tool_id, raw_id, source_system, source_message_id,
               received_ts_utc, event_ts_utc, payload_json, parse_status, error_message
        FROM EMUUSER.DT_EVENT_RAW_CUR
    """
    
    prod_cursor.execute(query)
    rows = prod_cursor.fetchall()
    print(f"[PROD] Found {len(rows)} records")
    
    local_db = SessionLocal()
    try:
        for row in rows:
            event = DT_EVENT_RAW_CUR(
                tool_id=row[0],
                raw_id=row[1],
                source_system=row[2],
                source_message_id=row[3],
                received_ts_utc=str(row[4]) if row[4] else None,
                event_ts_utc=str(row[5]) if row[5] else None,
                payload_json=row[6],
                parse_status=row[7] or 'NEW',
                error_message=row[8],
            )
            local_db.merge(event)
        
        local_db.commit()
        print(f"[SYNC] DT_EVENT_RAW_CUR synced: {len(rows)} records")
    finally:
        local_db.close()
    
    prod_cursor.close()
    prod_conn.close()


def sync_machines():
    """同步机台基础信息（可选：从seed_data初始化）"""
    print(f"\n[SYNC] Machines")
    
    # 检查本地是否已有数据
    local_db = SessionLocal()
    try:
        count = local_db.query(Machine).count()
        if count > 0:
            print(f"[SYNC] Machines already exist: {count} records, skipping")
            return
        
        # 如果没有，提示用户运行 seed_data.py
        print("[SYNC] No machines found. Run seed_data.py first or manually add machines.")
        print("[SYNC] Example: backend\\venv\\Scripts\\python.exe -c \"from backend.seed_data import *; db=SessionLocal(); create_machines(db)\"")
    finally:
        local_db.close()


def verify_local_db():
    """验证本地数据库连接"""
    print("\n[VERIFY] Local DB connection...")
    
    local_db = SessionLocal()
    try:
        # 测试查询
        result = local_db.execute(text("SELECT 1 FROM DUAL")).scalar()
        print(f"[VERIFY] Local DB connected: SELECT 1 = {result}")
        
        # 检查表是否存在
        tables = ['DT_EVENT_RAW', 'DT_EVENT_RAW_CUR', 'MACHINES', 'MACHINE_MODEL_CONFIGS']
        for tbl in tables:
            try:
                cnt = local_db.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
                print(f"[VERIFY] {tbl}: {cnt} records")
            except Exception as e:
                print(f"[VERIFY] {tbl}: ERROR - {e}")
        
    finally:
        local_db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync from production DB to local Oracle")
    parser.add_argument('--hours', type=int, default=24, help='Sync last N hours')
    parser.add_argument('--days', type=int, help='Sync last N days')
    parser.add_argument('--test', action='store_true', help='Test connection only')
    parser.add_argument('--init', action='store_true', help='Initialize local DB with seed data')
    args = parser.parse_args()
    
    hours = args.hours
    if args.days:
        hours = args.days * 24
    
    verify_local_db()
    
    if args.test:
        # 仅测试量产DB连接
        print("\n[TEST] Production DB connection...")
        try:
            conn = get_production_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT SYSDATE FROM DUAL")
            result = cursor.fetchone()
            print(f"[TEST] Production DB connected: SYSDATE = {result[0]}")
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[TEST] ERROR: {e}")
    else:
        # 执行同步
        sync_dt_event_raw(hours=hours)
        sync_dt_event_raw_cur()
        sync_machines()
    
    print("\n" + "=" * 70)
    print("Done")
    print("=" * 70)