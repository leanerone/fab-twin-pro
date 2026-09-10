# -*- coding: utf-8 -*-
"""
为 56 台机台生成 DT_STATE_SNAPSHOT 快照

根据 DT_EVENT_RAW_CUR 每台机的最新事件状态生成对应快照，
SNAPSHOT_JSON 格式参考量产真实样例。
"""
import os
import sys
import json
import random
from datetime import datetime

sys.path.insert(0, r'C:\Users\A\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a558d0e1709fecd225c0cc2\fab-twin-pro\backend')
from database import SessionLocal
from models import DT_STATE_SNAPSHOT, DT_EVENT_RAW_CUR

random.seed(20260910)

db = SessionLocal()

# 查询每台机的最新 CUR 事件
cur_events = db.query(DT_EVENT_RAW_CUR).all()
print(f"DT_EVENT_RAW_CUR: {len(cur_events)} 条")

snapshots = []
for ce in cur_events:
    tool = ce.tool_id
    if tool in ("Read", "VFEI", "UNKNOWN_EQP") or tool.startswith("ADV_") or tool.startswith("PODOPENER-9"):
        continue
    try:
        payload = json.loads(ce.payload_json)
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        continue

    event_name = payload.get("event_name") or "UNKNOWN"
    lot_id = payload.get("lot_id")
    if lot_id == "NULL" or lot_id is None:
        lot_id = None
    cassette = payload.get("cassette_id")
    if cassette == "NULL" or cassette is None:
        cassette = None
    mode = payload.get("machine_mode")
    if mode == "NULL" or mode is None:
        mode = "Auto"
    chamber = payload.get("chamber_id")
    port = payload.get("port_id")

    snap_ts = ce.received_ts_utc or datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 构造快照 JSON（参考真实格式）
    snapshot_json = {
        "tool_id": tool,
        "event_ts_utc": snap_ts.replace(" ", "T") + "Z",
        "event_type": "STATE_SNAPSHOT",
        "machine_state": event_name,
        "machine_mode": mode,
        "source_system": "SNAPSHOT",
        "source_message_id": f"SNAP-{tool}",
        "raw_payload": {
            "event_name": event_name,
            "port_id": port if port != "NULL" else None,
            "cassette_id": cassette,
            "chamber_id": chamber if chamber != "NULL" else None,
            "lot_id": lot_id,
        },
        "lot_id": lot_id,
        "carrier_id": cassette,
    }

    snap = DT_STATE_SNAPSHOT(
        tool_id=tool,
        snapshot_ts_utc=snap_ts,
        machine_state=event_name,
        machine_mode=mode,
        current_alarm_code=payload.get("alarm_code"),
        current_lot_id=lot_id,
        pod_position="1" if port not in (None, "NULL") else None,
        snapshot_json=json.dumps(snapshot_json, ensure_ascii=False),
    )
    snapshots.append(snap)
    db.add(snap)

db.commit()
print(f"DT_STATE_SNAPSHOT 新增: {len(snapshots)} 条")
db.close()
