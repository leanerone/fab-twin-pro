"""OHT天车API路由"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from database import get_db
from models import OHTPosition

router = APIRouter()


@router.get("/")
def get_oht_positions(db: Session = Depends(get_db)):
    """获取所有OHT天车最新位置"""
    ohts = db.query(OHTPosition.oht_id).distinct().all()
    result = []
    for oht in ohts:
        latest = db.query(OHTPosition).filter(
            OHTPosition.oht_id == oht.oht_id
        ).order_by(OHTPosition.timestamp.desc()).first()
        if latest:
            result.append({
                "oht_id": latest.oht_id,
                "lot_id": latest.lot_id,
                "x_pos": latest.x_pos,
                "y_pos": latest.y_pos,
                "z_pos": latest.z_pos,
                "status": latest.status,
                "target_machine_id": latest.target_machine_id,
                "timestamp": latest.timestamp,
            })
    return result


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
