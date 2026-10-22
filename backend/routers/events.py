"""事件相关 API（历史查询、回放、时间轴趋势）

关键设计：
- MachineEvent.timestamp 是 VARCHAR2，格式可能为 ISO T/空格/NLS中文，
  SQL 层用前缀 LIKE 缩小范围（T1-B），Python 层用 parse_ts 精确过滤兜底
- ORDER BY 时间戳仍在 Python 层做（字符串排序不可靠）
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import get_db
from models import MachineEvent, Machine
from schemas import EventOut
from services.time_utils import parse_ts, build_date_like_patterns

router = APIRouter(prefix="/api/events", tags=["events"])


def _apply_date_like(q, col, date: str):
    """VARCHAR2 时间列：有 date 时加前缀 LIKE 缩小 SQL 层范围（T1-B）。

    无 date 或 date 非法时原样返回，由 Python 层 parse_ts 兜底。
    """
    if not date:
        return q
    patterns = build_date_like_patterns(date)
    if patterns:
        q = q.filter(or_(*[col.like(p) for p in patterns]))
    return q


@router.get("/{machine_id}")
def get_events(
    machine_id: str,
    date: str = Query(default=None, description="日期 YYYY-MM-DD"),
    page: int = Query(default=None, ge=1, description="页码（T7：传入启用 SQL 层真分页）"),
    page_size: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """获取某机台某天所有事件（用于历史回放）

    T7 真分页：传 page 时按 id（≈时间序）SQL 层 OFFSET/FETCH（Oracle 12c+），
    返回 {total, page, page_size, items}；不传 page 保持旧行为（数组，5000 封顶）。
    """
    q = db.query(MachineEvent).filter(MachineEvent.machine_id == machine_id)
    q = _apply_date_like(q, MachineEvent.timestamp, date)

    if page is not None:
        total = q.count()
        rows = (
            q.order_by(MachineEvent.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        # 页内按解析时间正序（VARCHAR2 字符串排序不可靠）
        rows.sort(key=lambda ev: parse_ts(ev.timestamp) or parse_ts("1970-01-01"))
        return {"total": total, "page": page, "page_size": page_size,
                "items": [EventOut.model_validate(ev) for ev in rows]}

    events = q.limit(5000).all()

    if date:
        filtered = []
        for ev in events:
            dt = parse_ts(ev.timestamp)
            if dt and dt.strftime("%Y-%m-%d") == date:
                filtered.append(ev)
        events = filtered

    # Python 层按时间正序排序
    events_with_dt = [(parse_ts(ev.timestamp), ev) for ev in events]
    events_with_dt.sort(key=lambda x: x[0] or parse_ts("1970-01-01"))
    return [ev for _, ev in events_with_dt]


@router.get("/{machine_id}/latest", response_model=List[EventOut])
def get_latest_events(
    machine_id: str,
    limit: int = Query(default=60, le=500),
    db: Session = Depends(get_db),
):
    """获取最新事件（默认 60 条）

    由于 VARCHAR2 时间排序不可靠，按 id 倒序近似获取最新。
    """
    return (
        db.query(MachineEvent)
        .filter(MachineEvent.machine_id == machine_id)
        .order_by(MachineEvent.id.desc())
        .limit(limit)
        .all()
    )


@router.get("/{machine_id}/timeline")
def get_event_timeline(
    machine_id: str,
    date: str = Query(default=None, description="日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """获取时间轴数据（温度/压力/气体流量/RF 趋势）"""
    q = db.query(MachineEvent).filter(
        MachineEvent.machine_id == machine_id,
        MachineEvent.metric.isnot(None),
    )
    q = _apply_date_like(q, MachineEvent.timestamp, date)
    events = q.limit(5000).all()

    if date:
        filtered = []
        for ev in events:
            dt = parse_ts(ev.timestamp)
            if dt and dt.strftime("%Y-%m-%d") == date:
                filtered.append(ev)
        events = filtered

    # Python 层按时间正序排序
    events_with_dt = [(parse_ts(ev.timestamp), ev) for ev in events]
    events_with_dt.sort(key=lambda x: x[0] or parse_ts("1970-01-01"))

    series = {"temperature": [], "pressure": [], "gasflow": [], "rf": []}
    for _, ev in events_with_dt:
        if ev.metric in series:
            series[ev.metric].append({"timestamp": ev.timestamp, "value": ev.value})

    return {"machine_id": machine_id, "series": series}
