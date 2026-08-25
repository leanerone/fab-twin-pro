"""模型文件上传接口

支持 SVG / GLB / JSON 文件上传
上传文件关联到 machine_model_configs 表
支持版本管理和上传历史

v2.2 修复：
- _save_file_record 改为 merge 模式，不再覆盖 views_config_json
- 文件路径存储为相对URL路径（/uploads/models/xxx.svg），而非绝对路径
- 上传成功后自动更新 views_config 中对应视图的 model_source
- 上传接口添加 model_edit 权限校验
- 新增 SVG 部件提取接口，从 SVG 中提取所有带 id 的元素
"""
import os
import re
import uuid
import json
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import MachineModelConfig, User
from routers.auth import get_current_user, check_permission

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "models")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".svg", ".glb", ".gltf", ".json", ".html"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


def require_model_edit(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """要求当前用户拥有 model_edit 权限"""
    if not check_permission(user, "model_edit", db):
        raise HTTPException(status_code=403, detail="无权限：需要 model_edit 权限")
    return user


class ModelFileResponse(BaseModel):
    file_id: str
    file_name: str
    file_url: str
    file_type: str
    file_size: int
    model_id: str
    version: str
    uploaded_by: str
    created_at: str


class ModelFileListResponse(BaseModel):
    files: List[ModelFileResponse]
    total: int


class SvgPartItem(BaseModel):
    """SVG 中提取的部件信息"""
    element_id: str
    tag: str
    part_name: str


class SvgPartsResponse(BaseModel):
    """SVG 部件提取结果"""
    model_id: str
    parts: List[SvgPartItem]
    total: int


def _get_next_version(db: Session, model_id: str) -> str:
    """获取下一个版本号"""
    model = db.query(MachineModelConfig).filter(
        MachineModelConfig.model_id == model_id
    ).first()
    if not model:
        return "v1"
    current_ver = model.version or "v1"
    try:
        num = int(current_ver.replace("v", "").replace(".", ""))
        return f"v{num + 1}"
    except ValueError:
        return "v1"


def _slot_key_for_type(file_type: str) -> str:
    """文件类型 → source_files_json 中的存储槽 key

    v2.5.3：按 file_type 分槽存储，支持 SVG + JSON + GLB 等多文件并存
    （旧版只有 current_file 单文件，后上传的会覆盖前者，导致无法同时管理 SVG+JSON）
    """
    if file_type == ".svg":
        return "current_svg"
    if file_type == ".json":
        return "current_json"
    if file_type in (".glb", ".gltf"):
        return "current_glb"
    if file_type == ".html":
        return "current_html"
    return "current_other"


def _save_file_record(db: Session, model_id: str, file_id: str, file_name: str,
                      file_url: str, file_type: str, file_size: int,
                      version: str, uploaded_by: str):
    """保存文件记录到 source_files_json（merge模式，不覆盖 views_config_json）

    v2.5.3 修复：
    - 按 file_type 分槽存储（current_svg/current_json/current_glb/current_html），
      不再互相覆盖，支持 SVG + JSON 同时上传并存
    - 向后兼容：旧数据只有 current_file，读取时 fallback
    - 同时更新 views_config 中对应视图的 model_source，让视图组件能加载文件
    """
    model = db.query(MachineModelConfig).filter(
        MachineModelConfig.model_id == model_id
    ).first()
    if not model:
        raise HTTPException(status_code=404, detail=f"机型 {model_id} 不存在")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. 将文件信息 merge 到 source_files_json 对应槽位
    source_files = {}
    try:
        source_files = json.loads(model.source_files_json) if model.source_files_json else {}
    except (json.JSONDecodeError, TypeError):
        source_files = {}

    file_info = {
        "file_id": file_id,
        "file_name": file_name,
        "file_url": file_url,
        "file_type": file_type,
        "file_size": file_size,
        "version": version,
        "uploaded_by": uploaded_by,
        "created_at": now_str,
    }
    slot_key = _slot_key_for_type(file_type)
    source_files[slot_key] = file_info
    # 同时保留 current_file 兼容旧前端读取（指向最新上传的文件）
    source_files["current_file"] = file_info

    # 累积历史版本
    history = source_files.get("history", [])
    history.append(file_info)
    source_files["history"] = history

    model.source_files_json = json.dumps(source_files, ensure_ascii=False)

    # 2. 更新 views_config 中对应视图的 model_source
    views_config = {}
    try:
        views_config = json.loads(model.views_config_json) if model.views_config_json else {}
    except (json.JSONDecodeError, TypeError):
        views_config = {}

    if file_type == ".svg":
        # SVG → 2D 视图
        if "view_2d" not in views_config:
            views_config["view_2d"] = {}
        views_config["view_2d"]["svg_source"] = file_url
    elif file_type in (".glb", ".gltf"):
        # GLB/GLTF → 3D 视图
        if "view_3d" not in views_config:
            views_config["view_3d"] = {}
        views_config["view_3d"]["model_source"] = file_url
    elif file_type == ".json":
        # JSON → 3D JSON 模型（注意：Motion JSON 由 upload_model_file 单独写入 animation_config_json，
        # 这里只更新 view_3d.model_source 用于普通 JSON 模型文件，不冲突）
        if "view_3d" not in views_config:
            views_config["view_3d"] = {}
        views_config["view_3d"]["model_source"] = file_url

    model.views_config_json = json.dumps(views_config, ensure_ascii=False)
    model.updated_at = now_str
    model.version = version
    db.commit()


@router.post("/models", response_model=ModelFileResponse)
async def upload_model_file(
    file: UploadFile = File(...),
    model_id: str = Form(...),
    uploaded_by: str = Form("admin"),
    description: str = Form(""),
    db: Session = Depends(get_db),
    _: User = Depends(require_model_edit),
):
    """上传模型文件

    - 支持格式: .svg, .glb, .gltf, .json, .html
    - 最大文件: 50MB
    - 自动分配版本号 (v1, v2, ...)
    - 关联到 machine_model_configs 表
    - v2.2: 文件信息写入 source_files_json，同时更新 views_config 的 model_source
    """
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {ext}。支持的类型: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大: {len(content) / 1024 / 1024:.1f}MB。最大支持 {MAX_FILE_SIZE / 1024 / 1024:.0f}MB"
        )

    model = db.query(MachineModelConfig).filter(
        MachineModelConfig.model_id == model_id
    ).first()
    if not model:
        raise HTTPException(status_code=404, detail=f"机型 {model_id} 不存在")

    version = _get_next_version(db, model_id)
    file_id = str(uuid.uuid4())[:8]
    safe_name = f"{model_id}_{version}_{file_id}{ext}"
    abs_path = os.path.join(UPLOAD_DIR, safe_name)

    with open(abs_path, "wb") as f:
        f.write(content)

    file_size = len(content)
    # 存储为相对URL路径，前端可直接访问
    file_url = f"/uploads/models/{safe_name}"
    _save_file_record(db, model_id, file_id, file.filename, file_url,
                      ext, file_size, version, uploaded_by)

    # 如果是 JSON 文件且包含 schema_version，存入 animation_config_json
    if ext == ".json":
        try:
            json_data = json.loads(content.decode("utf-8"))
            if "schema_version" in json_data:
                model.animation_config_json = json.dumps(json_data, ensure_ascii=False)
                model.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                db.commit()
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass  # 非 Motion JSON 格式，忽略

    return ModelFileResponse(
        file_id=file_id,
        file_name=file.filename,
        file_url=file_url,
        file_type=ext,
        file_size=file_size,
        model_id=model_id,
        version=version,
        uploaded_by=uploaded_by,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


@router.get("/models", response_model=ModelFileListResponse)
async def list_model_files(
    model_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """查询模型文件列表

    v2.5.3: 遍历 source_files_json 中所有 file_type 槽位（current_svg/current_json/...），
            支持一个机型同时存在多个文件（SVG + JSON + GLB ...）
            旧版只有 current_file，向后兼容
    """
    query = db.query(MachineModelConfig)
    if model_id:
        query = query.filter(MachineModelConfig.model_id == model_id)
    models = query.all()

    # 所有可能的文件槽位 key
    slot_keys = ["current_svg", "current_json", "current_glb", "current_html", "current_other", "current_file"]

    files = []
    seen_file_ids = set()  # current_file 与具体槽位可能重复，去重
    for m in models:
        try:
            source_files = json.loads(m.source_files_json) if m.source_files_json else {}
            for key in slot_keys:
                current = source_files.get(key)
                if not current or not current.get("file_id"):
                    continue
                fid = current.get("file_id")
                if fid in seen_file_ids:
                    continue
                seen_file_ids.add(fid)
                files.append(ModelFileResponse(
                    file_id=fid,
                    file_name=current.get("file_name", ""),
                    file_url=current.get("file_url", ""),
                    file_type=current.get("file_type", ""),
                    file_size=current.get("file_size", 0),
                    model_id=m.model_id,
                    version=m.version or current.get("version", ""),
                    uploaded_by=current.get("uploaded_by", "system"),
                    created_at=current.get("created_at", m.created_at or ""),
                ))
        except (json.JSONDecodeError, TypeError):
            pass

    return ModelFileListResponse(files=files, total=len(files))


@router.delete("/models/{file_id}")
async def delete_model_file(
    file_id: str,
    model_id: str = "",
    db: Session = Depends(get_db),
    _: User = Depends(require_model_edit),
):
    """删除模型文件记录

    v2.2: 清理 source_files_json 和 views_config 中的引用
    """
    if not model_id:
        raise HTTPException(status_code=400, detail="需要提供 model_id 参数")

    model = db.query(MachineModelConfig).filter(
        MachineModelConfig.model_id == model_id
    ).first()
    if not model:
        raise HTTPException(status_code=404, detail=f"机型 {model_id} 不存在")

    # 从 source_files_json 获取文件路径并删除磁盘文件
    # v2.5.3: 遍历所有 file_type 槽位找到匹配 file_id 的记录，只清理对应槽，不影响其他文件
    deleted_slot = None
    deleted_file_url = ""
    try:
        source_files = json.loads(model.source_files_json) if model.source_files_json else {}
        slot_keys = ["current_svg", "current_json", "current_glb", "current_html", "current_other", "current_file"]
        for key in slot_keys:
            entry = source_files.get(key)
            if entry and entry.get("file_id") == file_id:
                deleted_slot = key
                deleted_file_url = entry.get("file_url", "")
                break
        if deleted_file_url:
            file_name = os.path.basename(deleted_file_url)
            abs_path = os.path.join(UPLOAD_DIR, file_name)
            if os.path.exists(abs_path):
                os.remove(abs_path)
    except Exception:
        pass

    # 只清理命中的槽位，保留其他文件；同时清理 current_file 兼容字段（若指向同一文件）
    try:
        if deleted_slot:
            source_files.pop(deleted_slot, None)
        cf = source_files.get("current_file")
        if cf and cf.get("file_id") == file_id:
            source_files.pop("current_file", None)
        model.source_files_json = json.dumps(source_files, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        model.source_files_json = "{}"

    # 清理 views_config 中对应的 model_source
    # v2.5.3: 仅在删除对应类型文件时清理对应字段（SVG→svg_source, GLB/JSON→model_source）
    try:
        views_config = json.loads(model.views_config_json) if model.views_config_json else {}
        if deleted_slot == "current_svg" and "view_2d" in views_config:
            views_config["view_2d"].pop("svg_source", None)
        if deleted_slot in ("current_glb", "current_json") and "view_3d" in views_config:
            views_config["view_3d"].pop("model_source", None)
        model.views_config_json = json.dumps(views_config, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        pass

    model.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.commit()

    return {"status": "success", "message": f"文件 {file_id} 已删除（槽位 {deleted_slot}）"}


@router.post("/models/{model_id}/extract-svg-parts", response_model=SvgPartsResponse)
async def extract_svg_parts(
    model_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_model_edit),
):
    """从已上传的 SVG 文件中提取所有带 id 的元素

    用于动画配置中的 targets 部件绑定：
    - 解析 SVG XML，提取所有带 id 属性的元素
    - 返回 element_id（SVG中的id）、tag（元素类型）、part_name（建议命名）
    """
    model = db.query(MachineModelConfig).filter(
        MachineModelConfig.model_id == model_id
    ).first()
    if not model:
        raise HTTPException(status_code=404, detail=f"机型 {model_id} 不存在")

    # 从 source_files_json 获取 SVG 文件路径
    # v2.5.3: 优先从 current_svg 槽读取，旧版 fallback 到 current_file
    source_files = {}
    try:
        source_files = json.loads(model.source_files_json) if model.source_files_json else {}
    except (json.JSONDecodeError, TypeError):
        source_files = {}

    current = source_files.get("current_svg") or source_files.get("current_file") or {}
    file_url = current.get("file_url", "")
    file_type = current.get("file_type", "")

    if not file_url or file_type != ".svg":
        raise HTTPException(status_code=400, detail="该机型没有已上传的 SVG 文件，请先上传 SVG")

    # 读取 SVG 文件
    file_name = os.path.basename(file_url)
    abs_path = os.path.join(UPLOAD_DIR, file_name)
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail=f"SVG 文件不存在: {file_url}")

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            svg_content = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取 SVG 文件失败: {str(e)}")

    # 解析 SVG XML，提取所有带 id 的元素
    parts = []
    try:
        # 注册 SVG 命名空间
        ET.register_namespace("", "http://www.w3.org/2000/svg")
        root = ET.fromstring(svg_content)

        # 递归遍历所有元素
        for elem in root.iter():
            elem_id = elem.get("id")
            if elem_id:
                tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                # 跳过 style、defs 等非视觉元素
                if tag in ("style", "defs", "metadata", "title", "desc"):
                    continue
                parts.append(SvgPartItem(
                    element_id=elem_id,
                    tag=tag,
                    part_name=elem_id,  # 默认使用 id 作为名称
                ))
    except ET.ParseError as e:
        raise HTTPException(status_code=400, detail=f"SVG 解析失败: {str(e)}")

    return SvgPartsResponse(
        model_id=model_id,
        parts=parts,
        total=len(parts),
    )


@router.post("/parse-html")
async def parse_html_file(
    file: UploadFile = File(...),
):
    """解析 HTML 文件，提取 UNITS 定义和部件配置

    v2.0 新增：
    - 支持上传 HTML 文件
    - 自动提取 UNITS 定义（部件坐标/尺寸）
    - 生成 parts_config_json 初稿
    - 兼容 OXE_2D.html 风格
    """
    if not file.filename.endswith('.html'):
        raise HTTPException(status_code=400, detail="只支持 .html 文件")

    try:
        content = await file.read()
        html_content = content.decode('utf-8', errors='ignore')

        # 导入解析器
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from services.html_parser import parse_html_file as parse_html

        result = parse_html(html_content, model_id='PARSED')

        return {
            "status": "success",
            "filename": file.filename,
            "source_info": result.get('source_info', {}),
            "units": result.get('units', {}),
            "parts_config": result.get('parts_config', []),
            "api_calls": result.get('api_calls', []),
            "functions": result.get('functions', []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")


@router.post("/export-svg/{model_id}")
async def export_svg_config(
    model_id: str,
    db: Session = Depends(get_db),
):
    """导出 SVG 配置文件

    v2.0 新增：
    - 根据机型配置生成 SVG 文件
    - 用于导入 Inkscape 进行精修
    - 每个部件带 id 属性，与 part_id 一致
    """
    model = db.query(MachineModelConfig).filter(
        MachineModelConfig.model_id == model_id
    ).first()

    if not model:
        raise HTTPException(status_code=404, detail=f"机型 {model_id} 不存在")

    try:
        parts_config = json.loads(model.parts_config_json) if model.parts_config_json else []
    except (json.JSONDecodeError, TypeError):
        parts_config = []

    # 生成 SVG 内容
    svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000" viewBox="0 0 1000 1000">
  <style>
    .part {{ fill: #374151; stroke: #1f2937; stroke-width: 2; }}
    .label {{ font-family: monospace; font-size: 10px; fill: #6b7280; }}
  </style>

  <!-- 标题 -->
  <text x="20" y="30" style="font-size: 16px; font-weight: bold;">{model.model_name}</text>
  <text x="20" y="50" style="font-size: 12px; fill: #6b7280;">Model ID: {model_id}</text>

  <!-- 部件（从 parts_config 生成） -->
'''

    for part in parts_config:
        part_id = part.get('part_id', 'unknown')
        part_name = part.get('part_name', part_id)
        view_2d = part.get('view_2d_iso', part.get('view_2d', {}))

        x = view_2d.get('x', 500)
        y = view_2d.get('y', 500)
        w = view_2d.get('width', view_2d.get('w', 50))
        h = view_2d.get('height', view_2d.get('h', 50))

        svg_content += f'''
  <!-- {part_name} -->
  <g id="{part_id}">
    <rect class="part" x="{x - w/2}" y="{y - h/2}" width="{w}" height="{h}" rx="4"/>
    <text class="label" x="{x}" y="{y + 4}">{part_id}</text>
  </g>
'''

    svg_content += '''
</svg>'''

    return {
        "status": "success",
        "model_id": model_id,
        "svg_content": svg_content,
        "parts_count": len(parts_config),
        "download_filename": f"{model_id}-export.svg",
    }
