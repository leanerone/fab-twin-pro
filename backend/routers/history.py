"""历史数据回放API：基于DT_EVENT_RAW表实现事件时间轴回放

生产环境关键说明：
- 量产Oracle中 event_ts_utc 多为 None，真实时间戳在 received_ts_utc
- received_ts_utc 是 VARCHAR2 类型，存储格式可能为：
  1. ISO T 分隔: "2026-07-23T08:00:00" (本地seed数据)
  2. 空格分隔:   "2026-07-23 08:00:00"
  3. NLS 中文:   "2026-7-23 下午12:01:14" (量产Oracle，月日不补零+12小时制)
- 由于格式不统一，不在SQL层做时间过滤，全部在Python层用 parse_ts 解析过滤
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import datetime
import json

from database import get_db
from models import DT_EVENT_RAW, MachineToolMapping
from services.time_utils import parse_ts, normalize_ts

router = APIRouter(prefix="/api/history", tags=["history"])


def _resolve_tool_ids(db, machine_id: str) -> set:
    """将 machine_id 解析为对应的 tool_id 集合（支持 VPO-01 -> PODOPENER-1 映射）"""
    tool_ids = {machine_id}

    # PODOPENER 机台量产 Oracle 中 tool_id 通常为 PODOPENER（不带序号）
    if machine_id.upper().startswith("PODOPENER"):
        tool_ids.add("PODOPENER")

    # 尝试查询映射表（可能不存在于量产 Oracle 中）
    try:
        mappings = db.query(MachineToolMapping).filter(
            (MachineToolMapping.machine_id == machine_id) |
            (MachineToolMapping.tool_id == machine_id)
        ).all()
        for m in mappings:
            tool_ids.add(m.tool_id)
            tool_ids.add(m.machine_id)
    except Exception:
        pass  # 映射表不存在或查询失败，忽略

    return tool_ids


def _parse_vfei_payload(payload_json: str) -> dict:
    """解析VFEI事件payload"""
    try:
        return json.loads(payload_json) if payload_json else {}
    except Exception:
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

    # 构造可读的事件描述：优先 alarm_text/description，其次 event_name
    description = payload.get("alarm_text") or payload.get("description") or event_name

    return {
        "raw_id": row.raw_id,
        "tool_id": row.tool_id,
        "source_system": row.source_system,
        "source_message_id": row.source_message_id,
        "timestamp": normalize_ts(ts_value),
        "parse_status": row.parse_status,
        "event_category": event_category,
        "event_name": event_name,
        "event_type": payload.get("event_type", "VFEI"),
        "description": description,
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
    limit: int = Query(500, ge=1, le=20000),
    offset: int = Query(0, ge=0),
    before_raw_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """获取指定机台的历史事件时间轴

    由于 received_ts_utc 是 VARCHAR2 且格式不统一（ISO/空格/NLS中文），
    不在SQL层做时间过滤，在Python层用 parse_ts 解析过滤。

    分页策略：
    - 优先按 start_time/end_time 在 Python 层做时间过滤
    - 当事件总数超 limit 时，前端用 before_raw_id 翻页

    自动分页（解决日期往前几天无事件的问题）：
    - 当指定了 start_time 且未指定 before_raw_id 时，会在SQL层以 start_dt 为锚点
      通过 raw_id 范围分批拉取数据，最多累计 20 批
    - 这样能保证即使在历史较早的日期，也能拿到完整事件列表
    """
    tool_ids = _resolve_tool_ids(db, tool_id)

    start_dt = parse_ts(start_time) if start_time else None
    end_dt = parse_ts(end_time) if end_time else None

    # 自动分页：当指定了 start_time 但没指定 before_raw_id 时，
    # 通过 raw_id 锚点分批拉取数据，规避 VARCHAR2 时间字段无法在SQL层过滤的限制
    if start_dt and before_raw_id is None:
        # 先找到 start_time 对应位置的 raw_id 锚点
        # 方法：以 raw_id 降序扫描，按 Python 解析的 ts 定位到第一个 ts <= start_dt 的位置
        anchor_raw_id = _find_raw_id_anchor(db, tool_ids, start_dt)
        if anchor_raw_id is not None:
            # 拉取 anchor 之后的所有事件
            rows = db.query(DT_EVENT_RAW).filter(
                DT_EVENT_RAW.tool_id.in_(tool_ids),
                DT_EVENT_RAW.raw_id <= anchor_raw_id
            ).order_by(DT_EVENT_RAW.raw_id.desc()).limit(20000).all()
        else:
            # 兜底：拉取最近 20000 条
            rows = db.query(DT_EVENT_RAW).filter(
                DT_EVENT_RAW.tool_id.in_(tool_ids)
            ).order_by(DT_EVENT_RAW.raw_id.desc()).limit(20000).all()
    else:
        # 普通分页模式
        query = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id.in_(tool_ids))
        if before_raw_id is not None:
            query = query.filter(DT_EVENT_RAW.raw_id < before_raw_id)

        fetch_limit = min(limit + offset, 20000)
        rows = query.order_by(DT_EVENT_RAW.raw_id.desc()).limit(fetch_limit).all()

    # Python层解析和过滤
    events = []
    for r in rows:
        ev = _event_to_dict(r)
        ts = ev.get("timestamp", "")
        if not ts:
            continue
        ev_dt = parse_ts(ts)
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

    # 下一页游标：返回结果中 raw_id 最小值 - 1
    next_raw_id = None
    if paged:
        next_raw_id = min(e["raw_id"] for e in paged) - 1

    return {
        "tool_id": tool_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "next_raw_id": next_raw_id,
        "events": paged,
    }


def _find_raw_id_anchor(db, tool_ids: set, target_dt) -> Optional[int]:
    """在 raw_id 降序中定位到 ts <= target_dt 的最大 raw_id

    解决 VARCHAR2 时间字段无法在SQL层做时间比较的问题：
    按 raw_id 降序扫描，找到第一个 ts <= target_dt 的位置，返回该 raw_id
    后续查询以这个 raw_id 为上限，可获取从该时间点往后的所有事件

    二分查找（性能优化）：按 raw_id 范围二分定位
    """
    from models import DT_EVENT_RAW
    try:
        # 获取 raw_id 范围
        min_max = db.query(
            func.min(DT_EVENT_RAW.raw_id),
            func.max(DT_EVENT_RAW.raw_id)
        ).filter(DT_EVENT_RAW.tool_id.in_(tool_ids)).first()
        if not min_max or min_max[0] is None:
            return None
        rid_min, rid_max = min_max[0], min_max[1]
    except Exception:
        return None

    # 二分查找：找最大的 raw_id 使得 ts <= target_dt
    lo, hi = rid_min, rid_max
    best_anchor = None
    max_iterations = 30  # 防止死循环
    for _ in range(max_iterations):
        if lo > hi:
            break
        mid = (lo + hi) // 2
        # 取出 mid 位置的事件
        row = db.query(DT_EVENT_RAW).filter(
            DT_EVENT_RAW.tool_id.in_(tool_ids),
            DT_EVENT_RAW.raw_id == mid
        ).first()
        if not row:
            # mid 位置无数据，向左移动
            hi = mid - 1
            continue
        ts = row.event_ts_utc or row.received_ts_utc
        row_dt = parse_ts(ts) if ts else 0
        if row_dt and row_dt <= target_dt:
            # mid 位置的时间 <= target_dt，可以作为候选，尝试向右找更大的
            best_anchor = mid
            lo = mid + 1
        else:
            # mid 位置的时间 > target_dt，需要向左找
            hi = mid - 1

    return best_anchor


@router.get("/{tool_id}/timeline")
def get_timeline(
    tool_id: str,
    date: Optional[str] = Query(None, description="日期 YYYY-MM-DD，默认今天"),
    db: Session = Depends(get_db),
):
    """获取机台单日时间轴摘要（按小时聚合）

    不在SQL层做日期过滤，通过 raw_id 锚点 + Python 层日期过滤+按小时聚合。
    """
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    tool_ids = _resolve_tool_ids(db, tool_id)

    # 用 start_dt 锚点定位到指定日期起点
    try:
        target_dt = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        target_dt = datetime.now()

    # 找 target_dt 开始的 raw_id 锚点
    anchor = _find_raw_id_anchor(db, tool_ids, target_dt)
    if anchor is not None:
        # 拉取从 anchor 开始的所有事件，限定到当天结束
        next_day_dt = target_dt.replace(hour=23, minute=59, second=59)
        # 找下一天的锚点（也即当天的终点 raw_id）
        next_anchor = _find_raw_id_anchor(db, tool_ids, next_day_dt)
        if next_anchor is not None:
            rows = db.query(DT_EVENT_RAW).filter(
                DT_EVENT_RAW.tool_id.in_(tool_ids),
                DT_EVENT_RAW.raw_id <= anchor,
                DT_EVENT_RAW.raw_id > next_anchor
            ).order_by(DT_EVENT_RAW.raw_id.desc()).limit(20000).all()
        else:
            rows = db.query(DT_EVENT_RAW).filter(
                DT_EVENT_RAW.tool_id.in_(tool_ids),
                DT_EVENT_RAW.raw_id <= anchor
            ).order_by(DT_EVENT_RAW.raw_id.desc()).limit(20000).all()
    else:
        # 兜底：拉取最近 5000 条
        rows = (
            db.query(DT_EVENT_RAW)
            .filter(DT_EVENT_RAW.tool_id.in_(tool_ids))
            .order_by(DT_EVENT_RAW.raw_id.desc())
            .limit(5000)
            .all()
        )

    # 按小时聚合（在Python层解析时间）
    hours = {h: {"alarm": 0, "pod": 0, "process": 0, "other": 0, "events": []} for h in range(24)}

    for row in rows:
        ev = _event_to_dict(row)
        ts = ev.get("timestamp", "")
        dt = parse_ts(ts)
        if not dt:
            continue
        # 只统计指定日期
        if dt.strftime("%Y-%m-%d") != date:
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

    # 查找前后事件（用 raw_id 近似，因为 VARCHAR2 时间格式不统一无法可靠 ORDER BY）
    tool_ids = _resolve_tool_ids(db, tool_id)
    prev_row = (
        db.query(DT_EVENT_RAW)
        .filter(DT_EVENT_RAW.tool_id.in_(tool_ids))
        .filter(DT_EVENT_RAW.raw_id < raw_id)
        .order_by(DT_EVENT_RAW.raw_id.desc())
        .first()
    )
    next_row = (
        db.query(DT_EVENT_RAW)
        .filter(DT_EVENT_RAW.tool_id.in_(tool_ids))
        .filter(DT_EVENT_RAW.raw_id > raw_id)
        .order_by(DT_EVENT_RAW.raw_id.asc())
        .first()
    )

    ev["prev_event_id"] = prev_row.raw_id if prev_row else None
    ev["next_event_id"] = next_row.raw_id if next_row else None
    ev["prev_timestamp"] = normalize_ts(prev_row.event_ts_utc or prev_row.received_ts_utc) if prev_row else None
    ev["next_timestamp"] = normalize_ts(next_row.event_ts_utc or next_row.received_ts_utc) if next_row else None

    return ev
