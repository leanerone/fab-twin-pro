"""消息调试接口（方案A）：手动注入一条事件到 DT_EVENT_RAW

事件走真实链路：DT_EVENT_RAW → db_poller 轮询 → WebSocket raw_event → 前端动画，
与外部系统写入效果完全一致，供 Motion2D 调试面板 / 联调使用。

生产安全：写接口要求管理员（require_admin）且必须显式开启环境开关
FABTWIN_DEBUG_WRITE_ENABLED=1 —— 开关未开启时管理员同样 403，权限不可绕过。
"""
import json
import os
from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import DT_EVENT_RAW, DT_EVENT_RAW_CUR, Machine
from core.deps import require_admin
from modules.production_monitor.routes.rvmessages import generate_raw_id

router = APIRouter(prefix="/api/debug", tags=["debug"])

_DEBUG_WRITE_ENV = "FABTWIN_DEBUG_WRITE_ENABLED"


def _debug_write_enabled() -> bool:
    """显式环境开关：仅认 1/true/yes/on（大小写不敏感），默认关闭。"""
    return os.getenv(_DEBUG_WRITE_ENV, "").strip().lower() in ("1", "true", "yes", "on")


class DebugEventIn(BaseModel):
    tool_id: str
    event_name: str
    event_type: str = "VFEI"
    run_mode: Optional[str] = None
    params: Dict[str, object] = {}


@router.post("/event")
def inject_event(body: DebugEventIn, db: Session = Depends(get_db), user=Depends(require_admin)):
    # 环境开关在 require_admin 之后再查：管理员无法绕过未开启的开关。
    if not _debug_write_enabled():
        raise HTTPException(
            status_code=403,
            detail=f"调试写入未启用：请设置 {_DEBUG_WRITE_ENV}=1 后重启服务",
        )
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
    # 复用 rvmessages 的生成器：TID.Z 前缀 + 固定宽度微秒 + UUID hex，
    # 字典序==时间序，恒排在模拟器 TID.<数字> 之前，poller 窗口内可见。
    raw_id = generate_raw_id()

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
