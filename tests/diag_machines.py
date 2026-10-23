# -*- coding: utf-8 -*-
"""逐条定位 derive_machines_state 的慢查询（千万级行环境）。

把首页/详情/统计共用的 derive_machines_state() 内部 Q1~Q5 逐条独立计时，
用于定位冷态卡顿真凶（2026-10-23 实测：Q5 今日产量 53.7s 为唯一真凶，
Q2/Q3 MAX+JOIN 对小表仅 39ms/9ms）。

结果写本目录 diag_machines.json。需后端依赖已装（import backend 包）。
"""
import sys, time, json, os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

from sqlalchemy import and_, func, or_
from database import SessionLocal
from models import Machine, DT_STATE_SNAPSHOT, DT_ALARM_EVENT, DT_EVENT_RAW, DT_EVENT_STD
from routers.machines import _day_clause, _today_str

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "diag_machines.json")

db = SessionLocal()
out = {}

# 各表行数
for name, m in [("raw", DT_EVENT_RAW), ("snapshot", DT_STATE_SNAPSHOT), ("std", DT_EVENT_STD), ("alarm", DT_ALARM_EVENT)]:
    try:
        t0 = time.time()
        out[f"count_{name}"] = {"n": db.query(func.count()).select_from(m).scalar(), "ms": round((time.time()-t0)*1000)}
    except Exception as e:
        out[f"count_{name}"] = {"err": str(e)[:100]}

machines = db.query(Machine).order_by(Machine.id).all()
tool_ids = [m.id for m in machines]
today = _today_str()
out["tool_n"] = len(tool_ids)

def timed(name, fn):
    t0 = time.time()
    try:
        r = fn()
        out[name] = {"ms": round((time.time()-t0)*1000), "rows": len(r) if hasattr(r, "__len__") else r}
    except Exception as e:
        out[name] = {"ms": round((time.time()-t0)*1000), "err": str(e)[:150]}

# Q1 活跃告警
timed("q1_active_alarms", lambda: (
    db.query(DT_ALARM_EVENT.tool_id)
    .filter(DT_ALARM_EVENT.tool_id.in_(tool_ids))
    .filter(DT_ALARM_EVENT.end_ts_utc.is_(None))
    .distinct().all()
))

# Q2 最新快照 MAX+JOIN
def q2():
    sq = (db.query(DT_STATE_SNAPSHOT.tool_id.label("tool_id"), func.max(DT_STATE_SNAPSHOT.snapshot_ts_utc).label("max_ts"))
          .filter(DT_STATE_SNAPSHOT.tool_id.in_(tool_ids)).group_by(DT_STATE_SNAPSHOT.tool_id).subquery())
    return (db.query(DT_STATE_SNAPSHOT)
            .join(sq, and_(DT_STATE_SNAPSHOT.tool_id == sq.c.tool_id, DT_STATE_SNAPSHOT.snapshot_ts_utc == sq.c.max_ts))
            .all())
timed("q2_snapshot_maxjoin", q2)

# Q3 最新标准事件 MAX+JOIN
def q3():
    sq = (db.query(DT_EVENT_STD.tool_id.label("tool_id"), func.max(DT_EVENT_STD.created_ts_utc).label("max_ts"))
          .filter(DT_EVENT_STD.tool_id.in_(tool_ids)).group_by(DT_EVENT_STD.tool_id).subquery())
    return (db.query(DT_EVENT_STD)
            .join(sq, and_(DT_EVENT_STD.tool_id == sq.c.tool_id, DT_EVENT_STD.created_ts_utc == sq.c.max_ts))
            .all())
timed("q3_std_maxjoin", q3)

# Q4 今日告警数
def q4():
    q = db.query(DT_ALARM_EVENT.tool_id, DT_ALARM_EVENT.start_ts_utc).filter(DT_ALARM_EVENT.tool_id.in_(tool_ids))
    c = _day_clause(db, DT_ALARM_EVENT, DT_ALARM_EVENT.start_ts_utc, today)
    if c is not None:
        q = q.filter(c)
    return q.limit(5000).all()
timed("q4_today_alarms", q4)

# Q5 今日产量（修复后口径：双分支各查，与 routers/machines.py 保持一致）
def q5():
    raw_rows = []
    for col in (DT_EVENT_RAW.received_ts_utc, DT_EVENT_RAW.event_ts_utc):
        q = (db.query(DT_EVENT_RAW.raw_id, DT_EVENT_RAW.tool_id,
                      DT_EVENT_RAW.event_ts_utc, DT_EVENT_RAW.received_ts_utc,
                      DT_EVENT_RAW.payload_json)
             .filter(DT_EVENT_RAW.tool_id.in_(tool_ids))
             .filter(DT_EVENT_RAW.parse_status == "PARSED"))
        c = _day_clause(db, DT_EVENT_RAW, col, today)
        if c is not None:
            q = q.filter(c)
        raw_rows.extend(q.limit(10000).all())
    return raw_rows
timed("q5_today_wafers", q5)

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print(f"DIAG_DONE -> {OUT}")
db.close()
