"""机台相关 API"""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Machine, Lot, User
from routers.auth import get_current_user, check_permission
from schemas import MachineOut

router = APIRouter(prefix="/api/machines", tags=["machines"])


def require_model_edit(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """要求当前用户拥有 model_edit 权限（管理员）"""
    if not check_permission(user, "model_edit", db):
        raise HTTPException(status_code=403, detail="无权限：需要 model_edit 权限")
    return user


@router.get("", response_model=List[MachineOut])
def list_machines(db: Session = Depends(get_db)):
    """获取所有机台列表（含实时状态）"""
    return db.query(Machine).order_by(Machine.id).all()


@router.get("/stats")
def machine_stats(db: Session = Depends(get_db)):
    """获取 KPI 统计：运行数/空闲数/告警数/产量/WIP/节拍/OEE"""
    machines = db.query(Machine).all()
    total = len(machines)
    running = sum(1 for m in machines if m.state == "run")
    idle = sum(1 for m in machines if m.state == "idle")
    error = sum(1 for m in machines if m.state == "error")
    maint = sum(1 for m in machines if m.state == "maint")
    setup = sum(1 for m in machines if m.state == "setup")
    total_wafers = sum(m.wafer_count for m in machines)
    total_alarms = sum(m.alarm_count for m in machines)

    wip = db.query(Lot).filter(Lot.status == "run").count()
    done = db.query(Lot).filter(Lot.status == "done").count()
    hold = db.query(Lot).filter(Lot.status == "hold").count()

    # 节拍：已完成 Lot 的平均加工时长（分钟）
    lots = db.query(Lot).filter(Lot.status == "done").all()
    cycle_times = []
    for lot in lots:
        try:
            st = datetime.fromisoformat(lot.start_time)
            et = datetime.fromisoformat(lot.end_time)
            cycle_times.append((et - st).total_seconds() / 60.0)
        except Exception:
            pass
    avg_cycle = round(sum(cycle_times) / len(cycle_times), 1) if cycle_times else 0.0

    # OEE 简化估算：运行率 × (1 - 告警占比)
    utilization = running / total if total else 0
    quality = max(0.0, 1 - total_alarms / max(1, total_wafers + total_alarms))
    oee = round(utilization * quality * 100, 1)

    return {
        "total": total,
        "running": running,
        "idle": idle,
        "error": error,
        "maint": maint,
        "setup": setup,
        "total_wafers": total_wafers,
        "total_alarms": total_alarms,
        "wip": wip,
        "done_lots": done,
        "hold_lots": hold,
        "avg_cycle_time_min": avg_cycle,
        "oee": oee,
    }


@router.get("/{machine_id}", response_model=MachineOut)
def get_machine(machine_id: str, db: Session = Depends(get_db)):
    """获取单台机台详情"""
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="机台不存在")
    return m


class ExternalLinkPayload(BaseModel):
    """外部跳转链接配置"""
    external_url: Optional[str] = ""
    use_external_url: Optional[int] = 0


@router.patch("/{machine_id}/external-link", response_model=MachineOut)
def update_external_link(
    machine_id: str,
    payload: ExternalLinkPayload,
    db: Session = Depends(get_db),
    _: User = Depends(require_model_edit),
):
    """更新机台外部跳转链接配置（仅管理员）"""
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="机台不存在")
    m.external_url = (payload.external_url or "").strip()
    m.use_external_url = 1 if payload.use_external_url else 0
    db.commit()
    db.refresh(m)
    return m
