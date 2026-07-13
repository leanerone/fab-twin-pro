"""Lot 批次 API"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Lot, MachineEvent
from schemas import LotOut, EventOut

router = APIRouter(prefix="/api/lots", tags=["lots"])


@router.get("", response_model=List[LotOut])
def list_lots(
    machine_id: str = Query(default=None),
    date: str = Query(default=None, description="日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """获取机台当天的 Lot 列表"""
    q = db.query(Lot)
    if machine_id:
        q = q.filter(Lot.machine_id == machine_id)
    if date:
        q = q.filter(Lot.start_time.like(f"{date}%"))
    return q.order_by(Lot.start_time).all()


@router.get("/{lot_id}", response_model=LotOut)
def get_lot(lot_id: str, db: Session = Depends(get_db)):
    """获取单个 Lot 详情"""
    lot = db.query(Lot).filter(Lot.id == lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot 不存在")
    return lot


@router.get("/{lot_id}/events", response_model=List[EventOut])
def get_lot_events(lot_id: str, db: Session = Depends(get_db)):
    """获取该 Lot 加工时间段内的事件"""
    lot = db.query(Lot).filter(Lot.id == lot_id).first()
    if not lot:
        raise HTTPException(status_code=404, detail="Lot 不存在")
    return (
        db.query(MachineEvent)
        .filter(
            MachineEvent.machine_id == lot.machine_id,
            MachineEvent.lot_id == lot_id,
        )
        .order_by(MachineEvent.timestamp)
        .all()
    )
