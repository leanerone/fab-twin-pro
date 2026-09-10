# -*- coding: utf-8 -*-
"""修正本机表结构，使其与量产 JSONL 数据匹配"""
import os
import shutil
import oracledb

oracledb.defaults.fetch_lobs = False

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(HERE, "prod_export_20260910")

conn = oracledb.connect(
    user="fabtwin", password="fabtwin",
    dsn=oracledb.makedsn("localhost", 1521, service_name="orclpdb"))
cur = conn.cursor()

def get_cols(table):
    cur.execute(f"SELECT column_name FROM user_tab_columns WHERE table_name = '{table}'")
    return {r[0] for r in cur.fetchall()}

def add_col(table, col, ddl):
    if col not in get_cols(table):
        cur.execute(f"ALTER TABLE {table} ADD ({col} {ddl})")
        print(f"  [OK] {table} 增加列 {col} {ddl}")
    else:
        print(f"  [SKIP] {table}.{col} 已存在")

# 1. DT_EVENT_STD 补充量产有但本机缺的列
print("=== 修正 DT_EVENT_STD ===")
add_col("DT_EVENT_STD", "EVENT_TS_UTC", "VARCHAR2(30)")
add_col("DT_EVENT_STD", "MACHINE_MODE", "VARCHAR2(32)")
add_col("DT_EVENT_STD", "CYCLE_ID", "VARCHAR2(64)")
add_col("DT_EVENT_STD", "CARRIER_ID", "VARCHAR2(64)")
add_col("DT_EVENT_STD", "THROUGHPUT_COUNT", "NUMBER")

# 2. DT_STATE_SNAPSHOT 补充 CURRENT_CYCLE_ID
print("=== 修正 DT_STATE_SNAPSHOT ===")
add_col("DT_STATE_SNAPSHOT", "CURRENT_CYCLE_ID", "VARCHAR2(64)")

# 3. 检查 DT_EVENT_RAW / DT_EVENT_RAW_CUR 的时间列类型
print("=== 检查 DT_EVENT_RAW 时间列类型 ===")
for table in ["DT_EVENT_RAW", "DT_EVENT_RAW_CUR"]:
    cur.execute(f"SELECT column_name, data_type FROM user_tab_columns WHERE table_name='{table}' AND column_name LIKE '%TIME%' OR table_name='{table}' AND column_name LIKE '%TS%' ORDER BY column_id")
    print(f"  {table}:")
    for r in cur.fetchall():
        print(f"    {r[0]:20s} {r[1]}")

conn.commit()
cur.close()
conn.close()
print("\n[DONE] 结构修正完成")
