"""告警统计 API

关键设计：
- Alarm.timestamp 是 VARCHAR2，格式可能为 ISO T/空格/NLS中文，
  SQL 层用前缀 LIKE 缩小范围（T1-B），Python 层用 parse_ts 精确过滤兜底
- ORDER BY 时间戳仍在 Python 层做（字符串排序不可靠）
"""
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import get_db
from models import Alarm
from schemas import AlarmOut
from services.time_utils import parse_ts, normalize_ts, build_date_like_patterns

router = APIRouter(prefix="/api/alarms", tags=["alarms"])


def _apply_date_like(q, col, date: str):
    """VARCHAR2 时间列：有 date 时加前缀 LIKE 缩小 SQL 层范围（T1-B）。

    无 date 或 date 非法时原样返回，由 Python 层 parse_ts 兜底。
    """
    if not date:
        return q
    patterns = build_date_like_patterns(date)
    if patterns:
        q = q.filter(or_(*[col.like(p) for p in patterns]))
    return q


@router.get("/stats")
def alarm_stats(
    machine_id: str = Query(default=None),
    date: str = Query(default=None, description="日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """获取告警分类统计（严重/警告/温度异常/压力异常/RF漂移 各多少个）"""
    q = db.query(Alarm)
    if machine_id:
        q = q.filter(Alarm.machine_id == machine_id)

    # T1-B: SQL 层按日期缩范围，Python 层 parse_ts 精确过滤兜底
    q = _apply_date_like(q, Alarm.timestamp, date)
    alarms = q.limit(5000).all()

    if date:
        filtered = []
        for a in alarms:
            dt = parse_ts(a.timestamp)
            if dt and dt.strftime("%Y-%m-%d") == date:
                filtered.append(a)
        alarms = filtered

    crit = sum(1 for a in alarms if a.level == "crit")
    warn = sum(1 for a in alarms if a.level == "warn")
    temp = sum(1 for a in alarms if a.alarm_code == "TEMP_OVER")
    press = sum(1 for a in alarms if a.alarm_code == "PRESS_UNSTABLE")
    rf = sum(1 for a in alarms if a.alarm_code == "RF_DRIFT")
    gas = sum(1 for a in alarms if a.alarm_code == "GAS_LEAK")
    resolved = sum(1 for a in alarms if a.resolved)

    return {
        "total": len(alarms),
        "crit": crit,
        "warn": warn,
        "temperature": temp,
        "pressure": press,
        "rf_drift": rf,
        "gas_leak": gas,
        "resolved": resolved,
        "unresolved": len(alarms) - resolved,
    }


@router.get("", response_model=List[AlarmOut])
def list_alarms(
    machine_id: str = Query(default=None),
    date: str = Query(default=None, description="日期 YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """获取机台当天告警

    Alarm.timestamp 是 VARCHAR2，格式不统一。SQL 层用前缀 LIKE 缩范围（T1-B），
    Python 层 parse_ts 精确过滤兜底。
    """
    q = db.query(Alarm)
    if machine_id:
        q = q.filter(Alarm.machine_id == machine_id)

    q = _apply_date_like(q, Alarm.timestamp, date)
    alarms = q.limit(5000).all()

    if date:
        filtered = []
        for a in alarms:
            dt = parse_ts(a.timestamp)
            if dt and dt.strftime("%Y-%m-%d") == date:
                filtered.append(a)
        alarms = filtered

    # Python 层按时间倒序排序（VARCHAR2 排序不可靠）
    alarms_with_dt = []
    for a in alarms:
        dt = parse_ts(a.timestamp)
        alarms_with_dt.append((dt, a))
    alarms_with_dt.sort(key=lambda x: x[0] or parse_ts("1970-01-01"), reverse=True)

    return [a for _, a in alarms_with_dt]
