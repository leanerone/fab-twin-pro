"""OHT天车API路由"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, and_
from sqlalchemy.orm import Session
from database import get_db
from modules.system_admin.routes.auth import get_current_user  # P0：生产数据只读端点也必须登录
from models import OHTPosition

router = APIRouter(prefix="/api/oht", tags=["oht"], dependencies=[Depends(get_current_user)])


@router.get("/")
def get_oht_positions(db: Session = Depends(get_db)):
    """获取所有OHT天车最新位置

    R4 2026-11-06：MAX(id)+JOIN 一次取回，替换旧版 1+N 逐台查询
    （先 distinct oht_id 再每台单独查最新位置，N 台 = N+1 次往返）。
    """
    latest_ids = (
        db.query(OHTPosition.oht_id, func.max(OHTPosition.id).label("max_id"))
        .group_by(OHTPosition.oht_id)
        .subquery()
    )
    rows = (
        db.query(OHTPosition)
        .join(latest_ids, and_(
            OHTPosition.oht_id == latest_ids.c.oht_id,
            OHTPosition.id == latest_ids.c.max_id,
        ))
        .order_by(OHTPosition.oht_id)
        .all()
    )
    return [
        {
            "oht_id": p.oht_id,
            "lot_id": p.lot_id,
            "x_pos": p.x_pos,
            "y_pos": p.y_pos,
            "z_pos": p.z_pos,
            "status": p.status,
            "target_machine_id": p.target_machine_id,
            "timestamp": p.timestamp,
        }
        for p in rows
    ]


@router.get("/{oht_id}")
def get_oht_history(oht_id: str, db: Session = Depends(get_db)):
    """获取单个OHT天车位置历史"""
    positions = db.query(OHTPosition).filter(
        OHTPosition.oht_id == oht_id
    ).order_by(OHTPosition.timestamp.desc()).limit(100).all()
    return [
        {
            "x_pos": p.x_pos,
            "y_pos": p.y_pos,
            "z_pos": p.z_pos,
            "status": p.status,
            "timestamp": p.timestamp,
        }
        for p in positions
    ]
