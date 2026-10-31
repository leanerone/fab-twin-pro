# -*- coding: utf-8 -*-
"""检查 DT_STATE_SNAPSHOT identity 列，测试正确插入语法"""
import oracledb
import json
import os

oracledb.defaults.fetch_lobs = False

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(HERE, "prod_export_20260910")

conn = oracledb.connect(
    user="fabtwin", password="fabtwin",
    dsn=oracledb.makedsn("localhost", 1521, service_name="orclpdb"))
cur = conn.cursor()

# 查看 identity 定义（Oracle 11g 兼容）
print("=== identity 列检查 ===")
cur.execute("SELECT column_name, data_default, identity_column FROM user_tab_cols WHERE table_name='DT_STATE_SNAPSHOT' AND identity_column='YES'")
for r in cur.fetchall():
    print(f"  列: {r[0]}, default: {r[1]}, identity: {r[2]}")

# 查看完整列定义
print("\n=== 全部列 ===")
cur.execute("SELECT column_name, data_type, nullable FROM user_tab_columns WHERE table_name='DT_STATE_SNAPSHOT' ORDER BY column_id")
cols = [(r[0], r[1]) for r in cur.fetchall()]
for c in cols:
    print(f"  {c[0]:25s} {c[1]}")

# 尝试插入（不带 SNAPSHOT_ID，让 identity 自动生成）
print("\n=== 尝试插入(剔除 SNAPSHOT_ID) ===")
with open(os.path.join(EXPORT_DIR, "DT_STATE_SNAPSHOT.jsonl"), "r", encoding="utf-8") as f:
    rows = [json.loads(line) for line in f if line.strip()]

r = rows[0]
insert_cols = [c for c in cols if c[0] != "SNAPSHOT_ID"]
col_list = ", ".join(f'"{c[0]}"' for c in insert_cols)
bind_list = ", ".join(f":{i+1}" for i in range(len(insert_cols)))
sql = f"INSERT INTO DT_STATE_SNAPSHOT ({col_list}) VALUES ({bind_list})"
print(f"SQL: {sql}")

vals = [None if r.get(c[0]) == "" else r.get(c[0]) for c in insert_cols]
try:
    cur.execute(sql, vals)
    print("成功! 自动生成 ID")
    conn.rollback()
except oracledb.DatabaseError as e:
    print(f"失败: {e}")

conn.close()
