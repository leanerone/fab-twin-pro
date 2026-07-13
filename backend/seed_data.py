"""模拟数据生成：机台、Lot、事件、告警、ODS数据等"""
import random
import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models import Machine, Lot, Recipe, ChamberSnapshot, OHTPosition, Floor, FloorArea
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
        {"id": "T01", "name": "刻蚀机 T01", "line": 1, "floor": 3, "has_smif": False, "x_pos": -8, "y_pos": 0, "floor_x": 5, "floor_y": 20},
        {"id": "T02", "name": "刻蚀机 T02", "line": 1, "floor": 3, "has_smif": False, "x_pos": -4, "y_pos": 0, "floor_x": 12, "floor_y": 20},
        {"id": "T03", "name": "刻蚀机 T03", "line": 1, "floor": 3, "has_smif": False, "x_pos": 0, "y_pos": 0, "floor_x": 19, "floor_y": 20},
        {"id": "T04", "name": "刻蚀机 T04", "line": 1, "floor": 3, "has_smif": False, "x_pos": 4, "y_pos": 0, "floor_x": 26, "floor_y": 20},
        {"id": "T05", "name": "刻蚀机 T05", "line": 1, "floor": 3, "has_smif": False, "x_pos": 8, "y_pos": 0, "floor_x": 33, "floor_y": 20},
        {"id": "T06", "name": "刻蚀机 T06", "line": 1, "floor": 3, "has_smif": False, "x_pos": 12, "y_pos": 0, "floor_x": 5, "floor_y": 55},
        {"id": "T07", "name": "刻蚀机 T07", "line": 1, "floor": 3, "has_smif": False, "x_pos": -8, "y_pos": 3, "floor_x": 12, "floor_y": 55},
        {"id": "T08", "name": "刻蚀机 T08", "line": 1, "floor": 3, "has_smif": False, "x_pos": -4, "y_pos": 3, "floor_x": 19, "floor_y": 55},
        {"id": "T09", "name": "刻蚀机 T09", "line": 1, "floor": 3, "has_smif": False, "x_pos": 0, "y_pos": 3, "floor_x": 26, "floor_y": 55},
        {"id": "T10", "name": "刻蚀机 T10", "line": 1, "floor": 3, "has_smif": False, "x_pos": 4, "y_pos": 3, "floor_x": 33, "floor_y": 55},
        # Line 2 (有SMIF)
        {"id": "T11", "name": "刻蚀机 T11", "line": 2, "floor": 3, "has_smif": True, "x_pos": -8, "y_pos": -3, "floor_x": 60, "floor_y": 20},
        {"id": "T12", "name": "刻蚀机 T12", "line": 2, "floor": 3, "has_smif": True, "x_pos": -4, "y_pos": -3, "floor_x": 67, "floor_y": 20},
        {"id": "T13", "name": "刻蚀机 T13", "line": 2, "floor": 3, "has_smif": True, "x_pos": 0, "y_pos": -3, "floor_x": 74, "floor_y": 20},
        {"id": "T14", "name": "刻蚀机 T14", "line": 2, "floor": 3, "has_smif": True, "x_pos": 4, "y_pos": -3, "floor_x": 81, "floor_y": 20},
        {"id": "T15", "name": "刻蚀机 T15", "line": 2, "floor": 3, "has_smif": True, "x_pos": 8, "y_pos": -3, "floor_x": 88, "floor_y": 20},
        {"id": "T16", "name": "刻蚀机 T16", "line": 2, "floor": 3, "has_smif": True, "x_pos": 12, "y_pos": -3, "floor_x": 60, "floor_y": 55},
        {"id": "T17", "name": "刻蚀机 T17", "line": 2, "floor": 3, "has_smif": True, "x_pos": -8, "y_pos": -6, "floor_x": 67, "floor_y": 55},
        {"id": "T18", "name": "刻蚀机 T18", "line": 2, "floor": 3, "has_smif": True, "x_pos": -4, "y_pos": -6, "floor_x": 74, "floor_y": 55},
        {"id": "T19", "name": "刻蚀机 T19", "line": 2, "floor": 3, "has_smif": True, "x_pos": 0, "y_pos": -6, "floor_x": 81, "floor_y": 55},
        {"id": "T20", "name": "刻蚀机 T20", "line": 2, "floor": 3, "has_smif": True, "x_pos": 4, "y_pos": -6, "floor_x": 88, "floor_y": 55},
        {"id": "STK-3F", "name": "STK传输机 3F", "line": 1, "floor": 3, "has_smif": False, "x_pos": 0, "y_pos": 0, "floor_x": 47, "floor_y": 38, "process_type": "STK"},

        # === 4F: 刻蚀区扩展 ===
        {"id": "T51", "name": "刻蚀机 T51", "line": 1, "floor": 4, "has_smif": False, "x_pos": -8, "y_pos": 0, "floor_x": 10, "floor_y": 20},
        {"id": "T52", "name": "刻蚀机 T52", "line": 1, "floor": 4, "has_smif": False, "x_pos": -4, "y_pos": 0, "floor_x": 25, "floor_y": 20},
        {"id": "T53", "name": "刻蚀机 T53", "line": 1, "floor": 4, "has_smif": False, "x_pos": 0, "y_pos": 0, "floor_x": 35, "floor_y": 50},
        {"id": "T61", "name": "刻蚀机 T61", "line": 2, "floor": 4, "has_smif": True, "x_pos": 4, "y_pos": 0, "floor_x": 60, "floor_y": 20},
        {"id": "T62", "name": "刻蚀机 T62", "line": 2, "floor": 4, "has_smif": True, "x_pos": 8, "y_pos": 0, "floor_x": 75, "floor_y": 20},
        {"id": "T63", "name": "刻蚀机 T63", "line": 2, "floor": 4, "has_smif": True, "x_pos": 12, "y_pos": 0, "floor_x": 85, "floor_y": 45},
        {"id": "T64", "name": "刻蚀机 T64", "line": 2, "floor": 4, "has_smif": True, "x_pos": 12, "y_pos": 3, "floor_x": 55, "floor_y": 50},
        {"id": "STK-4F", "name": "STK传输机 4F", "line": 1, "floor": 4, "has_smif": False, "x_pos": 0, "y_pos": 0, "floor_x": 47, "floor_y": 35, "process_type": "STK"},
    ]

    machines = []
    for m in machines_data:
        ptype = m.get("process_type", "ETCH") if m.get("process_type") else "ETCH"
        machine = Machine(
            id=m["id"],
            model="TEL DRM UNITY" if ptype == "ETCH" else ptype,
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
    today = datetime.now().strftime("%Y-%m-%d")
    for m in machines:
        lot_count = 5 + random.randint(0, 3)
        start_time = datetime.fromisoformat(f"{today}T08:00:00")

        for i in range(lot_count):
            lot_id = f"LOT{random.randint(100000, 999999)}"
            cycle_duration = (20 + random.random() * 8) * 60
            end_time = start_time + timedelta(seconds=cycle_duration)

            status_roll = random.random()
            status = "done"
            if status_roll > 0.85:
                status = "hold"
            elif status_roll > 0.7:
                status = "run"
            elif status_roll > 0.6:
                status = "pending"

            lot = Lot(
                id=lot_id,
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
                target_machine_id=f"ETCH-20{random.randint(1, 3)}" if random.random() > 0.3 else None,
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

    create_chamber_snapshots(db, machines)
    print("[Seed] 腔体快照生成完成")

    create_oht_positions(db)
    print("[Seed] OHT位置数据生成完成")

    seed_ods_data(db, machines)
    print("[Seed] ODS数据生成完成")

    print("[Seed] 所有模拟数据生成完成！")
