"""Lot 批次 API - 从 DT_EVENT_RAW 解析 Lot 信息

关键设计：
- received_ts_utc 是 VARCHAR2，格式不统一（ISO T/空格/NLS中文），
  不在 SQL 层做时间过滤或排序，全部在 Python 层用 parse_ts 处理
- payload_json 用 Python 层 json.loads 解析 lot_id，不用 SQL LIKE
  （避免 SQL 注入 + JSON 格式变化导致漏匹配）
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from fastapi import APIRouter, Depends, HTTPException, Query
import json
from datetime import datetime

from database import get_db
from routers.auth import get_current_user  # P0：生产数据只读端点也必须登录
from models import Lot, MachineEvent, DT_EVENT_RAW, MachineToolMapping
from schemas import LotOut, EventOut
from services.time_utils import parse_ts, normalize_ts, extract_date, build_date_like_patterns
from routers.machines import _day_clause

router = APIRouter(prefix="/api/lots", tags=["lots"], dependencies=[Depends(get_current_user)])


def _unwrap(payload: dict) -> dict:
    """兼容两种 payload 形态：量产为顶层平铺（lot_id/alarm_id 等在根上），
    本地种子数据为信封结构（业务字段在 data 子对象内）。
    返回合并视图：data 子键提升到顶层，同名字段以顶层为准。"""
    data = payload.get("data")
    if isinstance(data, dict) and data:
        merged = dict(data)
        merged.update(payload)
        merged.pop("data", None)
        return merged
    return payload


def _find_raw_id_anchor(db, tool_ids: set, target_dt: datetime) -> Optional[int]:
    """在 raw_id 中定位到 ts <= target_dt 的最大 raw_id（与 history.py 逻辑一致）"""
    try:
        min_max = db.query(
            func.min(DT_EVENT_RAW.raw_id),
            func.max(DT_EVENT_RAW.raw_id)
        ).filter(DT_EVENT_RAW.tool_id.in_(tool_ids)).first()
        if not min_max or min_max[0] is None:
            return None
        rid_min, rid_max = min_max[0], min_max[1]
    except Exception:
        return None
    lo, hi = rid_min, rid_max
    best_anchor = None
    for _ in range(15):  # 15次迭代足够覆盖单机台事件范围
        if lo > hi:
            break
        mid = (lo + hi) // 2
        row = db.query(DT_EVENT_RAW).filter(
            DT_EVENT_RAW.tool_id.in_(tool_ids),
            DT_EVENT_RAW.raw_id <= mid
        ).order_by(DT_EVENT_RAW.raw_id.desc()).limit(1).first()
        if not row:
            hi = mid - 1
            continue
        ts = row.event_ts_utc or row.received_ts_utc
        row_dt = parse_ts(ts) if ts else 0
        if row_dt and row_dt <= target_dt:
            best_anchor = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best_anchor


def _resolve_tool_ids(db: Session, machine_id: str) -> set:
    """将 machine_id 解析为对应的 tool_id 集合

    支持三种情况：
    1. machine_id 和 tool_id 相同（如 OXE-01）
    2. machine_id 通过 machine_tool_mappings 映射到 tool_id（如 VPO-01 -> PODOPENER-1）
    3. PODOPENER 机台：量产 Oracle 中 tool_id 为 PODOPENER（不带序号）

    注意：machine_tool_mappings 表可能不存在于量产 Oracle 中，需要 try-except。
    """
    # machine_id 为空时返回空集合（调用方查询命中空 IN 得到空列表，而非 None.upper() 500）
    if not machine_id:
        return set()
    tool_ids = {machine_id}

    # PODOPENER 机台量产 tool_id 通常是 PODOPENER（不带 -1）
    if machine_id.upper().startswith("PODOPENER"):
        tool_ids.add("PODOPENER")

    # 尝试查询映射表（可能不存在于量产 Oracle 中）
    try:
        mappings = db.query(MachineToolMapping).filter(
            (MachineToolMapping.machine_id == machine_id) |
            (MachineToolMapping.tool_id == machine_id)
        ).all()
        for m in mappings:
            tool_ids.add(m.tool_id)
            tool_ids.add(m.machine_id)
    except Exception:
        pass  # 映射表不存在或查询失败，忽略

    return tool_ids


@router.get("", response_model=List[LotOut])
def list_lots(
    machine_id: str = Query(default=None),
    date: str = Query(default=None, description="日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """获取机台当天的 Lot 列表

    从 DT_EVENT_RAW 解析 lot_id，而不是从模拟的 Lot 表读取。

    时间列是双形态（量产 TIMESTAMP/本地 VARCHAR2）：SQL 层按列类型用
    半开区间或前缀 LIKE 缩小范围，Python 层 parse_ts 精确过滤兜底。
    """
    # 解析 machine_id 对应的所有 tool_id（含映射关系）；
    # machine_id 为空时不加机台过滤，扫全机台最近事件（AI 场景常无参查批次）
    tool_ids = _resolve_tool_ids(db, machine_id)

    # T1-B: SQL 层按日期缩范围。原实现对 received/event 两列一律打 LIKE，
    # 在量产 TIMESTAMP 列上恒不匹配（恒空→回退全量 5000），历史日期永远查不到。
    # 现改为按列真实类型分支：TIMESTAMP 走半开区间、VARCHAR2 走前缀 LIKE。
    base_query = db.query(DT_EVENT_RAW)
    if tool_ids:
        base_query = base_query.filter(DT_EVENT_RAW.tool_id.in_(tool_ids))
    if date:
        cond_parts = []
        for col in (DT_EVENT_RAW.received_ts_utc, DT_EVENT_RAW.event_ts_utc):
            c = _day_clause(db, DT_EVENT_RAW, col, date)
            if c is not None:
                cond_parts.append(c)
        if cond_parts:
            base_query = base_query.filter(or_(*cond_parts))
    rows = (
        base_query.order_by(DT_EVENT_RAW.raw_id.desc())
        .limit(5000)
        .all()
    )

    # 解析 payload_json 提取 lot_id，在 Python 层过滤日期
    lot_set = {}  # lot_id -> {start_dt, end_dt, start_time, end_time, ...}
    for row in rows:
        try:
            payload = _unwrap(json.loads(row.payload_json) if row.payload_json else {})
        except Exception:
            payload = {}

        lot_id = payload.get("lot_id")
        # 过滤掉 NULL 字符串和空值
        if not lot_id or lot_id == "NULL":
            continue

        ts_dt = parse_ts(row.event_ts_utc or row.received_ts_utc)
        if not ts_dt:
            continue

        # 日期过滤（Python 层，支持中文格式时间戳）
        if date:
            row_date = ts_dt.strftime("%Y-%m-%d")
            if row_date != date:
                continue

        ts_str = normalize_ts(row.event_ts_utc or row.received_ts_utc)

        if lot_id not in lot_set:
            lot_set[lot_id] = {
                "id": lot_id,
                "machine_id": row.tool_id or machine_id,
                "product": payload.get("product", ""),
                "wafer_count": payload.get("QTY", 25),
                "status": "run" if payload.get("run_mode") else "done",
                "start_dt": ts_dt,
                "end_dt": ts_dt,
                "start_time": ts_str,
                "end_time": ts_str,
                "recipe_id": payload.get("recipe", ""),
            }
        else:
            # 用 datetime 比较，绝不能用字符串比较（格式不一致会出错）
            if ts_dt < lot_set[lot_id]["start_dt"]:
                lot_set[lot_id]["start_dt"] = ts_dt
                lot_set[lot_id]["start_time"] = ts_str
            if ts_dt > lot_set[lot_id]["end_dt"]:
                lot_set[lot_id]["end_dt"] = ts_dt
                lot_set[lot_id]["end_time"] = ts_str

    # 转换为列表（移除内部 _dt 字段）
    result = []
    for lot in lot_set.values():
        lot.pop("start_dt", None)
        lot.pop("end_dt", None)
        result.append(lot)
    return result


@router.get("/{lot_id}", response_model=LotOut)
def get_lot(lot_id: str, db: Session = Depends(get_db)):
    """获取单个 Lot 详情"""
    # ver2.13 雷区A：物化列等值过滤（原 payload_json LIKE '%lot%' 千万级全表扫 645s）
    rows = (
        db.query(DT_EVENT_RAW)
        .filter(DT_EVENT_RAW.lot_id == lot_id)
        .order_by(DT_EVENT_RAW.raw_id.desc())
        .limit(500)
        .all()
    )

    matched = []
    for row in rows:
        try:
            payload = _unwrap(json.loads(row.payload_json) if row.payload_json else {})
        except Exception:
            payload = {}
        if payload.get("lot_id") == lot_id:
            matched.append((row, payload))

    if not matched:
        raise HTTPException(status_code=404, detail="Lot 不存在")

    first_row, first_payload = matched[0]
    last_row, last_payload = matched[-1]

    return {
        "id": lot_id,
        "machine_id": first_row.tool_id,
        "product": first_payload.get("product", ""),
        "wafer_count": first_payload.get("QTY", 25),
        "status": "done",
        "start_time": normalize_ts(first_row.event_ts_utc or first_row.received_ts_utc),
        "end_time": normalize_ts(last_row.event_ts_utc or last_row.received_ts_utc),
        "recipe_id": first_payload.get("recipe", ""),
    }


@router.get("/{lot_id}/events", response_model=List[EventOut])
def get_lot_events(lot_id: str, db: Session = Depends(get_db)):
    """获取该 Lot 加工时间段内的事件"""
    # ver2.13 雷区A：物化列等值过滤（原 payload_json LIKE '%lot%' 全表扫 568s）
    rows = (
        db.query(DT_EVENT_RAW)
        .filter(DT_EVENT_RAW.lot_id == lot_id)
        .order_by(DT_EVENT_RAW.raw_id.desc())
        .limit(5000)
        .all()
    )

    events = []
    for row in rows:
        try:
            payload = _unwrap(json.loads(row.payload_json) if row.payload_json else {})
        except Exception:
            payload = {}
        if payload.get("lot_id") != lot_id:
            continue

        # EventOut.id 要求 int；本地 raw_id 形如 "RAW99960549"，提取数字部分
        raw_id_str = str(row.raw_id)
        digits = "".join(ch for ch in raw_id_str if ch.isdigit())
        events.append({
            "id": int(digits) if digits else 0,
            "machine_id": row.tool_id,
            "timestamp": normalize_ts(row.event_ts_utc or row.received_ts_utc),
            "event_type": payload.get("event_type", "VFEI"),
            "event_code": payload.get("event_name") or payload.get("action", ""),
            "description": payload.get("alarm_text") or payload.get("message", ""),
            "level": "warn" if (payload.get("alarm_id") or payload.get("alarm_code")) else "info",
            "metric": None,
            "value": None,
            "lot_id": lot_id,
        })

    return events
