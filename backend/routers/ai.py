"""AI 查询 API（模拟自然语言查询）

根据问题关键字路由到不同分析逻辑：
- 机台状态 / 报警统计 / 温度趋势 / 晶圆产量 / 异常检测 / Lot 查询
- 返回 jump_timestamp 用于前端跳转历史回放
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Machine, Alarm, Lot, MachineEvent
from schemas import AIQueryRequest, AIQueryResponse

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/query", response_model=AIQueryResponse)
def ai_query(req: AIQueryRequest, db: Session = Depends(get_db)):
    """接收自然语言问题，返回分析结果"""
    question = req.question.lower()
    machine_id = req.machine_id

    # 关键字匹配（按优先级）
    if any(k in question for k in ["lot", "批次"]):
        return _lot_query(db, machine_id, req.question)
    if any(k in question for k in ["报警", "告警", "alarm"]):
        return _alarm_summary(db, machine_id)
    if any(k in question for k in ["温度", "temperature", "temp"]):
        return _temp_trend(db, machine_id)
    if any(k in question for k in ["异常", "anomaly", "检测", "故障"]):
        return _anomaly_detect(db, machine_id)
    if any(k in question for k in ["产量", "晶圆", "wafer", "yield", "加工多少"]):
        return _wafer_yield(db, machine_id)
    if any(k in question for k in ["状态", "status", "怎么样", "情况", "运行"]):
        return _machine_status(db, machine_id)

    # 默认返回机台状态
    return _machine_status(db, machine_id)


def _machine_status(db: Session, machine_id: Optional[str]) -> AIQueryResponse:
    """机台状态查询"""
    if not machine_id:
        machines = db.query(Machine).all()
        running = sum(1 for m in machines if m.state == "run")
        idle = sum(1 for m in machines if m.state == "idle")
        maint = sum(1 for m in machines if m.state == "maint")
        answer = (
            f"当前厂区共 {len(machines)} 台机台：运行中 {running} 台，"
            f"空闲 {idle} 台，维护 {maint} 台。"
        )
        return AIQueryResponse(answer=answer, sql="SELECT * FROM machines", jump_timestamp=None)

    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        return AIQueryResponse(answer=f"未找到机台 {machine_id}", sql="", jump_timestamp=None)
    answer = (
        f"机台 {m.id}（{m.name}）当前状态：{m.state}，工艺步骤 {m.process_step}/6，"
        f"温度 {m.temp}°C，压力 {m.pressure} mTorr，RF 功率 {m.rf_power} W，"
        f"累计加工晶圆 {m.wafer_count} 片，告警 {m.alarm_count} 次。"
    )
    sql = f"SELECT * FROM machines WHERE id = '{m.id}'"
    return AIQueryResponse(answer=answer, sql=sql, jump_timestamp=m.updated_at)


def _alarm_summary(db: Session, machine_id: Optional[str]) -> AIQueryResponse:
    """告警统计查询"""
    q = db.query(Alarm)
    if machine_id:
        q = q.filter(Alarm.machine_id == machine_id)
    alarms = q.all()
    crit = sum(1 for a in alarms if a.level == "crit")
    warn = sum(1 for a in alarms if a.level == "warn")
    unresolved = sum(1 for a in alarms if not a.resolved)
    scope = f"机台 {machine_id}" if machine_id else "全厂"
    answer = (
        f"{scope} 告警统计：共 {len(alarms)} 条，严重 {crit} 条，"
        f"警告 {warn} 条，未解决 {unresolved} 条。"
    )
    where = f" WHERE machine_id='{machine_id}'" if machine_id else ""
    sql = f"SELECT level, COUNT(*) FROM alarms{where} GROUP BY level"
    # 跳转到最近一条严重告警的时间点
    jump = None
    crit_alarms = [a for a in alarms if a.level == "crit"]
    if crit_alarms:
        jump = max(crit_alarms, key=lambda a: a.timestamp).timestamp
    return AIQueryResponse(answer=answer, sql=sql, jump_timestamp=jump)


def _temp_trend(db: Session, machine_id: Optional[str]) -> AIQueryResponse:
    """温度趋势查询"""
    if not machine_id:
        return AIQueryResponse(answer="请指定机台 ID 以查询温度趋势。", sql="", jump_timestamp=None)
    events = (
        db.query(MachineEvent)
        .filter(
            MachineEvent.machine_id == machine_id,
            MachineEvent.metric == "temperature",
        )
        .order_by(MachineEvent.timestamp)
        .all()
    )
    if not events:
        return AIQueryResponse(answer=f"机台 {machine_id} 未找到温度数据。", sql="", jump_timestamp=None)
    values = [e.value for e in events if e.value is not None]
    avg = round(sum(values) / len(values), 2) if values else 0
    mx = max(values) if values else 0
    mn = min(values) if values else 0
    answer = (
        f"机台 {machine_id} 温度趋势：共 {len(values)} 个采样点，"
        f"平均 {avg}°C，最高 {mx}°C，最低 {mn}°C。"
    )
    sql = (
        f"SELECT timestamp, value FROM machine_events "
        f"WHERE machine_id='{machine_id}' AND metric='temperature'"
    )
    return AIQueryResponse(answer=answer, sql=sql, jump_timestamp=events[-1].timestamp)


def _wafer_yield(db: Session, machine_id: Optional[str]) -> AIQueryResponse:
    """晶圆产量查询"""
    q = db.query(Machine)
    if machine_id:
        q = q.filter(Machine.id == machine_id)
    machines = q.all()
    total = sum(m.wafer_count for m in machines)

    lots = db.query(Lot)
    if machine_id:
        lots = lots.filter(Lot.machine_id == machine_id)
    lot_count = lots.count()
    done = lots.filter(Lot.status == "done").count()
    scope = f"机台 {machine_id}" if machine_id else "全厂"
    answer = (
        f"{scope} 产量：累计加工晶圆 {total} 片，Lot 批次 {lot_count} 个，已完成 {done} 个。"
    )
    where = f" WHERE id='{machine_id}'" if machine_id else ""
    sql = f"SELECT SUM(wafer_count) FROM machines{where}"
    return AIQueryResponse(answer=answer, sql=sql, jump_timestamp=None)


def _anomaly_detect(db: Session, machine_id: Optional[str]) -> AIQueryResponse:
    """异常检测：列出近期告警"""
    q = db.query(Alarm)
    if machine_id:
        q = q.filter(Alarm.machine_id == machine_id)
    alarms = q.order_by(Alarm.timestamp.desc()).limit(20).all()
    if not alarms:
        return AIQueryResponse(answer="未检测到异常告警。", sql="", jump_timestamp=None)
    answer = f"检测到 {len(alarms)} 条近期异常：\n"
    for a in alarms[:5]:
        answer += f"- [{a.timestamp}] {a.description}（{a.level}）\n"
    sql = "SELECT * FROM alarms ORDER BY timestamp DESC LIMIT 20"
    return AIQueryResponse(answer=answer, sql=sql, jump_timestamp=alarms[0].timestamp)


def _lot_query(db: Session, machine_id: Optional[str], question: str) -> AIQueryResponse:
    """Lot 查询：尝试从问题中提取 LOT ID"""
    match = re.search(r"LOT\w+", question.upper())
    lot_id = match.group(0) if match else None

    if lot_id:
        lot = db.query(Lot).filter(Lot.id == lot_id).first()
        if lot:
            answer = (
                f"Lot {lot.id}：机台 {lot.machine_id}，产品 {lot.product}，"
                f"晶圆数 {lot.wafer_count}，状态 {lot.status}，"
                f"开始 {lot.start_time}，结束 {lot.end_time}。"
            )
            sql = f"SELECT * FROM lots WHERE id='{lot.id}'"
            # 跳转到该 Lot 的开始时间用于回放
            return AIQueryResponse(answer=answer, sql=sql, jump_timestamp=lot.start_time)
        return AIQueryResponse(answer=f"未找到 Lot {lot_id}。", sql="", jump_timestamp=None)

    # 未指定 Lot ID：列出机台最近的 Lot
    q = db.query(Lot)
    if machine_id:
        q = q.filter(Lot.machine_id == machine_id)
    lots = q.order_by(Lot.start_time.desc()).limit(5).all()
    if not lots:
        return AIQueryResponse(answer="未找到相关 Lot 记录。", sql="", jump_timestamp=None)
    answer = f"最近 {len(lots)} 个 Lot：\n"
    for lot in lots:
        answer += f"- {lot.id}（{lot.machine_id}，{lot.product}，{lot.status}）\n"
    sql = "SELECT * FROM lots ORDER BY start_time DESC LIMIT 5"
    return AIQueryResponse(answer=answer, sql=sql, jump_timestamp=lots[0].start_time)
