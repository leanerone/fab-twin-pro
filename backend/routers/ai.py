"""AI 中间适配层 API（统一接口）

包含：
- /api/ai/chat - 统一聊天接口（推荐）
- /api/ai/query - 旧版查询接口（兼容）
- /api/ai/config - 配置管理
- /api/ai/config/test - 连接测试
- /api/ai/sessions - 会话管理
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from database import get_db
from schemas import (
    AIQueryRequest, AIQueryResponse,
    AIChatRequest, AIChatResponse,
    AIConfigUpdate, AIConfigOut, AIConnectionTest,
)
from services.ai_middleware import ai_middleware
from services import speech_service

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ========== 统一聊天接口（新版） ==========

@router.post("/chat", response_model=AIChatResponse)
def ai_chat(req: AIChatRequest, db: Session = Depends(get_db)):
    """统一AI聊天接口 - 支持多模型、Dify、N8N联动

    - 本地规则引擎（默认，无需配置）
    - OpenAI兼容模型（GLM-5.2、GPT系列、本地私有化模型）
    - Dify 应用对接
    - N8N 工作流联动（管理员权限）
    """
    result = ai_middleware.chat(
        question=req.question,
        session_id=req.session_id,
        machine_id=req.machine_id,
        context=req.context,
        user_role=req.user_role or "user",
    )
    result["provider"] = ai_middleware.provider
    return AIChatResponse(**result)


# ========== 旧版兼容接口 ==========

@router.post("/query", response_model=AIQueryResponse)
def ai_query(req: AIQueryRequest, db: Session = Depends(get_db)):
    """旧版AI查询接口（兼容保留）

    内部转发到统一聊天接口
    """
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


# ========== 配置管理 ==========

@router.get("/config", response_model=AIConfigOut)
def get_ai_config():
    """获取AI配置（脱敏）"""
    config = ai_middleware.get_config()
    return AIConfigOut(**config)


@router.put("/config", response_model=dict)
def update_ai_config(config: AIConfigUpdate):
    """更新AI配置（运行时更新）"""
    config_dict = config.model_dump(exclude_none=True)
    success = ai_middleware.update_config(config_dict)
    if not success:
        raise HTTPException(status_code=400, detail="配置更新失败")
    return {"success": True, "message": "配置更新成功"}


@router.post("/config/test", response_model=dict)
def test_ai_connection(test_req: AIConnectionTest):
    """测试AI服务连接"""
    result = ai_middleware.test_connection(
        provider_type=test_req.provider_type,
        config=test_req.config,
    )
    return result


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
