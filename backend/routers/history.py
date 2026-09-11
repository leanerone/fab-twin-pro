"""历史数据回放API：基于DT_EVENT_RAW表实现事件时间轴回放

时间列类型（本地与量产不一致，务必按实际类型选过滤写法）：
- 量产 Oracle : RECEIVED_TS_UTC / EVENT_TS_UTC 均为 TIMESTAMP(6)，EVENT_TS_UTC 多为 NULL，
                真实时间戳在 RECEIVED_TS_UTC
- 本地建表    : 两者均为 VARCHAR2(255)，存 "2026-09-09 08:00:00" 这类字符串

为什么不能一律用 LIKE：
  LIKE 打在 TIMESTAMP 列上时，Oracle 会按 NLS_TIMESTAMP_FORMAT（默认 DD-MON-RR
  HH.MI.SSXFF AM）把时间隐式转成字符串再比，'2026-09-09%' 永远匹配不上，而且
  **不抛错**。于是「查某一天」会静默退化成「取最新 N 条」，历史日期永远返回空。
  反之，TO_DATE/区间比较打在 VARCHAR2 列上会因 NLS 不匹配直接 ORA-01861。
  两种写法互不通用，因此这里探测一次真实列类型（见 _ts_columns_are_temporal）。
"""
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import DateTime, and_, func, inspect, or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _decrement_raw_id(raw_id):
    """将 raw_id 减 1，兼容 "RAW12345678" 字符串格式和纯数字格式

    测试 DB 的 raw_id 形如 "RAW97166637"（前缀+数字），生产 DB 可能为纯数字字符串。
    返回与输入相同格式的字符串，用于下一页分页游标。
    """
    if raw_id is None:
        return None
    s = str(raw_id)
    m = re.match(r'^([A-Za-z]*)(\d+)$', s)
    if m:
        prefix, num_str = m.group(1), m.group(2)
        return f"{prefix}{int(num_str) - 1}"
    try:
        return int(s) - 1
    except (ValueError, TypeError):
        return None

from database import get_db
from models import DT_EVENT_RAW, MachineToolMapping
from services.time_utils import parse_ts, normalize_ts, build_date_like_patterns
from services.ai_tools import ALARM_EVENT_NAMES

router = APIRouter(prefix="/api/history", tags=["history"])


# 缓存 DT_EVENT_RAW 时间列的类型判定结果（每进程只探测一次）
_TS_COL_TEMPORAL = {}


def _ts_columns_are_temporal(db) -> bool:
    """DT_EVENT_RAW 的时间列是 DATE/TIMESTAMP 时返回 True，是字符列时返回 False。

    用 SQLAlchemy 反射读真实表结构，不受 models.py 里 String(255) 声明的影响
    （本地建表脚本确实按 String 建的，量产却是 TIMESTAMP(6)）。
    探测失败时按字符列处理，保证不至于把查询打死。
    """
    if "dt_event_raw" in _TS_COL_TEMPORAL:
        return _TS_COL_TEMPORAL["dt_event_raw"]

    temporal = False
    try:
        cols = inspect(db.get_bind()).get_columns(DT_EVENT_RAW.__tablename__)
        col = next(
            (c for c in cols if str(c.get("name", "")).lower() == "received_ts_utc"),
            None,
        )
        temporal = isinstance(col.get("type"), DateTime) if col else False
    except Exception as e:
        logger.warning("[history] 探测 DT_EVENT_RAW 时间列类型失败，按字符列处理: %s", e)

    logger.info(
        "[history] DT_EVENT_RAW 时间列类型判定: %s",
        "TIMESTAMP/DATE（量产形态）" if temporal else "VARCHAR2（本地形态）",
    )
    _TS_COL_TEMPORAL["dt_event_raw"] = temporal
    return temporal


def _date_scope_clause(db, date_str: str):
    """生成「限定在 date_str 这一天」的 SQL 条件，按时间列真实类型选写法。

    - TIMESTAMP 列：半开区间 [当日00:00, 次日00:00)，两个时间列都可能是真实时间源
    - VARCHAR2 列 ：前缀 LIKE，兼容 ISO T分隔/空格分隔/NLS 月日不补零等写法

    返回 None 表示 date_str 非法，调用方应跳过 SQL 层日期过滤。
    """
    if _ts_columns_are_temporal(db):
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            return None
        nxt = day + timedelta(days=1)
        return or_(
            and_(DT_EVENT_RAW.received_ts_utc >= day,
                 DT_EVENT_RAW.received_ts_utc < nxt),
            and_(DT_EVENT_RAW.event_ts_utc >= day,
                 DT_EVENT_RAW.event_ts_utc < nxt),
        )

    patterns = build_date_like_patterns(date_str)
    if not patterns:
        return None
    conds = []
    for p in patterns:
        conds.append(DT_EVENT_RAW.received_ts_utc.like(p))
        conds.append(DT_EVENT_RAW.event_ts_utc.like(p))
    return or_(*conds)


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
    # 告警事件名清单与 ai_tools/oxe 共用：量产 OXE 用的是 ALARM_REPORT，
    # 旧版此处只认 EC_ALARM_REPORT，导致真实告警被归为 other、alarm 字段为 null
    if str(event_name).upper().strip() in ALARM_EVENT_NAMES:
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
    before_raw_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """获取指定机台的历史事件时间轴

    性能优化策略：
    - SQL层：当 start_time/end_time 是同一天时，用 received_ts_utc LIKE 缩小范围
      （从全表20000条降到单日约1000条）
    - Python层：用 parse_ts 精确过滤（处理NLS中文格式等边缘情况）
    """
    tool_ids = _resolve_tool_ids(db, tool_id)

    start_dt = parse_ts(start_time) if start_time else None
    end_dt = parse_ts(end_time) if end_time else None

    # 构建基础查询
    base_query = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id.in_(tool_ids))

    if before_raw_id is not None:
        base_query = base_query.filter(DT_EVENT_RAW.raw_id < before_raw_id)

    fetch_limit = min(limit + offset, 5000)

    # SQL层日期过滤：当 start_time/end_time 是同一天时，把扫描范围压到这一天
    rows = []
    clause = None
    if start_dt and end_dt and start_dt.date() == end_dt.date():
        clause = _date_scope_clause(db, start_dt.strftime("%Y-%m-%d"))

    if clause is not None:
        # SQL 层已精确限定到这一天：取不到就说明这天真的没数据。
        # 注意这里不能回退成「取最新 N 条」——那会把过滤失效伪装成有数据，
        # 再被 Python 层按日期过滤后归零，最终表现为「只有当天查得到，历史日期全空」。
        rows = (
            base_query.filter(clause)
            .order_by(DT_EVENT_RAW.raw_id.desc())
            .limit(fetch_limit)
            .all()
        )
    else:
        # 跨天区间、或未传时间（实时模式取最新 N 条）：SQL 层无法只靠日期前缀表达，
        # 退化为按 raw_id 倒序扫一批，再由下面的 Python 层用 start_dt/end_dt 精确过滤
        rows = (
            base_query.order_by(DT_EVENT_RAW.raw_id.desc())
            .limit(fetch_limit)
            .all()
        )

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

    # 下一页游标：返回结果中 raw_id 最小值减 1
    # 兼容 "RAW12345678" 字符串格式和纯数字格式
    next_raw_id = None
    if paged:
        min_raw_id = min(e["raw_id"] for e in paged)
        next_raw_id = _decrement_raw_id(min_raw_id)

    return {
        "tool_id": tool_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "next_raw_id": next_raw_id,
        "events": paged,
    }


def _find_raw_id_anchor(db, tool_ids: set, target_dt) -> Optional[int]:
    """在 raw_id 中定位到 ts <= target_dt 的最大 raw_id

    解决 VARCHAR2 时间字段无法在SQL层做时间比较的问题：
    二分查找定位 ts <= target_dt 的最大 raw_id，作为时间锚点。
    由于 raw_id 随时间递增，后续查询应以 raw_id >= anchor 为条件，
    获取从该时间点往后的所有事件。
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
    max_iterations = 15  # 15次迭代可覆盖2^15=32768范围，足以定位单机台事件
    for _ in range(max_iterations):
        if lo > hi:
            break
        mid = (lo + hi) // 2
        # 取出 mid 位置之前的最近一条同机台事件
        # （raw_id 全表递增，mid 可能落在其他机台的行上，用 <= mid + DESC LIMIT 1 找到最近的）
        row = db.query(DT_EVENT_RAW).filter(
            DT_EVENT_RAW.tool_id.in_(tool_ids),
            DT_EVENT_RAW.raw_id <= mid
        ).order_by(DT_EVENT_RAW.raw_id.desc()).limit(1).first()
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

    # SQL层日期过滤：把扫描范围压到指定日期（按时间列真实类型选写法）
    base_query = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id.in_(tool_ids))
    clause = _date_scope_clause(db, date)
    rows = []
    if clause is not None:
        rows = (
            base_query.filter(clause)
            .order_by(DT_EVENT_RAW.raw_id.desc())
            .limit(5000)
            .all()
        )
    else:
        rows = (
            base_query.order_by(DT_EVENT_RAW.raw_id.desc())
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
