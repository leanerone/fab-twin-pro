"""机台工艺周期模拟器（后台任务）

启动后持续运行：
- 每台机台按 7 步工艺周期循环推进
- 每 2-3 秒推进一次（demo 加速）
- 生成 STATE / SENSOR 事件写入数据库
- 同时通过 WebSocket 推送给所有连接的客户端
"""
import asyncio
import random
import threading
from datetime import datetime

from database import SessionLocal
from models import Machine, MachineEvent
from services.realtime import manager

# Oracle 自增 ID 生成器（替代 autoincrement）
_simulator_id_counter = 0
_simulator_id_lock = threading.Lock()

def _next_event_id() -> int:
    global _simulator_id_counter
    with _simulator_id_lock:
        _simulator_id_counter += 1
        return 100000000 + _simulator_id_counter  # 大数字避免与现有数据冲突

# 工艺周期（与 seed_data 保持一致）
PROCESS_STEPS = [
    {"step": 0, "name": "等待晶圆",   "code": "WAIT",   "state": "idle",  "temp": 25.0,  "pressure": 760.0, "gas_flow": 0.0,   "rf_power": 0.0},
    {"step": 1, "name": "晶圆装载",   "code": "LOAD",   "state": "setup", "temp": 25.0,  "pressure": 760.0, "gas_flow": 0.0,   "rf_power": 0.0},
    {"step": 2, "name": "关门抽真空", "code": "PUMP",   "state": "run",   "temp": 30.0,  "pressure": 10.0,  "gas_flow": 0.0,   "rf_power": 0.0},
    {"step": 3, "name": "刻蚀工艺#1", "code": "ETCH1",  "state": "run",   "temp": 70.0,  "pressure": 15.0,  "gas_flow": 150.0, "rf_power": 1000.0},
    {"step": 4, "name": "刻蚀工艺#2", "code": "ETCH2",  "state": "run",   "temp": 75.0,  "pressure": 12.0,  "gas_flow": 180.0, "rf_power": 1200.0},
    {"step": 5, "name": "充气破真空", "code": "VENT",   "state": "run",   "temp": 50.0,  "pressure": 760.0, "gas_flow": 0.0,   "rf_power": 0.0},
    {"step": 6, "name": "晶圆卸载",   "code": "UNLOAD", "state": "setup", "temp": 30.0,  "pressure": 760.0, "gas_flow": 0.0,   "rf_power": 0.0},
]

# 各 metric 的噪声幅度
METRIC_AMP = {"temperature": 2.0, "pressure": 1.0, "gasflow": 5.0, "rf": 20.0}


def _noise(base: float, amp: float) -> float:
    return round(base + random.uniform(-amp, amp), 2)


def _make_sensor_event(machine_id: str, step: dict, lot_id=None) -> MachineEvent:
    """根据当前步骤生成一条随机 SENSOR 事件"""
    # 优先选择该步骤活跃的 metric
    candidates = []
    if step["step"] in (3, 4):
        candidates.append("temperature")
    candidates.append("pressure")
    if step["gas_flow"] > 0:
        candidates.append("gasflow")
    if step["rf_power"] > 0:
        candidates.append("rf")
    metric = random.choice(candidates) if candidates else "pressure"

    base = {
        "temperature": step["temp"],
        "pressure": step["pressure"],
        "gasflow": step["gas_flow"],
        "rf": step["rf_power"],
    }[metric]
    value = _noise(base, METRIC_AMP[metric])
    now = datetime.now().isoformat()
    return MachineEvent(
        id=_next_event_id(),
        machine_id=machine_id,
        timestamp=now,
        event_type="SENSOR",
        event_code=f"SENSOR_{metric.upper()}",
        description=f"{metric} = {value}",
        level="info",
        metric=metric,
        value=value,
        lot_id=lot_id,
    )


def _machine_to_dict(m: Machine) -> dict:
    """机台对象转字典（用于 WebSocket 推送）"""
    return {
        "id": m.id,
        "model": m.model,
        "name": m.name,
        "line": m.line,
        "chamber_count": m.chamber_count,
        "process_type": m.process_type,
        "state": m.state,
        "temp": m.temp,
        "pressure": m.pressure,
        "gas_flow": m.gas_flow,
        "rf_power": m.rf_power,
        "wafer_count": m.wafer_count,
        "alarm_count": m.alarm_count,
        "process_step": m.process_step,
        "has_smif": m.has_smif,
        "updated_at": m.updated_at,
    }


def _event_to_dict(ev: MachineEvent) -> dict:
    """事件对象转字典（用于 WebSocket 推送）"""
    return {
        "id": ev.id,
        "machine_id": ev.machine_id,
        "timestamp": ev.timestamp,
        "event_type": ev.event_type,
        "event_code": ev.event_code,
        "description": ev.description,
        "level": ev.level,
        "metric": ev.metric,
        "value": ev.value,
        "lot_id": ev.lot_id,
    }


async def run_simulator():
    """后台任务：循环推进每台机台的工艺周期"""
    await asyncio.sleep(1)

    while True:
        db = None
        try:
            db = SessionLocal()
            machines = db.query(Machine).all()
            events_to_push = []
            machines_to_push = []

            for m in machines:
                next_step = (m.process_step + 1) % len(PROCESS_STEPS)
                step = PROCESS_STEPS[next_step]
                m.process_step = next_step
                m.state = step["state"]
                m.temp = _noise(step["temp"], METRIC_AMP["temperature"])
                m.pressure = _noise(step["pressure"], METRIC_AMP["pressure"])
                m.gas_flow = _noise(step["gas_flow"], METRIC_AMP["gasflow"])
                m.rf_power = _noise(step["rf_power"], METRIC_AMP["rf"])
                m.updated_at = datetime.now().isoformat()

                state_event = MachineEvent(
                    id=_next_event_id(),
                    machine_id=m.id,
                    timestamp=m.updated_at,
                    event_type="STATE",
                    event_code=step["code"],
                    description=f"{m.id} 进入「{step['name']}」步骤",
                    level="info",
                    metric=None,
                    value=None,
                    lot_id=None,
                )
                db.add(state_event)
                events_to_push.append(state_event)

                sensor_event = _make_sensor_event(m.id, step)
                db.add(sensor_event)
                events_to_push.append(sensor_event)

                # VPO/PODOPENER机台：每5个周期生成一次POD穿入/脱出事件（用于动画演示）
                if m.process_type == "PODOPENER" or m.process_type == "OXIDE" or m.id.startswith("VPO"):
                    # VPO机台的POD事件关联VPO lot_id池
                    vpo_pod_lot = None
                    if m.id.startswith("VPO") or m.process_type == "PODOPENER":
                        import random as _r
                        _pool = ["V3NL8", "V394K", "PG0R3", "V39S5", "V3QS6", "PG0R4", "V394L"]
                        vpo_pod_lot = f"{_r.choice(_pool)}-D0-{_r.randint(0, 6)}"
                    if next_step == 0:
                        pod_event = MachineEvent(
                            id=_next_event_id(),
                            machine_id=m.id,
                            timestamp=m.updated_at,
                            event_type="POD_ATTACH",
                            event_code="POD_ATTACH",
                            description=f"{m.id} POD穿入",
                            level="info",
                            metric=None,
                            value=None,
                            lot_id=vpo_pod_lot,
                        )
                        db.add(pod_event)
                        events_to_push.append(pod_event)
                    elif next_step == 5:
                        pod_event = MachineEvent(
                            id=_next_event_id(),
                            machine_id=m.id,
                            timestamp=m.updated_at,
                            event_type="POD_DETACH",
                            event_code="POD_DETACH",
                            description=f"{m.id} POD脱出",
                            level="info",
                            metric=None,
                            value=None,
                            lot_id=vpo_pod_lot,
                        )
                        db.add(pod_event)
                        events_to_push.append(pod_event)

                machines_to_push.append(_machine_to_dict(m))

            db.commit()

            for ev in events_to_push:
                await manager.broadcast({"type": "event", "data": _event_to_dict(ev)})

            await manager.broadcast({"type": "machines", "data": machines_to_push})

            db.close()
        except Exception as e:
            print(f"[simulator] 错误: {e}")
            if db is not None:
                try:
                    db.close()
                except Exception:
                    pass

        await asyncio.sleep(random.uniform(2, 3))


async def start_simulator(manager_instance, cache_instance):
    """启动模拟器（兼容外部调用）"""
    await run_simulator()
