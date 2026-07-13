"""事件相关 API（历史查询、回放、时间轴趋势）"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import MachineEvent, Machine
from schemas import EventOut

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/{machine_id}", response_model=List[EventOut])
def get_events(
    machine_id: str,
    date: str = Query(default=None, description="日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """获取某机台某天所有事件（用于历史回放）"""
    q = db.query(MachineEvent).filter(MachineEvent.machine_id == machine_id)
    if date:
        q = q.filter(MachineEvent.timestamp.like(f"{date}%"))
    return q.order_by(MachineEvent.timestamp).all()


@router.get("/{machine_id}/latest", response_model=List[EventOut])
def get_latest_events(
    machine_id: str,
    limit: int = Query(default=60, le=500),
    db: Session = Depends(get_db),
):
    """获取最新事件（默认 60 条）"""
    return (
        db.query(MachineEvent)
        .filter(MachineEvent.machine_id == machine_id)
        .order_by(MachineEvent.timestamp.desc())
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
    if date:
        q = q.filter(MachineEvent.timestamp.like(f"{date}%"))
    events = q.order_by(MachineEvent.timestamp).all()

    series = {"temperature": [], "pressure": [], "gasflow": [], "rf": []}
    for ev in events:
        if ev.metric in series:
            series[ev.metric].append({"timestamp": ev.timestamp, "value": ev.value})

    return {"machine_id": machine_id, "series": series}
