"""历史数据回放API：基于DT_EVENT_RAW表实现事件时间轴回放

生产环境关键说明：
- 量产Oracle中 event_ts_utc 多为 None，真实时间戳在 received_ts_utc
- received_ts_utc 是 VARCHAR2 类型，存储格式为 Oracle NLS 中文：
  例如: "2026-7-23 下午12:01:14" (月/日不补零，12小时制+上午/下午)
- 由于格式不统一且月日不补零，查询用 LIKE 前缀匹配日期，Python层精确过滤
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional
from datetime import datetime
import json
import re

from database import get_db, DB_IS_SQLITE
from models import DT_EVENT_RAW

router = APIRouter(prefix="/api/history", tags=["history"])


def _parse_ts(ts) -> Optional[datetime]:
    """将各种格式的时间戳转换为 datetime 对象

    支持格式（按优先级）：
    1. datetime 对象（直接返回）
    2. Oracle NLS 中文: "2026-7-23 下午12:01:14" / "2026-07-23 上午08:30:00"
    3. "2026-07-21 00:00:00" (标准24小时制)
    4. "2026-07-21T00:00:00" (ISO)
    5. "2026-07-21T00:00:00.000Z" (带Z后缀)
    6. "2026-07-21" (仅日期)
    """
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts
    ts = str(ts).strip()
    if not ts:
        return None

    # 先去掉 Z 和时区后缀
    ts_clean = re.sub(r'(Z|[+-]\d{2}:\d{2})$', '', ts)

    # 格式1: Oracle NLS 中文 "2026-7-23 下午12:01:14"
    # 月日不补零，12小时制，上午/下午
    nls_match = re.match(
        r'^(\d{4})-(\d{1,2})-(\d{1,2})\s+(上午|下午)\s*(\d{1,2}):(\d{2}):(\d{2})$',
        ts_clean
    )
    if nls_match:
        year = int(nls_match.group(1))
        month = int(nls_match.group(2))
        day = int(nls_match.group(3))
        ampm = nls_match.group(4)
        hour = int(nls_match.group(5))
        minute = int(nls_match.group(6))
        second = int(nls_match.group(7))
        # 12小时制转24小时制
        if ampm == '下午' and hour != 12:
            hour += 12
        elif ampm == '上午' and hour == 12:
            hour = 0
        try:
            return datetime(year, month, day, hour, minute, second)
        except ValueError:
            pass

    # 格式2-5: 标准格式
    formats = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%Y-%-m-%-d %H:%M:%S",  # 不补零的24小时制
    ]
    for fmt in formats:
        try:
            return datetime.strptime(ts_clean, fmt)
        except ValueError:
            continue

    # 最后尝试：不补零的日期+时间（月日不补零，24小时制）
    loose_match = re.match(
        r'^(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})$',
        ts_clean
    )
    if loose_match:
        try:
            return datetime(
                int(loose_match.group(1)),
                int(loose_match.group(2)),
                int(loose_match.group(3)),
                int(loose_match.group(4)),
                int(loose_match.group(5)),
                int(loose_match.group(6)),
            )
        except ValueError:
            pass

    return None


def _normalize_ts(ts) -> str:
    """标准化时间戳为 'YYYY-MM-DD HH:MM:SS' 格式（用于API输出）"""
    dt = _parse_ts(ts)
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _date_to_like_prefix(date_str: str) -> str:
    """将 YYYY-MM-DD 转换为 LIKE 查询前缀
    由于 Oracle NLS 格式月日不补零，需要匹配 "2026-7-23 " 和 "2026-07-23 "
    返回多种可能的前缀列表
    """
    parts = date_str.split('-')
    if len(parts) != 3:
        return [f"{date_str}%"]
    y, m, d = parts
    mi = int(m)
    di = int(d)
    # 生成补零和不补零的组合
    prefixes = [
        f"{y}-{m}-{d} ",       # 都补零: 2026-07-23
        f"{y}-{mi}-{di} ",     # 都不补零: 2026-7-23
        f"{y}-{m}-{di} ",      # 月补零日不补零: 2026-07-23 (同第一个，但di可能一位)
        f"{y}-{mi}-{d} ",      # 月不补零日补零: 2026-7-23 (同第二个，但d可能两位)
    ]
    # 去重
    seen = set()
    unique = []
    for p in prefixes:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def _get_ts_column():
    """获取用于时间查询的列（优先 event_ts_utc，回退 received_ts_utc）"""
    from sqlalchemy import func
    return func.nvl(DT_EVENT_RAW.event_ts_utc, DT_EVENT_RAW.received_ts_utc)


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

    # 对于 VARCHAR2 列的时间范围查询：
    # 先用 LIKE 前缀匹配缩小范围（按日期），再在 Python 层精确过滤
    start_dt = _parse_ts(start_time) if start_time else None
    end_dt = _parse_ts(end_time) if end_time else None

    # 日期前缀匹配（减少数据量）
    if start_dt:
        date_str = start_dt.strftime("%Y-%m-%d")
        prefixes = _date_to_like_prefix(date_str)
        or_conditions = [ts_col.like(p) for p in prefixes]
        query = query.filter(or_(*or_conditions))
    if end_dt:
        # end_date 也加前缀匹配
        date_str = end_dt.strftime("%Y-%m-%d")
        prefixes = _date_to_like_prefix(date_str)
        or_conditions = [ts_col.like(p) for p in prefixes]
        # 注意：如果有 start 和 end 且在同一天，用 AND；跨天的话需要 OR
        # 这里简单处理：只按 end 日期过滤，精确范围在 Python 层做
        # 更稳妥的方式是不在这里限制 end，让 Python 层处理
        pass

    # 按 raw_id 降序（通常 raw_id 递增，近似时间顺序）
    # 由于 VARCHAR2 时间格式不统一，无法可靠 ORDER BY
    query = query.order_by(DT_EVENT_RAW.raw_id.desc())

    # 多取一些数据，在 Python 层过滤后分页
    fetch_limit = min(limit * 10 + offset, 5000)
    rows = query.limit(fetch_limit).all()

    # Python 层解析和过滤
    events = []
    for r in rows:
        ev = _event_to_dict(r)
        ts = ev.get("timestamp", "")
        if not ts:
            continue
        ev_dt = _parse_ts(ts)
        if not ev_dt:
            continue
        if start_dt and ev_dt < start_dt:
            continue
        if end_dt and ev_dt > end_dt:
            continue
        if event_category and ev["event_category"] != event_category:
            continue
        events.append(ev)

    # 按时间正序
    events.sort(key=lambda e: e["timestamp"])

    total = len(events)
    paged = events[offset:offset + limit]

    return {
        "tool_id": tool_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "events": paged,
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

    # 用 LIKE 前缀匹配当天数据
    ts_col = _get_ts_column()
    prefixes = _date_to_like_prefix(date)
    or_conditions = [ts_col.like(p) for p in prefixes]

    rows = (
        db.query(DT_EVENT_RAW)
        .filter(DT_EVENT_RAW.tool_id == tool_id)
        .filter(or_(*or_conditions))
        .order_by(DT_EVENT_RAW.raw_id.asc())
        .limit(5000)
        .all()
    )

    # 按小时聚合（在 Python 层解析时间）
    hours = {h: {"alarm": 0, "pod": 0, "process": 0, "other": 0, "events": []} for h in range(24)}

    for row in rows:
        ev = _event_to_dict(row)
        ts = ev.get("timestamp", "")
        dt = _parse_ts(ts)
        if not dt:
            continue
        hour = dt.hour

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
    # 先查历史事件，在 Python 层过滤 alarm
    result = get_history(
        tool_id=tool_id,
        start_time=start_time,
        end_time=end_time,
        event_category="alarm",
        limit=limit * 3,
        offset=0,
        db=db,
    )

    alarms = []
    for ev in result["events"]:
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

    # 查找前后事件（用 raw_id 近似，因为时间格式不统一）
    prev_row = (
        db.query(DT_EVENT_RAW)
        .filter(DT_EVENT_RAW.tool_id == tool_id)
        .filter(DT_EVENT_RAW.raw_id < raw_id)
        .order_by(DT_EVENT_RAW.raw_id.desc())
        .first()
    )
    next_row = (
        db.query(DT_EVENT_RAW)
        .filter(DT_EVENT_RAW.tool_id == tool_id)
        .filter(DT_EVENT_RAW.raw_id > raw_id)
        .order_by(DT_EVENT_RAW.raw_id.asc())
        .first()
    )

    ev["prev_event_id"] = prev_row.raw_id if prev_row else None
    ev["next_event_id"] = next_row.raw_id if next_row else None
    ev["prev_timestamp"] = _normalize_ts(prev_row.event_ts_utc or prev_row.received_ts_utc) if prev_row else None
    ev["next_timestamp"] = _normalize_ts(next_row.event_ts_utc or next_row.received_ts_utc) if next_row else None

    return ev
