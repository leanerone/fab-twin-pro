# -*- coding: utf-8 -*-
"""OpenAI 兼容 Provider（批次2自 ai_middleware.py 拆出）。归属：AI 应用线（朱明钊）。"""
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


class _OpenAIMixin:
    """OpenAI 兼容接口调用 + Function Calling 工具循环。"""

    def _call_openai_compatible(self, question: str, system_prompt: str,
                                history_messages: List[Dict], machine_id: str = None,
                                usage_tracker: Dict = None, 
                                tool_calls_recorder: list = None) -> Dict[str, Any]:
        """调用OpenAI兼容接口（支持GLM、GPT等），带 Function Calling 工具调用

        Args:
            usage_tracker: 外部传入的dict，用于记录token使用量
            tool_calls_recorder: 外部传入的list，用于记录工具调用
        """
        if not self.base_url or not self.api_key:
            return self._local_rule_engine(question, machine_id, tool_calls_record=tool_calls_recorder)

        # 构建消息列表
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history_messages[-40:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        url = self._build_chat_url(self.base_url)

        # 带 tools 的 payload（OpenAI Function Calling）
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
            "tools": TOOL_DEFINITIONS,
            "tool_choice": "auto",
        }

        tool_call_records = []
        max_tool_rounds = 5  # 防止死循环
        tools_supported = True

        # 收集工具结果中的跳转/表格数据（用于最终响应）
        collected_jump_machine_id = None
        collected_jump_timestamp = None
        collected_table_data = None
        # 工具真实执行过的 SQL：此前响应里 "sql" 恒为空，前端展示的来源无从追溯；
        # 真实执行的语句（query_fab_data）要沉上来，装饰性参考语句由下面统一标注。
        collected_sql = None

        try:
            for round_idx in range(max_tool_rounds):
                # 如果当前provider不支持tools，去掉tools参数重试
                if not tools_supported and "tools" in payload:
                    del payload["tools"]
                    del payload["tool_choice"]

                resp = requests.post(url, json=payload, headers=headers, timeout=60)

                # 处理不支持tools的情况（如部分国内API）
                if resp.status_code == 400 and tools_supported:
                    err_text = resp.text.lower()
                    if any(k in err_text for k in ["tools", "tool_choice", "function_call", "invalid parameter"]):
                        print(f"[AI] Provider不支持Function Calling，回退到普通对话模式")
                        tools_supported = False
                        del payload["tools"]
                        del payload["tool_choice"]
                        resp = requests.post(url, json=payload, headers=headers, timeout=60)

                resp.raise_for_status()
                data = resp.json()

                msg = data["choices"][0]["message"]

                # 提取token使用量（每个round累加）
                if usage_tracker is not None and "usage" in data:
                    usage = data["usage"]
                    usage_tracker["prompt_tokens"] += usage.get("prompt_tokens", 0)
                    usage_tracker["completion_tokens"] += usage.get("completion_tokens", 0)
                    usage_tracker["total_tokens"] += usage.get("total_tokens", 0)

                # 如果没有 tool_calls，说明 LLM 已经生成最终回答
                if not msg.get("tool_calls"):
                    answer = msg.get("content", "")

                    # 提取 jump_timestamp
                    jump_ts = None
                    jump_match = re.search(r'\[JUMP:\s*([^\]]+)\]', answer)
                    if jump_match:
                        jump_ts = jump_match.group(1).strip()
                        answer = answer.replace(jump_match.group(0), "").strip()

                    # 优先使用工具结果中的跳转信息
                    final_jump_ts = collected_jump_timestamp or jump_ts
                    final_jump_mid = collected_jump_machine_id or machine_id

                    # 也尝试从answer中解析jump_machine_id
                    mid_match = re.search(r'\[MACHINE:\s*([^\]]+)\]', answer)
                    if mid_match and not collected_jump_machine_id:
                        final_jump_mid = mid_match.group(1).strip()
                        answer = answer.replace(mid_match.group(0), "").strip()

                    return {
                        "answer": answer,
                        "sql": collected_sql or "",
                        "jump_timestamp": final_jump_ts,
                        "jump_machine_id": final_jump_mid,
                        "table_data": collected_table_data,
                        "tool_calls": tool_call_records,
                        "sources": [{"type": "llm", "model": self.model}],
                    }

                # 有 tool_calls：执行工具调用
                # 先把 assistant 的 tool_calls 消息加入对话
                messages.append(msg)

                for tc in msg["tool_calls"]:
                    func_name = tc["function"]["name"]
                    try:
                        func_args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        func_args = {}

                    # 补充 machine_id（如果用户没传但上下文有）
                    if "machine_id" in func_args and not func_args["machine_id"] and machine_id:
                        func_args["machine_id"] = machine_id

                    # 执行工具
                    handler = TOOL_HANDLERS.get(func_name)
                    if handler:
                        db = _get_db()
                        try:
                            result = handler(db, **func_args)
                            # 诚实化 sql 字段：只有真正执行过 SQL 的工具（query_fab_data）才让
                            # 它的语句原样展示；存量工具返回的都是手写参考语句（此前会让用户误以为
                            # 系统真的执行了它），这里统一标注来源。
                            if isinstance(result, dict) and result.get("sql") and func_name != "query_fab_data":
                                result["sql"] = (
                                    "-- 参考查询（本次由 ORM 取数，并未执行此语句）\n"
                                    + str(result["sql"])
                                )
                        finally:
                            db.close()

                        tool_call_record = {
                            "tool": func_name,
                            "args": func_args,
                            "status": "success",
                        }
                        tool_call_records.append(tool_call_record)
                        # 同步到外部记录器
                        if tool_calls_recorder is not None:
                            tool_calls_recorder.append(tool_call_record)

                        # 收集工具结果中的跳转/表格数据
                        if isinstance(result, dict):
                            if result.get("jump_machine_id") and not collected_jump_machine_id:
                                collected_jump_machine_id = result["jump_machine_id"]
                            if result.get("jump_timestamp") and not collected_jump_timestamp:
                                collected_jump_timestamp = result["jump_timestamp"]
                            if result.get("table_data") and not collected_table_data:
                                collected_table_data = result["table_data"]
                            # 只取真实执行过的那条 SQL（query_fab_data），
                            # 存量工具的装饰语句不参与上浮，避免用户误以为它们跑过。
                            if func_name == "query_fab_data" and result.get("sql") and not collected_sql:
                                collected_sql = result["sql"]

                        # 把工具结果中的answer提取出来，附加到LLM可见的上下文末尾
                        # 这样即使LLM遗漏了工具返回的结构化跳转信息，也能通过answer文本传递
                        tool_content = json.dumps(result, ensure_ascii=False, default=str)
                        # 在tool内容末尾附加跳转元信息（供LLM参考）
                        if isinstance(result, dict):
                            extra = {}
                            if result.get("jump_machine_id"):
                                extra["jump_machine_id"] = result["jump_machine_id"]
                            if result.get("jump_timestamp"):
                                extra["jump_timestamp"] = result["jump_timestamp"]
                            if extra:
                                tool_content += f"\n[META] {json.dumps(extra, ensure_ascii=False, default=str)}"

                        # 把工具结果作为 tool 角色消息回传给 LLM
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": tool_content,
                        })
                    else:
                        # 未知工具
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps({"error": f"未知工具: {func_name}"}, ensure_ascii=False, default=str),
                        })
                        unknown_record = {
                            "tool": func_name,
                            "args": func_args,
                            "status": "unknown_tool",
                        }
                        tool_call_records.append(unknown_record)
                        if tool_calls_recorder is not None:
                            tool_calls_recorder.append(unknown_record)

                # 更新 payload 继续下一轮（让 LLM 看到工具结果后生成回答）
                payload["messages"] = messages

            # 超过最大轮数
            return {
                "answer": "（工具调用轮数超限，请缩小问题范围后重试）",
                "sql": "",
                "tool_calls": tool_call_records,
                "sources": [{"type": "llm", "model": self.model}],
            }

        except Exception as e:
            print(f"[AI] OpenAI兼容接口调用失败: {e}")
            raise

    # ==================== Provider: Dify ====================

