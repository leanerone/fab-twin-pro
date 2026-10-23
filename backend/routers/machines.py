"""机台相关 API"""
import json
import logging
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import DateTime, and_, func, inspect, or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database import get_db
from models import (
    Machine, Lot, User,
    DT_STATE_SNAPSHOT, DT_ALARM_EVENT, DT_EVENT_RAW, DT_EVENT_STD,
)
from routers.auth import get_current_user, check_permission
from schemas import MachineOut
from services.cache import machine_state_ttl, kpi_stats_ttl
from services.time_utils import parse_ts, build_date_like_patterns

logger = logging.getLogger(__name__)

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

_COL_TEMPORAL_CACHE: Dict[str, bool] = {}


def _col_is_temporal(db, table_name: str, col_name: str) -> bool:
    """反射判定某列是否 DATE/TIMESTAMP（量产形态）；字符列返回 False（本地形态）。

    结果按 (table, col) 缓存。探测失败按字符列处理，避免把查询打死。
    """
    key = f"{table_name}.{col_name}"
    if key in _COL_TEMPORAL_CACHE:
        return _COL_TEMPORAL_CACHE[key]
    temporal = False
    try:
        cols = inspect(db.get_bind()).get_columns(table_name)
        col = next((c for c in cols if str(c.get("name", "")).lower() == col_name.lower()), None)
        temporal = isinstance(col.get("type"), DateTime) if col else False
    except Exception as e:
        logger.warning("[machines] 探测 %s 列类型失败，按字符列处理: %s", key, e)
    _COL_TEMPORAL_CACHE[key] = temporal
    return temporal


def _day_clause(db, model, col, date_str: str):
    """生成「限定在 date_str 这一天」的 SQL 条件，按列真实类型选写法。

    - TIMESTAMP/DATE 列：半开区间 [当日00:00, 次日00:00)
    - 字符列：前缀 LIKE，兼容 ISO T分隔/空格分隔/NLS 月日不补零
    返回 None 表示 date_str 非法，调用方应跳过 SQL 层日期过滤。
    """
    table = model.__tablename__
    if _col_is_temporal(db, table, col.key):
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            return None
        nxt = day + timedelta(days=1)
        return and_(col >= day, col < nxt)
    patterns = build_date_like_patterns(date_str)
    if not patterns:
        return None
    return or_(*[col.like(p) for p in patterns])


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
    T2: 结果按 tool_ids 组合缓存 60s（TTLCache），命中则直接返回。
    """
    tool_ids = [m.id for m in machines]
    cache_key = ",".join(sorted(tool_ids))
    cached = machine_state_ttl.get(cache_key)
    if cached is not None:
        return cached

    today = _today_str()
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
    # 千万级下 ORDER BY 时间列全表排序再 LIMIT 2000 是主要慢点：改 GROUP BY
    # 取每台 MAX(ts) 再回表 JOIN，只返回机台数量级行数。
    # （VARCHAR2 存 ISO "YYYY-MM-DD HH:MM:SS" 时 MAX 字典序 == 时间序，安全；
    #   同 ts 并列时 Python 层 dedup 兜底）
    latest_snap: Dict[str, DT_STATE_SNAPSHOT] = {}
    try:
        snap_max_sq = (
            db.query(
                DT_STATE_SNAPSHOT.tool_id.label("tool_id"),
                func.max(DT_STATE_SNAPSHOT.snapshot_ts_utc).label("max_ts"),
            )
            .filter(DT_STATE_SNAPSHOT.tool_id.in_(tool_ids))
            .group_by(DT_STATE_SNAPSHOT.tool_id)
            .subquery()
        )
        snaps = (
            db.query(DT_STATE_SNAPSHOT)
            .join(
                snap_max_sq,
                and_(
                    DT_STATE_SNAPSHOT.tool_id == snap_max_sq.c.tool_id,
                    DT_STATE_SNAPSHOT.snapshot_ts_utc == snap_max_sq.c.max_ts,
                ),
            )
            .all()
        )
        for s in snaps:
            if s.tool_id not in latest_snap:
                latest_snap[s.tool_id] = s
    except Exception:
        pass

    # 3) 最新标准事件 per tool_id（DT_EVENT_STD.machine_state），同快照的 MAX+JOIN
    latest_std: Dict[str, DT_EVENT_STD] = {}
    try:
        std_max_sq = (
            db.query(
                DT_EVENT_STD.tool_id.label("tool_id"),
                func.max(DT_EVENT_STD.created_ts_utc).label("max_ts"),
            )
            .filter(DT_EVENT_STD.tool_id.in_(tool_ids))
            .group_by(DT_EVENT_STD.tool_id)
            .subquery()
        )
        evs = (
            db.query(DT_EVENT_STD)
            .join(
                std_max_sq,
                and_(
                    DT_EVENT_STD.tool_id == std_max_sq.c.tool_id,
                    DT_EVENT_STD.created_ts_utc == std_max_sq.c.max_ts,
                ),
            )
            .all()
        )
        for e in evs:
            if e.tool_id not in latest_std:
                latest_std[e.tool_id] = e
    except Exception:
        pass

    # 4) 今日告警数 per tool_id（DT_ALARM_EVENT.start_ts_utc 今日）
    # T1-B: SQL 层按日期缩范围（量产 TIMESTAMP 走区间、本地 VARCHAR2 走 LIKE），
    #       再用 parse_ts 精确过滤兜底，语义与改前一致但不再全表扫描。
    alarm_count_today: Dict[str, int] = {tid: 0 for tid in tool_ids}
    try:
        # 列裁剪：只取 tool_id + start_ts_utc，避免整行（含大字段）回表
        q = db.query(
            DT_ALARM_EVENT.tool_id, DT_ALARM_EVENT.start_ts_utc
        ).filter(DT_ALARM_EVENT.tool_id.in_(tool_ids))
        day_cond = _day_clause(db, DT_ALARM_EVENT, DT_ALARM_EVENT.start_ts_utc, today)
        if day_cond is not None:
            q = q.filter(day_cond)
        today_alarms = q.limit(5000).all()
        for a in today_alarms:
            dt = parse_ts(a.start_ts_utc)
            if dt and dt.strftime("%Y-%m-%d") == today:
                alarm_count_today[a.tool_id] = alarm_count_today.get(a.tool_id, 0) + 1
    except Exception:
        pass

    # 5) 今日产量：DT_EVENT_RAW payload event_name 含 UNLOAD 今日（parse_status=PARSED）
    # 千万级实测：event_ts/received_ts 两列 LIKE 直接 OR，Oracle 放弃索引全表扫
    # （本地 10M 行冷态 53.7s，是首页/详情/统计 34s+ 的唯一真凶）。
    # 改为两分支各查再按 raw_id 合并去重：每个分支是单列谓词可走索引
    # （VARCHAR2 走前缀 LIKE 范围扫，TIMESTAMP 走半开区间），语义与 OR 完全一致；
    # 配合复合索引 IDX_DT_EVENT_RAW_PARSED_RECV(parse_status, received_ts_utc)
    # 让主路径（received 分支）全索引命中。
    wafer_count_today: Dict[str, int] = {tid: 0 for tid in tool_ids}
    try:
        # 列裁剪：只取判定所需列，payload_json CLOB 之外不再整行回表
        raw_rows = []
        for col in (DT_EVENT_RAW.received_ts_utc, DT_EVENT_RAW.event_ts_utc):
            q = (
                db.query(
                    DT_EVENT_RAW.raw_id,
                    DT_EVENT_RAW.tool_id,
                    DT_EVENT_RAW.event_ts_utc,
                    DT_EVENT_RAW.received_ts_utc,
                    DT_EVENT_RAW.payload_json,
                )
                .filter(DT_EVENT_RAW.tool_id.in_(tool_ids))
                .filter(DT_EVENT_RAW.parse_status == "PARSED")
            )
            day_cond = _day_clause(db, DT_EVENT_RAW, col, today)
            if day_cond is not None:
                q = q.filter(day_cond)
            raw_rows.extend(q.limit(10000).all())
        seen_raw_ids = set()
        for r in raw_rows:
            if r.raw_id in seen_raw_ids:
                continue
            seen_raw_ids.add(r.raw_id)
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
    machine_state_ttl.set(cache_key, result)
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
    T2: 整体结果缓存 60s（TTLCache）。
    """
    cached = kpi_stats_ttl.get("stats")
    if cached is not None:
        return cached

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

    resp = {
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
    kpi_stats_ttl.set("stats", resp)
    return resp

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
