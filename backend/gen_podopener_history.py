"""生成PODOPENER-1的7天历史数据

生成内容：
- 每天8:00-20:00运行
- 每小时约3个完整周期（穿入+脱出）
- 随机插入报警事件
- 写入DT_EVENT_RAW表
"""
import sys
import os
import json
import random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from database import engine
from sqlalchemy import text
from models import DT_EVENT_RAW, DT_EVENT_RAW_CUR, Base

LOT_POOL = ["V3NL8", "V394K", "PG0R3", "V39S5", "V3QS6", "PG0R4", "V394L"]
PRODUCT_POOL = ["NAND-3D", "DRAM-1X", "Logic-5nm", "Logic-7nm", "CMOS-Image"]

# 穿入流程（14步，时间间隔约10-30秒每步）
PACKING_STEPS = [
    ("POD_PLACED", "VFEI", "PACKING", False, 10),
    ("COMPLETED_PORT_LOCK", "VFEI", "PACKING", False, 8),
    ("READ_BATTERY", "VFEI", None, False, 5),
    ("READ_TAG", "VFEI", "PACKING", False, 8),
    ("BATCH_INFO_FROM_ECUI", "HOST", "PACKING", True, 12),
    ("OPEN_POD", "VFEI", "PACKING", True, 10),
    ("REACH_STAGE", "VFEI", "PACKING", True, 15),
    ("UI_CONFIRM", "HOST", "PACKING", True, 20),
    ("CLOSE_POD", "VFEI", "PACKING", True, 10),
    ("ACK_UI_DOUBLECHECK", "HOST", "PACKING", True, 15),
    ("REACH_POS", "VFEI", "PACKING", True, 12),
    ("WRITE_TAG", "VFEI", "PACKING", True, 8),
    ("COMPLETED_PORT_UNLOCK", "VFEI", "PACKING", True, 6),
    ("POD_REMOVED", "VFEI", "PACKING", True, 5),
]

# 脱出流程（6步）
UNPACKING_STEPS = [
    ("UI_CONFIRM", "HOST", "UNPACKING", True, 15),
    ("CLOSE_POD", "VFEI", "UNPACKING", True, 10),
    ("REACH_POS", "VFEI", "UNPACKING", True, 12),
    ("WRITE_TAG", "VFEI", "UNPACKING", True, 8),
    ("COMPLETED_PORT_UNLOCK", "VFEI", "UNPACKING", True, 6),
    ("POD_REMOVED", "VFEI", "UNPACKING", True, 5),
]

# 报警定义
ALARM_DEFS = [
    ("9004", "POD NOT FOUND", "crit"),
    ("9003", "POD DOOR NOT LOCKED", "warn"),
    ("20011", "TAG READ FAIL", "warn"),
    ("0411", "DOOR OPEN TIMEOUT", "info"),
    ("0201", "PORT LOCK FAIL", "crit"),
]


def _gen_cassette_id():
    return f"{random.randint(10000, 99999)}{random.choice('ABCDEF')}"


def _build_payload(event_name, event_type, mode, has_lot, lot_id, cassette_id):
    return json.dumps({
        "tool_id": "PODOPENER-1",
        "lot_id": lot_id if has_lot else "NULL",
        "run_mode": mode if mode else "NULL",
        "event_type": event_type,
        "event_name": event_name,
        "event_value": event_name,
        "status": event_name,
        "machine_state": event_name,
        "machine_mode": mode if mode else "NULL",
        "alarm_code": None,
        "alarm_id": None,
        "alarm_text": event_name,
        "source_system": "RV",
        "port_id": "1",
        "cassette_id": cassette_id,
        "pod_id": cassette_id,
        "smif_id": "1",
        "chamber_id": "NULL",
        "batch_id": f"BT_{cassette_id}" if has_lot else "NULL",
        "unit_id": "NULL",
        "slot_id": "NULL",
    }, ensure_ascii=False)


def _build_alarm_payload(alarm_id, alarm_text, lot_id, cassette_id):
    return json.dumps({
        "tool_id": "PODOPENER-1",
        "lot_id": lot_id,
        "run_mode": "PACKING",
        "event_type": "VFEI",
        "event_name": "EC_ALARM_REPORT",
        "event_value": alarm_id,
        "status": "ALARM",
        "machine_state": "ALARM",
        "machine_mode": "PACKING",
        "alarm_code": alarm_id,
        "alarm_id": alarm_id,
        "alarm_text": alarm_text,
        "source_system": "RV",
        "port_id": "1",
        "cassette_id": cassette_id,
        "pod_id": cassette_id,
        "smif_id": "1",
        "chamber_id": "NULL",
        "batch_id": f"BT_{cassette_id}",
        "unit_id": "NULL",
        "slot_id": "NULL",
        "severity": "warn",
    }, ensure_ascii=False)


def generate_history(days=7, start_hour=8, end_hour=20):
    """生成历史数据"""
    print(f"开始生成 {days} 天的 PODOPENER-1 历史数据...")
    print(f"每天运行时间: {start_hour}:00 - {end_hour}:00")

    # 先清空现有数据
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM DT_EVENT_RAW WHERE TOOL_ID = 'PODOPENER-1'"))
        conn.execute(text("DELETE FROM DT_EVENT_RAW_CUR WHERE TOOL_ID = 'PODOPENER-1'"))
        conn.execute(text("DELETE FROM LOTS WHERE MACHINE_ID = 'PODOPENER-1'"))
        conn.commit()
    print("已清空PODOPENER-1的旧数据（事件+当前状态+Lot）")

    now = datetime.now()
    total_events = 0
    raw_id_counter = 100000

    for day_offset in range(days - 1, -1, -1):
        day_date = now - timedelta(days=day_offset)
        day_start = day_date.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        day_end = day_date.replace(hour=end_hour, minute=0, second=0, microsecond=0)

        current_time = day_start
        day_events = 0

        while current_time < day_end:
            # 穿入流程
            lot_id = random.choice(LOT_POOL)
            cassette_id = _gen_cassette_id()
            lot_start_time = current_time.strftime("%Y-%m-%dT%H:%M:%S")
            lot_product = random.choice(PRODUCT_POOL)
            lot_wafer_count = random.choice([24, 25, 25, 26])
            lot_seq_id = f"POD{raw_id_counter}"

            # 创建Lot记录
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO LOTS (ID, MACHINE_ID, PRODUCT, WAFER_COUNT, STATUS, START_TIME, END_TIME, RECIPE_ID)
                    VALUES (:id, :machine_id, :product, :wafer_count, 'run', :start_time, NULL, NULL)
                """), {
                    "id": lot_seq_id,
                    "machine_id": "PODOPENER-1",
                    "product": lot_product,
                    "wafer_count": lot_wafer_count,
                    "start_time": lot_start_time,
                })
                conn.commit()

            for event_name, event_type, mode, has_lot, delay_sec in PACKING_STEPS:
                if current_time >= day_end:
                    break

                ts_str = current_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                payload = _build_payload(event_name, event_type, mode, has_lot, lot_id, cassette_id)

                raw_id = f"HIS.{raw_id_counter}"
                raw_id_counter += 1

                with engine.connect() as conn:
                    conn.execute(text("""
                        INSERT INTO DT_EVENT_RAW (RAW_ID, TOOL_ID, SOURCE_SYSTEM, SOURCE_MESSAGE_ID,
                            RECEIVED_TS_UTC, EVENT_TS_UTC, PAYLOAD_JSON, PARSE_STATUS, ERROR_MESSAGE)
                        VALUES (:raw_id, :tool_id, :source_system, :source_message_id,
                            :received_ts, :event_ts, :payload, 'PARSED', NULL)
                    """), {
                        "raw_id": raw_id,
                        "tool_id": "PODOPENER-1",
                        "source_system": "RV",
                        "source_message_id": raw_id,
                        "received_ts": ts_str,
                        "event_ts": ts_str,
                        "payload": payload,
                    })
                    conn.commit()

                day_events += 1
                total_events += 1
                current_time += timedelta(seconds=delay_sec + random.uniform(0, 5))

                # 10%概率插入报警
                if random.random() < 0.10 and event_name not in ("POD_PLACED", "POD_REMOVED"):
                    alarm_id, alarm_text, _ = random.choice(ALARM_DEFS)
                    alarm_payload = _build_alarm_payload(alarm_id, alarm_text, lot_id, cassette_id)
                    alarm_raw_id = f"HIS.{raw_id_counter}"
                    raw_id_counter += 1
                    alarm_ts = current_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")

                    with engine.connect() as conn:
                        conn.execute(text("""
                            INSERT INTO DT_EVENT_RAW (RAW_ID, TOOL_ID, SOURCE_SYSTEM, SOURCE_MESSAGE_ID,
                                RECEIVED_TS_UTC, EVENT_TS_UTC, PAYLOAD_JSON, PARSE_STATUS, ERROR_MESSAGE)
                            VALUES (:raw_id, :tool_id, :source_system, :source_message_id,
                                :received_ts, :event_ts, :payload, 'PARSED', NULL)
                        """), {
                            "raw_id": alarm_raw_id,
                            "tool_id": "PODOPENER-1",
                            "source_system": "RV",
                            "source_message_id": alarm_raw_id,
                            "received_ts": alarm_ts,
                            "event_ts": alarm_ts,
                            "payload": alarm_payload,
                        })
                        conn.commit()

                    day_events += 1
                    total_events += 1
                    current_time += timedelta(seconds=5 + random.uniform(0, 10))

            if current_time >= day_end:
                break

            # 脱出流程（同一张cassette）
            for event_name, event_type, mode, has_lot, delay_sec in UNPACKING_STEPS:
                if current_time >= day_end:
                    break

                ts_str = current_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                payload = _build_payload(event_name, event_type, mode, has_lot, lot_id, cassette_id)

                raw_id = f"HIS.{raw_id_counter}"
                raw_id_counter += 1

                with engine.connect() as conn:
                    conn.execute(text("""
                        INSERT INTO DT_EVENT_RAW (RAW_ID, TOOL_ID, SOURCE_SYSTEM, SOURCE_MESSAGE_ID,
                            RECEIVED_TS_UTC, EVENT_TS_UTC, PAYLOAD_JSON, PARSE_STATUS, ERROR_MESSAGE)
                        VALUES (:raw_id, :tool_id, :source_system, :source_message_id,
                            :received_ts, :event_ts, :payload, 'PARSED', NULL)
                    """), {
                        "raw_id": raw_id,
                        "tool_id": "PODOPENER-1",
                        "source_system": "RV",
                        "source_message_id": raw_id,
                        "received_ts": ts_str,
                        "event_ts": ts_str,
                        "payload": payload,
                    })
                    conn.commit()

                day_events += 1
                total_events += 1
                current_time += timedelta(seconds=delay_sec + random.uniform(0, 5))

            # 脱出流程结束，更新Lot状态为done
            lot_end_time = current_time.strftime("%Y-%m-%dT%H:%M:%S")
            with engine.connect() as conn:
                conn.execute(text("""
                    UPDATE LOTS SET STATUS = 'done', END_TIME = :end_time
                    WHERE ID = :lot_seq_id
                """), {
                    "end_time": lot_end_time,
                    "lot_seq_id": lot_seq_id,
                })
                conn.commit()

            # 间隔休息3-8分钟
            current_time += timedelta(minutes=random.randint(3, 8))

        print(f"  {day_date.strftime('%Y-%m-%d')}: 生成 {day_events} 条事件")

    # 设置CUR表的最后一条数据
    with engine.connect() as conn:
        last_raw = conn.execute(text("""
            SELECT RAW_ID, SOURCE_SYSTEM, SOURCE_MESSAGE_ID, RECEIVED_TS_UTC, EVENT_TS_UTC, PAYLOAD_JSON
            FROM DT_EVENT_RAW WHERE TOOL_ID = 'PODOPENER-1'
            ORDER BY RECEIVED_TS_UTC DESC FETCH FIRST 1 ROWS ONLY
        """)).first()

        if last_raw:
            conn.execute(text("""
                INSERT INTO DT_EVENT_RAW_CUR (TOOL_ID, RAW_ID, SOURCE_SYSTEM, SOURCE_MESSAGE_ID,
                    RECEIVED_TS_UTC, EVENT_TS_UTC, PAYLOAD_JSON, PARSE_STATUS, ERROR_MESSAGE)
                VALUES (:tool_id, :raw_id, :source_system, :source_message_id,
                    :received_ts, :event_ts, :payload, 'PARSED', NULL)
            """), {
                "tool_id": "PODOPENER-1",
                "raw_id": last_raw[0],
                "source_system": last_raw[1],
                "source_message_id": last_raw[2],
                "received_ts": last_raw[3],
                "event_ts": last_raw[4],
                "payload": last_raw[5],
            })
            conn.commit()

    print(f"\n生成完成！总共 {total_events} 条事件")


if __name__ == "__main__":
    generate_history(days=7, start_hour=8, end_hour=20)
