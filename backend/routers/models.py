"""机台型号配置与事件动作映射 API"""
import json
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import MachineModelConfig, EventActionMapping, User
from routers.auth import get_current_user, check_permission

router = APIRouter(prefix="/api/models", tags=["机台型号配置"])


def require_model_edit(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """要求当前用户拥有 model_edit 权限"""
    if not check_permission(user, "model_edit", db):
        raise HTTPException(status_code=403, detail="无权限：需要 model_edit 权限")
    return user


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _parse_json(s: str, default):
    try:
        return json.loads(s) if s else default
    except (json.JSONDecodeError, TypeError):
        return default


def _model_to_dict(m: MachineModelConfig) -> dict:
    """将 MachineModelConfig ORM 对象转换为字典
    
    v2.0 新增字段：
    - animation_config: 统一动画配置（flows/animations/targets）
    - source_files: 来源文件信息（HTML/SVG/GLB 解析状态）
    """
    return {
        "model_id": m.model_id,
        "model_name": m.model_name,
        "vendor": m.vendor,
        "process_type": m.process_type,
        "version": m.version,
        "view_mode": m.view_mode,
        "description": m.description,
        "views_config": _parse_json(m.views_config_json, {}),
        "parts_config": _parse_json(m.parts_config_json, []),
        "state_mapping": _parse_json(m.state_mapping_json, []),
        "hotspots_config": _parse_json(m.hotspots_config_json, []),
        # v2.0 新增
        "animation_config": _parse_json(getattr(m, 'animation_config_json', None) or '{}', {}),
        "source_files": _parse_json(getattr(m, 'source_files_json', None) or '{}', {}),
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }


def _mapping_to_dict(m: EventActionMapping) -> dict:
    return {
        "id": m.id,
        "model_id": m.model_id,
        "mapping_id": m.mapping_id,
        "description": m.description,
        "trigger": {
            "event_type": m.trigger_event_type,
            "event_code": m.trigger_event_code,
            "condition": _parse_json(m.trigger_condition_json, {}),
        },
        "action_sequence": _parse_json(m.action_sequence_json, []),
        "rollback": {
            "event_type": m.rollback_event_type,
            "event_code": m.rollback_event_code,
        },
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }


# ========== 机台型号配置 ==========

@router.get("")
def list_models(db: Session = Depends(get_db)):
    """获取所有机台型号列表"""
    models = db.query(MachineModelConfig).order_by(MachineModelConfig.model_id).all()
    result = [_model_to_dict(m) for m in models]
    print(f"[API] /api/models called, returning {len(result)} models: {[m.model_id for m in models]}", flush=True)
    return result


@router.get("/{model_id}")
def get_model(model_id: str, db: Session = Depends(get_db)):
    """获取单个机台型号的完整配置"""
    m = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == model_id).first()
    if not m:
        raise HTTPException(status_code=404, detail=f"机台型号 {model_id} 不存在")
    result = _model_to_dict(m)
    mappings = db.query(EventActionMapping).filter(EventActionMapping.model_id == model_id).all()
    result["event_action_mappings"] = [_mapping_to_dict(mp) for mp in mappings]
    return result


@router.post("")
def create_model(payload: dict, db: Session = Depends(get_db), _: User = Depends(require_model_edit)):
    """新建机台型号
    
    v2.0 新增支持：
    - animation_config: 统一动画配置
    - source_files: 来源文件信息
    """
    model_id = payload.get("model_id")
    if not model_id:
        raise HTTPException(status_code=400, detail="model_id 不能为空")
    existing = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == model_id).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"机台型号 {model_id} 已存在")
    now = _now_iso()
    m = MachineModelConfig(
        model_id=model_id,
        model_name=payload.get("model_name", model_id),
        vendor=payload.get("vendor", ""),
        process_type=payload.get("process_type", "ETCH"),
        version=payload.get("version", "1.0"),
        view_mode=payload.get("view_mode", "threejs"),
        description=payload.get("description", ""),
        views_config_json=json.dumps(payload.get("views_config", {}), ensure_ascii=False),
        parts_config_json=json.dumps(payload.get("parts_config", []), ensure_ascii=False),
        state_mapping_json=json.dumps(payload.get("state_mapping", []), ensure_ascii=False),
        hotspots_config_json=json.dumps(payload.get("hotspots_config", []), ensure_ascii=False),
        # v2.0 新增
        animation_config_json=json.dumps(payload.get("animation_config", {}), ensure_ascii=False),
        source_files_json=json.dumps(payload.get("source_files", {}), ensure_ascii=False),
        created_at=now,
        updated_at=now,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return _model_to_dict(m)


@router.put("/{model_id}")
def update_model(model_id: str, payload: dict, db: Session = Depends(get_db), _: User = Depends(require_model_edit)):
    """更新机台型号配置
    
    v2.0 新增支持：
    - animation_config: 统一动画配置
    - source_files: 来源文件信息
    """
    m = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == model_id).first()
    if not m:
        raise HTTPException(status_code=404, detail=f"机台型号 {model_id} 不存在")
    if "model_name" in payload:
        m.model_name = payload["model_name"]
    if "vendor" in payload:
        m.vendor = payload["vendor"]
    if "process_type" in payload:
        m.process_type = payload["process_type"]
    if "version" in payload:
        m.version = payload["version"]
    if "view_mode" in payload:
        m.view_mode = payload["view_mode"]
    if "description" in payload:
        m.description = payload["description"]
    if "views_config" in payload:
        m.views_config_json = json.dumps(payload["views_config"], ensure_ascii=False)
    if "parts_config" in payload:
        m.parts_config_json = json.dumps(payload["parts_config"], ensure_ascii=False)
    if "state_mapping" in payload:
        m.state_mapping_json = json.dumps(payload["state_mapping"], ensure_ascii=False)
    if "hotspots_config" in payload:
        m.hotspots_config_json = json.dumps(payload["hotspots_config"], ensure_ascii=False)
    # v2.0 新增
    if "animation_config" in payload:
        m.animation_config_json = json.dumps(payload["animation_config"], ensure_ascii=False)
    if "source_files" in payload:
        m.source_files_json = json.dumps(payload["source_files"], ensure_ascii=False)
    m.updated_at = _now_iso()
    db.commit()
    db.refresh(m)
    return _model_to_dict(m)


@router.delete("/{model_id}")
def delete_model(model_id: str, db: Session = Depends(get_db), _: User = Depends(require_model_edit)):
    """删除机台型号"""
    m = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == model_id).first()
    if not m:
        raise HTTPException(status_code=404, detail=f"机台型号 {model_id} 不存在")
    db.query(EventActionMapping).filter(EventActionMapping.model_id == model_id).delete()
    db.delete(m)
    db.commit()
    return {"status": "ok", "deleted": model_id}


@router.post("/{model_id}/duplicate")
def duplicate_model(model_id: str, payload: dict, db: Session = Depends(get_db), _: User = Depends(require_model_edit)):
    """复制机台型号（基于现有型号新建）"""
    m = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == model_id).first()
    if not m:
        raise HTTPException(status_code=404, detail=f"机台型号 {model_id} 不存在")
    new_id = payload.get("new_model_id")
    if not new_id:
        raise HTTPException(status_code=400, detail="new_model_id 不能为空")
    existing = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == new_id).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"机台型号 {new_id} 已存在")
    now = _now_iso()
    new_m = MachineModelConfig(
        model_id=new_id,
        model_name=payload.get("new_model_name", m.model_name + " (副本)"),
        vendor=m.vendor,
        process_type=m.process_type,
        version="1.0",
        view_mode=m.view_mode,
        description=m.description,
        views_config_json=m.views_config_json,
        parts_config_json=m.parts_config_json,
        state_mapping_json=m.state_mapping_json,
        hotspots_config_json=m.hotspots_config_json,
        created_at=now,
        updated_at=now,
    )
    db.add(new_m)
    mappings = db.query(EventActionMapping).filter(EventActionMapping.model_id == model_id).all()
    for mp in mappings:
        new_mp = EventActionMapping(
            model_id=new_id,
            mapping_id=mp.mapping_id,
            description=mp.description,
            trigger_event_type=mp.trigger_event_type,
            trigger_event_code=mp.trigger_event_code,
            trigger_condition_json=mp.trigger_condition_json,
            action_sequence_json=mp.action_sequence_json,
            rollback_event_type=mp.rollback_event_type,
            rollback_event_code=mp.rollback_event_code,
            created_at=now,
            updated_at=now,
        )
        db.add(new_mp)
    db.commit()
    return {"status": "ok", "new_model_id": new_id}


# ========== 事件动作映射 ==========

@router.get("/{model_id}/event-actions")
def list_event_actions(model_id: str, db: Session = Depends(get_db)):
    """获取指定型号的所有事件动作映射"""
    m = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == model_id).first()
    if not m:
        raise HTTPException(status_code=404, detail=f"机台型号 {model_id} 不存在")
    mappings = db.query(EventActionMapping).filter(EventActionMapping.model_id == model_id).order_by(EventActionMapping.id).all()
    return [_mapping_to_dict(mp) for mp in mappings]


@router.post("/{model_id}/event-actions")
def create_event_action(model_id: str, payload: dict, db: Session = Depends(get_db), _: User = Depends(require_model_edit)):
    """新建事件动作映射"""
    m = db.query(MachineModelConfig).filter(MachineModelConfig.model_id == model_id).first()
    if not m:
        raise HTTPException(status_code=404, detail=f"机台型号 {model_id} 不存在")
    mapping_id = payload.get("mapping_id")
    if not mapping_id:
        raise HTTPException(status_code=400, detail="mapping_id 不能为空")
    trigger = payload.get("trigger", {})
    rollback = payload.get("rollback", {})
    now = _now_iso()
    mp = EventActionMapping(
        model_id=model_id,
        mapping_id=mapping_id,
        description=payload.get("description", ""),
        trigger_event_type=trigger.get("event_type", "STATE_CHANGE"),
        trigger_event_code=trigger.get("event_code", ""),
        trigger_condition_json=json.dumps(trigger.get("condition", {}), ensure_ascii=False),
        action_sequence_json=json.dumps(payload.get("action_sequence", []), ensure_ascii=False),
        rollback_event_type=rollback.get("event_type", ""),
        rollback_event_code=rollback.get("event_code", ""),
        created_at=now,
        updated_at=now,
    )
    db.add(mp)
    db.commit()
    db.refresh(mp)
    return _mapping_to_dict(mp)


@router.put("/{model_id}/event-actions/{mapping_id}")
def update_event_action(model_id: str, mapping_id: str, payload: dict, db: Session = Depends(get_db), _: User = Depends(require_model_edit)):
    """更新事件动作映射"""
    mp = db.query(EventActionMapping).filter(
        EventActionMapping.model_id == model_id,
        EventActionMapping.mapping_id == mapping_id,
    ).first()
    if not mp:
        raise HTTPException(status_code=404, detail="事件动作映射不存在")
    if "description" in payload:
        mp.description = payload["description"]
    if "trigger" in payload:
        trigger = payload["trigger"]
        mp.trigger_event_type = trigger.get("event_type", mp.trigger_event_type)
        mp.trigger_event_code = trigger.get("event_code", mp.trigger_event_code)
        if "condition" in trigger:
            mp.trigger_condition_json = json.dumps(trigger["condition"], ensure_ascii=False)
    if "action_sequence" in payload:
        mp.action_sequence_json = json.dumps(payload["action_sequence"], ensure_ascii=False)
    if "rollback" in payload:
        rollback = payload["rollback"]
        mp.rollback_event_type = rollback.get("event_type", mp.rollback_event_type)
        mp.rollback_event_code = rollback.get("event_code", mp.rollback_event_code)
    mp.updated_at = _now_iso()
    db.commit()
    db.refresh(mp)
    return _mapping_to_dict(mp)


@router.delete("/{model_id}/event-actions/{mapping_id}")
def delete_event_action(model_id: str, mapping_id: str, db: Session = Depends(get_db), _: User = Depends(require_model_edit)):
    """删除事件动作映射"""
    mp = db.query(EventActionMapping).filter(
        EventActionMapping.model_id == model_id,
        EventActionMapping.mapping_id == mapping_id,
    ).first()
    if not mp:
        raise HTTPException(status_code=404, detail="事件动作映射不存在")
    db.delete(mp)
    db.commit()
    return {"status": "ok", "deleted": mapping_id}
