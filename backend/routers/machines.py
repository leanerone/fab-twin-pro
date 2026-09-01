"""机台相关 API"""
import json
from typing import List, Optional, Dict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database import get_db
from models import (
    Machine, Lot, User,
    DT_STATE_SNAPSHOT, DT_ALARM_EVENT, DT_EVENT_RAW, DT_EVENT_STD,
)
from routers.auth import get_current_user, check_permission
from schemas import MachineOut
from services.time_utils import parse_ts

router = APIRouter(prefix="/api/machines", tags=["machines"])


def require_model_edit(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """要求当前用户拥有 model_edit 权限（管理员）"""
    if not check_permission(user, "model_edit", db):
        raise HTTPException(status_code=403, detail="无权限：需要 model_edit 权限")
    return user


# ============== 机台状态实时推导（B-#4/B-#5）==============
# 状态优先级：活跃告警(DT_ALARM_EVENT.end_ts_utc IS NULL)→error(红)
#            → 最新快照(DT_STATE_SNAPSHOT.machine_state)
#            → 最新标准事件(DT_EVENT_STD.machine_state)
#            → DB 存储的 Machine.state
# 今日产量 = 今日 WaferUnloaded 事件数；今日告警数 = 今日 DT_ALARM_EVENT 数

def _normalize_state(raw_state: Optional[str]) -> str:
    """把 DT 的 machine_state 归一化到前端 state 词表 (run/idle/error/maint/setup)"""
    if not raw_state:
        return ""
    s = str(raw_state).strip().upper()
    if s in ("RUN", "RUNNING", "PROCESSING", "IN_PROCESS", "BUSY", "PRODUCTION"):
        return "run"
    if s in ("ALARM", "ERROR", "FAULT", "DOWN", "BREAKDOWN", "ABORT"):
        return "error"
    if s in ("MAINT", "MAINTENANCE", "PM", "ENGINEERING", "ENG"):
        return "maint"
    if s in ("SETUP", "INIT", "SETUP_MODE"):
        return "setup"
    # IDLE / 其它默认 idle
    return "idle"


def _today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def derive_machines_state(db: Session, machines) -> Dict[str, dict]:
    """批量推导机台实时状态 + 今日告警数 + 今日产量

    返回 { machine_id: { state, alarm_count_today, wafer_count_today } }
    全部 DT 表查询用 try/except 兜底，失败则回退 Machine 自身字段。
    """
    today = _today_str()
    tool_ids = [m.id for m in machines]
    result: Dict[str, dict] = {}

    # 1) 活跃告警：DT_ALARM_EVENT.end_ts_utc IS NULL
    active_alarm_tools = set()
    try:
        active = (
            db.query(DT_ALARM_EVENT.tool_id)
            .filter(DT_ALARM_EVENT.tool_id.in_(tool_ids))
            .filter(DT_ALARM_EVENT.end_ts_utc.is_(None))
            .distinct()
            .all()
        )
        active_alarm_tools = {r[0] for r in active}
    except Exception:
        pass

    # 2) 最新快照 per tool_id（DT_STATE_SNAPSHOT）
    latest_snap: Dict[str, DT_STATE_SNAPSHOT] = {}
    try:
        snaps = (
            db.query(DT_STATE_SNAPSHOT)
            .filter(DT_STATE_SNAPSHOT.tool_id.in_(tool_ids))
            .order_by(DT_STATE_SNAPSHOT.snapshot_ts_utc.desc())
            .limit(2000)
            .all()
        )
        for s in snaps:
            if s.tool_id not in latest_snap:
                latest_snap[s.tool_id] = s
    except Exception:
        pass

    # 3) 最新标准事件 per tool_id（DT_EVENT_STD.machine_state）
    latest_std: Dict[str, DT_EVENT_STD] = {}
    try:
        evs = (
            db.query(DT_EVENT_STD)
            .filter(DT_EVENT_STD.tool_id.in_(tool_ids))
            .order_by(DT_EVENT_STD.created_ts_utc.desc())
            .limit(2000)
            .all()
        )
        for e in evs:
            if e.tool_id not in latest_std:
                latest_std[e.tool_id] = e
    except Exception:
        pass

    # 4) 今日告警数 per tool_id（DT_ALARM_EVENT.start_ts_utc 今日）
    alarm_count_today: Dict[str, int] = {tid: 0 for tid in tool_ids}
    try:
        today_alarms = (
            db.query(DT_ALARM_EVENT)
            .filter(DT_ALARM_EVENT.tool_id.in_(tool_ids))
            .limit(5000)
            .all()
        )
        for a in today_alarms:
            dt = parse_ts(a.start_ts_utc)
            if dt and dt.strftime("%Y-%m-%d") == today:
                alarm_count_today[a.tool_id] = alarm_count_today.get(a.tool_id, 0) + 1
    except Exception:
        pass

    # 5) 今日产量：DT_EVENT_RAW payload event_name 含 UNLOAD 今日（parse_status=PARSED）
    wafer_count_today: Dict[str, int] = {tid: 0 for tid in tool_ids}
    try:
        rows = (
            db.query(DT_EVENT_RAW)
            .filter(DT_EVENT_RAW.tool_id.in_(tool_ids))
            .filter(DT_EVENT_RAW.parse_status == "PARSED")
            .limit(10000)
            .all()
        )
        for r in rows:
            dt = parse_ts(r.event_ts_utc or r.received_ts_utc)
            if not dt or dt.strftime("%Y-%m-%d") != today:
                continue
            try:
                p = json.loads(r.payload_json) if r.payload_json else {}
            except Exception:
                p = {}
            en = str(p.get("event_name") or "").upper()
            if "UNLOAD" in en or en == "WAFERUNLOADED":
                wafer_count_today[r.tool_id] = wafer_count_today.get(r.tool_id, 0) + 1
    except Exception:
        pass

    # 合成每台机台状态
    for m in machines:
        tid = m.id
        # 优先级 1: 活跃告警 → error
        if tid in active_alarm_tools:
            state = "error"
        else:
            state = ""
            # 优先级 2: 最新快照
            snap = latest_snap.get(tid)
            if snap and snap.current_alarm_code:
                state = "error"
            elif snap and snap.machine_state:
                state = _normalize_state(snap.machine_state)
            # 优先级 3: 最新标准事件
            if not state:
                ev = latest_std.get(tid)
                if ev and ev.machine_state:
                    state = _normalize_state(ev.machine_state)
            # 优先级 4: DB 存储 state
            if not state:
                state = (m.state or "idle")

        result[tid] = {
            "state": state,
            "alarm_count_today": alarm_count_today.get(tid, 0),
            "wafer_count_today": wafer_count_today.get(tid, 0),
        }
    return result


@router.get("", response_model=List[MachineOut])
def list_machines(db: Session = Depends(get_db)):
    """获取所有机台列表（含实时推导状态 + 今日告警数 + 今日产量）"""
    machines = db.query(Machine).order_by(Machine.id).all()
    derived = derive_machines_state(db, machines)
    # 用推导结果覆盖 state / alarm_count(今日) / wafer_count(今日)
    for m in machines:
        d = derived.get(m.id)
        if d:
            m.state = d["state"]
            m.alarm_count = d["alarm_count_today"]
            m.wafer_count = d["wafer_count_today"]
            m.updated_at = m.updated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return machines


@router.get("/stats")
def machine_stats(db: Session = Depends(get_db)):
    """获取 KPI 统计：运行数/空闲数/告警数/产量/WIP/节拍/OEE

    B-#5: 状态/今日告警/今日产量均使用 derive_machines_state 实时推导，
    不再使用 Machine 表缓存字段，确保 KPI 与实际一致。
    """
    machines = db.query(Machine).all()
    derived = derive_machines_state(db, machines)
    total = len(machines)
    running = 0
    idle = 0
    error = 0
    maint = 0
    setup = 0
    total_wafers = 0
    total_alarms = 0
    for m in machines:
        d = derived.get(m.id)
        st = d["state"] if d else (m.state or "idle")
        if st == "run":
            running += 1
        elif st == "error":
            error += 1
        elif st == "maint":
            maint += 1
        elif st == "setup":
            setup += 1
        else:
            idle += 1
        total_wafers += d["wafer_count_today"] if d else (m.wafer_count or 0)
        total_alarms += d["alarm_count_today"] if d else (m.alarm_count or 0)

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
    """获取单台机台详情（含实时推导状态 + 今日告警/产量）"""
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="机台不存在")
    derived = derive_machines_state(db, [m])
    d = derived.get(m.id)
    if d:
        m.state = d["state"]
        m.alarm_count = d["alarm_count_today"]
        m.wafer_count = d["wafer_count_today"]
        m.updated_at = m.updated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
