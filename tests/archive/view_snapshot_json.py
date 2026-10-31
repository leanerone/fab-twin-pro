# -*- coding: utf-8 -*-
"""查看 DT_STATE_SNAPSHOT 的 SNAPSHOT_JSON 真实格式"""
import oracledb
import json

oracledb.defaults.fetch_lobs = False

conn = oracledb.connect(
    user="fabtwin", password="fabtwin",
    dsn=oracledb.makedsn("localhost", 1521, service_name="orclpdb"))
cur = conn.cursor()

cur.execute("SELECT SNAPSHOT_JSON FROM DT_STATE_SNAPSHOT WHERE ROWNUM<=3")
for r in cur.fetchall():
    print(json.dumps(json.loads(r[0]), ensure_ascii=False, indent=1))
    print("---")

# 查看快照表列
print("\n=== DT_STATE_SNAPSHOT 列 ===")
cur.execute("SELECT column_name, data_type FROM user_tab_columns WHERE table_name='DT_STATE_SNAPSHOT' ORDER BY column_id")
for r in cur.fetchall():
    print(f"  {r[0]:25s} {r[1]}")

cur.close()
conn.close()
