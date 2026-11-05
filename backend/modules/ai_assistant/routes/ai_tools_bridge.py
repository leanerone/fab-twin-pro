# -*- coding: utf-8 -*-
"""AI 工具桥路由（T4 2026-11-06）：本地数据工具的 REST 暴露

目的：打破「走 Dify 就用不上本地 12+2 工具」的割裂——
  1. GET  /api/ai/tools                 工具清单（名称/描述/参数）
  2. POST /api/ai/tools/{name}          执行单个工具（登录即可，只读）
  3. GET  /api/ai/tools/openapi.json    Dify「自定义工具→导入OpenAPI-Spec」直接可用的规范

Dify 接入步骤（写进 NIGHT_REPORT）：
  Dify → 工具 → 自定义 → 导入 OpenAPI → 粘贴 openapi.json 内容
  → 鉴权方式选 API Key / Bearer，填后端服务账号 token
  → 在 Dify 应用里挂上这些工具 → 机台专属 Dify 即拥有全部本地取数能力
"""
import json
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from models import User
from modules.system_admin.routes.auth import get_current_user
from modules.ai_assistant.services import tool_bridge
from modules.ai_assistant.services.sql import SqlSafetyError

router = APIRouter(
    prefix="/api/ai/tools",
    tags=["ai-tools"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
def list_tools():
    """工具清单（前端/运维可视化用）"""
    return {"count": 0, "tools": tool_bridge.list_tool_metas()}


@router.post("/{name}")
def call_tool(name: str, body: Dict[str, Any] = Body(default=None),
              user: User = Depends(get_current_user)):
    """执行单个工具（与 LLM Function Calling 同一实现、同一只读边界）"""
    meta = tool_bridge.get_tool_meta(name)
    if not meta:
        raise HTTPException(status_code=404, detail=f"未知工具: {name}")
    try:
        result = tool_bridge.execute_tool(name, body)
    except SqlSafetyError as e:
        raise HTTPException(status_code=400, detail=f"SQL 安全拦截: {e}")
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except TypeError as e:
        raise HTTPException(status_code=400, detail=f"参数不合法: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"工具执行失败: {str(e)[:300]}")
    return JSONResponse(content=result)


@router.get("/openapi.json")
def openapi_spec(request: Request):
    """生成 Dify 自定义工具可导入的 OpenAPI 3.0 规范

    每个工具 = 一个 POST path，requestBody 即参数 schema；
    servers 取当前请求的 base url（内网直连后端时即为 http://host:8002）。
    """
    base = str(request.base_url).rstrip("/")
    # 反代场景下优先取外部访问头
    forwarded_host = request.headers.get("x-forwarded-host")
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_host:
        base = f"{forwarded_proto or 'http'}://{forwarded_host}"

    paths: Dict[str, Any] = {}
    for meta in tool_bridge.list_tool_metas():
        name = meta["name"]
        params = meta["parameters"] or {"type": "object", "properties": {}}
        paths[f"/api/ai/tools/{name}"] = {
            "post": {
                "operationId": name,
                "summary": name,
                "description": meta["description"][:1000],
                "requestBody": {
                    "required": False,
                    "content": {"application/json": {"schema": params}},
                },
                "responses": {
                    "200": {
                        "description": "工具执行结果",
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    }
                },
            }
        }

    spec = {
        "openapi": "3.0.1",
        "info": {
            "title": "FabTwin 本地数据工具集",
            "description": (
                "FabTwin 数字孪生平台本地数据工具（与 AI 助手 Function Calling 同一实现）。"
                "全部只读；调用前请在 Dify 鉴权设置中配置 Bearer token（后端登录账号）。"
            ),
            "version": "1.0.0",
        },
        "servers": [{"url": base}],
        "paths": paths,
        # 让 Dify 对所有工具统一带 Authorization
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"}
            }
        },
        "security": [{"bearerAuth": []}],
    }
    return JSONResponse(content=spec, media_type="application/json")
