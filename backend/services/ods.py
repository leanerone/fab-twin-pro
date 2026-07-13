"""ODS数据中台层：模拟数据同步 + CDC思路"""
import json
import random
import time
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models import DT_EVENT_RAW, DT_EVENT_STD, DT_STATE_SNAPSHOT, DT_ALARM_EVENT
from services.cache import cache


def generate_raw_event(machine_id, event_type, timestamp):
    payload = {
        "tool_id": machine_id,
        "event_type": event_type,
        "timestamp": timestamp,
        "data": {},
    }
    if event_type == "STATE":
        payload["data"] = {"state": random.choice(["RUN", "IDLE", "SETUP", "ERROR"]), "step": random.randint(0, 6)}
    elif event_type == "SENSOR":
        payload["data"] = {
            "temperature": round(22 + random.random() * 50, 2),
            "pressure": round(0.001 + random.random() * 0.999, 4),
            "gas_flow": round(random.random() * 200, 2),
            "rf_power": round(random.random() * 800, 2),
        }
    elif event_type == "ALARM":
        payload["data"] = {
            "alarm_code": random.choice(["TEMP_OVER", "RF_DRIFT", "PRESS_UNSTABLE", "GAS_LEAK"]),
            "severity": random.choice(["CRITICAL", "WARNING"]),
            "message": "模拟告警消息",
        }
    elif event_type == "TRANSFER":
        payload["data"] = {"lot_id": f"LOT{random.randint(10000, 99999)}", "action": random.choice(["LOAD", "UNLOAD"])}
    return json.dumps(payload)


def generate_std_event(raw_id, machine_id, event_type, timestamp):
    return {
        "event_id": f"EVT{raw_id}",
        "raw_id": raw_id,
        "tool_id": machine_id,
        "event_type": event_type,
        "machine_state": random.choice(["run", "idle", "setup"]),
        "lot_id": f"LOT{random.randint(10000, 99999)}" if random.random() > 0.3 else None,
        "recipe_id": f"REC{random.randint(100, 999)}" if random.random() > 0.5 else None,
        "pod_position": random.choice(["LOADPORT_01", "LOADPORT_02", "TRANSFER"]) if random.random() > 0.5 else None,
        "normalized_json": json.dumps({"source": "simulation"}),
        "created_ts_utc": timestamp,
    }


def generate_state_snapshot(machine_id, timestamp):
    return {
        "tool_id": machine_id,
        "snapshot_ts_utc": timestamp,
        "machine_state": random.choice(["RUN", "IDLE", "SETUP", "MAINT"]),
        "machine_mode": random.choice(["PRODUCTION", "TEST"]),
        "current_alarm_code": random.choice(["", "TEMP_OVER", "RF_DRIFT"]) if random.random() > 0.7 else "",
        "current_lot_id": f"LOT{random.randint(10000, 99999)}" if random.random() > 0.3 else "",
        "pod_position": random.choice(["LOADPORT_01", "TRANSFER", ""]),
        "snapshot_json": json.dumps({"source": "simulation"}),
    }


def generate_alarm_event(machine_id, start_time):
    duration = random.randint(60, 3600)
    end_time = (datetime.fromisoformat(start_time) + timedelta(seconds=duration)).isoformat()
    return {
        "tool_id": machine_id,
        "alarm_code": random.choice(["ALM_TEMP_HIGH", "ALM_RF_DRIFT", "ALM_PRESSURE", "ALM_GAS_FLOW", "ALM_ENDPOINT"]),
        "alarm_severity": random.choice(["CRITICAL", "WARNING"]),
        "start_ts_utc": start_time,
        "end_ts_utc": end_time if random.random() > 0.3 else None,
        "duration_sec": duration if random.random() > 0.3 else None,
        "cycle_id": f"CYC{random.randint(1000, 9999)}",
        "lot_id": f"LOT{random.randint(10000, 99999)}" if random.random() > 0.5 else None,
        "alarm_context_json": json.dumps({"source": "simulation"}),
    }


def seed_ods_data(db: Session, machines):
    print("[ODS] 开始生成ODS模拟数据...")

    today = datetime.now().strftime("%Y-%m-%d")
    start_ts = datetime.fromisoformat(today + "T08:00:00")

    for machine in machines:
        for i in range(50):
            event_time = (start_ts + timedelta(seconds=i * 120)).isoformat()
            event_type = random.choice(["STATE", "SENSOR", "TRANSFER", "ALARM", "STATE", "SENSOR"])

            raw_event = DT_EVENT_RAW(
                raw_id=f"RAW{random.randint(10000000, 99999999)}",
                tool_id=machine.id,
                source_system="TIBRV",
                source_message_id=f"MSG{random.randint(1000000, 9999999)}",
                received_ts_utc=event_time,
                event_ts_utc=event_time,
                payload_json=generate_raw_event(machine.id, event_type, event_time),
                parse_status="PARSED",
            )
            db.add(raw_event)

            std_event = DT_EVENT_STD(**generate_std_event(raw_event.raw_id, machine.id, event_type, event_time))
            db.add(std_event)

            if i % 5 == 0:
                snapshot = DT_STATE_SNAPSHOT(**generate_state_snapshot(machine.id, event_time))
                db.add(snapshot)

            if event_type == "ALARM":
                alarm = DT_ALARM_EVENT(**generate_alarm_event(machine.id, event_time))
                db.add(alarm)

    db.commit()
    print("[ODS] ODS数据生成完成")


def sync_ods_to_local(db: Session):
    if not cache.enabled:
        return

    try:
        machines = db.query(DT_STATE_SNAPSHOT).distinct(DT_STATE_SNAPSHOT.tool_id).all()
        for m in machines:
            latest_snapshot = db.query(DT_STATE_SNAPSHOT).filter(
                DT_STATE_SNAPSHOT.tool_id == m.tool_id
            ).order_by(DT_STATE_SNAPSHOT.snapshot_ts_utc.desc()).first()

            if latest_snapshot:
                state_data = {
                    "tool_id": latest_snapshot.tool_id,
                    "machine_state": latest_snapshot.machine_state,
                    "machine_mode": latest_snapshot.machine_mode,
                    "current_lot_id": latest_snapshot.current_lot_id,
                    "pod_position": latest_snapshot.pod_position,
                    "timestamp": latest_snapshot.snapshot_ts_utc,
                }
                cache.set_machine_state(m.tool_id, state_data)

        print("[ODS] 同步完成")
    except Exception as e:
        print(f"[ODS] 同步失败: {e}")
