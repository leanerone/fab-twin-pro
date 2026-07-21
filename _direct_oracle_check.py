"""直接连 Oracle 看真实数据 - 不走 env.bat
运行：backend\venv\Scripts\python.exe _direct_oracle_check.py
"""
import os
import sys

# 硬编码 Oracle 连接 - 用你提供的真实值
os.environ['ORACLE_HOST'] = '10.30.8.119'
os.environ['ORACLE_PORT'] = '1521'
os.environ['ORACLE_SERVICE'] = 'APCDB'
os.environ['ORACLE_USER'] = 'emuuser'
os.environ['ORACLE_PASSWORD'] = 'apcuser'
os.environ['ORACLE_DSN_TYPE'] = 'sid'
os.environ['ORACLE_CLIENT_DIR'] = r'C:\app\client\c11463\product\19.0.0\client_1'
os.environ['DB_TYPE'] = 'oracle'

# 绕过代理
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
BACKEND_DIR = os.path.join(BASE_DIR, 'backend')
sys.path.insert(0, BACKEND_DIR)

print("=" * 70)
print("Direct Oracle check (bypassing env.bat)")
print("=" * 70)
print(f"ORACLE_HOST = {os.environ['ORACLE_HOST']}")
print(f"ORACLE_PORT = {os.environ['ORACLE_PORT']}")
print(f"ORACLE_SERVICE = {os.environ['ORACLE_SERVICE']}")
print(f"ORACLE_USER = {os.environ['ORACLE_USER']}")
print(f"ORACLE_DSN_TYPE = {os.environ['ORACLE_DSN_TYPE']}")
print(f"ORACLE_CLIENT_DIR = {os.environ['ORACLE_CLIENT_DIR']}")

from database import SessionLocal, engine, DB_IS_SQLITE
from sqlalchemy import text

print(f"\nDB_IS_SQLITE = {DB_IS_SQLITE}")
print(f"Engine URL: {engine.url}")

db = SessionLocal()
try:
    print("\n" + "=" * 70)
    print("Test 1: Direct SQL query")
    print("=" * 70)
    result = db.execute(text("SELECT USER, SYSDATE FROM DUAL"))
    row = result.fetchone()
    print(f"  Connected as: {row[0]}")
    print(f"  Server time: {row[1]}")

    print("\n" + "=" * 70)
    print("Test 2: Show all MACHINE_MODEL_CONFIGS")
    print("=" * 70)
    result = db.execute(text("SELECT MODEL_ID, VIEW_MODE, MODEL_NAME FROM MACHINE_MODEL_CONFIGS ORDER BY MODEL_ID"))
    for row in result:
        print(f"  {row[0]:20} | {row[1]:12} | {row[2]}")

    print("\n" + "=" * 70)
    print("Test 3: Find PODOPENER related")
    print("=" * 70)
    result = db.execute(text("SELECT MODEL_ID, VIEW_MODE, MODEL_NAME FROM MACHINE_MODEL_CONFIGS WHERE MODEL_ID LIKE '%PODOPENER%' OR MODEL_ID LIKE '%VPO%'"))
    for row in result:
        print(f"  {row[0]:20} | {row[1]:12} | {row[2]}")

    print("\n" + "=" * 70)
    print("Test 4: Machine PODOPENER-1 mapping")
    print("=" * 70)
    result = db.execute(text("""
        SELECT m.ID, m.MODEL, m.STATE, m.NAME,
               c.MODEL_ID AS CONFIG_MODEL_ID, c.VIEW_MODE
        FROM MACHINES m
        LEFT JOIN MACHINE_MODEL_CONFIGS c ON m.MODEL = c.MODEL_ID
        WHERE m.ID = 'PODOPENER-1'
    """))
    for row in result:
        print(f"  Machine ID: {row[0]}")
        print(f"  Machine.MODEL: {row[1]}")
        print(f"  Machine.STATE: {row[2]}")
        print(f"  Machine.NAME: {row[3]}")
        print(f"  Config.MODEL_ID: {row[4]}")
        print(f"  Config.VIEW_MODE: {row[5]}")
        if row[4]:
            print(f"  [OK] MATCH")
        else:
            print(f"  [ERROR] NO MATCH - Machine.MODEL='{row[1]}' has no corresponding config")

finally:
    db.close()
print("\n" + "=" * 70)
print("Done")
print("=" * 70)
