"""告警统计 API"""
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Alarm
from schemas import AlarmOut

router = APIRouter(prefix="/api/alarms", tags=["alarms"])


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
    if date:
        q = q.filter(Alarm.timestamp.like(f"{date}%"))
    alarms = q.all()

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
    """获取机台当天告警"""
    q = db.query(Alarm)
    if machine_id:
        q = q.filter(Alarm.machine_id == machine_id)
    if date:
        q = q.filter(Alarm.timestamp.like(f"{date}%"))
    return q.order_by(Alarm.timestamp.desc()).all()
