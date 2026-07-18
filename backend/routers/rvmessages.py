"""RV消息API：接收RV实时消息，查询当前状态"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import json

from database import get_db
from models import DT_EVENT_RAW, DT_EVENT_RAW_CUR
from services.realtime import manager

router = APIRouter(prefix="/api/rv", tags=["rv"])


class RVMessageRequest(BaseModel):
    tool_id: str
    source_system: str = "RV"
    source_message_id: str
    received_ts_utc: str = None
    event_ts_utc: str = None
    payload_json: str
    parse_status: str = "PARSED"


@router.post("/message")
async def receive_rv_message(data: RVMessageRequest, db: Session = Depends(get_db)):
    """接收RV实时消息，写入DT_EVENT_RAW和DT_EVENT_RAW_CUR"""
    now = datetime.now().isoformat()
    received_ts = data.received_ts_utc or now
    event_ts = data.event_ts_utc or now

    raw_event = DT_EVENT_RAW(
        raw_id=f"TID.{int(datetime.now().timestamp())}",
        tool_id=data.tool_id,
        source_system=data.source_system,
        source_message_id=data.source_message_id,
        received_ts_utc=received_ts,
        event_ts_utc=event_ts,
        payload_json=data.payload_json,
        parse_status=data.parse_status,
    )
    db.add(raw_event)

    cur_event = DT_EVENT_RAW_CUR(
        tool_id=data.tool_id,
        raw_id=raw_event.raw_id,
        source_system=data.source_system,
        source_message_id=data.source_message_id,
        received_ts_utc=received_ts,
        event_ts_utc=event_ts,
        payload_json=data.payload_json,
        parse_status=data.parse_status,
    )
    db.merge(cur_event)

    db.commit()

    payload = json.loads(data.payload_json) if data.payload_json else {}
    await manager.broadcast({
        "type": "rv_event",
        "data": {
            "tool_id": data.tool_id,
            "event_name": payload.get("event_name", "UNKNOWN"),
            "lot_id": payload.get("lot_id"),
            "timestamp": event_ts,
            "payload": payload,
        }
    })

    return {"status": "ok", "raw_id": raw_event.raw_id}


@router.get("/current/{tool_id}")
def get_current_rv(tool_id: str, db: Session = Depends(get_db)):
    """获取机台最新的RV消息"""
    cur = db.query(DT_EVENT_RAW_CUR).filter(DT_EVENT_RAW_CUR.tool_id == tool_id).first()
    if not cur:
        return {"tool_id": tool_id, "message": "No data"}

    payload = json.loads(cur.payload_json) if cur.payload_json else {}
    return {
        "tool_id": cur.tool_id,
        "raw_id": cur.raw_id,
        "source_system": cur.source_system,
        "source_message_id": cur.source_message_id,
        "received_ts_utc": cur.received_ts_utc,
        "event_ts_utc": cur.event_ts_utc,
        "event_name": payload.get("event_name", "UNKNOWN"),
        "lot_id": payload.get("lot_id"),
        "cassette_id": payload.get("cassette_id"),
        "payload": payload,
    }


@router.get("/history/{tool_id}")
def get_rv_history(
    tool_id: str,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """获取机台RV消息历史"""
    rows = (
        db.query(DT_EVENT_RAW)
        .filter(DT_EVENT_RAW.tool_id == tool_id)
        .order_by(DT_EVENT_RAW.event_ts_utc.desc())
        .limit(limit)
        .all()
    )

    events = []
    for row in rows:
        payload = json.loads(row.payload_json) if row.payload_json else {}
        events.append({
            "raw_id": row.raw_id,
            "event_ts_utc": row.event_ts_utc,
            "event_name": payload.get("event_name", "UNKNOWN"),
            "lot_id": payload.get("lot_id"),
            "cassette_id": payload.get("cassette_id"),
            "alarm_id": payload.get("alarm_id"),
            "alarm_text": payload.get("alarm_text"),
        })

    return {"tool_id": tool_id, "total": len(events), "events": events}
