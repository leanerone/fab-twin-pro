"""Lot 批次 API - 从 DT_EVENT_RAW 解析 Lot 信息"""
from typing import List
from sqlalchemy import func, distinct

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Lot, MachineEvent, DT_EVENT_RAW
from schemas import LotOut, EventOut
import json

router = APIRouter(prefix="/api/lots", tags=["lots"])


def _parse_ts(ts) -> str:
    """解析时间戳为日期字符串"""
    if not ts:
        return ""
    ts_str = str(ts).strip()
    # 取日期部分
    if len(ts_str) >= 10:
        return ts_str[:10]
    return ts_str


def _extract_date(ts_str: str) -> str:
    """从时间戳字符串中提取日期部分（YYYY-MM-DD）
    
    支持多种格式：
    - 2026-07-22 15:00:48
    - 2026-7-22 下午3:00:48
    - 2026-07-22T15:00:48
    """
    if not ts_str:
        return ""
    try:
        # 取第一个空格或T之前的部分作为日期
        date_part = ts_str.split()[0].split('T')[0]
        parts = date_part.split('-')
        if len(parts) == 3:
            return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    except Exception:
        pass
    return ""


@router.get("", response_model=List[LotOut])
def list_lots(
    machine_id: str = Query(default=None),
    date: str = Query(default=None, description="日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """获取机台当天的 Lot 列表
    
    从 DT_EVENT_RAW 解析 lot_id，而不是从模拟的 Lot 表读取
    
    注意：Oracle 中 received_ts_utc 可能是中文格式（如 2026-7-22 下午3:00:48），
    因此不在 SQL 层用 LIKE 过滤日期，而是在 Python 层过滤。
    """
    # 时间列：优先 event_ts_utc，fallback received_ts_utc
    ts_col = func.coalesce(DT_EVENT_RAW.event_ts_utc, DT_EVENT_RAW.received_ts_utc)
    
    # 查询条件：只按 machine_id 过滤（避免 Oracle LIKE 对中文时间戳的问题）
    q = db.query(
        DT_EVENT_RAW.tool_id,
        DT_EVENT_RAW.payload_json,
        ts_col.label("ts")
    ).filter(DT_EVENT_RAW.tool_id == machine_id)
    
    rows = q.order_by(ts_col).all()
    
    # 解析 payload_json 提取 lot_id
    lot_set = {}  # lot_id -> {start_time, end_time, event_count}
    for row in rows:
        try:
            payload = json.loads(row.payload_json) if row.payload_json else {}
        except Exception:
            payload = {}
        
        lot_id = payload.get("lot_id")
        # 过滤掉 NULL 字符串和空值
        if not lot_id or lot_id == "NULL":
            continue
        
        ts_str = str(row.ts) if row.ts else ""
        
        # 日期过滤（Python 层，支持中文格式时间戳）
        if date:
            row_date = _extract_date(ts_str)
            if row_date != date:
                continue
        
        if lot_id not in lot_set:
            lot_set[lot_id] = {
                "id": lot_id,
                "machine_id": machine_id,
                "product": payload.get("product", ""),
                "wafer_count": payload.get("QTY", 25),
                "status": "run" if payload.get("run_mode") else "done",
                "start_time": ts_str,
                "end_time": ts_str,
                "recipe_id": payload.get("recipe", ""),
            }
        else:
            # 更新时间范围
            if ts_str < lot_set[lot_id]["start_time"]:
                lot_set[lot_id]["start_time"] = ts_str
            if ts_str > lot_set[lot_id]["end_time"]:
                lot_set[lot_id]["end_time"] = ts_str
    
    # 转换为列表
    result = list(lot_set.values())
    return result


@router.get("/{lot_id}", response_model=LotOut)
def get_lot(lot_id: str, db: Session = Depends(get_db)):
    """获取单个 Lot 详情"""
    # 从 DT_EVENT_RAW 查询
    rows = db.query(DT_EVENT_RAW).filter(
        DT_EVENT_RAW.payload_json.like(f'%"lot_id": "{lot_id}"%')
    ).order_by(DT_EVENT_RAW.received_ts_utc).all()
    
    if not rows:
        raise HTTPException(status_code=404, detail="Lot 不存在")
    
    # 解析第一条和最后一条
    first_payload = json.loads(rows[0].payload_json) if rows[0].payload_json else {}
    last_payload = json.loads(rows[-1].payload_json) if rows[-1].payload_json else {}
    
    return {
        "id": lot_id,
        "machine_id": rows[0].tool_id,
        "product": first_payload.get("product", ""),
        "wafer_count": first_payload.get("QTY", 25),
        "status": "done",
        "start_time": str(rows[0].event_ts_utc or rows[0].received_ts_utc),
        "end_time": str(rows[-1].event_ts_utc or rows[-1].received_ts_utc),
        "recipe_id": first_payload.get("recipe", ""),
    }


@router.get("/{lot_id}/events", response_model=List[EventOut])
def get_lot_events(lot_id: str, db: Session = Depends(get_db)):
    """获取该 Lot 加工时间段内的事件"""
    # 从 DT_EVENT_RAW 查询该 lot_id 的所有事件
    rows = db.query(DT_EVENT_RAW).filter(
        DT_EVENT_RAW.payload_json.like(f'%"lot_id": "{lot_id}"%')
    ).order_by(DT_EVENT_RAW.received_ts_utc).all()
    
    events = []
    for row in rows:
        payload = json.loads(row.payload_json) if row.payload_json else {}
        events.append({
            "id": row.raw_id,
            "machine_id": row.tool_id,
            "timestamp": str(row.event_ts_utc or row.received_ts_utc),
            "event_type": payload.get("event_type", "VFEI"),
            "event_code": payload.get("event_name", ""),
            "description": payload.get("alarm_text", ""),
            "level": "warn" if payload.get("alarm_id") else "info",
            "metric": None,
            "value": None,
            "lot_id": lot_id,
        })
    
    return events