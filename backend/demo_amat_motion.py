"""AMAT-METSPUT Motion2D 演示脚本（方案B）

按 AMAT Motion JSON 的 6 个 step 顺序往 DT_EVENT_RAW / DT_EVENT_RAW_CUR 写事件，
走真实链路：DT_EVENT_RAW → db_poller 轮询 → WebSocket raw_event → 前端动画。
前端打开 AMAT-T1 详情页（实时模式、Motion2D 视图）即可看到动画自动播完整流程。

用法（在 backend 目录下）：
    python demo_amat_motion.py                 # 默认机台 AMAT-T1
    python demo_amat_motion.py AMAT-T1 0.8     # 指定机台、节奏倍率（越小越快）

raw_id 采用 "TID.Z<epoch_ms>"：'Z' 大于数字，词法降序恒排在模拟器 TID.<数字> 之前，
保证不会被 db_poller "raw_id desc limit 100" 的窗口挤出。
"""
import json
import random
import sys
import time
from datetime import datetime

from database import SessionLocal
from models import DT_EVENT_RAW, DT_EVENT_RAW_CUR

TOOL_ID = sys.argv[1] if len(sys.argv) > 1 else "AMAT-T1"
PACE = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0

LOT_ID = "DEMO_LOT01"

# (event_name, 业务参数, 发送后等待秒数) —— 等待时长覆盖该 step 动画播放时长
SEQUENCE = [
    ("POD_PLACED",            {"SMIFPORTID": "1"}, 3.5),
    ("BATCH_INFO_FROM_ECUI",  {"BATCH_ID": "BT_DEMO01", "LOT_ID": LOT_ID, "Qty": "25",
                               "RunMode": "PACKING", "RECIPE1": "RCP_AU_01", "PORT": "1"}, 3.5),
    ("CASSETTE_ARRIVAL",      {"PORT": "1"}, 3.5),
    # 同臂取放：LLA(ARM_1) → E 腔(ARM_1)
    ("CHAMBER_PS",            {"LOT_ID": LOT_ID, "SLOT": "1", "CHAMBER": "E"}, 8.0),
    # 跨臂演示：LLA(ARM_1) → 1 号腔(ARM_2)，含 Cross 交接
    ("CHAMBER_PS",            {"LOT_ID": LOT_ID, "SLOT": "2", "CHAMBER": "1"}, 8.0),
    # 加工完成：E 腔 → 载具（回 LLA）
    ("WAFER_PROCESS_COMPLETE", {"LOT_ID": LOT_ID, "SLOT": "1"}, 5.5),
    ("POD_REMOVED",           {"SMIFPORTID": "1"}, 1.0),
]


def write_event(db, tool_id: str, event_name: str, params: dict) -> str:
    """写入一条 DT_EVENT_RAW + 更新 CUR（格式与 simulator._write_raw_event 对齐）"""
    ts = datetime.now().isoformat()
    payload = {
        "tool_id": tool_id,
        "lot_id": params.get("LOT_ID", "NULL"),
        "run_mode": params.get("RunMode", "PACKING"),
        "event_type": "VFEI",
        "event_name": event_name,
        "event_value": event_name,
        "status": event_name,
        "machine_state": event_name,
        "machine_mode": params.get("RunMode", "PACKING"),
        "alarm_code": None,
        "alarm_id": None,
        "alarm_text": event_name,
        "source_system": "DEMO",
        "port_id": params.get("PORT", params.get("SMIFPORTID", "NULL")),
        "cassette_id": "NULL",
        "pod_id": "NULL",
        "smif_id": params.get("SMIFPORTID", "NULL"),
        "chamber_id": params.get("CHAMBER", "NULL"),
        "batch_id": params.get("BATCH_ID", "NULL"),
        "unit_id": "NULL",
        "slot_id": params.get("SLOT", "NULL"),
        # 业务参数平铺（大写键），前端 toMotionPayload 直接提取
        **params,
    }
    payload_json = json.dumps(payload, ensure_ascii=False)
    raw_id = f"TID.Z{int(time.time() * 1000)}{random.randint(0, 999):03d}"

    db.add(DT_EVENT_RAW(
        raw_id=raw_id, tool_id=tool_id, source_system="DEMO",
        source_message_id=raw_id, received_ts_utc=ts, event_ts_utc=ts,
        payload_json=payload_json, parse_status="PARSED",
    ))
    db.merge(DT_EVENT_RAW_CUR(
        tool_id=tool_id, raw_id=raw_id, source_system="DEMO",
        source_message_id=raw_id, received_ts_utc=ts, event_ts_utc=ts,
        payload_json=payload_json, parse_status="PARSED",
    ))
    db.commit()
    return raw_id


def main():
    print(f"[DEMO] 目标机台: {TOOL_ID}，节奏倍率: {PACE}")
    print("[DEMO] 请确认前端已打开该机台详情页（实时模式）... 3 秒后开始")
    time.sleep(3)
    db = SessionLocal()
    try:
        for i, (event_name, params, gap) in enumerate(SEQUENCE, 1):
            raw_id = write_event(db, TOOL_ID, event_name, params)
            print(f"[DEMO] ({i}/{len(SEQUENCE)}) {event_name} 已写入 {raw_id} params={params}", flush=True)
            time.sleep(max(0.5, gap * PACE))
    finally:
        db.close()
    print("[DEMO] 完整流程发送完毕")


if __name__ == "__main__":
    main()
