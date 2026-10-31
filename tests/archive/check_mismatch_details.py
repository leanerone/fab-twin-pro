# -*- coding: utf-8 -*-
"""检查列不匹配表的详细情况"""
import os
import json
import oracledb

oracledb.defaults.fetch_lobs = False

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(HERE, "prod_export_20260910")

conn = oracledb.connect(
    user="fabtwin", password="fabtwin",
    dsn=oracledb.makedsn("localhost", 1521, service_name="orclpdb"))
cur = conn.cursor()

def show_local_schema(table):
    cur.execute(f"SELECT column_name, data_type FROM user_tab_columns WHERE table_name = '{table}' ORDER BY column_id")
    print(f"\n=== 本机 {table} 表结构 ===")
    for r in cur.fetchall():
        print(f"  {r[0]:30s} {r[1]}")

for t in ["AI_USAGE_LOGS", "ALARMS", "DT_EVENT_STD", "DT_STATE_SNAPSHOT"]:
    show_local_schema(t)

# 检查 AI_USAGE_LOGS JSONL 内容
print("\n=== AI_USAGE_LOGS.jsonl 前2行 ===")
with open(os.path.join(EXPORT_DIR, "AI_USAGE_LOGS.jsonl"), "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i >= 2:
            break
        d = json.loads(line)
        print(json.dumps(d, ensure_ascii=False)[:300])
        print()

# 检查有没有 ALARMS.jsonl
print("\n=== 导出目录文件清单 ===")
for f in sorted(os.listdir(EXPORT_DIR)):
    if f.endswith(".jsonl"):
        print(" ", f)

# 检查 DT_EVENT_STD.jsonl 内容
print("\n=== DT_EVENT_STD.jsonl 前1行 ===")
with open(os.path.join(EXPORT_DIR, "DT_EVENT_STD.jsonl"), "r", encoding="utf-8") as f:
    d = json.loads(f.readline())
    print(json.dumps(d, ensure_ascii=False)[:300])

# 检查 DT_STATE_SNAPSHOT.jsonl 前1行
print("\n=== DT_STATE_SNAPSHOT.jsonl 前1行 ===")
with open(os.path.join(EXPORT_DIR, "DT_STATE_SNAPSHOT.jsonl"), "r", encoding="utf-8") as f:
    d = json.loads(f.readline())
    print(json.dumps(d, ensure_ascii=False)[:300])

cur.close()
conn.close()
