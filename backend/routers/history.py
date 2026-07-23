"""历史数据回放API：基于DT_EVENT_RAW表实现事件时间轴回放

生产环境关键说明：
- 量产Oracle中 event_ts_utc 多为 None，真实时间戳在 received_ts_utc
- received_ts_utc 是 datetime 类型，不是字符串
- 必须用 datetime 对象查询，不能用字符串，否则报 ORA-01843
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
from datetime import datetime
import json
import re

from database import get_db
from models import DT_EVENT_RAW

router = APIRouter(prefix="/api/history", tags=["history"])


def _parse_ts(ts) -> Optional[datetime]:
    """将各种格式的时间戳转换为 datetime 对象
    
    支持格式：
    - datetime 对象（直接返回）
    - "2026-07-21T00:00:00" (ISO)
    - "2026-07-21 00:00:00" (空格分隔)
    - "2026-07-21T00:00:00.000Z" (带Z后缀)
    - "2026-07-21" (仅日期)
    """
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts
    ts = str(ts).strip()
    # 去掉 Z 和时区后缀
    ts = re.sub(r'(Z|[+-]\d{2}:\d{2})$', '', ts)
    # 尝试多种格式
    formats = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return None


def _format_ts_for_query(dt: datetime) -> str:
    """将 datetime 转换为字符串，用于与 VARCHAR2 列比较
    
    Oracle VARCHAR2 存储格式混合：有 'YYYY-MM-DD HH:MM:SS' 也有 'YYYY-MM-DDTHH:MM:SS'
    使用 'YYYY-MM-DD' 格式做前缀匹配比较更安全
    对于范围查询，使用 'YYYY-MM-DDTHH:MM:SS' (ISO T格式)
    """
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _normalize_ts(ts) -> str:
    """标准化时间戳为 'YYYY-MM-DD HH:MM:SS' 格式（用于API输出）"""
    dt = _parse_ts(ts)
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _parse_vfei_payload(payload_json: str) -> dict:
    """解析VFEI事件payload"""
    try:
        return json.loads(payload_json) if payload_json else {}
    except:
        return {"_raw": payload_json}


def _event_to_dict(row: DT_EVENT_RAW) -> dict:
    """将DT_EVENT_RAW行转换为API响应格式"""
    payload = _parse_vfei_payload(row.payload_json)
    event_name = payload.get("event_name", "UNKNOWN")

    # 统一事件类型分类
    event_category = "other"
    if event_name == "EC_ALARM_REPORT":
        event_category = "alarm"
    elif event_name in ("DETACH_POD_PLACE", "ATTACH_POD_PLACE", "POD_PLACED", "POD_REMOVED", 
                        "LOCK_PORT_COMPLETED", "UNLOCK_PORT_COMPLETED", "MVIN", "MVOU",
                        "POD_LOCK", "POD_UNLOCK", "READ_TAG", "WRITE_TAG",
                        "COMPLETED_PORT_LOCK", "COMPLETED_PORT_UNLOCK",
                        "READ_BATTERY", "OPEN_POD", "CLOSE_POD"):
        event_category = "pod"
    elif event_name in ("STATE_CHANGE", "PROCESS_START", "PROCESS_END", 
                        "DOOR_OPEN", "DOOR_CLOSE", "LOAD_CYCLE_STARTED", "LOAD_CYCLE_COMPLETED",
                        "UNLOAD_CYCLE_COMPLETED", "StartMapping_LEFT", "StartMapping_RIGHT",
                        "EndMapping", "Start", "PS", "PE", "WaferLoaded", "WaferUnloaded",
                        "LotEnd", "JobEnd", "ReadyToUnload", "BATCH_START", "UI_CONFIRM",
                        "ATTACH_POD_UP", "ATTACH_POD_REACH_STAGE", "ATTACH_CST_PLACE",
                        "ATTACH_POD_DOWN", "ATTACH_POD_REACH_POS", "UI_DOUBLECHECK",
                        "DETACH_POD_UP", "DETACH_POD_REACH_STAGE", "DETACH_CST_REMOVE",
                        "DETACH_POD_DOWN", "DETACH_POD_REACH_POS", "ATTACH_POD_REMOVE",
                        "DETACH_POD_REMOVE",
                        "BATCH_INFO_FROM_ECUI", "REACH_STAGE", "REACH_POS",
                        "ACK_UI_DOUBLECHECK"):
        event_category = "process"

    # 提取alarm信息
    alarm_info = None
    if event_category == "alarm":
        alarm_id = payload.get("alarm_id", "")
        alarm_text = payload.get("alarm_text", "")
        severity = "warn"
        if alarm_id in ("9004", "0201"):
            severity = "crit"
        elif alarm_id == "9003":
            severity = "warn"
        elif alarm_id == "20011":
            severity = "warn"
        elif alarm_id == "0411":
            severity = "info"

        alarm_info = {
            "alarm_id": alarm_id,
            "alarm_text": alarm_text,
            "severity": severity,
        }

    # 优先使用 event_ts_utc，为空则回退 received_ts_utc
    ts_value = row.event_ts_utc or row.received_ts_utc

    return {
        "raw_id": row.raw_id,
        "tool_id": row.tool_id,
        "source_system": row.source_system,
        "source_message_id": row.source_message_id,
        "timestamp": _normalize_ts(ts_value),
        "parse_status": row.parse_status,
        "event_category": event_category,
        "event_name": event_name,
        "event_type": payload.get("event_type", "VFEI"),
        "lot_id": payload.get("lot_id") if payload.get("lot_id") != "NULL" else None,
        "cassette_id": payload.get("cassette_id") if payload.get("cassette_id") != "NULL" else None,
        "chamber_id": payload.get("chamber_id") if payload.get("chamber_id") != "NULL" else None,
        "port_id": payload.get("port_id") if payload.get("port_id") != "NULL" else None,
        "batch_id": payload.get("batch_id") if payload.get("batch_id") != "NULL" else None,
        "alarm": alarm_info,
        "payload": payload,
    }


def _get_ts_column():
    """获取用于时间查询的列
    
    生产环境中 event_ts_utc 多为 None，使用 received_ts_utc 查询
    Oracle 中这两个列是 VARCHAR2 类型，存储格式为 'YYYY-MM-DD HH:MM:SS'
    使用 COALESCE + NVL 优先取 event_ts_utc，为空则取 received_ts_utc
    """
    from sqlalchemy import func
    return func.nvl(DT_EVENT_RAW.event_ts_utc, DT_EVENT_RAW.received_ts_utc)


@router.get("/{tool_id}")
def get_history(
    tool_id: str,
    start_time: Optional[str] = Query(None, description="开始时间 ISO格式"),
    end_time: Optional[str] = Query(None, description="结束时间 ISO格式"),
    event_category: Optional[str] = Query(None, description="事件分类过滤: alarm/pod/process/other"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """获取指定机台的历史事件时间轴"""
    query = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id == tool_id)

    ts_col = _get_ts_column()
    if start_time:
        start_dt = _parse_ts(start_time)
        if start_dt:
            query = query.filter(ts_col >= _format_ts_for_query(start_dt))
    if end_time:
        end_dt = _parse_ts(end_time)
        if end_dt:
            query = query.filter(ts_col <= _format_ts_for_query(end_dt))

    query = query.order_by(ts_col.asc())
    total = query.count()
    rows = query.offset(offset).limit(limit).all()

    events = [_event_to_dict(r) for r in rows]

    # 如果有过滤条件，在Python层过滤
    if event_category:
        events = [e for e in events if e["event_category"] == event_category]

    return {
        "tool_id": tool_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": events,
    }


@router.get("/{tool_id}/timeline")
def get_timeline(
    tool_id: str,
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    db: Session = Depends(get_db),
):
    """获取机台单日时间轴摘要（按小时聚合）"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    # VARCHAR2 列存储 ISO T 格式 'YYYY-MM-DDTHH:MM:SS'，用字符串前缀比较
    start_str = f"{date}T00:00:00"
    end_str = f"{date}T23:59:59"

    ts_col = _get_ts_column()
    rows = (
        db.query(DT_EVENT_RAW)
        .filter(DT_EVENT_RAW.tool_id == tool_id)
        .filter(ts_col >= start_str)
        .filter(ts_col <= end_str)
        .order_by(ts_col.asc())
        .all()
    )

    # 按小时聚合
    hours = {h: {"alarm": 0, "pod": 0, "process": 0, "other": 0, "events": []} for h in range(24)}

    for row in rows:
        ev = _event_to_dict(row)
        ts = ev.get("timestamp", "")
        try:
            hour = int(ts[11:13]) if len(ts) >= 13 else 0
        except:
            hour = 0

        cat = ev["event_category"]
        if 0 <= hour < 24:
            hours[hour][cat] += 1
            hours[hour]["events"].append({
                "raw_id": ev["raw_id"],
                "event_name": ev["event_name"],
                "timestamp": ts,
                "alarm": ev.get("alarm"),
            })

    timeline = []
    for h in range(24):
        d = hours[h]
        total = d["alarm"] + d["pod"] + d["process"] + d["other"]
        timeline.append({
            "hour": h,
            "alarm_count": d["alarm"],
            "pod_count": d["pod"],
            "process_count": d["process"],
            "total_count": total,
            "has_events": total > 0,
        })

    return {
        "tool_id": tool_id,
        "date": date,
        "timeline": timeline,
    }


@router.get("/{tool_id}/alarms")
def get_alarm_history(
    tool_id: str,
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    severity: Optional[str] = Query(None, description="严重程度过滤: crit/warn/info"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """获取机台Alarm历史记录"""
    query = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id == tool_id)

    ts_col = _get_ts_column()
    if start_time:
        start_dt = _parse_ts(start_time)
        if start_dt:
            query = query.filter(ts_col >= _format_ts_for_query(start_dt))
    if end_time:
        end_dt = _parse_ts(end_time)
        if end_dt:
            query = query.filter(ts_col <= _format_ts_for_query(end_dt))

    query = query.order_by(ts_col.desc())
    rows = query.limit(limit * 3).all()

    alarms = []
    for row in rows:
        ev = _event_to_dict(row)
        if ev["event_category"] == "alarm" and ev.get("alarm"):
            alarm = ev["alarm"]
            if severity and alarm.get("severity") != severity:
                continue
            alarms.append({
                "raw_id": ev["raw_id"],
                "timestamp": ev["timestamp"],
                "alarm_id": alarm["alarm_id"],
                "alarm_text": alarm["alarm_text"],
                "severity": alarm["severity"],
                "lot_id": ev.get("lot_id"),
                "cassette_id": ev.get("cassette_id"),
            })
            if len(alarms) >= limit:
                break

    return {
        "tool_id": tool_id,
        "total": len(alarms),
        "alarms": alarms,
    }


@router.get("/{tool_id}/events/{raw_id}")
def get_event_detail(
    tool_id: str,
    raw_id: str,
    db: Session = Depends(get_db),
):
    """获取单个事件的详细信息（用于回放详情弹窗）"""
    row = (
        db.query(DT_EVENT_RAW)
        .filter(DT_EVENT_RAW.tool_id == tool_id)
        .filter(DT_EVENT_RAW.raw_id == raw_id)
        .first()
    )
    if not row:
        return {"error": "Event not found"}

    ev = _event_to_dict(row)

    # 查找前后事件（用于连续回放）
    ts_col = _get_ts_column()
    current_ts = row.event_ts_utc or row.received_ts_utc
    # VARCHAR2 列，直接用字符串比较
    current_ts_str = _normalize_ts(current_ts) if current_ts else None

    prev_row = None
    next_row = None
    if current_ts_str:
        prev_row = (
            db.query(DT_EVENT_RAW)
            .filter(DT_EVENT_RAW.tool_id == tool_id)
            .filter(ts_col < current_ts_str)
            .order_by(ts_col.desc())
            .first()
        )
        next_row = (
            db.query(DT_EVENT_RAW)
            .filter(DT_EVENT_RAW.tool_id == tool_id)
            .filter(ts_col > current_ts_str)
            .order_by(ts_col.asc())
            .first()
        )

    ev["prev_event_id"] = prev_row.raw_id if prev_row else None
    ev["next_event_id"] = next_row.raw_id if next_row else None
    ev["prev_timestamp"] = _normalize_ts(prev_row.event_ts_utc or prev_row.received_ts_utc) if prev_row else None
    ev["next_timestamp"] = _normalize_ts(next_row.event_ts_utc or next_row.received_ts_utc) if next_row else None

    return ev
