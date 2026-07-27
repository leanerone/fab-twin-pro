"""模型文件上传接口

支持 SVG / GLB / JSON 文件上传
上传文件关联到 machine_model_configs 表
支持版本管理和上传历史
"""
import os
import uuid
import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import MachineModelConfig

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "models")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".svg", ".glb", ".gltf", ".json", ".html"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


class ModelFileResponse(BaseModel):
    file_id: str
    file_name: str
    file_path: str
    file_type: str
    file_size: int
    model_id: str
    version: str
    uploaded_by: str
    created_at: str


class ModelFileListResponse(BaseModel):
    files: List[ModelFileResponse]
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


def _save_file_record(db: Session, model_id: str, file_id: str, file_name: str,
                      file_path: str, file_type: str, file_size: int,
                      version: str, uploaded_by: str):
    """保存文件记录"""
    model = db.query(MachineModelConfig).filter(
        MachineModelConfig.model_id == model_id
    ).first()
    if not model:
        raise HTTPException(status_code=404, detail=f"机型 {model_id} 不存在")

    model.views_config_json = json.dumps({
        "file_id": file_id,
        "file_name": file_name,
        "file_path": file_path,
        "file_type": file_type,
        "file_size": file_size,
        "version": version,
        "uploaded_by": uploaded_by,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "model_id": model_id,
    }, ensure_ascii=False)
    model.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    model.version = version
    db.commit()


@router.post("/models", response_model=ModelFileResponse)
async def upload_model_file(
    file: UploadFile = File(...),
    model_id: str = Form(...),
    uploaded_by: str = Form("admin"),
    description: str = Form(""),
    db: Session = Depends(get_db),
):
    """上传模型文件

    - 支持格式: .svg, .glb, .gltf, .json, .html
    - 最大文件: 50MB
    - 自动分配版本号 (v1, v2, ...)
    - 关联到 machine_model_configs 表
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
    file_id = str(uuid.uuid4())
    safe_name = f"{model_id}_{version}_{file_id}{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)

    with open(file_path, "wb") as f:
        f.write(content)

    file_size = len(content)
    _save_file_record(db, model_id, file_id, file.filename, file_path,
                      ext, file_size, version, uploaded_by)

    return ModelFileResponse(
        file_id=file_id,
        file_name=file.filename,
        file_path=file_path,
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
    """查询模型文件列表"""
    query = db.query(MachineModelConfig)
    if model_id:
        query = query.filter(MachineModelConfig.model_id == model_id)
    models = query.all()

    files = []
    for m in models:
        try:
            config = json.loads(m.views_config_json) if m.views_config_json else {}
            if isinstance(config, dict) and "file_id" in config:
                files.append(ModelFileResponse(
                    file_id=config.get("file_id", ""),
                    file_name=config.get("file_name", ""),
                    file_path=config.get("file_path", ""),
                    file_type=config.get("file_type", ""),
                    file_size=config.get("file_size", 0),
                    model_id=m.model_id,
                    version=m.version or config.get("version", ""),
                    uploaded_by=config.get("uploaded_by", "system"),
                    created_at=config.get("created_at", m.created_at or ""),
                ))
        except (json.JSONDecodeError, TypeError):
            pass

    return ModelFileListResponse(files=files, total=len(files))


@router.delete("/models/{file_id}")
async def delete_model_file(
    file_id: str,
    model_id: str = "",
    db: Session = Depends(get_db),
):
    """删除模型文件记录"""
    if not model_id:
        raise HTTPException(status_code=400, detail="需要提供 model_id 参数")

    model = db.query(MachineModelConfig).filter(
        MachineModelConfig.model_id == model_id
    ).first()
    if not model:
        raise HTTPException(status_code=404, detail=f"机型 {model_id} 不存在")

    try:
        config = json.loads(model.views_config_json) if model.views_config_json else {}
        file_path = config.get("file_path", "")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass

    model.views_config_json = "{}"
    model.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    model.version = "v0"
    db.commit()

    return {"status": "success", "message": f"文件 {file_id} 已删除"}


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
