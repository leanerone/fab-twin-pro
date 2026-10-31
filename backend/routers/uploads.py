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
import sys
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
from services.html_parser import parse_html_file as _parse_html_lib
from xml.sax.saxutils import escape as _xml_escape

# 根目录 models/ 与后端 models.py 同名，加入其内部路径后按 svg_kit 包导入，避免模块冲突。
_SVG_KIT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "models"))
if _SVG_KIT_ROOT not in sys.path:
    sys.path.append(_SVG_KIT_ROOT)
from svg_kit.validate import extract_ids, extract_parts, validate_content  # noqa: E402

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "models")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".svg", ".glb", ".gltf", ".json", ".html"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_HTML_SIZE = 10 * 1024 * 1024  # parse-html 上限 10MB（test31）

# 文件槽位 key（test31 提为模块常量，消除三处硬编码重复）
SLOT_KEYS = ["current_svg", "current_json", "current_glb", "current_html", "current_other", "current_file"]

# model_id 白名单（test31）：model_id 会拼进落盘文件名，禁止路径分隔符等字符，
# 防止路径穿越写文件
_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_model_id(model_id: str) -> str:
    if not model_id or not _MODEL_ID_RE.match(model_id):
        raise HTTPException(
            status_code=400,
            detail="model_id 只允许字母/数字/下划线/中划线（防路径穿越）",
        )
    return model_id


from core.deps import require_model_edit  # noqa: E402,F811  批次1：依赖收拢


class DraftValidationRequest(BaseModel):
    svg_text: str
    motion: dict


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
    # Motion JSON 导入校验警告（缺 viewBox/parts、SVG id 未匹配等；不阻断导入）
    warnings: List[str] = []
    # 消除 pydantic 对 model_id 字段的 protected namespace 警告
    model_config = {"protected_namespaces": ()}


# Motion JSON 支持的动作类型白名单（与前端 useMotionPlayback 对齐）
MOTION_ACTION_WHITELIST = {"offset", "rotate", "scale", "opacity", "visibility", "snap", "move_to", "text"}


def _model_svg_url(model: MachineModelConfig) -> str:
    """读取当前 SVG；上传记录缺失时回退到 view_2d 的现有绑定。"""
    try:
        source_files = json.loads(model.source_files_json) if model.source_files_json else {}
    except (json.JSONDecodeError, TypeError):
        source_files = {}
    current = source_files.get("current_svg") or source_files.get("current_file") or {}
    file_url = current.get("file_url", "")
    if file_url and str(file_url).lower().endswith(".svg"):
        return file_url
    try:
        views = json.loads(model.views_config_json) if model.views_config_json else {}
    except (json.JSONDecodeError, TypeError):
        views = {}
    view_2d = views.get("view_2d") or {}
    file_url = view_2d.get("svg_source") or view_2d.get("model_source") or ""
    return file_url if str(file_url).lower().endswith(".svg") else ""


def _extract_svg_ids_from_model(model: MachineModelConfig) -> set:
    """读取机型当前 SVG，提取全部元素 id（用于 Motion JSON 的 SVG id 校验）"""
    file_url = _model_svg_url(model)
    if not file_url:
        return set()
    abs_path = os.path.join(UPLOAD_DIR, os.path.basename(file_url))
    if not os.path.exists(abs_path):
        return set()
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            root = ET.fromstring(f.read())
        return {e.get("id") for e in root.iter() if e.get("id")}
    except Exception:
        return set()


def _validate_motion_json(json_data: dict, svg_ids: set) -> List[str]:
    """Motion JSON 导入校验

    阻断项（抛 HTTP 400）：
    - motions 缺失/为空、motion 缺 step 或 rules、rule 缺 actions
    - 动作类型不在白名单（offset/rotate/scale/opacity/visibility/snap/move_to/text）
    - 模板花括号不配对

    警告项（返回 warnings，可播放但标出）：
    - 缺 document.viewBox
    - 缺 parts 定义
    - 非模板 part_id 在 SVG 中找不到（运行时可能经 part_aliases 命中，故只警告）
    - rotate 缺 axis（v1.1 建议显式声明 "z"）

    结构约定：rule = { phase, target_part_id, when, actions: [{ type, ... }] }
    """
    warnings = []
    motions = json_data.get("motions")
    if not isinstance(motions, list) or not motions:
        raise HTTPException(status_code=400, detail="Motion JSON 校验失败：motions 缺失或为空数组")

    doc = json_data.get("document") or {}
    # viewBox 可能直接挂在 document 上，或按规范挂在 document.coord 下
    viewbox = doc.get("viewBox") or (doc.get("coord") or {}).get("viewBox")
    if not viewbox:
        warnings.append("缺 document.viewBox：可播放，运行时将按 ext.viewBox_fallback 或 SVG 自身尺寸兜底")
    if not json_data.get("parts"):
        warnings.append("缺 parts 定义：可播放，部件几何将在加载时动态测量")

    template_re = re.compile(r"\{[^{}]*\}")

    def check_template(field_val: str, where: str):
        if not isinstance(field_val, str):
            return
        stripped = template_re.sub("", field_val)
        if "{" in stripped or "}" in stripped:
            raise HTTPException(status_code=400, detail=f"Motion JSON 校验失败：{where} 模板花括号不配对: {field_val}")

    def check_part_id(part_id, where: str):
        if not part_id or not isinstance(part_id, str):
            return
        check_template(part_id, where)
        if "{" in part_id:
            return  # 模板 id 运行时解析，导入期无法校验
        if svg_ids and part_id not in svg_ids:
            warnings.append(f"{where} 引用的部件 id「{part_id}」在已上传 SVG 中不存在（如走 part_aliases 别名可忽略）")

    for mi, motion in enumerate(motions):
        step = motion.get("step")
        where_m = f"motions[{mi}]({step or '?'})"
        if not step:
            raise HTTPException(status_code=400, detail=f"Motion JSON 校验失败：{where_m} 缺 step（事件名）")
        rules = motion.get("rules")
        if not isinstance(rules, list) or not rules:
            raise HTTPException(status_code=400, detail=f"Motion JSON 校验失败：{where_m} 缺 rules 或为空数组")
        for ri, rule in enumerate(rules):
            where_r = f"{where_m}.rules[{ri}]"
            check_part_id(rule.get("target_part_id"), f"{where_r}.target_part_id")
            actions = rule.get("actions")
            if not isinstance(actions, list) or not actions:
                raise HTTPException(status_code=400, detail=f"Motion JSON 校验失败：{where_r} 缺 actions 或为空数组")
            for ai, action in enumerate(actions):
                where_a = f"{where_r}.actions[{ai}]"
                atype = action.get("type")
                if atype not in MOTION_ACTION_WHITELIST:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Motion JSON 校验失败：{where_a} 动作类型「{atype}」不支持，"
                               f"仅支持: {', '.join(sorted(MOTION_ACTION_WHITELIST))}"
                    )
                check_part_id(action.get("follow_part_id"), f"{where_a}.follow_part_id")
                to_pid = action.get("to_part_id")
                if to_pid and str(to_pid).strip() not in ("{home}", "home"):
                    check_part_id(to_pid, f"{where_a}.to_part_id")
                if atype == "rotate":
                    if "axis" not in action:
                        warnings.append(f"{where_a} rotate 未声明 axis，建议显式写 \"axis\": \"z\"")
                    if isinstance(action.get("angle"), str):
                        check_template(action["angle"], f"{where_a}.angle")
                elif atype == "text" and action.get("content"):
                    check_template(action["content"], f"{where_a}.content")

    return warnings


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
    model_config = {"protected_namespaces": ()}
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


@router.post("/models/validate-draft")
def validate_model_draft(
    payload: DraftValidationRequest,
    _: User = Depends(require_model_edit),
):
    """复用 svg-kit 规则校验编辑器内存中的 SVG 与 Motion 草稿"""
    errors, warnings = validate_content(payload.svg_text, payload.motion)
    return {
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "id_count": len(set(extract_ids(payload.svg_text))),
            "part_count": len(set(extract_parts(payload.svg_text))),
            "motion_count": len(payload.motion.get("motions", [])),
        },
    }


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

    # test31：model_id 白名单校验（拼落盘文件名，防路径穿越）
    _validate_model_id(model_id)

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

    # Motion JSON（含 schema_version）：先校验再落盘，阻断项直接 400 不产生文件记录
    motion_data = None
    motion_warnings: List[str] = []
    if ext == ".json":
        try:
            parsed = json.loads(content.decode("utf-8"))
            if "schema_version" in parsed:
                motion_data = parsed
                svg_ids = _extract_svg_ids_from_model(model)
                motion_warnings = _validate_motion_json(parsed, svg_ids)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass  # 非 Motion JSON 格式，按普通 JSON 模型文件处理

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

    # Motion JSON 校验通过，存入 animation_config_json
    # test31 修复：写配置后失效 /api/models 的 300s 缓存——此前上传后机台页
    # 最长 10 分钟（后端300s+前端300s）仍跑旧动画配置（失效链断裂点）
    if motion_data is not None:
        model.animation_config_json = json.dumps(motion_data, ensure_ascii=False)
        model.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.commit()
        try:
            from routers.models import models_config_ttl
            models_config_ttl.invalidate()
        except ImportError:
            pass

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
        warnings=motion_warnings,
    )


@router.get("/models", response_model=ModelFileListResponse)
async def list_model_files(
    model_id: Optional[str] = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_model_edit),
):
    """查询模型文件列表

    v2.5.3: 遍历 source_files_json 中所有 file_type 槽位（current_svg/current_json/...），
            支持一个机型同时存在多个文件（SVG + JSON + GLB ...）
            旧版只有 current_file，向后兼容
    test31: 补 require_model_edit 认证（此前无认证）
    """
    if model_id:
        _validate_model_id(model_id)
    query = db.query(MachineModelConfig)
    if model_id:
        query = query.filter(MachineModelConfig.model_id == model_id)
    models = query.all()

    files = []
    seen_file_ids = set()  # current_file 与具体槽位可能重复，去重
    for m in models:
        try:
            source_files = json.loads(m.source_files_json) if m.source_files_json else {}
            for key in SLOT_KEYS:
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
    _validate_model_id(model_id)

    model = db.query(MachineModelConfig).filter(
        MachineModelConfig.model_id == model_id
    ).first()
    if not model:
        raise HTTPException(status_code=404, detail=f"机型 {model_id} 不存在")

    # 从 source_files_json 获取文件路径
    # v2.5.3: 遍历所有 file_type 槽位找到匹配 file_id 的记录，只清理对应槽，不影响其他文件
    # test31: 改为先改库后删盘（原顺序 DB 失败会产生悬空引用；现在删盘失败仅留下孤儿文件并记日志）
    deleted_slot = None
    deleted_file_url = ""
    try:
        source_files = json.loads(model.source_files_json) if model.source_files_json else {}
        for key in SLOT_KEYS:
            entry = source_files.get(key)
            if entry and entry.get("file_id") == file_id:
                deleted_slot = key
                deleted_file_url = entry.get("file_url", "")
                break
    except (json.JSONDecodeError, TypeError):
        source_files = {}

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

    # DB 已提交，再删磁盘文件；失败只留孤儿文件（下次上传同槽位会覆盖），不影响一致性
    if deleted_file_url:
        try:
            file_name = os.path.basename(deleted_file_url)
            abs_path = os.path.join(UPLOAD_DIR, file_name)
            if os.path.exists(abs_path):
                os.remove(abs_path)
        except OSError as e:
            print(f"[uploads] 删除磁盘文件失败（忽略，孤儿文件）: {deleted_file_url}: {e}", flush=True)

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

    # DB 同步的机型可能没有上传历史，但 view_2d 已绑定当前 SVG。
    file_url = _model_svg_url(model)
    if not file_url:
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
    _: User = Depends(require_model_edit),
):
    """解析 HTML 文件，提取 UNITS 定义和部件配置

    v2.0 新增：
    - 支持上传 HTML 文件
    - 自动提取 UNITS 定义（部件坐标/尺寸）
    - 生成 parts_config_json 初稿
    - 兼容 OXE_2D.html 风格
    test31: 补 require_model_edit 认证 + 10MB 大小限制，删除 sys.path hack
    """
    if not file.filename.endswith('.html'):
        raise HTTPException(status_code=400, detail="只支持 .html 文件")

    try:
        content = await file.read()
        if len(content) > MAX_HTML_SIZE:
            raise HTTPException(status_code=400, detail=f"文件过大（>{MAX_HTML_SIZE // 1024 // 1024}MB）")
        html_content = content.decode('utf-8', errors='ignore')

        result = _parse_html_lib(html_content, model_id='PARSED')

        return {
            "status": "success",
            "filename": file.filename,
            "source_info": result.get('source_info', {}),
            "units": result.get('units', {}),
            "parts_config": result.get('parts_config', []),
            "api_calls": result.get('api_calls', []),
            "functions": result.get('functions', []),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")


@router.post("/export-svg/{model_id}")
async def export_svg_config(
    model_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_model_edit),
):
    """导出 SVG 配置文件

    v2.0 新增：
    - 根据机型配置生成 SVG 文件
    - 用于导入 Inkscape 进行精修
    - 每个部件带 id 属性，与 part_id 一致
    test31: 补认证 + XML 转义（part_id/part_name 原样拼入 XML 存在注入）
    """
    _validate_model_id(model_id)
    model = db.query(MachineModelConfig).filter(
        MachineModelConfig.model_id == model_id
    ).first()

    if not model:
        raise HTTPException(status_code=404, detail=f"机型 {model_id} 不存在")

    try:
        parts_config = json.loads(model.parts_config_json) if model.parts_config_json else []
    except (json.JSONDecodeError, TypeError):
        parts_config = []

    # 生成 SVG 内容（文本节点/属性统一 XML 转义）
    svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000" viewBox="0 0 1000 1000">
  <style>
    .part {{ fill: #374151; stroke: #1f2937; stroke-width: 2; }}
    .label {{ font-family: monospace; font-size: 10px; fill: #6b7280; }}
  </style>

  <!-- 标题 -->
  <text x="20" y="30" style="font-size: 16px; font-weight: bold;">{_xml_escape(model.model_name or "")}</text>
  <text x="20" y="50" style="font-size: 12px; fill: #6b7280;">Model ID: {_xml_escape(model_id)}</text>

  <!-- 部件（从 parts_config 生成） -->
'''

    for part in parts_config:
        part_id = _xml_escape(str(part.get('part_id', 'unknown')))
        part_name = _xml_escape(str(part.get('part_name', part.get('part_id', 'unknown'))))
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
