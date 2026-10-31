# -*- coding: utf-8 -*-
"""验证本机 Oracle 各表行数"""
import oracledb

oracledb.defaults.fetch_lobs = False

conn = oracledb.connect(user="fabtwin", password="fabtwin",
                        dsn=oracledb.makedsn("localhost", 1521, service_name="orclpdb"))
cur = conn.cursor()

tables = [
    "AI_INSIGHTS","ALARMS","CHAMBER_SNAPSHOTS","DASHBOARD_KPI",
    "EVENT_ACTION_MAPPINGS","FLOORS","FLOOR_AREAS","LOTS",
    "MACHINES","MACHINE_EVENTS","MACHINE_MODEL_CONFIGS","MACHINE_TOOL_MAPPINGS",
    "OHT_POSITIONS","PERM_DATA","RECIPES","ROLES","ROLE_PERMISSIONS",
    "TRACKS","USERS","VEHICLES",
    "AI_CONFIGS","AI_PROVIDER_CONFIGS","AI_USAGE_LOGS",
    "DT_EVENT_RAW","DT_EVENT_RAW_CUR","DT_EVENT_STD","DT_STATE_SNAPSHOT",
    "DT_ALARM_EVENT","MACHINE_DIFY_CONFIGS",
]

print(f"{'表名':<30} {'行数':>8}")
print("-" * 40)
for t in tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = cur.fetchone()[0]
        print(f"{t:<30} {cnt:>8}")
    except oracledb.DatabaseError as e:
        print(f"{t:<30} {'不存在':>8}")

cur.close()
conn.close()
