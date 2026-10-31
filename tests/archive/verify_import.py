# -*- coding: utf-8 -*-
"""验证本机所有表的数据行数"""
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

print("=" * 70)
print("本机 DB 数据行数验证")
print("=" * 70)

tables = [
    "PERM_DATA", "ROLES", "USERS", "ROLE_PERMISSIONS", "FLOORS", "FLOOR_AREAS",
    "MACHINES", "RECIPES", "MACHINE_MODEL_CONFIGS", "MACHINE_TOOL_MAPPINGS",
    "EVENT_ACTION_MAPPINGS", "AI_CONFIGS", "AI_PROVIDER_CONFIGS",
    "MACHINE_DIFY_CONFIGS", "ALARMS", "LOTS", "MACHINE_EVENTS", "CHAMBER_SNAPSHOTS",
    "DT_EVENT_RAW", "DT_EVENT_RAW_CUR", "DT_EVENT_STD", "DT_STATE_SNAPSHOT",
    "DT_EVENT_REALTIMELOT", "DT_RTLOT_TOOL_PORT_RULE", "DT_RTLOT_EVENT_RULE",
]

total = 0
for t in tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = cur.fetchone()[0]
    except Exception as e:
        cnt = f"ERR {e}"
    # 对比 JSONL
    p = os.path.join(EXPORT_DIR, f"{t}.jsonl")
    jsonl_cnt = "N/A"
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            jsonl_cnt = len([l for l in f if l.strip()])
    mark = "OK" if isinstance(cnt, int) and (jsonl_cnt == "N/A" or abs(cnt - jsonl_cnt) <= 2) else "?"
    if isinstance(cnt, int):
        total += cnt
    print(f"  [{mark}] {t:30s} 本机={cnt:<6} JSONL={jsonl_cnt}")

# 空表状态
print("\n空表（无数据/未导入）:")
empty = ["AI_INSIGHTS", "DASHBOARD_KPI", "DT_ALARM_EVENT", "OHT_POSITIONS",
         "TRACKS", "VEHICLES", "AI_USAGE_LOGS"]
for t in empty:
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    print(f"  {t:30s} {cur.fetchone()[0]} 行")

print(f"\n合计数据行: {total}")
cur.close()
conn.close()
