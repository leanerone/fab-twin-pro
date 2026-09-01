"""楼层管理 API"""
import json
from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Floor, FloorArea, Machine, Track, Vehicle
from routers.auth import get_current_user, check_permission
from models import User

router = APIRouter(prefix="/api/floors", tags=["floors"])


def require_floor_edit(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """要求当前用户拥有 floor_edit 权限"""
    if not check_permission(user, "floor_edit", db):
        raise HTTPException(status_code=403, detail="无权限：需要 floor_edit 权限")
    return user


@router.get("", response_model=List[dict])
def list_floors(db: Session = Depends(get_db)):
    """获取所有楼层列表"""
    floors = db.query(Floor).order_by(Floor.id).all()
    result = []
    for f in floors:
        machine_count = db.query(Machine).filter(Machine.floor == f.id).count()
        result.append({
            "id": f.id,
            "name": f.name,
            "description": f.description,
            "machine_count": machine_count,
            "width": f.width,
            "height": f.height,
        })
    return result


@router.get("/{floor_id}", response_model=dict)
def get_floor(floor_id: int, db: Session = Depends(get_db)):
    """获取楼层详情（含区域、机台、轨迹、天车）"""
    floor = db.query(Floor).filter(Floor.id == floor_id).first()
    if not floor:
        raise HTTPException(status_code=404, detail="楼层不存在")
    
    areas = db.query(FloorArea).filter(FloorArea.floor_id == floor_id).order_by(
        func.coalesce(FloorArea.display_order, 0).asc(), FloorArea.id.asc()
    ).all()
    machines = db.query(Machine).filter(Machine.floor == floor_id).order_by(
        func.coalesce(Machine.display_order, 0).asc(), Machine.id.asc()
    ).all()
    tracks = db.query(Track).filter(Track.floor_id == floor_id).all()
    vehicles = db.query(Vehicle).filter(Vehicle.floor_id == floor_id).all()
    
    return {
        "id": floor.id,
        "name": floor.name,
        "description": floor.description,
        "width": floor.width,
        "height": floor.height,
        "areas": [{
            "id": a.id,
            "name": a.name,
            "area_type": a.area_type,
            "x_pos": a.x_pos,
            "y_pos": a.y_pos,
            "width": a.width,
            "height": a.height,
            "color": a.color,
            "description": a.description,
            "display_order": a.display_order or 0,
        } for a in areas],
        "machines": [{
            "id": m.id,
            "name": m.name,
            "model": m.model,
            "state": m.state,
            "process_type": m.process_type,
            "alarm_count": m.alarm_count,
            "floor_x": m.floor_x,
            "floor_y": m.floor_y,
            "display_order": m.display_order or 0,
        } for m in machines],
        "tracks": [{
            "id": t.id,
            "name": t.name,
            "track_type": t.track_type,
            "points": json.loads(t.points_json) if t.points_json else [],
            "color": t.color,
            "speed": t.speed,
        } for t in tracks],
        "vehicles": [{
            "id": v.id,
            "name": v.name,
            "vehicle_type": v.vehicle_type,
            "track_id": v.track_id,
            "state": v.state,
            "progress": v.progress,
            "lot_id": v.lot_id,
            "target_machine_id": v.target_machine_id,
            "speed": v.speed,
        } for v in vehicles],
    }


@router.get("/{floor_id}/machines", response_model=List[dict])
def get_floor_machines(floor_id: int, db: Session = Depends(get_db)):
    """获取楼层机台列表（含位置信息）"""
    machines = db.query(Machine).filter(Machine.floor == floor_id).all()
    return [{
        "id": m.id,
        "name": m.name,
        "model": m.model,
        "state": m.state,
        "process_type": m.process_type,
        "alarm_count": m.alarm_count,
        "floor_x": m.floor_x,
        "floor_y": m.floor_y,
        "line": m.line,
        "has_smif": m.has_smif,
    } for m in machines]


@router.post("/{floor_id}/areas")
def add_area(floor_id: int, area: dict, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """添加楼层区域"""
    floor = db.query(Floor).filter(Floor.id == floor_id).first()
    if not floor:
        raise HTTPException(status_code=404, detail="楼层不存在")

    # Oracle 表无 identity 列，需手动生成 ID
    max_id = db.query(func.max(FloorArea.id)).scalar() or 0

    new_area = FloorArea(
        id=max_id + 1,
        floor_id=floor_id,
        name=area.get("name"),
        area_type=area.get("area_type", "equipment"),
        x_pos=area.get("x_pos", 0),
        y_pos=area.get("y_pos", 0),
        width=area.get("width", 10),
        height=area.get("height", 10),
        color=area.get("color", "#1e293b"),
        description=area.get("description"),
        display_order=area.get("display_order"),
    )
    db.add(new_area)
    db.commit()
    return {"id": new_area.id, "name": new_area.name}


@router.put("/{floor_id}/areas/{area_id}")
def update_area(floor_id: int, area_id: int, data: dict, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """更新楼层区域位置和尺寸"""
    area = db.query(FloorArea).filter(FloorArea.id == area_id, FloorArea.floor_id == floor_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="区域不存在")
    
    if "x_pos" in data:
        area.x_pos = data["x_pos"]
    if "y_pos" in data:
        area.y_pos = data["y_pos"]
    if "width" in data:
        area.width = data["width"]
    if "height" in data:
        area.height = data["height"]
    if "name" in data:
        area.name = data["name"]
    if "color" in data:
        area.color = data["color"]
    if "display_order" in data:
        try:
            area.display_order = int(data["display_order"])
        except Exception:
            pass

    db.commit()
    return {"message": "区域更新成功"}


@router.post("/{floor_id}/machines")
def add_machine(floor_id: int, machine: dict, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """添加新机台到楼层

    支持字段：
    - id: 机台ID（必填）
    - name: 名称（可选，默认同ID）
    - model: 模型ID，绑定 MachineModelConfig（可选）
    - process_type: 工艺类型（可选）
    - line: 产线（可选）
    - floor_x, floor_y: 地图位置（百分比）

    若机台ID已存在但未分配楼层（从平面图删除后），则重新分配到当前楼层，而非报错。
    """
    from models import MachineModelConfig

    floor = db.query(Floor).filter(Floor.id == floor_id).first()
    if not floor:
        raise HTTPException(status_code=404, detail="楼层不存在")

    machine_id = machine.get("id")
    if not machine_id:
        raise HTTPException(status_code=400, detail="机台ID不能为空")

    # 检查模型是否存在（新建和重新分配都校验）
    model_id = machine.get("model")
    if model_id:
        model_config = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == model_id).first()
        if not model_config:
            raise HTTPException(status_code=400, detail=f"模型 '{model_id}' 不存在，请先创建模型配置")

    existing = db.query(Machine).filter(Machine.id == machine_id).first()
    if existing:
        # 机台已存在：已分配到其它楼层 → 报错；未分配（删除后）→ 重新分配
        if existing.floor is not None and existing.floor != floor_id:
            raise HTTPException(
                status_code=409,
                detail=f"机台ID已存在且已分配到楼层 {existing.floor}，请先从该楼层移除",
            )
        existing.floor = floor_id
        existing.floor_x = machine.get("floor_x", existing.floor_x)
        existing.floor_y = machine.get("floor_y", existing.floor_y)
        if machine.get("name"):
            existing.name = machine["name"]
        if model_id:
            existing.model = model_id
        if machine.get("process_type"):
            existing.process_type = machine["process_type"]
        if machine.get("line") is not None:
            existing.line = machine["line"]
        db.commit()
        return {"id": existing.id, "name": existing.name, "model": existing.model, "message": "机台已重新添加到楼层"}

    new_machine = Machine(
        id=machine_id,
        model=model_id or "GENERIC-ETCH",
        name=machine.get("name", machine_id),
        line=machine.get("line", 1),
        floor=floor_id,
        chamber_count=machine.get("chamber_count", 4),
        process_type=machine.get("process_type", "ETCH"),
        state="idle",
        temp=22.0,
        pressure=1.0,
        gas_flow=0.0,
        rf_power=0.0,
        wafer_count=0,
        alarm_count=0,
        process_step=0,
        has_smif=machine.get("has_smif", False),
        updated_at=datetime.now().isoformat(),
        x_pos=0,
        y_pos=0,
        floor_x=machine.get("floor_x", 50),
        floor_y=machine.get("floor_y", 50),
    )
    db.add(new_machine)
    db.commit()
    return {"id": new_machine.id, "name": new_machine.name, "model": new_machine.model, "message": "机台添加成功"}


@router.delete("/{floor_id}/areas/{area_id}")
def delete_area(floor_id: int, area_id: int, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """删除楼层区域"""
    area = db.query(FloorArea).filter(FloorArea.id == area_id, FloorArea.floor_id == floor_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="区域不存在")
    db.delete(area)
    db.commit()
    return {"message": "区域删除成功"}


@router.delete("/{floor_id}/machines/{machine_id}")
def delete_machine(floor_id: int, machine_id: str, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """从楼层删除机台（仅清除楼层关联，不删除机台记录）"""
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if not machine:
        raise HTTPException(status_code=404, detail="机台不存在")
    machine.floor = None
    machine.floor_x = 0
    machine.floor_y = 0
    db.commit()
    return {"message": "机台已从楼层移除"}


@router.put("/{floor_id}/machines/{machine_id}/position")
def update_machine_position(floor_id: int, machine_id: str, position: dict, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """更新机台在楼层平面图上的位置"""
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if not machine:
        raise HTTPException(status_code=404, detail="机台不存在")
    
    machine.floor_x = position.get("x", machine.floor_x)
    machine.floor_y = position.get("y", machine.floor_y)
    machine.floor = floor_id
    db.commit()
    return {"message": "位置更新成功"}


@router.put("/{floor_id}/machines/{machine_id}")
def update_machine_info(floor_id: int, machine_id: str, data: dict, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """更新机台信息（名称/工艺类型/产线）"""
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
    if not machine:
        raise HTTPException(status_code=404, detail="机台不存在")

    if "name" in data and data["name"]:
        machine.name = data["name"]
    if "process_type" in data and data["process_type"]:
        machine.process_type = data["process_type"]
    if "line" in data and data["line"] is not None:
        machine.line = data["line"]
    db.commit()
    return {"id": machine.id, "name": machine.name, "process_type": machine.process_type, "line": machine.line, "message": "机台信息更新成功"}


# ================= D 批：区域/机台 批量复制 + 置顶置底 =================

@router.post("/{floor_id}/areas/batch-clone")
def batch_clone_areas(floor_id: int, data: dict, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """批量复制区域（每个 area_id 的副本：名称加后缀 _copy + 位置偏移 + 置顶 display_order）

    payload: { area_ids: [id,...], offset_x: 3, offset_y: 3 }
    返回: [ {id, name, x_pos, y_pos}, ... ] 新建的区域。
    """
    floor = db.query(Floor).filter(Floor.id == floor_id).first()
    if not floor:
        raise HTTPException(status_code=404, detail="楼层不存在")
    area_ids = data.get("area_ids", []) or []
    offset_x = float(data.get("offset_x", 3))
    offset_y = float(data.get("offset_y", 3))
    max_id = db.query(func.max(FloorArea.id)).scalar() or 0
    max_order = db.query(func.max(func.coalesce(FloorArea.display_order, 0))).filter(
        FloorArea.floor_id == floor_id
    ).scalar() or 0
    next_id = max_id + 1
    next_order = max_order + 1
    result = []
    for aid in area_ids:
        src = db.query(FloorArea).filter(FloorArea.id == int(aid)).first()
        if not src:
            continue
        nx = max(0.0, min(100.0, (src.x_pos or 0) + offset_x))
        ny = max(0.0, min(100.0, (src.y_pos or 0) + offset_y))
        nw = min(float(src.width or 10), 100 - nx)
        nh = min(float(src.height or 10), 100 - ny)
        if nw < 1: nw = min(float(src.width or 10), 100)
        if nh < 1: nh = min(float(src.height or 10), 100)
        new_name = f"{src.name or 'area'}_copy"
        clone = FloorArea(
            id=next_id,
            floor_id=floor_id,
            name=new_name,
            area_type=src.area_type,
            x_pos=nx, y_pos=ny, width=nw, height=nh,
            color=src.color,
            description=src.description,
            display_order=next_order,
        )
        db.add(clone)
        result.append({"id": next_id, "name": new_name, "x_pos": nx, "y_pos": ny})
        next_id += 1
        next_order += 1
    db.commit()
    return {"created": len(result), "items": result}


@router.post("/{floor_id}/machines/batch-clone")
def batch_clone_machines(floor_id: int, data: dict, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """批量复制机台（机台 ID 不允许重复：new_id="{old_id}_copy1/_copy2/..." 自动递增；若不存在则直接用 new_id 创建）

    payload: { machine_ids: ["ID1", ...], offset_x: 3, offset_y: 3 }
    返回: [ {id, name, floor_x, floor_y}, ... ]
    """
    floor = db.query(Floor).filter(Floor.id == floor_id).first()
    if not floor:
        raise HTTPException(status_code=404, detail="楼层不存在")
    machine_ids = data.get("machine_ids", []) or []
    offset_x = float(data.get("offset_x", 3))
    offset_y = float(data.get("offset_y", 3))
    max_order = db.query(func.max(func.coalesce(Machine.display_order, 0))).filter(
        Machine.floor == floor_id
    ).scalar() or 0
    next_order = max_order + 1
    result = []
    for mid in machine_ids:
        src = db.query(Machine).filter(Machine.id == mid).first()
        if not src:
            continue
        # 生成不重复的新 ID
        base = src.id
        idx = 1
        new_id = f"{base}_copy{idx}"
        while db.query(Machine.id).filter(Machine.id == new_id).first():
            idx += 1
            new_id = f"{base}_copy{idx}"
        nx = max(0.0, min(100.0, (src.floor_x or 0) + offset_x))
        ny = max(0.0, min(100.0, (src.floor_y or 0) + offset_y))
        clone = Machine(
            id=new_id,
            model=src.model,
            name=f"{src.name or src.id} (副本)",
            line=src.line,
            floor=floor_id,
            chamber_count=src.chamber_count,
            process_type=src.process_type,
            state="idle",
            floor_x=nx, floor_y=ny,
            display_order=next_order,
        )
        db.add(clone)
        result.append({"id": new_id, "name": clone.name, "floor_x": nx, "floor_y": ny})
        next_order += 1
    db.commit()
    return {"created": len(result), "items": result}


@router.post("/{floor_id}/areas/reorder")
def reorder_areas(floor_id: int, data: dict, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """区域图层重排：置顶/置底/前一层/后一层

    payload: { area_id: int, action: "top" | "bottom" | "up" | "down" }
    """
    action = data.get("action")
    area_id = int(data.get("area_id", 0))
    area = db.query(FloorArea).filter(FloorArea.id == area_id, FloorArea.floor_id == floor_id).first()
    if not area:
        raise HTTPException(status_code=404, detail="区域不存在")
    # 获取所有同楼层按 display_order+id 排序列表
    rows = db.query(FloorArea).filter(FloorArea.floor_id == floor_id).order_by(
        func.coalesce(FloorArea.display_order, 0).asc(), FloorArea.id.asc()
    ).all()
    try:
        idx = next(i for i, r in enumerate(rows) if r.id == area.id)
    except StopIteration:
        idx = -1
    if action == "bottom":
        # 置底：比当前最小 order 再小 1
        min_o = min((r.display_order or 0) for r in rows) if rows else 0
        area.display_order = min_o - 1
    elif action == "top":
        max_o = max((r.display_order or 0) for r in rows) if rows else 0
        area.display_order = max_o + 1
    elif action == "up" and idx > 0:
        # 与前一项交换
        prev = rows[idx - 1]
        prev_order = prev.display_order or 0
        cur_order = area.display_order or 0
        prev.display_order = cur_order
        area.display_order = prev_order
    elif action == "down" and 0 <= idx < len(rows) - 1:
        nxt = rows[idx + 1]
        nxt_order = nxt.display_order or 0
        cur_order = area.display_order or 0
        nxt.display_order = cur_order
        area.display_order = nxt_order
    db.commit()
    return {"message": "重排成功", "area_id": area.id, "action": action, "new_order": area.display_order}


@router.post("/{floor_id}/machines/reorder")
def reorder_machines(floor_id: int, data: dict, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """机台图层重排：置顶/置底/前一层/后一层

    payload: { machine_id: str, action: "top" | "bottom" | "up" | "down" }
    """
    action = data.get("action")
    machine_id = str(data.get("machine_id", ""))
    machine = db.query(Machine).filter(Machine.id == machine_id, Machine.floor == floor_id).first()
    if not machine:
        raise HTTPException(status_code=404, detail="机台不存在")
    rows = db.query(Machine).filter(Machine.floor == floor_id).order_by(
        func.coalesce(Machine.display_order, 0).asc(), Machine.id.asc()
    ).all()
    try:
        idx = next(i for i, r in enumerate(rows) if r.id == machine.id)
    except StopIteration:
        idx = -1
    if action == "bottom":
        min_o = min((r.display_order or 0) for r in rows) if rows else 0
        machine.display_order = min_o - 1
    elif action == "top":
        max_o = max((r.display_order or 0) for r in rows) if rows else 0
        machine.display_order = max_o + 1
    elif action == "up" and idx > 0:
        prev = rows[idx - 1]
        prev_order = prev.display_order or 0
        cur_order = machine.display_order or 0
        prev.display_order = cur_order
        machine.display_order = prev_order
    elif action == "down" and 0 <= idx < len(rows) - 1:
        nxt = rows[idx + 1]
        nxt_order = nxt.display_order or 0
        cur_order = machine.display_order or 0
        nxt.display_order = cur_order
        machine.display_order = nxt_order
    db.commit()
    return {"message": "重排成功", "machine_id": machine.id, "action": action, "new_order": machine.display_order}


@router.post("/import")
def import_floor_plan(data: dict, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """批量导入楼层平面图数据"""
    floor_id = data.get("floor_id")
    areas = data.get("areas", [])
    machines = data.get("machines", [])
    
    for area_data in areas:
        existing = db.query(FloorArea).filter(
            FloorArea.floor_id == floor_id,
            FloorArea.name == area_data.get("name")
        ).first()
        if existing:
            existing.area_type = area_data.get("area_type", existing.area_type)
            existing.x_pos = area_data.get("x_pos", existing.x_pos)
            existing.y_pos = area_data.get("y_pos", existing.y_pos)
            existing.width = area_data.get("width", existing.width)
            existing.height = area_data.get("height", existing.height)
            existing.color = area_data.get("color", existing.color)
        else:
            new_area = FloorArea(
                floor_id=floor_id,
                name=area_data.get("name"),
                area_type=area_data.get("area_type", "equipment"),
                x_pos=area_data.get("x_pos", 0),
                y_pos=area_data.get("y_pos", 0),
                width=area_data.get("width", 10),
                height=area_data.get("height", 10),
                color=area_data.get("color", "#1e293b"),
            )
            db.add(new_area)
    
    for machine_data in machines:
        machine = db.query(Machine).filter(Machine.id == machine_data.get("id")).first()
        if machine:
            machine.floor = floor_id
            machine.floor_x = machine_data.get("floor_x", machine.floor_x)
            machine.floor_y = machine_data.get("floor_y", machine.floor_y)
    
    db.commit()
    return {"message": "导入成功"}


@router.get("/export/{floor_id}")
def export_floor_plan(floor_id: int, db: Session = Depends(get_db)):
    """导出楼层平面图数据（JSON格式）"""
    floor = db.query(Floor).filter(Floor.id == floor_id).first()
    if not floor:
        raise HTTPException(status_code=404, detail="楼层不存在")
    
    areas = db.query(FloorArea).filter(FloorArea.floor_id == floor_id).all()
    machines = db.query(Machine).filter(Machine.floor == floor_id).all()
    
    return {
        "floor_id": floor_id,
        "floor_name": floor.name,
        "areas": [{
            "name": a.name,
            "area_type": a.area_type,
            "x_pos": a.x_pos,
            "y_pos": a.y_pos,
            "width": a.width,
            "height": a.height,
            "color": a.color,
        } for a in areas],
        "machines": [{
            "id": m.id,
            "name": m.name,
            "floor_x": m.floor_x,
            "floor_y": m.floor_y,
        } for m in machines],
    }


# ========== 天车轨迹 API ==========

@router.post("/{floor_id}/tracks")
def add_track(floor_id: int, data: dict, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """添加天车轨迹"""
    floor = db.query(Floor).filter(Floor.id == floor_id).first()
    if not floor:
        raise HTTPException(status_code=404, detail="楼层不存在")
    
    points = data.get("points", [])
    new_track = Track(
        floor_id=floor_id,
        name=data.get("name", f"轨迹_{datetime.now().strftime('%H%M%S')}"),
        track_type=data.get("track_type", "oht"),
        points_json=json.dumps(points),
        color=data.get("color", "#00d4ff"),
        speed=data.get("speed", 1.0),
        created_at=datetime.now().isoformat(),
    )
    db.add(new_track)
    db.commit()
    db.refresh(new_track)
    return {"id": new_track.id, "name": new_track.name, "message": "轨迹创建成功"}


@router.put("/{floor_id}/tracks/{track_id}")
def update_track(floor_id: int, track_id: int, data: dict, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """更新天车轨迹"""
    track = db.query(Track).filter(Track.id == track_id, Track.floor_id == floor_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="轨迹不存在")
    
    if "points" in data:
        track.points_json = json.dumps(data["points"])
    if "name" in data:
        track.name = data["name"]
    if "color" in data:
        track.color = data["color"]
    if "speed" in data:
        track.speed = data["speed"]
    
    db.commit()
    return {"message": "轨迹更新成功"}


@router.delete("/{floor_id}/tracks/{track_id}")
def delete_track(floor_id: int, track_id: int, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """删除天车轨迹"""
    track = db.query(Track).filter(Track.id == track_id, Track.floor_id == floor_id).first()
    if not track:
        raise HTTPException(status_code=404, detail="轨迹不存在")
    # 同时解绑天车
    vehicles = db.query(Vehicle).filter(Vehicle.track_id == track_id).all()
    for v in vehicles:
        v.track_id = None
    db.delete(track)
    db.commit()
    return {"message": "轨迹删除成功"}


# ========== 天车 API ==========

@router.post("/{floor_id}/vehicles")
def add_vehicle(floor_id: int, data: dict, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """添加天车"""
    floor = db.query(Floor).filter(Floor.id == floor_id).first()
    if not floor:
        raise HTTPException(status_code=404, detail="楼层不存在")
    
    vehicle_id = data.get("id")
    if not vehicle_id:
        raise HTTPException(status_code=400, detail="天车ID不能为空")
    
    existing = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="天车ID已存在")
    
    track_id = data.get("track_id")
    # 计算同一轨道上的天车数量，分配不同的初始进度，避免堆叠
    if track_id:
        existing_count = db.query(Vehicle).filter(Vehicle.track_id == track_id).count()
        initial_progress = (existing_count * 0.15) % 1.0
    else:
        initial_progress = 0.0
    new_vehicle = Vehicle(
        id=vehicle_id,
        name=data.get("name", vehicle_id),
        vehicle_type=data.get("vehicle_type", "oht"),
        floor_id=floor_id,
        track_id=track_id,
        state="moving" if track_id else "idle",
        progress=initial_progress,
        speed=data.get("speed", 1.0),
        updated_at=datetime.now().isoformat(),
    )
    db.add(new_vehicle)
    db.commit()
    return {"id": new_vehicle.id, "name": new_vehicle.name, "message": "天车添加成功"}


@router.put("/{floor_id}/vehicles/{vehicle_id}")
def update_vehicle(floor_id: int, vehicle_id: str, data: dict, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """更新天车状态"""
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.floor_id == floor_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="天车不存在")
    
    if "track_id" in data:
        vehicle.track_id = data["track_id"]
    if "state" in data:
        vehicle.state = data["state"]
    if "progress" in data:
        vehicle.progress = data["progress"]
    if "speed" in data:
        vehicle.speed = data["speed"]
    if "name" in data:
        vehicle.name = data["name"]
    if "lot_id" in data:
        vehicle.lot_id = data["lot_id"]
    if "target_machine_id" in data:
        vehicle.target_machine_id = data["target_machine_id"]
    
    vehicle.updated_at = datetime.now().isoformat()
    db.commit()
    return {"message": "天车更新成功"}


@router.delete("/{floor_id}/vehicles/{vehicle_id}")
def delete_vehicle(floor_id: int, vehicle_id: str, db: Session = Depends(get_db), _: User = Depends(require_floor_edit)):
    """删除天车"""
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.floor_id == floor_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="天车不存在")
    db.delete(vehicle)
    db.commit()
    return {"message": "天车删除成功"}