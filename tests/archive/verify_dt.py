# -*- coding: utf-8 -*-
"""验证全部 8 张 DT 表"""
import oracledb
oracledb.defaults.fetch_lobs = False

conn = oracledb.connect(user="fabtwin", password="fabtwin",
                        dsn=oracledb.makedsn("localhost", 1521, service_name="orclpdb"))
cur = conn.cursor()

print("===== 全部 DT 表（8 张）=====")
dt_tables = [
    "DT_EVENT_RAW",
    "DT_EVENT_RAW_CUR",
    "DT_EVENT_STD",
    "DT_STATE_SNAPSHOT",
    "DT_ALARM_EVENT",
    "DT_EVENT_REALTIMELOT",
    "DT_RTLOT_TOOL_PORT_RULE",
    "DT_RTLOT_EVENT_RULE",
]

print(f"{'表名':<30} {'行数':>8} {'列数':>6}")
print("-" * 50)
for t in dt_tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = cur.fetchone()[0]
        cur.execute(f"SELECT COUNT(*) FROM user_tab_columns WHERE table_name='{t}'")
        cols = cur.fetchone()[0]
        print(f"{t:<30} {cnt:>8} {cols:>6}")
    except oracledb.DatabaseError as e:
        print(f"{t:<30} {'不存在':>8}")

print("\n===== 全部表清单 =====")
cur.execute("SELECT table_name FROM user_tables ORDER BY table_name")
all_tables = [r[0] for r in cur.fetchall()]
print(f"共 {len(all_tables)} 张表:")
for t in all_tables:
    print(f"  {t}")

cur.close()
conn.close()
