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

import json

from database import SessionLocal
from models import Machine, MachineEvent, DT_EVENT_RAW, DT_EVENT_RAW_CUR
from services.realtime import manager

# Oracle 自增 ID 生成器（替代 autoincrement）
_simulator_id_counter = 0
_simulator_id_lock = threading.Lock()

def _init_id_counter():
    """从数据库查询最大ID，初始化计数器"""
    global _simulator_id_counter
    try:
        db = SessionLocal()
        max_id = db.query(MachineEvent.id).order_by(MachineEvent.id.desc()).first()
        db.close()
        if max_id and max_id[0]:
            _simulator_id_counter = max_id[0]
            print(f"[Simulator] ID计数器初始化为: {_simulator_id_counter}")
    except Exception as e:
        print(f"[Simulator] ID计数器初始化失败: {e}")

def _next_event_id() -> int:
    global _simulator_id_counter
    with _simulator_id_lock:
        _simulator_id_counter += 1
        return _simulator_id_counter

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

# PODOPENER 穿入流程（PACKING） - 14个事件
PACKING_EVENTS = [
    {"event_name": "POD_PLACED", "event_type": "VFEI", "mode": "PACKING", "has_lot": False, "desc": "POD放置到位"},
    {"event_name": "COMPLETED_PORT_LOCK", "event_type": "VFEI", "mode": "PACKING", "has_lot": False, "desc": "端口锁定完成"},
    {"event_name": "READ_BATTERY", "event_type": "VFEI", "mode": None, "has_lot": False, "desc": "读取电池状态"},
    {"event_name": "READ_TAG", "event_type": "VFEI", "mode": "PACKING", "has_lot": False, "desc": "读取RFID标签"},
    {"event_name": "BATCH_INFO_FROM_ECUI", "event_type": "HOST", "mode": "PACKING", "has_lot": True, "desc": "获取批次信息"},
    {"event_name": "OPEN_POD", "event_type": "VFEI", "mode": "PACKING", "has_lot": True, "desc": "打开POD盖"},
    {"event_name": "REACH_STAGE", "event_type": "VFEI", "mode": "PACKING", "has_lot": True, "desc": "机械臂到达平台"},
    {"event_name": "UI_CONFIRM", "event_type": "HOST", "mode": "PACKING", "has_lot": True, "desc": "操作员确认"},
    {"event_name": "CLOSE_POD", "event_type": "VFEI", "mode": "PACKING", "has_lot": True, "desc": "关闭POD盖"},
    {"event_name": "ACK_UI_DOUBLECHECK", "event_type": "HOST", "mode": "PACKING", "has_lot": True, "desc": "二次确认"},
    {"event_name": "REACH_POS", "event_type": "VFEI", "mode": "PACKING", "has_lot": True, "desc": "机械臂到位"},
    {"event_name": "WRITE_TAG", "event_type": "VFEI", "mode": "PACKING", "has_lot": True, "desc": "写入RFID标签"},
    {"event_name": "COMPLETED_PORT_UNLOCK", "event_type": "VFEI", "mode": "PACKING", "has_lot": True, "desc": "端口解锁完成"},
    {"event_name": "POD_REMOVED", "event_type": "VFEI", "mode": "PACKING", "has_lot": True, "desc": "POD移走"},
]

# PODOPENER 脱出流程（UNPACKING） - 6个事件
UNPACKING_EVENTS = [
    {"event_name": "UI_CONFIRM", "event_type": "HOST", "mode": "UNPACKING", "has_lot": True, "desc": "操作员确认"},
    {"event_name": "CLOSE_POD", "event_type": "VFEI", "mode": "UNPACKING", "has_lot": True, "desc": "关闭POD盖"},
    {"event_name": "REACH_POS", "event_type": "VFEI", "mode": "UNPACKING", "has_lot": True, "desc": "机械臂到位"},
    {"event_name": "WRITE_TAG", "event_type": "VFEI", "mode": "UNPACKING", "has_lot": True, "desc": "写入RFID标签"},
    {"event_name": "COMPLETED_PORT_UNLOCK", "event_type": "VFEI", "mode": "UNPACKING", "has_lot": True, "desc": "端口解锁完成"},
    {"event_name": "POD_REMOVED", "event_type": "VFEI", "mode": "UNPACKING", "has_lot": True, "desc": "POD移走"},
]

LOT_POOL = ["V3NL8", "V394K", "PG0R3", "V39S5", "V3QS6", "PG0R4", "V394L"]

_podopener_state = {}


def _gen_cassette_id():
    return f"{random.randint(10000, 99999)}{random.choice('ABCDEF')}"


def _write_raw_event(db, machine_id, event_def, lot_id, cassette_id, timestamp):
    """写入一条DT_EVENT_RAW和DT_EVENT_RAW_CUR"""
    payload = {
        "tool_id": machine_id,
        "lot_id": lot_id if event_def["has_lot"] else "NULL",
        "run_mode": event_def["mode"] if event_def["mode"] else "NULL",
        "event_type": event_def["event_type"],
        "event_name": event_def["event_name"],
        "event_value": event_def["event_name"],
        "status": event_def["event_name"],
        "machine_state": event_def["event_name"],
        "machine_mode": event_def["mode"] if event_def["mode"] else "NULL",
        "alarm_code": None,
        "alarm_id": None,
        "alarm_text": event_def["event_name"],
        "source_system": "RV",
        "port_id": "1",
        "cassette_id": cassette_id,
        "pod_id": cassette_id,
        "smif_id": "1",
        "chamber_id": "NULL",
        "batch_id": f"BT_{cassette_id}" if event_def["has_lot"] else "NULL",
        "unit_id": "NULL",
        "slot_id": "NULL",
    }
    payload_json = json.dumps(payload, ensure_ascii=False)
    raw_id = f"TID.{_next_event_id()}"

    raw_event = DT_EVENT_RAW(
        raw_id=raw_id,
        tool_id=machine_id,
        source_system="RV",
        source_message_id=raw_id,
        received_ts_utc=timestamp,
        event_ts_utc=timestamp,
        payload_json=payload_json,
        parse_status="PARSED",
    )
    db.add(raw_event)

    cur_event = DT_EVENT_RAW_CUR(
        tool_id=machine_id,
        raw_id=raw_id,
        source_system="RV",
        source_message_id=raw_id,
        received_ts_utc=timestamp,
        event_ts_utc=timestamp,
        payload_json=payload_json,
        parse_status="PARSED",
    )
    db.merge(cur_event)

    return raw_event


def _gen_podopener_events(db, machine, events_to_push, next_step):
    """生成PODOPENER机台的业务流程事件"""
    global _podopener_state

    mid = machine.id
    if mid not in _podopener_state:
        _podopener_state[mid] = {
            "phase": "PACKING",
            "step": 0,
            "lot_id": random.choice(LOT_POOL),
            "cassette_id": _gen_cassette_id(),
        }

    state = _podopener_state[mid]
    events = PACKING_EVENTS if state["phase"] == "PACKING" else UNPACKING_EVENTS

    ev_def = events[state["step"]]
    timestamp = machine.updated_at.isoformat() if hasattr(machine.updated_at, 'isoformat') else str(machine.updated_at)

    raw_event = _write_raw_event(
        db, mid, ev_def, state["lot_id"], state["cassette_id"], timestamp
    )

    mevent = MachineEvent(
        id=_next_event_id(),
        machine_id=mid,
        timestamp=machine.updated_at,
        event_type=ev_def["event_type"],
        event_code=ev_def["event_name"],
        description=ev_def["desc"],
        level="info",
        metric=None,
        value=None,
        lot_id=state["lot_id"] if ev_def["has_lot"] else None,
    )
    db.add(mevent)
    events_to_push.append(mevent)

    state["step"] += 1
    if state["step"] >= len(events):
        state["step"] = 0
        state["phase"] = "UNPACKING" if state["phase"] == "PACKING" else "PACKING"
        if state["phase"] == "PACKING":
            state["lot_id"] = random.choice(LOT_POOL)
            state["cassette_id"] = _gen_cassette_id()


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

                if m.process_type == "PODOPENER":
                    _gen_podopener_events(db, m, events_to_push, next_step)
                else:
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

        await asyncio.sleep(random.uniform(5, 15))


async def start_simulator(manager_instance, cache_instance):
    """启动模拟器（兼容外部调用）"""
    _init_id_counter()
    await run_simulator()
