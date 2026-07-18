"""测试WinForm事件写入和DB Poller推送"""
import sys
sys.path.insert(0, '.')

import json
from datetime import datetime
from database import engine
from sqlalchemy import text

TOOL_ID = "PODOPENER-1"

# 1. 查看当前DB Poller的初始时间戳
print("=== 1. 查看数据库最新事件 ===")
with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT RAW_ID, RECEIVED_TS_UTC, EVENT_TS_UTC 
        FROM DT_EVENT_RAW 
        WHERE TOOL_ID = :tool_id 
        ORDER BY RECEIVED_TS_UTC DESC 
        FETCH FIRST 3 ROWS ONLY
    """), {'tool_id': TOOL_ID}).fetchall()
    
    for row in result:
        print(f"  raw_id: {row[0][:30]}")
        print(f"  received_ts_utc: {row[1]}")
        print(f"  event_ts_utc: {row[2]}")
        print()

# 2. 写入一条测试事件
print("=== 2. 写入测试事件 ===")
ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
raw_id = f"WINFORM_TEST.{datetime.now().timestamp()}"

payload = json.dumps({
    "tool_id": TOOL_ID,
    "lot_id": "TEST-LOT-001",
    "run_mode": "PACKING",
    "event_type": "VFEI",
    "event_name": "ATTACH_POD_PLACE",
    "event_value": "ATTACH_POD_PLACE",
    "status": "ATTACH_POD_PLACE",
    "machine_state": "ATTACH_POD_PLACE",
    "machine_mode": "PACKING",
    "alarm_code": None,
    "alarm_id": None,
    "alarm_text": None,
    "source_system": "RV",
    "port_id": "1",
    "cassette_id": "TEST-12345",
    "pod_id": "TEST-12345",
    "smif_id": "1",
    "chamber_id": "NULL",
    "batch_id": "BT_TEST",
    "unit_id": "NULL",
    "slot_id": "NULL",
}, ensure_ascii=False)

with engine.connect() as conn:
    conn.execute(text("""
        INSERT INTO DT_EVENT_RAW (RAW_ID, TOOL_ID, SOURCE_SYSTEM, SOURCE_MESSAGE_ID,
            RECEIVED_TS_UTC, EVENT_TS_UTC, PAYLOAD_JSON, PARSE_STATUS, ERROR_MESSAGE)
        VALUES (:raw_id, :tool_id, :source_system, :source_message_id,
            :received_ts, :event_ts, :payload, 'PARSED', NULL)
    """), {
        "raw_id": raw_id,
        "tool_id": TOOL_ID,
        "source_system": "RV",
        "source_message_id": raw_id,
        "received_ts": ts,
        "event_ts": ts,
        "payload": payload,
    })
    
    conn.execute(text("DELETE FROM DT_EVENT_RAW_CUR WHERE TOOL_ID = :tool_id"), {"tool_id": TOOL_ID})
    conn.execute(text("""
        INSERT INTO DT_EVENT_RAW_CUR (TOOL_ID, RAW_ID, SOURCE_SYSTEM, SOURCE_MESSAGE_ID,
            RECEIVED_TS_UTC, EVENT_TS_UTC, PAYLOAD_JSON, PARSE_STATUS, ERROR_MESSAGE)
        VALUES (:tool_id, :raw_id, :source_system, :source_message_id,
            :received_ts, :event_ts, :payload, 'PARSED', NULL)
    """), {
        "tool_id": TOOL_ID,
        "raw_id": raw_id,
        "source_system": "RV",
        "source_message_id": raw_id,
        "received_ts": ts,
        "event_ts": ts,
        "payload": payload,
    })
    conn.commit()

print(f"  写入成功!")
print(f"  raw_id: {raw_id}")
print(f"  timestamp: {ts}")
print(f"  event_name: ATTACH_POD_PLACE")
print()
print("  请观察后端日志中是否有 [DB Poller] 推送消息")
print(f"  如果没有推送，说明DB Poller的_last_poll_ts > {ts}")
