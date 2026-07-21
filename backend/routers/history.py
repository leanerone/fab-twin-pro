"""历史数据回放API：基于DT_EVENT_RAW表实现事件时间轴回放"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import json
import re

from database import get_db
from models import DT_EVENT_RAW

router = APIRouter(prefix="/api/history", tags=["history"])


def _normalize_ts(ts: str) -> str:
    """标准化时间戳：去掉Z后缀和时区信息，统一为东八区本地时间格式
    数据库中存在两种格式：
    1. 2026-07-12T08:00:00.000Z （本地时间被错误标记为UTC）
    2. 2026-07-18T20:25:00.054573 （本地时间无后缀）
    3. 2026-07-17 00:52:55 （Oracle存储为空格分隔）
    返回空格分隔格式，同时保留原始格式用于多格式匹配
    """
    if not ts:
        return ""
    ts = str(ts).strip()
    ts = re.sub(r'(Z|[+-]\d{2}:\d{2})$', '', ts)
    ts = ts.replace('T', ' ')
    return ts


def _get_ts_filter(column, start_ts=None, end_ts=None):
    """生成时间范围查询条件，同时支持T分隔和空格分隔的时间戳格式
    
    关键问题：Oracle中event_ts_utc是String类型，字符串比较是按ASCII码：
    - 空格(32) < T(84)，所以 "2026-07-17 00:00:00" < "2026-07-17T00:00:00"
    如果只查询空格格式，会漏掉所有T分隔的数据！
    
    解决方案：用OR条件同时匹配两种格式
    """
    from sqlalchemy import or_
    
    conditions = []
    if start_ts:
        start_space = _normalize_ts(start_ts)
        start_T = start_space.replace(' ', 'T')
        conditions.append(or_(
            column >= start_space,
            column >= start_T
        ))
    if end_ts:
        end_space = _normalize_ts(end_ts)
        end_T = end_space.replace(' ', 'T')
        conditions.append(or_(
            column <= end_space,
            column <= end_T
        ))
    return conditions


def _parse_vfei_payload(payload_json: str) -> dict:
    """解析VFEI事件payload，统一返回结构化数据"""
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

    return {
        "raw_id": row.raw_id,
        "tool_id": row.tool_id,
        "source_system": row.source_system,
        "source_message_id": row.source_message_id,
        "timestamp": _normalize_ts(row.event_ts_utc or row.received_ts_utc),
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
    """
    获取指定机台的历史事件时间轴

    参数:
    - tool_id: 机台ID (如 VPO-01, OXE-01)
    - start_time: 开始时间 (ISO格式, 如 2026-06-14T00:00:00)
    - end_time: 结束时间
    - event_category: 过滤事件类型 alarm/pod/process
    - limit: 返回数量上限
    - offset: 分页偏移
    """
    query = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id == tool_id)

    ts_conditions = _get_ts_filter(DT_EVENT_RAW.event_ts_utc, start_time, end_time)
    for cond in ts_conditions:
        query = query.filter(cond)

    query = query.order_by(DT_EVENT_RAW.event_ts_utc.asc())
    total = query.count()
    rows = query.offset(offset).limit(limit).all()

    events = [_event_to_dict(r) for r in rows]

    # 如果有过滤条件，在Python层过滤（因为event_category是从payload解析的）
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
    """
    获取机台单日时间轴摘要（用于时间轴缩略图）
    返回按小时聚合的事件统计
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    start = f"{date} 00:00:00"
    end = f"{date} 23:59:59.999999"

    rows = (
        db.query(DT_EVENT_RAW)
        .filter(DT_EVENT_RAW.tool_id == tool_id)
        .filter(or_(DT_EVENT_RAW.event_ts_utc >= start, DT_EVENT_RAW.event_ts_utc >= start.replace(' ', 'T')))
        .filter(or_(DT_EVENT_RAW.event_ts_utc <= end, DT_EVENT_RAW.event_ts_utc <= end.replace(' ', 'T')))
        .order_by(DT_EVENT_RAW.event_ts_utc.asc())
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

    ts_conditions = _get_ts_filter(DT_EVENT_RAW.event_ts_utc, start_time, end_time)
    for cond in ts_conditions:
        query = query.filter(cond)

    query = query.order_by(DT_EVENT_RAW.event_ts_utc.desc())
    rows = query.limit(limit * 3).all()  # 多取一些用于过滤

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
    ts_str = str(row.event_ts_utc)
    ts_space = ts_str.replace('T', ' ')
    ts_T = ts_str.replace(' ', 'T')
    
    prev_row = (
        db.query(DT_EVENT_RAW)
        .filter(DT_EVENT_RAW.tool_id == tool_id)
        .filter(or_(DT_EVENT_RAW.event_ts_utc < ts_space, DT_EVENT_RAW.event_ts_utc < ts_T))
        .order_by(DT_EVENT_RAW.event_ts_utc.desc())
        .first()
    )
    next_row = (
        db.query(DT_EVENT_RAW)
        .filter(DT_EVENT_RAW.tool_id == tool_id)
        .filter(or_(DT_EVENT_RAW.event_ts_utc > ts_space, DT_EVENT_RAW.event_ts_utc > ts_T))
        .order_by(DT_EVENT_RAW.event_ts_utc.asc())
        .first()
    )

    ev["prev_event_id"] = prev_row.raw_id if prev_row else None
    ev["next_event_id"] = next_row.raw_id if next_row else None
    ev["prev_timestamp"] = _normalize_ts(prev_row.event_ts_utc) if prev_row else None
    ev["next_timestamp"] = _normalize_ts(next_row.event_ts_utc) if next_row else None

    return ev
