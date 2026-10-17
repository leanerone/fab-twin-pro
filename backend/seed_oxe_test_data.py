"""为 OXE-01 生成最近 2 天的测试数据（事件+快照+报警+KPI）

生成内容：
- DT_EVENT_RAW / DT_EVENT_RAW_CUR：~250 条（2 天 × 6 批次 × 13 个事件/批次 + 噪声）
- machine_events：每批次 STATE 切换 + SENSOR 采样
- chamber_snapshots：每 10 分钟 × 4 chamber × 2 天
- alarms：3 条不同等级告警
- dashboard_kpi：2 天 × 6 个类别

执行：cd backend && python seed_oxe_test_data.py
"""
import json
import random
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, engine
from models import (
    DT_EVENT_RAW, DT_EVENT_RAW_CUR, MachineEvent, Alarm,
    ChamberSnapshot, DashboardKPI, Machine,
)

random.seed(42)

MACHINE_ID = "OXE-01"
CHAMBER_COUNT = 4
LOT_POOL = ["V3NL8", "V394K", "PG0R3", "V39S5", "V3QS6", "PG0R4", "V394L"]

# OXE 工艺 7 步（与 simulator 保持一致）
PROCESS_STEPS = [
    {"step": 0, "name": "等待晶圆",   "code": "WAIT",   "state": "idle",  "temp": 25.0,  "pressure": 760.0, "gas_flow": 0.0,   "rf_power": 0.0},
    {"step": 1, "name": "晶圆装载",   "code": "LOAD",   "state": "setup", "temp": 25.0,  "pressure": 760.0, "gas_flow": 0.0,   "rf_power": 0.0},
    {"step": 2, "name": "关门抽真空", "code": "PUMP",   "state": "run",   "temp": 30.0,  "pressure": 10.0,  "gas_flow": 0.0,   "rf_power": 0.0},
    {"step": 3, "name": "刻蚀工艺#1", "code": "ETCH1",  "state": "run",   "temp": 70.0,  "pressure": 15.0,  "gas_flow": 150.0, "rf_power": 1000.0},
    {"step": 4, "name": "刻蚀工艺#2", "code": "ETCH2",  "state": "run",   "temp": 75.0,  "pressure": 12.0,  "gas_flow": 180.0, "rf_power": 1200.0},
    {"step": 5, "name": "充气破真空", "code": "VENT",   "state": "run",   "temp": 50.0,  "pressure": 760.0, "gas_flow": 0.0,   "rf_power": 0.0},
    {"step": 6, "name": "晶圆卸载",   "code": "UNLOAD", "state": "setup", "temp": 30.0,  "pressure": 760.0, "gas_flow": 0.0,   "rf_power": 0.0},
]

EVENT_FLOW = [
    ("POD_PLACED",         "VFEI", "POD放置到位"),
    ("COMPLETED_PORT_LOCK","VFEI", "端口锁定完成"),
    ("READ_BATTERY",       "VFEI", "读取电池状态"),
    ("READ_TAG",           "VFEI", "读取RFID标签"),
    ("BATCH_INFO_FROM_ECUI","HOST","获取批次信息"),
    ("OPEN_POD",           "VFEI", "打开POD盖"),
    ("REACH_STAGE",        "VFEI", "机械臂到达平台"),
    ("UI_CONFIRM",         "HOST", "操作员确认"),
    ("CLOSE_POD",          "VFEI", "关闭POD盖"),
    ("ACK_UI_DOUBLECHECK", "HOST", "二次确认"),
    ("REACH_POS",          "VFEI", "机械臂到位"),
    ("WRITE_TAG",          "VFEI", "写入RFID标签"),
    ("COMPLETED_PORT_UNLOCK","VFEI","端口解锁完成"),
    ("POD_REMOVED",        "VFEI", "POD移走"),
]

ALARM_DEFS = [
    {"code": "TEMP_OVER",    "level": "warn", "desc": "温度过高 (75.3°C)"},
    {"code": "RF_DRIFT",     "level": "warn", "desc": "RF 功率漂移"},
    {"code": "PRESS_UNSTABLE","level": "crit", "desc": "腔体压力异常波动"},
]

METRIC_AMP = {"temp": 2.0, "pressure": 1.0, "gas_flow": 5.0, "rf_power": 20.0}


def ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def noise(base, amp):
    return round(base + random.uniform(-amp, amp), 2)


def write_raw_event(db, machine_id, event_def, lot_id, cassette_id, dt):
    raw_id = f"TID.OSEED.{int(dt.timestamp() * 1000)}.{random.randint(100, 999)}"
    payload = {
        "tool_id": machine_id,
        "lot_id": lot_id,
        "run_mode": "PRODUCTION",
        "event_type": event_def[1],
        "event_name": event_def[0],
        "event_value": event_def[0],
        "status": event_def[0],
        "machine_state": event_def[0],
        "machine_mode": "PRODUCTION",
        "alarm_code": None,
        "alarm_id": None,
        "alarm_text": event_def[2],
        "source_system": "RV",
        "port_id": "1",
        "cassette_id": cassette_id,
        "pod_id": cassette_id,
        "smif_id": "1",
        "chamber_id": "NULL",
        "batch_id": f"BT_{cassette_id}",
        "unit_id": "NULL",
        "slot_id": "NULL",
    }
    payload_json = json.dumps(payload, ensure_ascii=False)
    db.add(DT_EVENT_RAW(
        raw_id=raw_id,
        tool_id=machine_id,
        source_system="RV",
        source_message_id=raw_id,
        received_ts_utc=ts(dt),
        event_ts_utc=ts(dt),
        payload_json=payload_json,
        parse_status="PARSED",
    ))
    return raw_id, payload_json


def gen_one_batch(db, machine_id, batch_no, batch_start_dt, lot_id):
    """生成一批次（14 个 POD 流程事件 + 7 个 STATE 切换 + 多次 SENSOR 采样）"""
    cassette_id = f"{random.randint(10000, 99999)}{random.choice('ABCDEF')}"
    cur_dt = batch_start_dt
    state_idx = 0
    last_raw_id = None
    last_payload_json = None
    last_ts = None

    # POD 流程事件
    for ev in EVENT_FLOW:
        last_raw_id, last_payload_json = write_raw_event(db, machine_id, ev, lot_id, cassette_id, cur_dt)
        last_ts = cur_dt
        db.add(MachineEvent(
            machine_id=machine_id,
            timestamp=ts(cur_dt),
            event_type=ev[1],
            event_code=ev[0],
            description=ev[2],
            level="info",
            lot_id=lot_id,
        ))
        cur_dt += timedelta(seconds=random.randint(20, 60))

    # STATE 切换（7 步）+ SENSOR 采样
    for step_def in PROCESS_STEPS:
        cur_dt += timedelta(seconds=random.randint(15, 45))
        db.add(MachineEvent(
            machine_id=machine_id,
            timestamp=ts(cur_dt),
            event_type="STATE",
            event_code=step_def["code"],
            description=step_def["name"],
            level="info",
            lot_id=lot_id,
        ))
        # 每个状态采 3 次 SENSOR
        for _ in range(3):
            cur_dt += timedelta(seconds=random.randint(8, 18))
            for metric in ("temp", "pressure", "gas_flow", "rf_power"):
                val = noise(step_def[metric], METRIC_AMP[metric])
                db.add(MachineEvent(
                    machine_id=machine_id,
                    timestamp=ts(cur_dt),
                    event_type="SENSOR",
                    event_code=f"{metric.upper()}_SAMPLE",
                    description=f"{metric}={val}",
                    level="info",
                    metric=metric,
                    value=val,
                    lot_id=lot_id,
                ))

    # 本批次最后一条写入 _CUR 表（覆盖前一批次的"当前态"）
    if last_raw_id:
        # 先删旧的 CUR 行（merge 在已存在时不会自动覆盖 TOOL_ID 之外的字段，所以直接删）
        db.query(DT_EVENT_RAW_CUR).filter(DT_EVENT_RAW_CUR.tool_id == machine_id).delete()
        db.flush()
        db.add(DT_EVENT_RAW_CUR(
            tool_id=machine_id,
            raw_id=last_raw_id,
            source_system="RV",
            source_message_id=last_raw_id,
            received_ts_utc=ts(last_ts),
            event_ts_utc=ts(last_ts),
            payload_json=last_payload_json,
            parse_status="PARSED",
        ))
        db.flush()
    return cur_dt


def gen_snapshots(db, machine_id, start_dt, end_dt, interval_min=10):
    """每隔 interval_min 分钟为每个 chamber 写一条快照"""
    cur = start_dt
    while cur < end_dt:
        for ch in range(1, CHAMBER_COUNT + 1):
            base = random.choice(PROCESS_STEPS[2:5])  # 偏向运行态
            db.add(ChamberSnapshot(
                machine_id=machine_id,
                chamber_id=f"CH{ch}",
                timestamp=ts(cur),
                temperature=noise(base["temp"], METRIC_AMP["temp"]),
                pressure=noise(base["pressure"], METRIC_AMP["pressure"]),
                rf_power=noise(base["rf_power"], METRIC_AMP["rf_power"]),
                gas_flow=noise(base["gas_flow"], METRIC_AMP["gas_flow"]),
                is_running=1 if base["state"] == "run" else 0,
            ))
        cur += timedelta(minutes=interval_min)


def gen_alarms(db, machine_id, start_dt, end_dt):
    """随机插 3 条不同等级告警"""
    span = (end_dt - start_dt).total_seconds()
    for defn in ALARM_DEFS:
        start = start_dt + timedelta(seconds=random.uniform(0, span))
        duration = random.randint(60, 600)
        end = start + timedelta(seconds=duration)
        db.add(Alarm(
            machine_id=machine_id,
            timestamp=ts(start),
            alarm_code=defn["code"],
            description=defn["desc"],
            level=defn["level"],
            resolved=random.random() < 0.5,
            lot_id=random.choice(LOT_POOL),
        ))


def gen_kpi(db, machine_id, start_dt, end_dt):
    """按天生成 KPI（date 是 Oracle 保留字，用原生 SQL 写入）"""
    from sqlalchemy import text
    cur = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    while cur <= end_dt:
        date_str = cur.strftime("%Y-%m-%d")
        kpis = [
            ("OEE", round(random.uniform(0.75, 0.92), 4)),
            ("THROUGHPUT", float(random.randint(120, 220))),
            ("MTBF", round(random.uniform(8, 24), 2)),
            ("MTTR", round(random.uniform(15, 45), 2)),
            ("ALARM_COUNT", float(random.randint(0, 5))),
            ("WAFER_COUNT", float(random.randint(400, 720))),
        ]
        for cat, val in kpis:
            db.execute(text(
                'INSERT INTO dashboard_kpi (machine_id, "DATE", category, value, updated_at) '
                "VALUES (:mid, :d, :cat, :val, :upd)"
            ), {"mid": machine_id, "d": date_str, "cat": cat, "val": val,
                "upd": ts(cur + timedelta(hours=23, minutes=59))})
        cur += timedelta(days=1)


def main():
    db = SessionLocal()
    try:
        # 检查机台存在
        m = db.query(Machine).filter(Machine.id == MACHINE_ID).first()
        if not m:
            print(f"[FATAL] 机台 {MACHINE_ID} 不存在，请先运行 seed_data 初始化")
            sys.exit(1)

        # 时间范围：现在 - 2 天 到 现在
        end_dt = datetime(2026, 10, 1, 22, 15, 0)  # 与运行时一致，避免未来时间戳
        start_dt = end_dt - timedelta(days=2)

        print(f"[OXE-01] 生成时间范围: {start_dt} → {end_dt}")

        # 清理 OXE-01 已存在的测试数据（避免重复插入）
        n_raw = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id == MACHINE_ID).delete()
        n_cur = db.query(DT_EVENT_RAW_CUR).filter(DT_EVENT_RAW_CUR.tool_id == MACHINE_ID).delete()
        n_ev = db.query(MachineEvent).filter(MachineEvent.machine_id == MACHINE_ID).delete()
        n_snap = db.query(ChamberSnapshot).filter(ChamberSnapshot.machine_id == MACHINE_ID).delete()
        n_alarm = db.query(Alarm).filter(Alarm.machine_id == MACHINE_ID).delete()
        n_kpi = db.query(DashboardKPI).filter(DashboardKPI.machine_id == MACHINE_ID).delete()
        db.commit()
        print(f"[清理] 删除 OXE-01 旧测试数据: raw={n_raw} cur={n_cur} events={n_ev} snapshots={n_snap} alarms={n_alarm} kpi={n_kpi}")

        # 生成 6 批次（3 批次/天 × 2 天）
        batch_count = 6
        interval = (end_dt - start_dt) / batch_count
        for i in range(batch_count):
            lot_id = random.choice(LOT_POOL)
            batch_start = start_dt + interval * i + timedelta(minutes=random.randint(0, 30))
            print(f"[批次 {i+1}/{batch_count}] lot={lot_id} start={batch_start.strftime('%m-%d %H:%M')}")
            gen_one_batch(db, MACHINE_ID, i + 1, batch_start, lot_id)

        # 快照（每 10 分钟）
        gen_snapshots(db, MACHINE_ID, start_dt, end_dt, interval_min=10)

        # 报警（3 条）
        gen_alarms(db, MACHINE_ID, start_dt, end_dt)

        # KPI（按天）
        gen_kpi(db, MACHINE_ID, start_dt, end_dt)

        db.commit()
        print(f"\n[完成] OXE-01 测试数据生成成功")

        # 统计（KPI 表的 date 列在 Oracle 是保留字，ORM 会用小写，绕开）
        from sqlalchemy import text
        print(f"  DT_EVENT_RAW:     {db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id == MACHINE_ID).count()}")
        print(f"  DT_EVENT_RAW_CUR: {db.query(DT_EVENT_RAW_CUR).filter(DT_EVENT_RAW_CUR.tool_id == MACHINE_ID).count()}")
        print(f"  machine_events:   {db.query(MachineEvent).filter(MachineEvent.machine_id == MACHINE_ID).count()}")
        print(f"  chamber_snapshots:{db.query(ChamberSnapshot).filter(ChamberSnapshot.machine_id == MACHINE_ID).count()}")
        print(f"  alarms:           {db.query(Alarm).filter(Alarm.machine_id == MACHINE_ID).count()}")
        kpi_count = db.execute(text("SELECT COUNT(*) FROM dashboard_kpi WHERE machine_id=:m"), {"m": MACHINE_ID}).scalar()
        print(f"  dashboard_kpi:    {kpi_count}")

    finally:
        db.close()


if __name__ == "__main__":
    main()