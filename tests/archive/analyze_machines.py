# -*- coding: utf-8 -*-
"""分析机台情况：MACHINES 有哪些机台，哪些有事件数据"""
import oracledb

oracledb.defaults.fetch_lobs = False

conn = oracledb.connect(
    user="fabtwin", password="fabtwin",
    dsn=oracledb.makedsn("localhost", 1521, service_name="orclpdb"))
cur = conn.cursor()

# 查看 MACHINES 表结构
cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name='MACHINES' ORDER BY column_id")
print("MACHINES 列:", [r[0] for r in cur.fetchall()])

# 所有机台
print("\n=== MACHINES 表机台清单 ===")
cur.execute("SELECT * FROM MACHINES ORDER BY 1")
machines = cur.fetchall()
cols = [d[0] for d in cur.description]
print("列:", cols)
for m in machines:
    print(f"  {m[0]:20s} {str(m[1] if len(m)>1 else ''):25s} ...")

# DT_EVENT_RAW 中有数据的机台
print("\n=== DT_EVENT_RAW 中有事件的机台 ===")
cur.execute("SELECT TOOL_ID, COUNT(*) FROM DT_EVENT_RAW GROUP BY TOOL_ID ORDER BY TOOL_ID")
raw_tools = cur.fetchall()
for t in raw_tools:
    print(f"  {t[0]:20s} {t[1]} 条")

# DT_EVENT_RAW_CUR
print("\n=== DT_EVENT_RAW_CUR 中的机台 ===")
cur.execute("SELECT TOOL_ID, COUNT(*) FROM DT_EVENT_RAW_CUR GROUP BY TOOL_ID ORDER BY TOOL_ID")
cur_tools = cur.fetchall()
for t in cur_tools:
    print(f"  {t[0]:20s} {t[1]} 条")

# DT_STATE_SNAPSHOT
print("\n=== DT_STATE_SNAPSHOT 中的机台 ===")
cur.execute("SELECT TOOL_ID, COUNT(*) FROM DT_STATE_SNAPSHOT GROUP BY TOOL_ID ORDER BY TOOL_ID")
snap_tools = cur.fetchall()
for t in snap_tools:
    print(f"  {t[0]:20s} {t[1]} 条")

cur.close()
conn.close()
