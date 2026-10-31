# -*- coding: utf-8 -*-
"""N8N Provider（批次2自 ai_middleware.py 拆出）：webhook 触发。
归属：AI 应用线（朱明钊）。"""
import os
import re
import json
import time
import uuid
import asyncio
import logging
import httpx
import requests
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger("fabtwin.ai_middleware")

from config import (
    AI_MCP_ENABLED, AI_MCP_URL, AI_MCP_API_KEY,
    AI_PROVIDER, AI_BASE_URL, AI_API_KEY, AI_MODEL,
    AI_TEMPERATURE, AI_MAX_TOKENS,
    DIFY_ENABLED, DIFY_BASE_URL, DIFY_API_KEY, DIFY_APP_ID,
    N8N_ENABLED, N8N_BASE_URL, N8N_WEBHOOK_SECRET,
)
from services.ai.config_store import _get_db, PROVIDER_PRESETS, CONFIG_KEYS
from services.ai.tools import (
    get_machine_status,
    get_machine_alarms,
    get_event_timeline,
    get_yield_stats,
    get_lot_info,
    get_recipe_info,
    TOOL_DEFINITIONS,
    TOOL_HANDLERS,
)


class _N8nMixin:
    """N8N 工作流触发与结果等待。"""

    def _trigger_n8n_workflow(self, question: str, machine_id: str = None,
                              user_role: str = "user", workflow_type: str = None,
                              usage_tracker: Dict = None,
                              tool_calls_recorder: List = None) -> Dict[str, Any]:
        """触发N8N工作流
        - 通过 Webhook 调用 n8n 工作流，支持 5 种 workflow_type
        - 解析 n8n 返回的执行元数据（executionId / duration）写入 tool_calls_recorder
        - 解析 n8n 返回的 token usage（若 n8n 内部调用了 LLM 节点）回写 usage_tracker
        """
        if user_role != "admin":
            if tool_calls_recorder is not None:
                tool_calls_recorder.append({
                    "tool": "n8n_workflow", "status": "denied",
                    "reason": "需要管理员权限",
                })
            return {
                "answer": "抱歉，自动化流程操作需要管理员权限。请联系管理员。",
                "sql": "",
            }

        if not self.n8n_enabled or not self.n8n_base_url:
            if tool_calls_recorder is not None:
                tool_calls_recorder.append({
                    "tool": "n8n_workflow", "status": "skip",
                    "reason": "N8N 未启用或缺少配置",
                })
            return {
                "answer": (
                    "N8N 自动化服务未配置。\n"
                    "请在 AI 配置面板中配置 N8N 服务地址后使用此功能。\n\n"
                    "支持的自动化流程：\n"
                    "• 导出报警报表\n"
                    "• 生成故障工单\n"
                    "• 批量导出设备数据\n"
                    "• 产线报表自动推送"
                ),
                "sql": "",
            }

        # 识别工作流类型
        if not workflow_type:
            if "导出" in question and ("报警" in question or "告警" in question):
                workflow_type = "export_alarm_report"
            elif "工单" in question or "故障" in question:
                workflow_type = "generate_work_order"
            elif "导出" in question and "数据" in question:
                workflow_type = "export_machine_data"
            elif "报表" in question and "推送" in question:
                workflow_type = "push_daily_report"
            else:
                workflow_type = "general_query"

        try:
            base = self.n8n_base_url.rstrip('/')
            webhook_url = f"{base}/webhook/{workflow_type}"
            if self.n8n_webhook_secret:
                webhook_url += f"?secret={self.n8n_webhook_secret}"

            payload = {
                "question": question,
                "machine_id": machine_id,
                "user_role": user_role,
                "workflow_type": workflow_type,
                "timestamp": datetime.now().isoformat(),
            }

            resp = requests.post(webhook_url, json=payload, timeout=120)
            resp.raise_for_status()
            result_data = resp.json()

            answer = result_data.get("answer", result_data.get("message", "工作流已触发，请稍候查看结果。"))

            # 解析 n8n 返回的 token usage（n8n 内部 LLM 节点可能返回）
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            n8n_usage = result_data.get("usage") or result_data.get("token_usage") or {}
            if isinstance(n8n_usage, dict):
                prompt_tokens = int(n8n_usage.get("prompt_tokens") or n8n_usage.get("input_tokens") or 0)
                completion_tokens = int(n8n_usage.get("completion_tokens") or n8n_usage.get("output_tokens") or 0)
                total_tokens = int(n8n_usage.get("total_tokens") or 0)
                if total_tokens == 0:
                    total_tokens = prompt_tokens + completion_tokens

            if usage_tracker is not None:
                usage_tracker["prompt_tokens"] = prompt_tokens
                usage_tracker["completion_tokens"] = completion_tokens
                usage_tracker["total_tokens"] = total_tokens

            # 解析表格数据
            table_data = None
            if "data" in result_data and isinstance(result_data["data"], list):
                if result_data["data"] and isinstance(result_data["data"][0], dict):
                    headers = list(result_data["data"][0].keys())
                    rows = [list(item.values()) for item in result_data["data"][:20]]
                    table_data = {"headers": headers, "rows": rows}

            # 记录工具调用详情
            if tool_calls_recorder is not None:
                tool_calls_recorder.append({
                    "tool": f"n8n_{workflow_type}",
                    "status": "success",
                    "execution_id": result_data.get("executionId") or result_data.get("execution_id"),
                    "duration_ms": result_data.get("duration") or result_data.get("elapsed_ms"),
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "rows_count": len(result_data["data"]) if isinstance(result_data.get("data"), list) else 0,
                })

            return {
                "answer": f"🤖 [N8N自动化] {answer}",
                "sql": result_data.get("sql", ""),
                "table_data": table_data,
                "sources": [{"type": "n8n", "workflow": workflow_type}],
            }
        except requests.HTTPError as e:
            body = ""
            try:
                body = e.response.text[:500]
            except Exception:
                pass
            print(f"[AI] N8N调用失败 HTTP {e.response.status_code}: {body}")
            if tool_calls_recorder is not None:
                tool_calls_recorder.append({
                    "tool": f"n8n_{workflow_type}", "status": "error",
                    "error": f"HTTP {e.response.status_code}: {body[:200]}",
                })
            return {
                "answer": f"⚠️ N8N 工作流调用失败（HTTP {e.response.status_code}）：{body[:200]}\n\n请检查 N8N 服务配置和网络连接。",
                "sql": "",
            }
        except Exception as e:
            print(f"[AI] N8N调用失败: {e}")
            if tool_calls_recorder is not None:
                tool_calls_recorder.append({
                    "tool": f"n8n_{workflow_type}", "status": "error",
                    "error": str(e)[:200],
                })
            return {
                "answer": f"⚠️ N8N 工作流调用失败：{str(e)}\n\n请检查 N8N 服务配置和网络连接。",
                "sql": "",
            }

    # ==================== 配置管理 ====================

