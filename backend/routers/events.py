"""事件相关 API（历史查询、回放、时间轴趋势）

关键设计：
- MachineEvent.timestamp 是 VARCHAR2，格式可能为 ISO T/空格/NLS中文，
  不在 SQL 层用 LIKE 过滤日期或 ORDER BY 时间戳
- 全部在 Python 层用 parse_ts 解析和过滤
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import MachineEvent, Machine
from schemas import EventOut
from services.time_utils import parse_ts

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/{machine_id}", response_model=List[EventOut])
def get_events(
    machine_id: str,
    date: str = Query(default=None, description="日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """获取某机台某天所有事件（用于历史回放）"""
    q = db.query(MachineEvent).filter(MachineEvent.machine_id == machine_id)
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
def get_timeline(
    machine_id: str,
    date: str = Query(default=None, description="日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """获取时间轴数据（温度/压力/气体流量/RF 趋势）"""
    q = db.query(MachineEvent).filter(
        MachineEvent.machine_id == machine_id,
        MachineEvent.metric.isnot(None),
    )
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
