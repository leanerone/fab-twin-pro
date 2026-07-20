"""模拟数据生成：机台、Lot、事件、告警、ODS数据等"""
import random
import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import uuid

from models import Machine, Lot, Recipe, ChamberSnapshot, OHTPosition, Floor, FloorArea, MachineModelConfig, EventActionMapping, DT_EVENT_RAW, User, Role, Permission, RolePermission, MachineToolMapping, Alarm, MachineEvent
from services.ods import seed_ods_data

product_names = ["DRAM-1X", "NAND-3D", "Logic-7nm", "Logic-5nm", "CMOS-Image", "Power-IC"]


def create_machines(db: Session):
    machines_data = [
        # === 1F: 测试与分选区 ===
        {"id": "WAT-01", "name": "WAT测试机 WAT-01", "line": 1, "floor": 1, "has_smif": False, "x_pos": -8, "y_pos": 0, "floor_x": 10, "floor_y": 15, "process_type": "WAT"},
        {"id": "WAT-02", "name": "WAT测试机 WAT-02", "line": 1, "floor": 1, "has_smif": False, "x_pos": -4, "y_pos": 0, "floor_x": 25, "floor_y": 15, "process_type": "WAT"},
        {"id": "WAT-03", "name": "WAT测试机 WAT-03", "line": 1, "floor": 1, "has_smif": False, "x_pos": 0, "y_pos": 0, "floor_x": 40, "floor_y": 15, "process_type": "WAT"},
        {"id": "WS-01", "name": "晶圆分选机 WS-01", "line": 1, "floor": 1, "has_smif": False, "x_pos": -8, "y_pos": 3, "floor_x": 10, "floor_y": 45, "process_type": "WS"},
        {"id": "WS-02", "name": "晶圆分选机 WS-02", "line": 1, "floor": 1, "has_smif": False, "x_pos": -4, "y_pos": 3, "floor_x": 25, "floor_y": 45, "process_type": "WS"},
        {"id": "WS-03", "name": "晶圆分选机 WS-03", "line": 1, "floor": 1, "has_smif": False, "x_pos": 0, "y_pos": 3, "floor_x": 40, "floor_y": 45, "process_type": "WS"},
        {"id": "STK-1F", "name": "STK传输机 1F", "line": 1, "floor": 1, "has_smif": False, "x_pos": 4, "y_pos": 0, "floor_x": 55, "floor_y": 30, "process_type": "STK"},

        # === 2F: 电梯与通道(办公区) - 少量设备 ===
        {"id": "STK-2F", "name": "STK传输机 2F", "line": 1, "floor": 2, "has_smif": False, "x_pos": 0, "y_pos": 0, "floor_x": 45, "floor_y": 40, "process_type": "STK"},

        # === 3F: 主生产楼层 ===
        # Line 1 (无SMIF)
        {"id": "OXE-01", "name": "刻蚀机 OXE-01", "line": 1, "floor": 3, "has_smif": False, "x_pos": -8, "y_pos": 0, "floor_x": 5, "floor_y": 20},
        {"id": "OXE-02", "name": "刻蚀机 OXE-02", "line": 1, "floor": 3, "has_smif": False, "x_pos": -4, "y_pos": 0, "floor_x": 12, "floor_y": 20},
        {"id": "OXE-03", "name": "刻蚀机 OXE-03", "line": 1, "floor": 3, "has_smif": False, "x_pos": 0, "y_pos": 0, "floor_x": 19, "floor_y": 20},
        {"id": "OXE-04", "name": "刻蚀机 OXE-04", "line": 1, "floor": 3, "has_smif": False, "x_pos": 4, "y_pos": 0, "floor_x": 26, "floor_y": 20},
        {"id": "OXE-05", "name": "刻蚀机 OXE-05", "line": 1, "floor": 3, "has_smif": False, "x_pos": 8, "y_pos": 0, "floor_x": 33, "floor_y": 20},
        {"id": "OXE-06", "name": "刻蚀机 OXE-06", "line": 1, "floor": 3, "has_smif": False, "x_pos": 12, "y_pos": 0, "floor_x": 5, "floor_y": 55},
        {"id": "OXE-07", "name": "刻蚀机 OXE-07", "line": 1, "floor": 3, "has_smif": False, "x_pos": -8, "y_pos": 3, "floor_x": 12, "floor_y": 55},
        {"id": "OXE-08", "name": "刻蚀机 OXE-08", "line": 1, "floor": 3, "has_smif": False, "x_pos": -4, "y_pos": 3, "floor_x": 19, "floor_y": 55},
        {"id": "OXE-09", "name": "刻蚀机 OXE-09", "line": 1, "floor": 3, "has_smif": False, "x_pos": 0, "y_pos": 3, "floor_x": 26, "floor_y": 55},
        {"id": "OXE-10", "name": "刻蚀机 OXE-10", "line": 1, "floor": 3, "has_smif": False, "x_pos": 4, "y_pos": 3, "floor_x": 33, "floor_y": 55},
        # Line 2 (有SMIF)
        {"id": "OXE-11", "name": "刻蚀机 OXE-11", "line": 2, "floor": 3, "has_smif": True, "x_pos": -8, "y_pos": -3, "floor_x": 60, "floor_y": 20},
        {"id": "OXE-12", "name": "刻蚀机 OXE-12", "line": 2, "floor": 3, "has_smif": True, "x_pos": -4, "y_pos": -3, "floor_x": 67, "floor_y": 20},
        {"id": "OXE-13", "name": "刻蚀机 OXE-13", "line": 2, "floor": 3, "has_smif": True, "x_pos": 0, "y_pos": -3, "floor_x": 74, "floor_y": 20},
        {"id": "OXE-14", "name": "刻蚀机 OXE-14", "line": 2, "floor": 3, "has_smif": True, "x_pos": 4, "y_pos": -3, "floor_x": 81, "floor_y": 20},
        {"id": "OXE-15", "name": "刻蚀机 OXE-15", "line": 2, "floor": 3, "has_smif": True, "x_pos": 8, "y_pos": -3, "floor_x": 88, "floor_y": 20},
        {"id": "OXE-16", "name": "刻蚀机 OXE-16", "line": 2, "floor": 3, "has_smif": True, "x_pos": 12, "y_pos": -3, "floor_x": 60, "floor_y": 55},
        {"id": "OXE-17", "name": "刻蚀机 OXE-17", "line": 2, "floor": 3, "has_smif": True, "x_pos": -8, "y_pos": -6, "floor_x": 67, "floor_y": 55},
        {"id": "OXE-18", "name": "刻蚀机 OXE-18", "line": 2, "floor": 3, "has_smif": True, "x_pos": -4, "y_pos": -6, "floor_x": 74, "floor_y": 55},
        {"id": "OXE-19", "name": "刻蚀机 OXE-19", "line": 2, "floor": 3, "has_smif": True, "x_pos": 0, "y_pos": -6, "floor_x": 81, "floor_y": 55},
        {"id": "OXE-20", "name": "刻蚀机 OXE-20", "line": 2, "floor": 3, "has_smif": True, "x_pos": 4, "y_pos": -6, "floor_x": 88, "floor_y": 55},
        {"id": "PODOPENER-1", "name": "POD开盖机 PODOPENER-1", "line": 1, "floor": 3, "has_smif": True, "x_pos": 16, "y_pos": 0, "floor_x": 40, "floor_y": 8, "process_type": "PODOPENER", "model": "PODOPENER-2200"},
        {"id": "STK-3F", "name": "STK传输机 3F", "line": 1, "floor": 3, "has_smif": False, "x_pos": 0, "y_pos": 0, "floor_x": 47, "floor_y": 38, "process_type": "STK"},

        # === 4F: 刻蚀区扩展 ===
        {"id": "OXE-51", "name": "刻蚀机 OXE-51", "line": 1, "floor": 4, "has_smif": False, "x_pos": -8, "y_pos": 0, "floor_x": 10, "floor_y": 20},
        {"id": "OXE-52", "name": "刻蚀机 OXE-52", "line": 1, "floor": 4, "has_smif": False, "x_pos": -4, "y_pos": 0, "floor_x": 25, "floor_y": 20},
        {"id": "OXE-53", "name": "刻蚀机 OXE-53", "line": 1, "floor": 4, "has_smif": False, "x_pos": 0, "y_pos": 0, "floor_x": 35, "floor_y": 50},
        {"id": "OXE-61", "name": "刻蚀机 OXE-61", "line": 2, "floor": 4, "has_smif": True, "x_pos": 4, "y_pos": 0, "floor_x": 60, "floor_y": 20},
        {"id": "OXE-62", "name": "刻蚀机 OXE-62", "line": 2, "floor": 4, "has_smif": True, "x_pos": 8, "y_pos": 0, "floor_x": 75, "floor_y": 20},
        {"id": "OXE-63", "name": "刻蚀机 OXE-63", "line": 2, "floor": 4, "has_smif": True, "x_pos": 12, "y_pos": 0, "floor_x": 85, "floor_y": 45},
        {"id": "OXE-64", "name": "刻蚀机 OXE-64", "line": 2, "floor": 4, "has_smif": True, "x_pos": 12, "y_pos": 3, "floor_x": 55, "floor_y": 50},
        {"id": "STK-4F", "name": "STK传输机 4F", "line": 1, "floor": 4, "has_smif": False, "x_pos": 0, "y_pos": 0, "floor_x": 47, "floor_y": 35, "process_type": "STK"},
    ]

    machines = []
    for m in machines_data:
        ptype = m.get("process_type", "ETCH") if m.get("process_type") else "ETCH"
        default_model = m.get("model") or ("TEL-DRM-UNIT" if ptype == "ETCH" else ptype)
        machine = Machine(
            id=m["id"],
            model=default_model,
            name=m["name"],
            line=m["line"],
            floor=m["floor"],
            chamber_count=4,
            process_type=ptype,
            state="idle",
            temp=22.0,
            pressure=1.0,
            gas_flow=0.0,
            rf_power=0.0,
            wafer_count=0,
            alarm_count=0,
            process_step=0,
            has_smif=m["has_smif"],
            updated_at=datetime.now().isoformat(),
            x_pos=m["x_pos"],
            y_pos=m["y_pos"],
            floor_x=m["floor_x"],
            floor_y=m["floor_y"],
        )
        db.add(machine)
        machines.append(machine)

    db.commit()
    return machines


def create_recipes(db: Session, machines):
    recipes = [
        {"id": "REC-ETCH-A", "name": "刻蚀工艺A", "process_type": "ETCH", "temperature": 72, "pressure": 0.005, "rf_power": 600, "gas_flow": 180, "process_time": 7500},
        {"id": "REC-ETCH-B", "name": "刻蚀工艺B", "process_type": "ETCH", "temperature": 68, "pressure": 0.003, "rf_power": 500, "gas_flow": 150, "process_time": 7000},
    ]

    for r in recipes:
        for m in machines:
            recipe = Recipe(
                id=f"{r['id']}-{m.id}",
                name=r["name"],
                machine_id=m.id,
                process_type=r["process_type"],
                temperature=r["temperature"],
                pressure=r["pressure"],
                rf_power=r["rf_power"],
                gas_flow=r["gas_flow"],
                process_time=r["process_time"],
                updated_at=datetime.now().isoformat(),
            )
            db.add(recipe)

    db.commit()


def create_lots(db: Session, machines):
    """创建Lot批次：覆盖过去5天 + 当天，确保历史回放可选日期"""
    lot_counter = 100000
    base_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    vpo_lot_pool = ["V3NL8", "V394K", "PG0R3", "V39S5", "V3QS6", "PG0R4", "V394L"]

    for m in machines:
        # 每台机台每天生成 5-8 个 Lot，覆盖过去5天到今天
        for day_offset in range(5, -1, -1):
            day_base = base_day - timedelta(days=day_offset)
            lot_count = 5 + random.randint(0, 3)
            start_time = day_base + timedelta(hours=8, minutes=random.randint(0, 30))

            for i in range(lot_count):
                # VPO机台用特殊lot_id格式（带日期后缀确保唯一性）
                if m.id.startswith("VPO") or m.process_type == "PODOPENER":
                    base_lot = random.choice(vpo_lot_pool)
                    actual_lot_id = f"{base_lot}-D{day_offset}-{i}"
                else:
                    actual_lot_id = f"LOT{lot_counter}"
                    lot_counter += 1

                cycle_duration = (20 + random.random() * 8) * 60
                end_time = start_time + timedelta(seconds=cycle_duration)

                # 状态分布：当天部分为run/pending，过去日期为done/hold
                if day_offset == 0:
                    status_roll = random.random()
                    if status_roll > 0.85:
                        status = "hold"
                    elif status_roll > 0.7:
                        status = "run"
                    elif status_roll > 0.6:
                        status = "pending"
                    else:
                        status = "done"
                else:
                    status_roll = random.random()
                    if status_roll > 0.92:
                        status = "hold"
                    else:
                        status = "done"

                lot = Lot(
                    id=actual_lot_id,
                    machine_id=m.id,
                    product=product_names[random.randint(0, len(product_names)-1)],
                    wafer_count=24 + random.randint(0, 2),
                    status=status,
                    start_time=start_time.isoformat(),
                    end_time=end_time.isoformat(),
                    recipe_id=f"REC-ETCH-{chr(65 + random.randint(0, 1))}-{m.id}",
                )
                db.add(lot)

                start_time = end_time + timedelta(seconds=random.randint(-120, 300))

    db.commit()
    print(f"[Seed] Lot数据生成完成 ({lot_counter - 100000 + sum(1 for m in machines if m.id.startswith('VPO') or m.process_type == 'PODOPENER' for _ in range(6) for _ in range(5))} 条)")


def create_alarms(db: Session, machines):
    """创建告警数据：每台机台每天 2-3 条告警，覆盖过去5天+今天"""
    # 告警模板（与DT_EVENT_RAW的alarm templates保持一致）
    alarm_templates = [
        {"alarm_code": "TEMP_OVER", "level": "warn", "description": "腔体温度超过阈值", "lot_id": None},
        {"alarm_code": "RF_DRIFT", "level": "warn", "description": "RF功率漂移", "lot_id": None},
        {"alarm_code": "PRESS_UNSTABLE", "level": "crit", "description": "腔体压力不稳定", "lot_id": None},
        {"alarm_code": "GAS_LEAK", "level": "crit", "description": "气体流量异常", "lot_id": None},
        {"alarm_code": "9003", "level": "warn", "description": "测试时间快到警告", "lot_id": "V3NL8"},
        {"alarm_code": "9004", "level": "crit", "description": "超过测试限Run产品批数", "lot_id": "PG0R3"},
        {"alarm_code": "20011", "level": "warn", "description": "Pod DirtyBit异常", "lot_id": "V39S5"},
        {"alarm_code": "0201", "level": "crit", "description": "POD电池电压异常", "lot_id": None},
        {"alarm_code": "0411", "level": "warn", "description": "POD清洗日期快到", "lot_id": None},
    ]

    base_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    count = 0
    vpo_lot_pool = ["V3NL8", "V394K", "PG0R3", "V39S5", "V3QS6", "PG0R4", "V394L"]
    for m in machines:
        for day_offset in range(5, -1, -1):
            day_base = base_day - timedelta(days=day_offset)
            # 每台机台每天 1-3 条告警
            alarm_count = 1 + random.randint(0, 2)
            for i in range(alarm_count):
                tpl = alarm_templates[(hash(m.id + str(day_offset)) + i) % len(alarm_templates)]
                # 告警时间在工作时段 8:00-20:00
                hour = 8 + random.randint(0, 11)
                minute = random.randint(0, 59)
                ts = day_base + timedelta(hours=hour, minutes=minute)
                # VPO/PODOPENER 使用固定lot_id池
                if m.id.startswith("VPO") or m.process_type == "PODOPENER":
                    base_lot = tpl["lot_id"] or random.choice(vpo_lot_pool)
                    tpl_lot = f"{base_lot}-D{day_offset}-{i}"
                else:
                    tpl_lot = tpl["lot_id"] or f"LOT{100000 + random.randint(0, 5000)}"

                alarm = Alarm(
                    machine_id=m.id,
                    timestamp=ts.isoformat(),
                    alarm_code=tpl["alarm_code"],
                    description=tpl["description"],
                    level=tpl["level"],
                    resolved=day_offset > 0,  # 过去的告警标记为已解决
                    lot_id=tpl_lot,
                )
                db.add(alarm)
                count += 1

    db.commit()
    print(f"[Seed] 告警数据生成完成 ({count} 条)")


def create_chamber_snapshots(db: Session, machines):
    today = datetime.now().strftime("%Y-%m-%d")
    for m in machines:
        start_time = datetime.fromisoformat(f"{today}T08:00:00")
        for i in range(30):
            for chamber_id in ["PM-1", "PM-2", "PM-3", "PM-4"]:
                snapshot = ChamberSnapshot(
                    machine_id=m.id,
                    chamber_id=chamber_id,
                    timestamp=(start_time + timedelta(seconds=i * 120)).isoformat(),
                    temperature=22 + random.random() * 50,
                    pressure=0.001 + random.random() * 0.999,
                    rf_power=random.random() * 800,
                    gas_flow=random.random() * 200,
                    is_running=random.random() > 0.5,
                )
                db.add(snapshot)

    db.commit()


def create_oht_positions(db: Session):
    today = datetime.now().strftime("%Y-%m-%d")
    ohts = ["OHT-001", "OHT-002"]

    for oht_id in ohts:
        start_time = datetime.fromisoformat(f"{today}T08:00:00")
        x_pos = 4.0

        for i in range(50):
            position = OHTPosition(
                oht_id=oht_id,
                lot_id=f"LOT{random.randint(10000, 99999)}" if random.random() > 0.3 else None,
                x_pos=x_pos,
                y_pos=3.0,
                z_pos=0.0,
                status="moving" if random.random() > 0.2 else "idle",
                target_machine_id=f"OXE-{random.randint(1, 20):02d}" if random.random() > 0.3 else None,
                timestamp=(start_time + timedelta(seconds=i * 60)).isoformat(),
            )
            db.add(position)

            x_pos += random.uniform(-0.5, 0.5)
            x_pos = max(4.0, min(12.0, x_pos))

    db.commit()


def create_floors(db: Session):
    floors_data = [
        {"id": 1, "name": "1F", "description": "测试与分选区", "width": 100, "height": 80},
        {"id": 2, "name": "2F", "description": "电梯与通道(办公区)", "width": 100, "height": 80},
        {"id": 3, "name": "3F", "description": "主生产楼层", "width": 100, "height": 80},
        {"id": 4, "name": "4F", "description": "刻蚀区扩展", "width": 100, "height": 80},
    ]

    for f in floors_data:
        floor = Floor(
            id=f["id"],
            name=f["name"],
            description=f["description"],
            width=f["width"],
            height=f["height"],
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        db.add(floor)

    db.commit()


def create_floor_areas(db: Session):
    areas_data = [
        # === 1F: 测试与分选区 ===
        {"floor_id": 1, "name": "WAT测试区", "area_type": "equipment", "x_pos": 3, "y_pos": 8, "width": 45, "height": 18, "color": "#1e3a5f"},
        {"floor_id": 1, "name": "WS分选区", "area_type": "equipment", "x_pos": 3, "y_pos": 38, "width": 45, "height": 18, "color": "#2d1b4e"},
        {"floor_id": 1, "name": "STK传输区", "area_type": "stk", "x_pos": 50, "y_pos": 20, "width": 12, "height": 25, "color": "#1a4a3a"},
        {"floor_id": 1, "name": "T1 过道", "area_type": "walkway", "x_pos": 3, "y_pos": 30, "width": 45, "height": 6, "color": "#3a3a3a"},
        {"floor_id": 1, "name": "T2 过道", "area_type": "walkway", "x_pos": 65, "y_pos": 8, "width": 6, "height": 60, "color": "#3a3a3a"},
        {"floor_id": 1, "name": "电梯", "area_type": "elevator", "x_pos": 90, "y_pos": 30, "width": 6, "height": 15, "color": "#4a3728"},
        {"floor_id": 1, "name": "逃生门1", "area_type": "exit", "x_pos": 0, "y_pos": 70, "width": 3, "height": 5, "color": "#8b0000"},
        {"floor_id": 1, "name": "逃生门2", "area_type": "exit", "x_pos": 97, "y_pos": 70, "width": 3, "height": 5, "color": "#8b0000"},
        
        # === 2F: 电梯与通道(办公区) ===
        {"floor_id": 2, "name": "办公区", "area_type": "equipment", "x_pos": 10, "y_pos": 10, "width": 35, "height": 25, "color": "#1e3a5f"},
        {"floor_id": 2, "name": "会议室", "area_type": "equipment", "x_pos": 10, "y_pos": 45, "width": 25, "height": 15, "color": "#2d1b4e"},
        {"floor_id": 2, "name": "STK传输区", "area_type": "stk", "x_pos": 40, "y_pos": 30, "width": 15, "height": 20, "color": "#1a4a3a"},
        {"floor_id": 2, "name": "T1 过道", "area_type": "walkway", "x_pos": 3, "y_pos": 38, "width": 35, "height": 5, "color": "#3a3a3a"},
        {"floor_id": 2, "name": "T2 过道", "area_type": "walkway", "x_pos": 60, "y_pos": 10, "width": 5, "height": 60, "color": "#3a3a3a"},
        {"floor_id": 2, "name": "电梯井", "area_type": "elevator", "x_pos": 88, "y_pos": 25, "width": 8, "height": 25, "color": "#4a3728"},
        {"floor_id": 2, "name": "逃生门", "area_type": "exit", "x_pos": 0, "y_pos": 70, "width": 3, "height": 5, "color": "#8b0000"},
        
        # === 3F: 主生产楼层 ===
        {"floor_id": 3, "name": "Line 1 设备区", "area_type": "equipment", "x_pos": 2, "y_pos": 12, "width": 40, "height": 55, "color": "#0d2818"},
        {"floor_id": 3, "name": "Line 2 设备区", "area_type": "equipment", "x_pos": 56, "y_pos": 12, "width": 40, "height": 55, "color": "#281828"},
        {"floor_id": 3, "name": "STK传输区", "area_type": "stk", "x_pos": 43, "y_pos": 25, "width": 12, "height": 30, "color": "#1a4a3a"},
        {"floor_id": 3, "name": "T1 过道", "area_type": "walkway", "x_pos": 2, "y_pos": 35, "width": 40, "height": 6, "color": "#3a3a3a"},
        {"floor_id": 3, "name": "T2 过道", "area_type": "walkway", "x_pos": 56, "y_pos": 35, "width": 40, "height": 6, "color": "#3a3a3a"},
        {"floor_id": 3, "name": "PUMP区", "area_type": "pump", "x_pos": 2, "y_pos": 2, "width": 20, "height": 8, "color": "#2d1b4e"},
        {"floor_id": 3, "name": "CST清洗区", "area_type": "equipment", "x_pos": 25, "y_pos": 2, "width": 15, "height": 8, "color": "#1e3a5f"},
        {"floor_id": 3, "name": "电气间", "area_type": "equipment", "x_pos": 75, "y_pos": 2, "width": 15, "height": 8, "color": "#3a2a4a"},
        {"floor_id": 3, "name": "电梯", "area_type": "elevator", "x_pos": 90, "y_pos": 30, "width": 6, "height": 15, "color": "#4a3728"},
        {"floor_id": 3, "name": "逃生门1", "area_type": "exit", "x_pos": 0, "y_pos": 72, "width": 3, "height": 5, "color": "#8b0000"},
        {"floor_id": 3, "name": "逃生门2", "area_type": "exit", "x_pos": 97, "y_pos": 72, "width": 3, "height": 5, "color": "#8b0000"},
        
        # === 4F: 刻蚀区扩展 ===
        {"floor_id": 4, "name": "BGBM区", "area_type": "equipment", "x_pos": 2, "y_pos": 10, "width": 25, "height": 15, "color": "#1e3a5f"},
        {"floor_id": 4, "name": "附属设备区", "area_type": "equipment", "x_pos": 30, "y_pos": 10, "width": 20, "height": 15, "color": "#2d1b4e"},
        {"floor_id": 4, "name": "Line 1 设备区", "area_type": "equipment", "x_pos": 2, "y_pos": 35, "width": 40, "height": 30, "color": "#0d2818"},
        {"floor_id": 4, "name": "Line 2 设备区", "area_type": "equipment", "x_pos": 56, "y_pos": 35, "width": 40, "height": 30, "color": "#281828"},
        {"floor_id": 4, "name": "STK传输区", "area_type": "stk", "x_pos": 43, "y_pos": 25, "width": 12, "height": 25, "color": "#1a4a3a"},
        {"floor_id": 4, "name": "T1 过道", "area_type": "walkway", "x_pos": 2, "y_pos": 30, "width": 40, "height": 5, "color": "#3a3a3a"},
        {"floor_id": 4, "name": "T2 过道", "area_type": "walkway", "x_pos": 56, "y_pos": 30, "width": 40, "height": 5, "color": "#3a3a3a"},
        {"floor_id": 4, "name": "电气间", "area_type": "equipment", "x_pos": 75, "y_pos": 10, "width": 15, "height": 8, "color": "#3a2a4a"},
        {"floor_id": 4, "name": "PM ROOM", "area_type": "equipment", "x_pos": 56, "y_pos": 10, "width": 15, "height": 8, "color": "#4a3728"},
        {"floor_id": 4, "name": "电梯", "area_type": "elevator", "x_pos": 90, "y_pos": 30, "width": 6, "height": 15, "color": "#4a3728"},
        {"floor_id": 4, "name": "逃生门", "area_type": "exit", "x_pos": 0, "y_pos": 72, "width": 3, "height": 5, "color": "#8b0000"},
    ]

    for a in areas_data:
        area = FloorArea(
            floor_id=a["floor_id"],
            name=a["name"],
            area_type=a["area_type"],
            x_pos=a["x_pos"],
            y_pos=a["y_pos"],
            width=a["width"],
            height=a["height"],
            color=a["color"],
            description=a.get("description"),
        )
        db.add(area)

    db.commit()


def create_machine_model_configs(db: Session):
    """创建机台型号配置（VPO、OXE/DRM等）和事件动作映射"""
    now = datetime.now(timezone.utc).isoformat() if hasattr(datetime, 'now') and False else "2026-07-14T00:00:00Z"
    from datetime import timezone
    now = datetime.now(timezone.utc).isoformat()

    existing = db.query(MachineModelConfig).count()
    if existing > 0:
        print(f"[Seed] 机台型号配置已存在 ({existing} 个)，跳过")
        return

    vpo_parts = [
        {"part_id": "base_plate", "part_name": "底座底板", "part_type": "structure",
         "view_3d": {"type": "box", "size": [520, 680, 38], "position": [0, -10, 19], "color": "#4b535c"}},
        {"part_id": "front_stage", "part_name": "前载台", "part_type": "stage",
         "view_3d": {"type": "box", "size": [300, 240, 48], "position": [0, -36, 124], "color": "#cbd5e1"}},
        {"part_id": "left_rail", "part_name": "左侧导轨", "part_type": "rail",
         "view_3d": {"type": "box", "size": [18, 306, 760], "position": [-181, -22, 484], "color": "#5f6972"}},
        {"part_id": "right_rail", "part_name": "右侧导轨", "part_type": "rail",
         "view_3d": {"type": "box", "size": [18, 306, 760], "position": [181, -22, 484], "color": "#5f6972"}},
        {"part_id": "rear_panel", "part_name": "后面板", "part_type": "panel",
         "view_3d": {"type": "box", "size": [330, 32, 690], "position": [0, 112, 444], "color": "#b7ad99"}},
        {"part_id": "wafer_port", "part_name": "Wafer入口", "part_type": "port",
         "view_3d": {"type": "cylinder", "size": [230, 230, 14], "position": [0, -142, 130], "color": "#94a3b8"},
         "hotspots": [{"hotspot_id": "wafer_port_front", "name": "晶圆入口", "position_3d": [0, -180, 130]}]},
        {"part_id": "chamber", "part_name": "工艺腔体", "part_type": "chamber",
         "view_3d": {"type": "cylinder", "size": [200, 200, 50], "position": [0, 0, 900], "color": "#17202a"}},
        {"part_id": "control_box", "part_name": "操作控制盒", "part_type": "control",
         "view_3d": {"type": "box", "size": [198, 92, 112], "position": [0, -472, 76], "color": "#111827"},
         "hotspots": [{"hotspot_id": "operator_control", "name": "控制盒", "position_3d": [0, -500, 76]}]},
        {"part_id": "pod", "part_name": "POD/晶舟", "part_type": "pod",
         "view_3d": {"type": "cylinder", "size": [150, 150, 300], "position": [0, -300, 200], "color": "#f59e0b"},
         "animated": True},
    ]

    vpo_hotspots = [
        {"hotspot_id": "machine_body", "name": "机身主体", "part_ids": ["left_rail", "right_rail", "rear_panel"]},
        {"hotspot_id": "wafer_port_front", "name": "Wafer入口", "part_ids": ["wafer_port"]},
        {"hotspot_id": "operator_control", "name": "控制盒", "part_ids": ["control_box"]},
    ]

    vpo_states = [
        {"state_id": "idle", "state_name": "待机", "color": "#9ca3af",
         "part_overrides": [{"part_id": "chamber", "emissive_intensity": 0}]},
        {"state_id": "running", "state_name": "运行", "color": "#22c55e",
         "part_overrides": [{"part_id": "chamber", "emissive": "#22c55e", "emissive_intensity": 0.5}]},
        {"state_id": "hold", "state_name": "暂停", "color": "#f59e0b",
         "part_overrides": [{"part_id": "wafer_port", "emissive": "#f59e0b", "emissive_intensity": 0.3}]},
        {"state_id": "alarm", "state_name": "告警", "color": "#ef4444",
         "part_overrides": [{"part_id": "chamber", "emissive": "#ef4444", "emissive_intensity": 0.8, "pulse": True}]},
    ]

    vpo_views = {
        "view_3d": {"type": "vpo", "model_source": "/models/podopener-2200-3d.json",
                    "default_camera": {"position": [700, -300, 400], "target": [0, 0, 400]}},
        "view_2d": {"type": "vpo", "svg_source": "procedural",
                    "view_label": "正视图"},
    }

    vpo_model = MachineModelConfig(
        model_id="VPO-2200",
        model_name="VPO 立式氧化炉",
        vendor="TEL",
        process_type="OXIDE",
        version="1.0",
        view_mode="vpo",
        description="VPO 立式氧化炉 2D/3D 统一视图，支持POD穿入脱出动画",
        views_config_json=json.dumps(vpo_views, ensure_ascii=False),
        parts_config_json=json.dumps(vpo_parts, ensure_ascii=False),
        state_mapping_json=json.dumps(vpo_states, ensure_ascii=False),
        hotspots_config_json=json.dumps(vpo_hotspots, ensure_ascii=False),
        created_at=now,
        updated_at=now,
    )
    db.add(vpo_model)

    oxe_parts = [
        {"part_id": "loadport_1", "part_name": "Load Port 1", "part_type": "loadport",
         "view_3d": {"type": "box", "size": [120, 180, 60], "position": [-285, -80, 180], "color": "#2a3a5a"},
         "view_2d_iso": {"x": 100, "y": 50, "width": 60, "height": 40, "isometric_depth": 20}},
        {"part_id": "loadport_2", "part_name": "Load Port 2", "part_type": "loadport",
         "view_3d": {"type": "box", "size": [120, 180, 60], "position": [-285, 80, 180], "color": "#2a3a5a"},
         "view_2d_iso": {"x": 100, "y": 150, "width": 60, "height": 40, "isometric_depth": 20}},
        {"part_id": "efem", "part_name": "EFEM 传输腔", "part_type": "efem",
         "view_3d": {"type": "box", "size": [200, 300, 200], "position": [-150, 0, 200], "color": "#374151"},
         "view_2d_iso": {"x": 200, "y": 100, "width": 100, "height": 120, "isometric_depth": 30}},
        {"part_id": "efem_robot", "part_name": "EFEM 机械臂", "part_type": "robot",
         "view_3d": {"type": "cylinder", "size": [30, 30, 120], "position": [-150, 0, 220], "color": "#60a5fa"},
         "animated": True},
        {"part_id": "aligner", "part_name": "Aligner 对中器", "part_type": "aligner",
         "view_3d": {"type": "cylinder", "size": [50, 50, 40], "position": [-150, -100, 180], "color": "#94a3b8"}},
        {"part_id": "vacuum_lock_1", "part_name": "真空锁 1", "part_type": "vacuum_lock",
         "view_3d": {"type": "box", "size": [100, 120, 80], "position": [-20, -80, 200], "color": "#475569"}},
        {"part_id": "vacuum_lock_2", "part_name": "真空锁 2", "part_type": "vacuum_lock",
         "view_3d": {"type": "box", "size": [100, 120, 80], "position": [-20, 80, 200], "color": "#475569"}},
        {"part_id": "transfer_chamber", "part_name": "传输腔 (VTM)", "part_type": "vtm",
         "view_3d": {"type": "cylinder", "size": [220, 220, 180], "position": [120, 0, 220], "color": "#1e293b"},
         "view_2d_iso": {"x": 350, "y": 100, "width": 100, "height": 120, "isometric_depth": 30}},
        {"part_id": "vtm_robot", "part_name": "VTM 机械臂", "part_type": "robot",
         "view_3d": {"type": "cylinder", "size": [25, 25, 100], "position": [120, 0, 230], "color": "#f59e0b"},
         "animated": True},
        {"part_id": "chamber_1", "part_name": "工艺腔 PM1", "part_type": "chamber",
         "view_3d": {"type": "cylinder", "size": [120, 120, 150], "position": [250, -150, 230], "color": "#1e3a5f"},
         "view_2d_iso": {"x": 480, "y": 40, "width": 60, "height": 60, "isometric_depth": 25}},
        {"part_id": "chamber_2", "part_name": "工艺腔 PM2", "part_type": "chamber",
         "view_3d": {"type": "cylinder", "size": [120, 120, 150], "position": [250, 150, 230], "color": "#1e3a5f"},
         "view_2d_iso": {"x": 480, "y": 170, "width": 60, "height": 60, "isometric_depth": 25}},
        {"part_id": "wafer", "part_name": "晶圆", "part_type": "wafer",
         "view_3d": {"type": "cylinder", "size": [50, 50, 3], "position": [-150, 0, 280], "color": "#60a5fa"},
         "animated": True},
    ]

    oxe_hotspots = [
        {"hotspot_id": "lp1", "name": "Load Port 1", "part_ids": ["loadport_1"]},
        {"hotspot_id": "lp2", "name": "Load Port 2", "part_ids": ["loadport_2"]},
        {"hotspot_id": "efem", "name": "EFEM", "part_ids": ["efem", "efem_robot"]},
        {"hotspot_id": "vtm", "name": "传输腔", "part_ids": ["transfer_chamber", "vtm_robot"]},
        {"hotspot_id": "pm1", "name": "工艺腔 1", "part_ids": ["chamber_1"]},
        {"hotspot_id": "pm2", "name": "工艺腔 2", "part_ids": ["chamber_2"]},
    ]

    oxe_states = [
        {"state_id": "idle", "state_name": "待机", "color": "#9ca3af"},
        {"state_id": "running", "state_name": "运行", "color": "#22c55e",
         "part_overrides": [
             {"part_id": "chamber_1", "emissive": "#22c55e", "emissive_intensity": 0.5},
             {"part_id": "chamber_2", "emissive": "#22c55e", "emissive_intensity": 0.5},
         ]},
        {"state_id": "hold", "state_name": "暂停", "color": "#f59e0b"},
        {"state_id": "alarm", "state_name": "告警", "color": "#ef4444",
         "part_overrides": [
             {"part_id": "transfer_chamber", "emissive": "#ef4444", "emissive_intensity": 0.8, "pulse": True},
         ]},
    ]

    oxe_views = {
        "view_3d": {"type": "threejs", "model_source": "procedural",
                    "default_camera": {"position": [7, 5, 8], "target": [0, 1.8, 0]}},
        "view_2d": {"type": "isometric",
                    "projection": {"scale": 30, "angle_x": 30, "angle_y": 45},
                    "view_label": "等角 2.5D 视图"},
    }

    oxe_model = MachineModelConfig(
        model_id="TEL-DRM-UNIT",
        model_name="TEL DRM UNITY 刻蚀机",
        vendor="TEL",
        process_type="ETCH",
        version="1.0",
        view_mode="isometric",
        description="OXE 刻蚀机 2.5D 等角视图，匹配 OXE_2D.html 的 Canvas 渲染布局",
        views_config_json=json.dumps(oxe_views, ensure_ascii=False),
        parts_config_json=json.dumps(oxe_parts, ensure_ascii=False),
        state_mapping_json=json.dumps(oxe_states, ensure_ascii=False),
        hotspots_config_json=json.dumps(oxe_hotspots, ensure_ascii=False),
        created_at=now,
        updated_at=now,
    )
    db.add(oxe_model)

    generic_parts = [
        {"part_id": "main_body", "part_name": "机身主体", "part_type": "structure",
         "view_3d": {"type": "box", "size": [4, 3, 3], "position": [0, 1.5, 0], "color": "#374151"}},
        {"part_id": "top_section", "part_name": "顶部", "part_type": "structure",
         "view_3d": {"type": "box", "size": [3.5, 2.5, 1], "position": [0, 4.25, 0], "color": "#1f2937"}},
        {"part_id": "status_light", "part_name": "状态灯", "part_type": "indicator",
         "view_3d": {"type": "cylinder", "size": [0.15, 0.15, 0.4], "position": [0, 5.7, 0], "color": "#22c55e"},
         "animated": True},
    ]

    generic_states = [
        {"state_id": "idle", "state_name": "待机", "color": "#9ca3af",
         "part_overrides": [{"part_id": "status_light", "color": "#9ca3af"}]},
        {"state_id": "run", "state_name": "运行", "color": "#22c55e",
         "part_overrides": [{"part_id": "status_light", "color": "#22c55e"}]},
        {"state_id": "error", "state_name": "故障", "color": "#ef4444",
         "part_overrides": [{"part_id": "status_light", "color": "#ef4444", "pulse": True}]},
        {"state_id": "maint", "state_name": "维护", "color": "#3b82f6",
         "part_overrides": [{"part_id": "status_light", "color": "#3b82f6"}]},
    ]

    generic_views = {
        "view_3d": {"type": "threejs", "model_source": "procedural",
                    "default_camera": {"position": [7, 5, 8], "target": [0, 1.8, 0]}},
    }

    generic_model = MachineModelConfig(
        model_id="GENERIC-ETCH",
        model_name="通用刻蚀机 (默认)",
        vendor="Generic",
        process_type="ETCH",
        version="1.0",
        view_mode="threejs",
        description="通用刻蚀机模型，用于未配置专用型号的机台",
        views_config_json=json.dumps(generic_views, ensure_ascii=False),
        parts_config_json=json.dumps(generic_parts, ensure_ascii=False),
        state_mapping_json=json.dumps(generic_states, ensure_ascii=False),
        hotspots_config_json=json.dumps([], ensure_ascii=False),
        created_at=now,
        updated_at=now,
    )
    db.add(generic_model)

    vpo_mappings = [
        {
            "mapping_id": "pod_attach",
            "description": "POD 穿入",
            "trigger_event_type": "POD_ATTACH",
            "trigger_event_code": "",
            "trigger_condition": {},
            "action_sequence": [
                {"step": 1, "part_id": "pod", "action": "move_linear",
                 "params": {"from": [0, -600, 200], "to": [0, -300, 200], "duration": 2.0, "easing": "easeInOut"}},
                {"step": 2, "part_id": "pod", "action": "move_linear",
                 "params": {"from": [0, -300, 200], "to": [0, -100, 300], "duration": 1.5, "easing": "easeInOut"}, "wait_for_step": 1},
            ],
            "rollback_event_type": "POD_DETACH",
            "rollback_event_code": "",
        },
        {
            "mapping_id": "pod_detach",
            "description": "POD 脱出",
            "trigger_event_type": "POD_DETACH",
            "trigger_event_code": "",
            "trigger_condition": {},
            "action_sequence": [
                {"step": 1, "part_id": "pod", "action": "move_linear",
                 "params": {"from": [0, -100, 300], "to": [0, -300, 200], "duration": 1.5, "easing": "easeInOut"}},
                {"step": 2, "part_id": "pod", "action": "move_linear",
                 "params": {"from": [0, -300, 200], "to": [0, -600, 200], "duration": 2.0, "easing": "easeInOut"}, "wait_for_step": 1},
            ],
            "rollback_event_type": "POD_ATTACH",
            "rollback_event_code": "",
        },
    ]

    for mp in vpo_mappings:
        db.add(EventActionMapping(
            model_id="PODOPENER-2200",
            mapping_id=mp["mapping_id"],
            description=mp["description"],
            trigger_event_type=mp["trigger_event_type"],
            trigger_event_code=mp["trigger_event_code"],
            trigger_condition_json=json.dumps(mp["trigger_condition"], ensure_ascii=False),
            action_sequence_json=json.dumps(mp["action_sequence"], ensure_ascii=False),
            rollback_event_type=mp["rollback_event_type"],
            rollback_event_code=mp["rollback_event_code"],
            created_at=now,
            updated_at=now,
        ))

    oxe_mappings = [
        {
            "mapping_id": "wafer_load_lp_to_chamber",
            "description": "晶圆装载：Load Port → EFEM → 工艺腔",
            "trigger_event_type": "TRANSFER",
            "trigger_event_code": "WaferLoad",
            "trigger_condition": {"from": "loadport", "to": "chamber"},
            "action_sequence": [
                {"step": 1, "part_id": "wafer", "action": "move_linear",
                 "params": {"from": [-285, -80, 280], "to": [-150, 0, 280], "duration": 1.5, "easing": "easeInOut"}},
                {"step": 2, "part_id": "efem_robot", "action": "rotate",
                 "params": {"axis": "z", "angle": 90, "duration": 1.0, "easing": "easeInOut"}, "wait_for_step": 1},
                {"step": 3, "part_id": "wafer", "action": "move_linear",
                 "params": {"from": [-150, 0, 280], "to": [120, 0, 280], "duration": 2.0, "easing": "easeInOut"}, "wait_for_step": 2},
                {"step": 4, "part_id": "vtm_robot", "action": "rotate",
                 "params": {"axis": "z", "angle": -45, "duration": 1.0, "easing": "easeInOut"}, "wait_for_step": 3},
                {"step": 5, "part_id": "wafer", "action": "move_linear",
                 "params": {"from": [120, 0, 280], "to": [250, -150, 280], "duration": 1.5, "easing": "easeInOut"}, "wait_for_step": 4},
            ],
            "rollback_event_type": "TRANSFER",
            "rollback_event_code": "WaferUnload",
        },
    ]

    for mp in oxe_mappings:
        db.add(EventActionMapping(
            model_id="TEL-DRM-UNIT",
            mapping_id=mp["mapping_id"],
            description=mp["description"],
            trigger_event_type=mp["trigger_event_type"],
            trigger_event_code=mp["trigger_event_code"],
            trigger_condition_json=json.dumps(mp["trigger_condition"], ensure_ascii=False),
            action_sequence_json=json.dumps(mp["action_sequence"], ensure_ascii=False),
            rollback_event_type=mp["rollback_event_type"],
            rollback_event_code=mp["rollback_event_code"],
            created_at=now,
            updated_at=now,
        ))

    db.commit()


def create_dt_event_raw_samples(db: Session):
    """从alarm.docx样例生成DT_EVENT_RAW模拟数据（VPO-01机台真实事件模板）"""
    existing = db.query(DT_EVENT_RAW).count()
    if existing > 0:
        print(f"[Seed] DT_EVENT_RAW已存在 ({existing}条)，跳过")
        return

    # VFEI事件样例数据（基于alarm.docx解析的真实模板）
    base_time = datetime(2026, 6, 14, 7, 50, 0)
    events = []

    # Alarm事件模板
    alarm_templates = [
        {"alarm_id": "9003", "alarm_text": "測机時間快到了!LAST_TEST is out of Warning SPEC :: LastTime:2026-06-12 07:42:44", "severity": "warn"},
        {"alarm_id": "9004", "alarm_text": "超過測机限Run 產品批數, 需等待測机結果! :: LAST_TEST(NULL). 目前已Run批數(0).", "severity": "crit"},
        {"alarm_id": "20011", "alarm_text": "Pod DirtyBit <> Cassette DirtyBit! :: PodDirtyBit:0CassetteDirtyBit=2", "severity": "warn"},
        {"alarm_id": "0201", "alarm_text": "SERIAL_ID=328201,電池電壓异常！ :: 此POD即將沒電，請盡快送至W/S處理，謝謝！", "severity": "crit"},
        {"alarm_id": "0411", "alarm_text": "此POD尚余3天到清洗日期，請盡速更換新POD, Pod Clean Due Date=2026-06-18 :: No Alarm Description", "severity": "warn"},
    ]

    # 生成连续多天的alarm事件
    tid = 21000
    for day_offset in range(5):
        day_base = base_time + timedelta(days=day_offset)
        for i in range(20):
            tpl = alarm_templates[i % len(alarm_templates)]
            ts = day_base + timedelta(minutes=i * 15 + random.randint(0, 10))
            lot_ids = ["V3NL8", "V394K", "PG0R3", "V39S5", "V3QS6", None]
            lot_id = lot_ids[i % len(lot_ids)]
            payload = {
                "lot_id": lot_id or "NULL",
                "run_mode": "NULL",
                "event_type": "VFEI",
                "event_name": "EC_ALARM_REPORT",
                "port_id": "1",
                "cassette_id": f"EMPTY{random.randint(10000,99999)}{random.choice(['A','B'])}",
                "chamber_id": "1",
                "smif_id": "1",
                "batch_id": lot_id or "NULL",
                "unit_id": "1",
                "slot_id": "NULL",
                "alarm_id": tpl["alarm_id"],
                "alarm_text": tpl["alarm_text"],
            }
            events.append(DT_EVENT_RAW(
                raw_id=f"RV-{tid}",
                tool_id="PODOPENER-1",
                source_system="RV",
                source_message_id=f"TID.{tid}",
                received_ts_utc=ts.isoformat(),
                event_ts_utc=ts.isoformat(),
                payload_json=json.dumps(payload, ensure_ascii=False),
                parse_status="PARSED",
                error_message=None,
            ))
            tid += 1

    # 生成DETACH_POD_PLACE事件（Pod放置/分离）
    lot_list = ["PG0R3", "V39S5", "V3NL8", "V394K", "V3QS6"]
    for i, lot_id in enumerate(lot_list):
        ts = base_time + timedelta(hours=i * 3 + 1)
        payload = {
            "lot_id": lot_id,
            "run_mode": "UNPACK",
            "event_type": "VFEI",
            "event_name": "DETACH_POD_PLACE",
            "port_id": "1",
            "cassette_id": f"{random.randint(10000,99999)}{random.choice(['A','B','P','S','K'])}",
            "chamber_id": "1",
            "smif_id": "1",
            "batch_id": lot_id,
            "unit_id": "1",
            "slot_id": "NULL",
            "alarm_id": "NULL",
            "alarm_text": "NULL",
        }
        events.append(DT_EVENT_RAW(
                raw_id=f"RV-{tid}",
                tool_id="PODOPENER-1",
            source_system="RV",
            source_message_id=f"TID.{tid}",
            received_ts_utc=ts.isoformat(),
            event_ts_utc=ts.isoformat(),
            payload_json=json.dumps(payload, ensure_ascii=False),
            parse_status="PARSED",
            error_message=None,
        ))
        tid += 1

    # 生成OXE-01、OXE-09、OXE-11、OXE-15刻蚀机的丰富VFEI事件（支持回放）
    oxe_machines = ["OXE-01", "OXE-09", "OXE-11", "OXE-15"]
    for m_idx, m_id in enumerate(oxe_machines):
        lot_id = f"LOT{100000 + m_idx * 1000 + random.randint(100, 999)}"
        recipe = f"REC-ETCH-{chr(65 + m_idx % 2)}"
        day_base = base_time + timedelta(days=m_idx % 3)
        
        # 生成一个完整的Lot处理流程（约2小时）
        flow_events = [
            ("POD_PLACED", 0, "pod", {"port": "1", "smif_id": "SMIF1", "cst_id": f"CS{random.randint(10000,99999)}K", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running"}),
            ("LOCK_PORT_COMPLETED", 1, "pod", {"port": "1", "smif_id": "SMIF1", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running"}),
            ("MVIN", 20, "pod", {"port": "1", "smif_id": "SMIF1", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running"}),
            ("DOOR_OPEN", 180, "process", {"port": "1", "smif_id": "SMIF1", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running"}),
            ("LOAD_CYCLE_STARTED", 181, "process", {"port": "1", "smif_id": "SMIF1", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running", "duration_sec": 60}),
            ("LOAD_CYCLE_COMPLETED", 240, "process", {"port": "1", "smif_id": "SMIF1", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running"}),
            ("DOOR_CLOSE", 258, "process", {"port": "1", "smif_id": "SMIF1", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running"}),
            ("StartMapping_LEFT", 259, "process", {"port": "1", "smif_id": "SMIF1", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running", "duration_sec": 120}),
            ("EndMapping", 380, "process", {"port_id": "PORT1", "WAFERMAP": "1111111111111111111111111", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running"}),
            ("Start", 380, "process", {"chamber_id": "CHAMBER_A", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running"}),
            ("PS", 382, "process", {"chamber_id": "CHAMBER_A", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running"}),
        ]
        
        # 添加25片晶圆的WaferLoaded/WaferUnloaded事件
        for wafer_idx in range(25):
            load_offset = 430 + wafer_idx * 300
            unload_offset = load_offset + 280
            flow_events.append((
                "WaferLoaded", load_offset, "process",
                {"port_id": "PORT1", "chamber_id": "CHAMBER_A", "wafer_id": wafer_idx + 1, "slot": wafer_idx + 1,
                 "lot_id": lot_id, "recipe": recipe, "machine_state": "Running", "duration_sec": 6}
            ))
            flow_events.append((
                "WaferUnloaded", unload_offset, "process",
                {"port_id": "PORT1", "chamber_id": "CHAMBER_A", "wafer_id": wafer_idx + 1, "slot": wafer_idx + 1,
                 "lot_id": lot_id, "recipe": recipe, "machine_state": "Running", "duration_sec": 5}
            ))
        
        # Lot结束事件
        flow_events.extend([
            ("LotEnd", 430 + 25 * 300 + 60, "process", {"port": "1", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running", "QTY": 25}),
            ("JobEnd", 430 + 25 * 300 + 61, "process", {"port": "1", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running"}),
            ("PE", 430 + 25 * 300 + 180, "process", {"chamber_id": "CHAMBER_A", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running"}),
            ("ReadyToUnload", 430 + 25 * 300 + 181, "process", {"chamber_id": "CHAMBER_A", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running", "duration_sec": 10}),
            ("DOOR_OPEN", 430 + 25 * 300 + 182, "process", {"port": "1", "smif_id": "SMIF1", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running"}),
            ("UNLOAD_CYCLE_COMPLETED", 430 + 25 * 300 + 183, "process", {"port": "1", "smif_id": "SMIF1", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running", "duration_sec": 60}),
            ("DOOR_CLOSE", 430 + 25 * 300 + 244, "process", {"port": "1", "smif_id": "SMIF1", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running"}),
            ("MVOU", 430 + 25 * 300 + 245, "pod", {"port": "1", "smif_id": "SMIF1", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running"}),
            ("UNLOCK_PORT_COMPLETED", 430 + 25 * 300 + 246, "pod", {"port": "1", "smif_id": "SMIF1", "lot_id": lot_id, "recipe": recipe, "machine_state": "Running"}),
            ("POD_REMOVED", 430 + 25 * 300 + 255, "pod", {"port": "1", "smif_id": "SMIF1", "lot_id": lot_id, "recipe": recipe, "machine_state": "Idle"}),
        ])
        
        # 生成事件
        for ename, offset_min, cat, extra in flow_events:
            ts = day_base + timedelta(minutes=offset_min)
            payload = {
                "event_type": "VFEI",
                "event_name": ename,
                "machine_id": m_id,
                **extra
            }
            events.append(DT_EVENT_RAW(
                raw_id=f"RV-{tid}",
                tool_id=m_id,
                source_system="RV",
                source_message_id=f"TID.{tid}",
                received_ts_utc=ts.isoformat(),
                event_ts_utc=ts.isoformat(),
                payload_json=json.dumps(payload, ensure_ascii=False),
                parse_status="PARSED",
                error_message=None,
            ))
            tid += 1
        
        # 添加一些告警事件
        for alarm_i in range(5):
            ts = day_base + timedelta(minutes=60 + alarm_i * 45)
            alarm_templates = [
                ("9003", "測机時間快到了!LAST_TEST is out of Warning SPEC", "warn"),
                ("20011", "Pod DirtyBit <> Cassette DirtyBit!", "warn"),
                ("0411", "此POD尚余3天到清洗日期", "warn"),
            ]
            aid, atxt, sev = alarm_templates[alarm_i % len(alarm_templates)]
            payload = {
                "event_type": "VFEI",
                "event_name": "EC_ALARM_REPORT",
                "machine_id": m_id,
                "lot_id": lot_id,
                "port_id": "1",
                "chamber_id": "1",
                "alarm_id": aid,
                "alarm_text": atxt,
                "severity": sev,
            }
            events.append(DT_EVENT_RAW(
                raw_id=f"RV-{tid}",
                tool_id=m_id,
                source_system="RV",
                source_message_id=f"TID.{tid}",
                received_ts_utc=ts.isoformat(),
                event_ts_utc=ts.isoformat(),
                payload_json=json.dumps(payload, ensure_ascii=False),
                parse_status="PARSED",
                error_message=None,
            ))
            tid += 1

    for ev in events:
        db.add(ev)
    db.commit()
    print(f"[Seed] DT_EVENT_RAW样例数据生成完成 ({len(events)}条)")


def init_seed_data(db: Session):
    print("[Seed] 开始生成模拟数据...")

    create_floors(db)
    print("[Seed] 楼层数据生成完成")

    create_floor_areas(db)
    print("[Seed] 楼层区域数据生成完成")

    machines = create_machines(db)
    print("[Seed] 机台数据生成完成")

    create_recipes(db, machines)
    print("[Seed] 配方数据生成完成")

    create_lots(db, machines)
    print("[Seed] Lot数据生成完成")

    create_alarms(db, machines)
    print("[Seed] 告警数据生成完成")

    create_chamber_snapshots(db, machines)
    print("[Seed] 腔体快照生成完成")

    create_oht_positions(db)
    print("[Seed] OHT位置数据生成完成")

    seed_ods_data(db, machines)
    print("[Seed] ODS数据生成完成")

    create_machine_model_configs(db)
    print("[Seed] 机台型号配置数据生成完成")

    create_dt_event_raw_samples(db)

    create_roles_and_permissions(db)
    print("[Seed] 角色权限数据生成完成")

    create_users(db)
    print("[Seed] 用户数据生成完成")

    create_machine_tool_mappings(db)
    print("[Seed] 机台Tool映射数据生成完成")

    print("[Seed] 所有模拟数据生成完成！")


def create_roles_and_permissions(db: Session):
    """创建角色和权限数据"""
    existing = db.query(Role).count()
    if existing > 0:
        print(f"[Seed] 角色权限已存在 ({existing} 个)，跳过")
        return

    roles = [
        {"id": "admin", "name": "管理员", "description": "系统管理员，拥有所有权限"},
        {"id": "engineer", "name": "工程师", "description": "设备工程师，可查看和编辑模型"},
        {"id": "user", "name": "普通用户", "description": "普通用户，只能使用基础功能"},
    ]

    for r in roles:
        db.add(Role(id=r["id"], name=r["name"], description=r["description"]))

    permissions = [
        {"id": "machine_view", "name": "查看机台", "description": "查看机台状态和模型", "resource": "machine", "action": "view"},
        {"id": "machine_edit", "name": "编辑机台", "description": "编辑机台配置和模型", "resource": "machine", "action": "edit"},
        {"id": "floor_view", "name": "查看平面图", "description": "查看楼层平面图", "resource": "floor", "action": "view"},
        {"id": "floor_edit", "name": "编辑平面图", "description": "编辑楼层平面图", "resource": "floor", "action": "edit"},
        {"id": "model_view", "name": "查看模型", "description": "查看机台3D/2D模型", "resource": "model", "action": "view"},
        {"id": "model_edit", "name": "编辑模型", "description": "编辑机台模型配置", "resource": "model", "action": "edit"},
        {"id": "history_view", "name": "查看历史", "description": "查看历史数据和回放", "resource": "history", "action": "view"},
        {"id": "ai_analysis", "name": "AI分析", "description": "使用AI分析功能", "resource": "ai", "action": "use"},
        {"id": "alarm_view", "name": "查看告警", "description": "查看告警信息", "resource": "alarm", "action": "view"},
        {"id": "user_manage", "name": "用户管理", "description": "管理用户和权限", "resource": "user", "action": "manage"},
    ]

    for p in permissions:
        db.add(Permission(id=p["id"], name=p["name"], description=p["description"],
                          resource=p["resource"], action=p["action"]))

    role_permissions = [
        ("admin", ["machine_view", "machine_edit", "floor_view", "floor_edit", 
                   "model_view", "model_edit", "history_view", "ai_analysis", 
                   "alarm_view", "user_manage"]),
        ("engineer", ["machine_view", "machine_edit", "floor_view", "floor_edit", 
                      "model_view", "model_edit", "history_view", "ai_analysis", "alarm_view"]),
        ("user", ["machine_view", "floor_view", "model_view", "history_view", "alarm_view"]),
    ]

    for role_id, perm_ids in role_permissions:
        for perm_id in perm_ids:
            db.add(RolePermission(role_id=role_id, permission_id=perm_id))

    db.commit()


def create_users(db: Session):
    """创建默认用户"""
    existing = db.query(User).count()
    if existing > 0:
        print(f"[Seed] 用户已存在 ({existing} 个)，跳过")
        return

    users = [
        {
            "id": str(uuid.uuid4()),
            "username": "admin",
            "display_name": "管理员",
            "email": "admin@fab-twin.com",
            "department": "IT",
            "role": "admin",
            "windows_sid": "S-1-5-21-0000000000-0000000000-0000000001",
        },
        {
            "id": str(uuid.uuid4()),
            "username": "engineer",
            "display_name": "设备工程师",
            "email": "engineer@fab-twin.com",
            "department": "设备部",
            "role": "engineer",
            "windows_sid": "S-1-5-21-0000000000-0000000000-0000000002",
        },
        {
            "id": str(uuid.uuid4()),
            "username": "user",
            "display_name": "普通用户",
            "email": "user@fab-twin.com",
            "department": "生产部",
            "role": "user",
            "windows_sid": "S-1-5-21-0000000000-0000000000-0000000003",
        },
        {
            "id": str(uuid.uuid4()),
            "username": "default",
            "display_name": "默认用户",
            "email": "",
            "department": "",
            "role": "user",
            "windows_sid": "S-1-5-21-0000000000-0000000000-0000000004",
        },
    ]

    now = datetime.now().isoformat()
    for u in users:
        db.add(User(
            id=u["id"],
            username=u["username"],
            display_name=u["display_name"],
            email=u["email"],
            department=u["department"],
            role=u["role"],
            windows_sid=u["windows_sid"],
            last_login_at=now,
            created_at=now,
            updated_at=now,
        ))

    db.commit()


def create_machine_tool_mappings(db: Session):
    """创建机台与Tool ID映射（VPO→PODOPENER）"""
    existing = db.query(MachineToolMapping).count()
    if existing > 0:
        print(f"[Seed] 机台映射已存在 ({existing} 个)，跳过")
        return

    mappings = [
        {"machine_id": "VPO-01", "tool_id": "PODOPENER-1", "description": "VPO-01对应Tool ID PODOPENER-1", "is_primary": True},
    ]

    for m in mappings:
        db.add(MachineToolMapping(
            machine_id=m["machine_id"],
            tool_id=m["tool_id"],
            description=m["description"],
            is_primary=m["is_primary"],
        ))

    db.commit()
