"""RV消息API：接收RV实时消息，查询当前状态

关键设计：
- 写入 DT_EVENT_RAW 时 received_ts_utc 用 ISO T 分隔格式
  （parse_ts 可正确解析，与 NLS 中文格式兼容）
- 查询历史时按 raw_id 降序，不用 VARCHAR2 时间排序
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
import hmac
import json
import os

from database import get_db
from models import DT_EVENT_RAW, DT_EVENT_RAW_CUR
from services.realtime import manager
from services.time_utils import normalize_ts

router = APIRouter(prefix="/api/rv", tags=["rv"])


def _ingest_key() -> str:
    return os.getenv("FABTWIN_INGEST_API_KEY", "").strip()


def _client_is_local(request: Request) -> bool:
    host = (request.client.host if request.client else "") or ""
    if host in ("127.0.0.1", "::1", "localhost"):
        return True
    try:
        import ipaddress
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback
    except Exception:
        return False


def require_ingest_auth(
    request: Request,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """事件注入鉴权。

    2026-10-29 安全修复：`POST /api/rv/message` 此前零鉴权，任何人都能向千万级的
    DT_EVENT_RAW 注入伪造事件，污染历史回放 / AI 分析 / 前端动画，并广播给所有客户端。

    策略（兼顾 EAP/WinForm 对接与开发便利）：
      1. 设置 FABTWIN_INGEST_API_KEY → 必须携带匹配的 X-API-Key（恒定时间比较）
      2. 未设置 → 仅允许本机/内网来源（开发调试与同机部署可用），外网一律 401
    """
    expected = _ingest_key()
    if expected:
        provided = x_api_key or ""
        auth_header = request.headers.get("Authorization", "")
        if auth_header.lower().startswith("bearer "):
            provided = provided or auth_header[7:].strip()
        if not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
        return True
    if not _client_is_local(request):
        raise HTTPException(
            status_code=401,
            detail="事件注入需要鉴权：请设置 FABTWIN_INGEST_API_KEY 并在请求头携带 X-API-Key",
        )
    return True


class RVMessageRequest(BaseModel):
    tool_id: str
    source_system: str = "RV"
    source_message_id: str
    received_ts_utc: str = None
    event_ts_utc: str = None
    payload_json: str
    parse_status: str = "PARSED"


@router.post("/message")
def receive_rv_message(
    data: RVMessageRequest,
    request: Request,
    db: Session = Depends(get_db),
    _auth=Depends(require_ingest_auth),
):
    """接收RV实时消息，写入DT_EVENT_RAW和DT_EVENT_RAW_CUR

    普通 def（FastAPI 自动放入线程池执行）：同步DB写入不再阻塞事件循环。
    广播经 manager.broadcast_from_thread 调度回事件循环。
    """
    now = datetime.now().isoformat()
    received_ts = data.received_ts_utc or now
    event_ts = data.event_ts_utc or now

    # raw_id 必须与存量事件保持同序（Z{timestamp} 前缀），
    # 否则 db_poller 按 raw_id DESC 拉最近 300 行时新事件被挤出窗口。
    raw_event = DT_EVENT_RAW(
        raw_id=f"TID.Z{int(datetime.now().timestamp())}{os.getpid() % 1000:03d}",
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
    # 广播格式对齐 db_poller._parse_event_payload 输出，
    # 前端 useWebSocket 只认 type="raw_event"。
    try:
        from services.db_poller import _parse_event_payload
        parsed = _parse_event_payload(raw_event)
        manager.broadcast_from_thread({"type": "raw_event", "data": parsed})
    except Exception:
        # 降级：最小化格式，兜底保证前端能收到
        manager.broadcast_from_thread({
            "type": "raw_event",
            "data": {
                "raw_id": raw_event.raw_id,
                "tool_id": data.tool_id,
                "event_name": payload.get("event_name", "UNKNOWN"),
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
    """获取机台RV消息历史

    按 raw_id 降序（近似时间倒序；VARCHAR2 时间排序不可靠）。
    """
    rows = (
        db.query(DT_EVENT_RAW)
        .filter(DT_EVENT_RAW.tool_id == tool_id)
        .order_by(DT_EVENT_RAW.raw_id.desc())
        .limit(limit)
        .all()
    )

    events = []
    for row in rows:
        payload = json.loads(row.payload_json) if row.payload_json else {}
        events.append({
            "raw_id": row.raw_id,
            "event_ts_utc": normalize_ts(row.event_ts_utc or row.received_ts_utc),
            "event_name": payload.get("event_name", "UNKNOWN"),
            "lot_id": payload.get("lot_id"),
            "cassette_id": payload.get("cassette_id"),
            "alarm_id": payload.get("alarm_id"),
            "alarm_text": payload.get("alarm_text"),
        })

    return {"tool_id": tool_id, "total": len(events), "events": events}
