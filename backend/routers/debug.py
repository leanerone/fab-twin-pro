"""消息调试接口（方案A）：手动注入一条事件到 DT_EVENT_RAW

事件走真实链路：DT_EVENT_RAW → db_poller 轮询 → WebSocket raw_event → 前端动画，
与外部系统写入效果完全一致，供 Motion2D 调试面板 / 联调使用。
"""
import json
import random
import time
from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import DT_EVENT_RAW, DT_EVENT_RAW_CUR, Machine
from routers.auth import get_current_user

router = APIRouter(prefix="/api/debug", tags=["debug"])


class DebugEventIn(BaseModel):
    tool_id: str
    event_name: str
    event_type: str = "VFEI"
    run_mode: Optional[str] = None
    params: Dict[str, object] = {}


@router.post("/event")
def inject_event(body: DebugEventIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    tool_id = (body.tool_id or "").strip()
    event_name = (body.event_name or "").strip().upper()
    if not tool_id or not event_name:
        raise HTTPException(status_code=400, detail="tool_id / event_name 不能为空")
    if not db.query(Machine).filter(Machine.id == tool_id).first():
        raise HTTPException(status_code=404, detail=f"机台 {tool_id} 不存在")

    params = dict(body.params or {})
    # 参数值统一转字符串（DB payload 为 JSON，前端 when 表达式按字符串/数字比较均可）
    params = {str(k): ("" if v is None else v) for k, v in params.items()}

    ts = datetime.now().isoformat()
    run_mode = body.run_mode or params.get("RunMode") or "NULL"
    payload = {
        "tool_id": tool_id,
        "lot_id": params.get("LOT_ID", "NULL"),
        "run_mode": run_mode,
        "event_type": body.event_type or "VFEI",
        "event_name": event_name,
        "event_value": event_name,
        "status": event_name,
        "machine_state": event_name,
        "machine_mode": run_mode,
        "alarm_code": None,
        "alarm_id": None,
        "alarm_text": event_name,
        "source_system": "DEBUG",
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
    # 'Z' 大于数字：词法降序恒排在模拟器 TID.<数字> 之前，保证在 poller 的
    # "raw_id desc limit 100" 窗口内可见
    raw_id = f"TID.Z{int(time.time() * 1000)}{random.randint(0, 999):03d}"

    db.add(DT_EVENT_RAW(
        raw_id=raw_id, tool_id=tool_id, source_system="DEBUG",
        source_message_id=raw_id, received_ts_utc=ts, event_ts_utc=ts,
        payload_json=payload_json, parse_status="PARSED",
    ))
    db.merge(DT_EVENT_RAW_CUR(
        tool_id=tool_id, raw_id=raw_id, source_system="DEBUG",
        source_message_id=raw_id, received_ts_utc=ts, event_ts_utc=ts,
        payload_json=payload_json, parse_status="PARSED",
    ))
    db.commit()

    return {
        "ok": True,
        "raw_id": raw_id,
        "tool_id": tool_id,
        "event_name": event_name,
        "timestamp": ts,
    }
