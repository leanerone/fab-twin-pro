"""机台相关 API"""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

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


class MachineUpdatePayload(BaseModel):
    """机台信息更新（改名/改型号/产线/工艺/腔数）"""
    name: Optional[str] = None
    model: Optional[str] = None
    line: Optional[int] = None
    process_type: Optional[str] = None
    chamber_count: Optional[int] = None


@router.patch("/{machine_id}", response_model=MachineOut)
def update_machine(
    machine_id: str,
    payload: MachineUpdatePayload,
    db: Session = Depends(get_db),
    _: User = Depends(require_model_edit),
):
    """更新机台基本信息（改名/型号/产线/工艺/腔数，仅管理员）"""
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="机台不存在")
    if payload.name is not None and payload.name.strip():
        m.name = payload.name.strip()
    if payload.model is not None and payload.model.strip():
        m.model = payload.model.strip()
    if payload.line is not None:
        m.line = payload.line
    if payload.process_type is not None and payload.process_type.strip():
        m.process_type = payload.process_type.strip()
    if payload.chamber_count is not None and payload.chamber_count > 0:
        m.chamber_count = payload.chamber_count
    db.commit()
    db.refresh(m)
    return m


@router.delete("/{machine_id}")
def delete_machine_record(
    machine_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_model_edit),
):
    """彻底删除机台记录（连带从平面图移除，仅管理员）

    注意：DT_* 量产表不动；仅删 FABTWIN.MACHINES 记录。
    若有关联的 FABTWIN 事件/Lot 外键约束，会返回 409 提示先清理。
    """
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="机台不存在")
    try:
        db.delete(m)
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"该机台存在关联数据（事件/Lot/区域），无法直接删除。请先清理关联记录。原因：{e.orig}",
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败：{e}")
    return {"message": f"机台 {machine_id} 已彻底删除", "id": machine_id}
