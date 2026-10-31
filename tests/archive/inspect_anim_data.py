# -*- coding: utf-8 -*-
"""查看动画配置与现有数据时间分布，为造数提供依据"""
import json
import oracledb

oracledb.defaults.fetch_lobs = False
conn = oracledb.connect(user="fabtwin", password="fabtwin", dsn="localhost:1521/orclpdb")
cur = conn.cursor()


def show(title, sql, limit=None, trunc=100):
    print(f"\n=== {title} ===")
    try:
        cur.execute(sql)
    except Exception as e:
        print("  ERR:", e)
        return
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    if limit:
        rows = rows[:limit]
    print("  cols:", cols)
    for r in rows:
        print("  ", [str(x)[:trunc] for x in r])


show("MACHINES 列", "SELECT * FROM machines WHERE id='PODOPENER-1'", trunc=60)
show("三台机台", "SELECT id, name, model, type FROM machines "
     "WHERE id IN ('PODOPENER-1','OXE-1','OXE-51')")
show("MACHINE_MODEL_CONFIGS", "SELECT model_key, model_name FROM machine_model_configs")
show("EVENT_ACTION_MAPPINGS", "SELECT * FROM event_action_mappings", trunc=150)
show("DT_EVENT_RAW 日期分布",
     "SELECT SUBSTR(event_ts_utc,1,10) d, COUNT(*) FROM dt_event_raw "
     "GROUP BY SUBSTR(event_ts_utc,1,10) ORDER BY 1")
show("三台机台现有事件",
     "SELECT tool_id, SUBSTR(event_ts_utc,1,10) d, COUNT(*), MIN(event_ts_utc), MAX(event_ts_utc) "
     "FROM dt_event_raw WHERE tool_id IN ('PODOPENER-1','OXE-1','OXE-51') "
     "GROUP BY tool_id, SUBSTR(event_ts_utc,1,10) ORDER BY 1,2")
show("OXE-51 事件名分布",
     "SELECT json_value(payload_json,'$.event_name') en, COUNT(*) FROM dt_event_raw "
     "WHERE tool_id='OXE-51' GROUP BY json_value(payload_json,'$.event_name') ORDER BY 2 DESC")
show("PODOPENER-1 事件名分布",
     "SELECT json_value(payload_json,'$.event_name') en, COUNT(*) FROM dt_event_raw "
     "WHERE tool_id='PODOPENER-1' GROUP BY json_value(payload_json,'$.event_name') ORDER BY 2 DESC")
show("OXE-1 事件名分布",
     "SELECT json_value(payload_json,'$.event_name') en, COUNT(*) FROM dt_event_raw "
     "WHERE tool_id='OXE-1' GROUP BY json_value(payload_json,'$.event_name') ORDER BY 2 DESC")
show("DT_EVENT_REALTIMELOT 样例",
     "SELECT * FROM dt_event_realtimelot FETCH FIRST 3 ROWS ONLY", trunc=60)
show("DT_STATE_SNAPSHOT 样例",
     "SELECT * FROM dt_state_snapshot FETCH FIRST 3 ROWS ONLY", trunc=60)

cur.close()
conn.close()
