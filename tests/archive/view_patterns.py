# -*- coding: utf-8 -*-
"""查看现有真实数据模式，用于生成补充数据"""
import oracledb
import json

oracledb.defaults.fetch_lobs = False

conn = oracledb.connect(
    user="fabtwin", password="fabtwin",
    dsn=oracledb.makedsn("localhost", 1521, service_name="orclpdb"))
cur = conn.cursor()

# 1. DT_EVENT_RAW 中 PODOPENER-1 的 payload 样本
print("=== PODOPENER-1 事件序列（按时间排序）===")
cur.execute("""SELECT RECEIVED_TS_UTC, PAYLOAD_JSON FROM DT_EVENT_RAW
               WHERE TOOL_ID='PODOPENER-1' ORDER BY RECEIVED_TS_UTC""")
for r in cur.fetchall()[:5]:
    p = json.loads(r[1])
    print(f"  {r[0]} event={p.get('event_name')} state={p.get('machine_state')} mode={p.get('machine_mode')}")

# 2. OXE-51 事件序列
print("\n=== OXE-51 事件序列（按时间排序）===")
cur.execute("""SELECT RECEIVED_TS_UTC, PAYLOAD_JSON FROM DT_EVENT_RAW
               WHERE TOOL_ID='OXE-51' ORDER BY RECEIVED_TS_UTC""")
for r in cur.fetchall()[:5]:
    p = json.loads(r[1])
    print(f"  {r[0]} event={p.get('event_name')} state={p.get('machine_state')}")

# 3. MACHINES 表当前状态
print("\n=== MACHINES 表 STATE 分布 ===")
cur.execute("SELECT STATE, COUNT(*) FROM MACHINES GROUP BY STATE")
for r in cur.fetchall():
    print(f"  {r[0]:20s} {r[1]} 台")

# 4. DT_EVENT_RAW_CUR 样本
print("\n=== DT_EVENT_RAW_CUR 样本（5条）===")
cur.execute("""SELECT TOOL_ID, PAYLOAD_JSON, PARSE_STATUS FROM DT_EVENT_RAW_CUR
               WHERE ROWNUM <= 5""")
for r in cur.fetchall():
    p = r[1]
    try:
        pj = json.loads(p)
        ev = pj.get('event_name') if isinstance(pj, dict) else p
    except Exception:
        ev = p[:100]
    print(f"  {r[0]:15s} event={ev} status={r[2]}")

# 5. DT_STATE_SNAPSHOT 样本
print("\n=== DT_STATE_SNAPSHOT 样本（5条）===")
cur.execute("""SELECT TOOL_ID, SNAPSHOT_TS_UTC, MACHINE_STATE, CURRENT_LOT_ID FROM DT_STATE_SNAPSHOT
               WHERE ROWNUM <= 5""")
for r in cur.fetchall():
    print(f"  {r[0]:15s} ts={r[1]} state={r[2]} lot={r[3]}")

cur.close()
conn.close()
