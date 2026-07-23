"""Lot 批次 API - 从 DT_EVENT_RAW 解析 Lot 信息

关键设计：
- received_ts_utc 是 VARCHAR2，格式不统一（ISO T/空格/NLS中文），
  不在 SQL 层做时间过滤或排序，全部在 Python 层用 parse_ts 处理
- payload_json 用 Python 层 json.loads 解析 lot_id，不用 SQL LIKE
  （避免 SQL 注入 + JSON 格式变化导致漏匹配）
"""
from typing import List
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Query
import json

from database import get_db
from models import Lot, MachineEvent, DT_EVENT_RAW, MachineToolMapping
from schemas import LotOut, EventOut
from services.time_utils import parse_ts, normalize_ts, extract_date

router = APIRouter(prefix="/api/lots", tags=["lots"])


def _resolve_tool_ids(db: Session, machine_id: str) -> set:
    """将 machine_id 解析为对应的 tool_id 集合

    支持三种情况：
    1. machine_id 和 tool_id 相同（如 OXE-01）
    2. machine_id 通过 machine_tool_mappings 映射到 tool_id（如 VPO-01 -> PODOPENER-1）
    3. PODOPENER 机台：量产 Oracle 中 tool_id 为 PODOPENER（不带序号）

    注意：machine_tool_mappings 表可能不存在于量产 Oracle 中，需要 try-except。
    """
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

    注意：Oracle 中 received_ts_utc 可能是中文格式（如 2026-7-22 下午3:00:48），
    因此不在 SQL 层用 LIKE 过滤日期或 ORDER BY 时间戳，全部在 Python 层处理。
    """
    # 解析 machine_id 对应的所有 tool_id（含映射关系）
    tool_ids = _resolve_tool_ids(db, machine_id)

    # 查询条件：按 tool_id 集合过滤
    # 用 raw_id 降序取最新 5000 条（raw_id 递增，降序=最新数据优先）
    # 避免事件数 >5000 的机台只取到旧数据导致当天 Lot 丢失
    rows = (
        db.query(DT_EVENT_RAW)
        .filter(DT_EVENT_RAW.tool_id.in_(tool_ids))
        .order_by(DT_EVENT_RAW.raw_id.desc())
        .limit(5000)
        .all()
    )

    # 解析 payload_json 提取 lot_id，在 Python 层过滤日期
    lot_set = {}  # lot_id -> {start_dt, end_dt, start_time, end_time, ...}
    for row in rows:
        try:
            payload = json.loads(row.payload_json) if row.payload_json else {}
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
                "machine_id": machine_id,
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
    # 降序取最新 5000 条，避免旧机台事件数 >5000 时取不到近期数据
    rows = (
        db.query(DT_EVENT_RAW)
        .order_by(DT_EVENT_RAW.raw_id.desc())
        .limit(5000)
        .all()
    )

    matched = []
    for row in rows:
        try:
            payload = json.loads(row.payload_json) if row.payload_json else {}
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
    # Lot ID 不是 machine/tool ID，不做映射，全表扫描后过滤
    # 降序取最新 5000 条，避免旧机台事件数 >5000 时取不到近期数据
    rows = (
        db.query(DT_EVENT_RAW)
        .order_by(DT_EVENT_RAW.raw_id.desc())
        .limit(5000)
        .all()
    )

    events = []
    for row in rows:
        try:
            payload = json.loads(row.payload_json) if row.payload_json else {}
        except Exception:
            payload = {}
        if payload.get("lot_id") != lot_id:
            continue

        events.append({
            "id": row.raw_id,
            "machine_id": row.tool_id,
            "timestamp": normalize_ts(row.event_ts_utc or row.received_ts_utc),
            "event_type": payload.get("event_type", "VFEI"),
            "event_code": payload.get("event_name", ""),
            "description": payload.get("alarm_text", ""),
            "level": "warn" if payload.get("alarm_id") else "info",
            "metric": None,
            "value": None,
            "lot_id": lot_id,
        })

    return events
