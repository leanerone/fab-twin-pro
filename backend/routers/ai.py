"""AI 中间适配层 API（统一接口）

包含：
- /api/ai/chat - 统一聊天接口（推荐）
- /api/ai/query - 旧版查询接口（兼容）
- /api/ai/config - Dify/N8N配置管理
- /api/ai/config/test - 连接测试
- /api/ai/providers - 可用Provider预设列表
- /api/ai/model-configs - LLM多配置管理（CRUD）
- /api/ai/model-configs/{id}/switch - 切换当前配置
- /api/ai/usage/stats - Token使用量统计
- /api/ai/usage/logs - 使用日志
- /api/ai/sessions - 会话管理
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session

from database import get_db
from schemas import (
    AIQueryRequest, AIQueryResponse,
    AIChatRequest, AIChatResponse,
    AIConfigUpdate, AIConfigOut, AIConnectionTest,
    AIProviderConfigIn, AIProviderConfigOut, AIProviderConfigUpdate,
    AIUsageStats, AIUsageLogOut,
)
from services.ai_middleware import ai_middleware, PROVIDER_PRESETS
from services import speech_service

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ========== 统一聊天接口（新版） ==========

@router.post("/chat", response_model=AIChatResponse)
def ai_chat(req: AIChatRequest, db: Session = Depends(get_db)):
    """统一AI聊天接口 - 支持多模型、配置切换、Dify、N8N联动

    - 本地规则引擎（默认，无需配置）
    - OpenAI兼容模型（GLM、GPT、DeepSeek、Qwen等）
    - Dify 应用对接
    - N8N 工作流联动（管理员权限）
    """
    result = ai_middleware.chat(
        question=req.question,
        session_id=req.session_id,
        machine_id=req.machine_id,
        context=req.context,
        user_role=req.user_role or "user",
        config_id=req.config_id,
    )
    return AIChatResponse(**result)


# ========== 旧版兼容接口 ==========

@router.post("/query", response_model=AIQueryResponse)
def ai_query(req: AIQueryRequest, db: Session = Depends(get_db)):
    """旧版AI查询接口（兼容保留）"""
    result = ai_middleware.chat(
        question=req.question,
        machine_id=req.machine_id,
        user_role="user",
    )
    return AIQueryResponse(
        answer=result.get("answer", ""),
        sql=result.get("sql", ""),
        jump_timestamp=result.get("jump_timestamp"),
    )


# ========== Dify/N8N 配置管理 ==========

@router.get("/config", response_model=AIConfigOut)
def get_ai_config():
    """获取当前AI配置（脱敏）- 含当前LLM配置 + Dify/N8N"""
    config = ai_middleware.get_config()
    return AIConfigOut(**config)


@router.put("/config", response_model=dict)
def update_ai_config(config: AIConfigUpdate):
    """更新Dify/N8N配置（运行时更新 + 持久化到DB）"""
    config_dict = config.model_dump(exclude_none=True)
    success = ai_middleware.update_config(config_dict)
    if not success:
        raise HTTPException(status_code=400, detail="配置更新失败")
    return {"success": True, "message": "配置已更新并保存"}


@router.post("/config/test", response_model=dict)
def test_ai_connection(test_req: AIConnectionTest):
    """测试AI服务连接"""
    result = ai_middleware.test_connection(
        provider_type=test_req.provider_type,
        config=test_req.config,
    )
    return result


# ========== Provider 预设管理 ==========

@router.get("/providers")
def list_providers():
    """获取可用AI Provider预设列表（含默认配置）"""
    return {
        "providers": PROVIDER_PRESETS,
        "current": ai_middleware.provider,
        "current_name": ai_middleware.provider_name or ai_middleware._infer_provider_name(),
        "current_config_id": ai_middleware.current_config_id,
    }


# ========== LLM 多配置管理 ==========

@router.get("/model-configs")
def list_model_configs():
    """列出所有LLM配置"""
    configs = ai_middleware.list_provider_configs()
    return {"configs": configs, "total": len(configs)}


@router.post("/model-configs", response_model=dict)
def create_model_config(config: AIProviderConfigIn):
    """创建新的LLM配置"""
    result = ai_middleware.create_provider_config(config.model_dump())
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@router.put("/model-configs/{config_id}", response_model=dict)
def update_model_config(config_id: int, config: AIProviderConfigUpdate):
    """更新LLM配置"""
    result = ai_middleware.update_provider_config(config_id, config.model_dump(exclude_none=True))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@router.delete("/model-configs/{config_id}", response_model=dict)
def delete_model_config(config_id: int):
    """删除LLM配置"""
    result = ai_middleware.delete_provider_config(config_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@router.put("/model-configs/{config_id}/default", response_model=dict)
def set_default_model_config(config_id: int):
    """设为默认配置"""
    result = ai_middleware.set_default_provider_config(config_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@router.put("/model-configs/{config_id}/toggle", response_model=dict)
def toggle_model_config(config_id: int):
    """启用/禁用配置"""
    result = ai_middleware.toggle_provider_config(config_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@router.post("/model-configs/switch", response_model=dict)
def switch_model_config(config_id: int = Query(..., description="要切换到的配置ID")):
    """切换当前使用的LLM配置"""
    result = ai_middleware.switch_config(config_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


# ========== 使用量统计 ==========

@router.get("/usage/stats")
def get_usage_stats(days: int = Query(30, ge=1, le=365)):
    """获取Token使用量统计"""
    stats = ai_middleware.get_usage_stats(days=days)
    return stats


@router.get("/usage/logs")
def get_usage_logs(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    """获取使用日志列表"""
    logs = ai_middleware.get_usage_logs(limit=limit, offset=offset)
    return {"logs": logs, "total": len(logs)}


# ========== 会话管理 ==========

@router.get("/sessions")
def list_sessions(limit: int = 20):
    """列出最近的AI会话"""
    sessions = ai_middleware.list_sessions(limit=limit)
    return {"sessions": sessions, "total": len(sessions)}


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    """获取指定会话详情"""
    session = ai_middleware.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.delete("/sessions/{session_id}")
def clear_session(session_id: str):
    """清除指定会话"""
    success = ai_middleware.clear_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"success": True, "message": "会话已清除"}


# ========== 语音识别接口（本地 Whisper，离线运行） ==========

@router.post("/speech-to-text")
async def speech_to_text(
    audio: UploadFile = File(...),
    language: str = Form("zh"),
):
    """
    语音转文字 - 基于本地 faster-whisper，无需网络

    接收前端上传的音频文件（webm/wav/mp3 等），返回识别文本。
    首次调用会自动下载模型（tiny 约 75MB），之后离线可用。
    """
    try:
        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="音频文件为空")

        # 限制音频大小（10MB）
        if len(audio_bytes) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="音频文件过大（>10MB）")

        text = speech_service.transcribe(audio_bytes, language=language or "zh")
        return {
            "success": True,
            "text": text,
            "language": language,
        }
    except HTTPException:
        raise
    except Exception as e:
        # 模型未下载/加载失败等
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "text": "",
                "error": str(e),
                "hint": "可能是首次加载需下载模型，或缺少 ffmpeg。请查看后端日志。",
            },
        )


@router.get("/speech/status")
def speech_status():
    """检查语音识别服务状态"""
    return {
        "available": speech_service.is_available(),
        "engine": "faster-whisper (local)",
        "model_size": speech_service._model_size,
        "device": speech_service._device,
    }
