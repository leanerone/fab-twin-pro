"""OXE 机台专用接口：为 oxe.html 提供 latest-event / history-events

设计说明：
- 数据源：DT_EVENT_RAW_CUR（最新一条）+ DT_EVENT_RAW（历史）
- 字段转换：量产 DB payload 已包含 HTML 所需字段（event_name/port_id/chamber_id 等），
  HTML 的 normalizeIncomingEvent/getEffectiveEventName 会自动处理大写事件名和 "NULL" 字符串。
- 唯一需要后端处理的：ALARM_REPORT 事件的 port_id/chamber_id 等字段被 bridge.py 错误
  填充为告警描述词（如 "AGC"/"Time"/"Sensor-2"），需清空这些字段，只保留 alarm_text。
  此逻辑已提取为 services.ai_tools.clean_alarm_event 公共函数，AI 工具层复用。
- 时间戳：量产 DB 的 event_ts_utc 为 null，用 received_ts_utc 作为 fallback。
"""
import json
import logging
from fastapi import APIRouter, Query, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import DT_EVENT_RAW, DT_EVENT_RAW_CUR
from services.ai_tools import clean_alarm_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/oxe", tags=["oxe"])


def _parse_payload(payload_json) -> dict:
    """解析 CLOB payload_json，失败返回空 dict"""
    if not payload_json:
        return {}
    # oracledb CLOB 读取
    if hasattr(payload_json, "read"):
        payload_json = payload_json.read()
    try:
        return json.loads(payload_json) if isinstance(payload_json, str) else {}
    except Exception:
        return {"_raw": str(payload_json)[:500]}


def _convert_event(row, table_name: str) -> dict:
    """将 DT_EVENT_RAW / DT_EVENT_RAW_CUR 行转换为 HTML 期望的事件格式

    转换规则：
    1. 解析 payload_json
    2. 如果是 ALARM 事件，清空被错误填充的字段（复用 clean_alarm_event）
    3. received_ts_utc 作为 event_ts_utc 的 fallback
    4. raw_id 用于轮询去重
    """
    payload = _parse_payload(row.payload_json)

    # ALARM 事件：清空被错误解析的字段（复用公共函数，保持与 AI 工具层一致）
    payload = clean_alarm_event(payload)

    # 时间戳 fallback：event_ts_utc 为 null 时用 received_ts_utc
    received_ts = str(row.received_ts_utc) if row.received_ts_utc else ""
    if not payload.get("event_ts_utc"):
        payload["event_ts_utc"] = received_ts
    # 同时保留 received_ts_utc 供 HTML normalizeIncomingEvent 使用
    payload["received_ts_utc"] = received_ts
    # raw_id 用于轮询去重（HTML 通过比较 raw_id 判断是否有新事件）
    payload["raw_id"] = str(row.raw_id)

    return payload


@router.get("/latest-event")
def get_latest_event(tool_id: str = Query(..., description="机台 tool_id，如 OXE-51"), db: Session = Depends(get_db)):
    """获取机台最新一条事件（用于 1 秒轮询实时画面）

    数据源：DT_EVENT_RAW_CUR（每机台保留最新一条）
    """
    row = (
        db.query(DT_EVENT_RAW_CUR)
        .filter(DT_EVENT_RAW_CUR.tool_id == tool_id)
        .first()
    )
    if not row:
        return {"error": "not_found", "tool_id": tool_id, "message": "该机台无当前事件"}
    return _convert_event(row, "DT_EVENT_RAW_CUR")


@router.get("/history-events")
def get_history_events(
    tool_id: str = Query(..., description="机台 tool_id，如 OXE-51"),
    limit: int = Query(2000, ge=1, le=5000, description="最大返回条数"),
    db: Session = Depends(get_db),
):
    """获取机台历史事件（用于历史回放 + 状态重建 bootstrap）

    数据源：DT_EVENT_RAW（完整历史表）
    排序：raw_id DESC（最新在前），HTML 端会自行排序
    """
    rows = (
        db.query(DT_EVENT_RAW)
        .filter(DT_EVENT_RAW.tool_id == tool_id)
        .filter(DT_EVENT_RAW.parse_status == "PARSED")
        .order_by(DT_EVENT_RAW.raw_id.desc())
        .limit(limit)
        .all()
    )
    events = [_convert_event(r, "DT_EVENT_RAW") for r in rows]
    return {
        "tool_id": tool_id,
        "count": len(events),
        "events": events,
    }
