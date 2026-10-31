# -*- coding: utf-8 -*-
"""AI 中间件门面（批次2拆包后剩余的编排核心）。

统一请求/返回结构，按配置路由到 [本地规则引擎 / OpenAI兼容 / Dify / N8N]。
各 Provider 的实现见 providers/，配置存储见 config_store.py，用量见 usage.py。
"""
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
from services.ai.config_store import _ConfigMixin
from services.ai.conversations import _ConversationsMixin
from services.ai.providers.openai import _OpenAIMixin
from services.ai.providers.dify import _DifyMixin
from services.ai.providers.n8n import _N8nMixin
from services.ai.usage import _UsageMixin


class AIMiddleware(_ConfigMixin, _ConversationsMixin, _OpenAIMixin, _DifyMixin, _N8nMixin, _UsageMixin):
    """AI 中间适配层 - 统一调度入口

    架构升级：支持多AI配置管理
    - LLM配置存储在 ai_provider_configs 表中，支持多配置切换
    - Dify/N8N配置仍存储在 ai_configs 键值对表中
    - Token使用量记录在 ai_usage_logs 表中
    """

    def __init__(self):
        # LLM配置（从 ai_provider_configs 加载）
        self.provider = AI_PROVIDER
        self.base_url = AI_BASE_URL
        self.api_key = AI_API_KEY
        self.model = AI_MODEL
        self.temperature = AI_TEMPERATURE
        self.max_tokens = AI_MAX_TOKENS
        self.provider_name = ""
        self.current_config_id = None  # 当前使用的配置ID

        # Dify配置（从 ai_configs 键值对表加载）
        self.dify_enabled = DIFY_ENABLED
        self.dify_base_url = DIFY_BASE_URL
        self.dify_api_key = DIFY_API_KEY
        self.dify_app_id = DIFY_APP_ID

        # N8N配置（从 ai_configs 键值对表加载）
        self.n8n_enabled = N8N_ENABLED
        self.n8n_base_url = N8N_BASE_URL
        self.n8n_webhook_secret = N8N_WEBHOOK_SECRET

        # 会话存储（内存中）
        self.sessions = {}
        # 前端 session_id (sess_xxx) → Dify conversation_id (UUID) 映射
        # 原因: Dify conversation_id 必须是 UUID, 且首次对话不能传, 由 Dify 返回。
        # 若传前端自己生成的 sess_xxx（非 UUID），Dify 会报:
        #   "conversation_id must be a valid UUID"
        self._dify_conv_map: Dict[str, str] = {}

        # 启动时加载配置
        self._load_dify_n8n_from_db()  # 加载Dify/N8N
        self._load_llm_config()         # 加载LLM默认配置
        self._cleanup_old_conversations()  # T5: 清理7天未更新的会话映射（表未建则跳过）


    def chat(self, question: str, session_id: str = None, machine_id: str = None,
             context: Dict = None, user_role: str = "user", config_id: int = None) -> Dict[str, Any]:
        """统一聊天入口

        Args:
            question: 用户问题
            session_id: 会话ID，不传则新建
            machine_id: 关联机台ID
            context: 额外上下文数据
            user_role: 用户角色（user/admin）
            config_id: 指定使用的AI配置ID（None则使用默认配置）

        Returns:
            统一响应结构体（含 provider_name、model、usage）
        """
        if not session_id:
            session_id = f"sess_{uuid.uuid4().hex[:16]}"

        # 如有指定config_id，切换到对应配置
        if config_id and config_id != self.current_config_id:
            self._load_llm_config(config_id)

        # 机台专属 Dify 路由（test31 重构：请求级配置，不再就地改写 self.* ——
        # 原实现两个用户对不同机台同时提问会互相覆盖 provider/base_url/key，
        # 且命中后的状态会"粘"在单例上影响后续请求）
        machine_dify = None
        if not config_id and machine_id:
            machine_dify = self._get_machine_dify_config(machine_id)
        if machine_dify:
            dify_cfg = {
                "enabled": True,  # 命中专属Dify必须显式启用，否则_call_dify守卫失败
                "base_url": machine_dify.get("dify_base_url", ""),
                "api_key": machine_dify.get("dify_api_key", ""),
                "provider_name": machine_dify.get("config_name", "Dify"),
                "model": f"dify-{machine_dify.get('config_name', '')}",
            }
            route_provider = "dify"
            print(f"[AI] 机台 {machine_id} 命中专属 Dify: {dify_cfg['provider_name']}, "
                  f"url={dify_cfg['base_url']!r}, key_len={len(dify_cfg['api_key'] or '')}")
        else:
            dify_cfg = None
            route_provider = self.provider
            # 没有专属配置，确保用默认配置
            if not config_id and not self.current_config_id:
                self._load_default_config()
                route_provider = self.provider

        # 获取或创建会话
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "messages": [],
                "created_at": datetime.now().isoformat(),
                "machine_id": machine_id,
            }
        session = self.sessions[session_id]

        # 保存用户消息
        session["messages"].append({
            "role": "user",
            "content": question,
            "timestamp": datetime.now().isoformat(),
        })

        # 构建系统提示词（带上下文）
        system_prompt = self._build_system_prompt(machine_id, context, user_role)

        # 路由到不同provider
        openai_compatible_providers = {"openai", "zhipu", "deepseek", "qwen", "custom"}

        result = None
        success = True
        error_msg = None
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        # 执行日志追踪
        execution_log = []
        tool_calls_record = []
        execution_log.append({"step": "start", "provider": route_provider, "timestamp": datetime.now().isoformat()})

        # 记录路由决策
        if route_provider in openai_compatible_providers and self.base_url and self.api_key:
            execution_log.append({"step": "route", "decision": "llm", "provider": route_provider, "model": self.model})
        elif route_provider in openai_compatible_providers:
            execution_log.append({"step": "route", "decision": "fallback_local", "reason": "缺少 base_url 或 api_key"})
        else:
            execution_log.append({"step": "route", "decision": "local_rule_engine", "provider": route_provider})

        try:
            # 管理员显式自动化指令统一前置到 N8N，避免 custom/OpenAI 路由绕过；
            # 命中后直接返回，不再进入本地规则或 LLM，确保只触发一次。
            if user_role == "admin" and self._is_n8n_command(question.lower()):
                execution_log.append({"step": "match_intent", "intent": "n8n_command"})
                result = self._trigger_n8n_workflow(
                    question, machine_id, user_role,
                    usage_tracker=usage, tool_calls_recorder=tool_calls_record,
                )
            elif route_provider in openai_compatible_providers and self.base_url and self.api_key:
                execution_log.append({"step": "call_llm", "url": self._build_chat_url(self.base_url)})
                result = self._call_openai_compatible(
                    question, system_prompt, session["messages"], machine_id,
                    usage_tracker=usage, tool_calls_recorder=tool_calls_record
                )
                execution_log.append({"step": "llm_done", "tool_calls_count": len(tool_calls_record)})
            elif route_provider in openai_compatible_providers:
                print(f"[AI] provider={route_provider} 但未配置 base_url 或 api_key，回退本地规则")
                execution_log.append({"step": "fallback", "reason": "缺少 base_url 或 api_key"})
                result = self._local_rule_engine(question, machine_id, user_role, execution_log=execution_log, tool_calls_record=tool_calls_record, usage_tracker=usage)
            elif route_provider == "dify":
                execution_log.append({"step": "call_dify"})
                result = self._call_dify(
                    question, session_id, machine_id, user_role,
                    usage_tracker=usage, tool_calls_recorder=tool_calls_record,
                    dify_cfg=dify_cfg,
                )
            elif route_provider == "hybrid":
                try:
                    execution_log.append({"step": "call_dify_hybrid"})
                    result = self._call_dify(
                        question, session_id, machine_id, user_role,
                        usage_tracker=usage, tool_calls_recorder=tool_calls_record,
                        dify_cfg=dify_cfg,
                    )
                except Exception as e:
                    print(f"[AI] Dify调用失败，回退本地规则: {e}")
                    execution_log.append({"step": "fallback", "reason": f"Dify失败: {str(e)[:100]}"})
                    success = False
                    error_msg = f"Dify调用失败，回退本地规则: {str(e)}"
                    result = self._local_rule_engine(question, machine_id, user_role, execution_log=execution_log, tool_calls_record=tool_calls_record, usage_tracker=usage)
            else:
                execution_log.append({"step": "call_local_rule"})
                result = self._local_rule_engine(question, machine_id, user_role, execution_log=execution_log, tool_calls_record=tool_calls_record, usage_tracker=usage)
        except Exception as e:
            print(f"[AI] 调用失败: {e}")
            execution_log.append({"step": "error", "error": str(e)[:200]})
            success = False
            error_msg = str(e)
            # 纯 Dify 模式：不做本地规则兜底，直接返回错误，便于调试真实 Dify 响应
            if route_provider == "dify":
                result = {
                    "answer": (
                        f"❌ Dify 调用失败，未做本地兜底。\n"
                        f"错误详情：{str(e)[:300]}\n\n"
                        f"请检查 Dify 服务状态、API Key、Base URL 是否正确。"
                    ),
                    "sql": "",
                }
            else:
                try:
                    result = self._local_rule_engine(question, machine_id, user_role, execution_log=execution_log, tool_calls_record=tool_calls_record, usage_tracker=usage)
                except Exception as e2:
                    print(f"[AI] 本地规则引擎也失败: {e2}")
                    execution_log.append({"step": "error", "error": f"本地规则引擎也失败: {str(e2)[:200]}"})
                    result = {
                        "answer": f"抱歉，AI 服务暂时不可用。\n错误详情：{str(e)[:200]}\n\n请稍后重试，或联系管理员检查 AI 配置。",
                        "sql": "",
                    }
                    success = False
                    error_msg = f"双重失败: LLM={str(e)[:100]}, 本地={str(e2)[:100]}"

        # 确保返回格式统一
        result = self._normalize_response(result)

        # 注入当前Provider信息到响应（机台专属路由用请求级配置，其余用单例当前值）
        result["provider"] = route_provider
        result["provider_name"] = (dify_cfg or {}).get("provider_name") or self.provider_name or self._infer_provider_name()
        result["model"] = (dify_cfg or {}).get("model") or self.model
        result["config_id"] = None if machine_dify else self.current_config_id
        result["usage"] = usage
        result["tool_calls"] = tool_calls_record

        # 保存AI回复
        session["messages"].append({
            "role": "assistant",
            "content": result.get("answer", ""),
            "timestamp": datetime.now().isoformat(),
            "metadata": {k: v for k, v in result.items() if k != "answer"},
        })

        # 限制会话历史长度
        if len(session["messages"]) > 100:
            session["messages"] = session["messages"][-100:]

        result["session_id"] = session_id

        # 记录使用量和执行日志
        try:
            self._log_usage(
                session_id=session_id,
                config_id=None if machine_dify else self.current_config_id,
                provider=route_provider,
                provider_name=(dify_cfg or {}).get("provider_name") or self.provider_name or self._infer_provider_name(),
                model=(dify_cfg or {}).get("model") or self.model,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                question_preview=question[:500],
                answer_preview=result.get("answer", "")[:500],
                success=success,
                error_msg=error_msg,
                tool_calls=tool_calls_record,
                execution_log=execution_log,
            )
        except Exception as e:
            print(f"[AI] 使用量记录失败: {e}")
            import traceback
            traceback.print_exc()

        return result

    # ==================== 流式聊天（SSE 透传，T4） ====================
    #
    # 后端 → 前端帧协议（每帧一行 "data: {json}\n\n"）：
    #   透传帧：Dify 原始事件（agent_message 正文分片 / agent_thought 工具过程 /
    #           message_end usage / retriever_resources RAG 引用 等）
    #   错误帧：{"event": "error", "message": "..."}
    #   收尾帧：{"event": "final", "session_id":..., "answer": 完整干净正文,
    #           "jump_timestamp":..., "jump_machine_id":..., "table_data":...,
    #           "sources":[...], "tool_calls":[...], "usage":{...},
    #           "provider":..., "provider_name":..., "model":..., "config_id":...,
    #           "success": true|false}
    #   结束标记：data: [DONE]
    #
    # 路由策略：Dify 走 _stream_dify() 逐 chunk 透传；非 Dify（本地规则 /
    # OpenAI 兼容）委托 chat() 同步执行后包装单帧下发——前端只需一套渲染逻辑。

    _FAB_TAG = "<FABTWIN>"

    @staticmethod
    def _sse_line(obj) -> str:
        """事件对象编码为一帧 SSE data 行"""
        return "data: " + json.dumps(obj, ensure_ascii=False, default=str) + "\n\n"

    def _parse_fab_block(self, fab_text: str, tool_calls_recorder: list = None):
        """解析 <FABTWIN>{...}</FABTWIN> 块 → (jump_ts, jump_mid, table_data, extra_sources)。
        解析失败/格式不合法时对应字段返回 None，并记录到 tool_calls_recorder。"""
        m = re.search(r'<FABTWIN>\s*(\{.*?\})\s*</FABTWIN>', fab_text or "", re.DOTALL)
        if not m:
            # 无闭合标签（流被截断）→ 宽松提取首个 JSON 对象尝试解析
            m = re.search(r'<FABTWIN>\s*(\{.*)', fab_text or "", re.DOTALL)
        if not m:
            return None, None, None, None
        try:
            block = json.loads(m.group(1))
        except Exception as e:
            if tool_calls_recorder is not None:
                tool_calls_recorder.append({
                    "tool": "fabtwin_structured_parse", "status": "error",
                    "error": f"<FABTWIN> JSON 解析失败: {str(e)[:200]}",
                    "raw": m.group(1)[:300],
                })
            return None, None, None, None
        if not isinstance(block, dict):
            return None, None, None, None
        jump_ts = jump_mid = None
        table_data = None
        extra_sources = None
        td = block.get("table_data")
        if td is not None:
            if isinstance(td, dict) and isinstance(td.get("headers"), list) and isinstance(td.get("rows"), list):
                table_data = td
            elif tool_calls_recorder is not None:
                tool_calls_recorder.append({
                    "tool": "fabtwin_structured_parse", "status": "warn",
                    "warn": f"table_data 格式不合法，丢弃: {str(td)[:200]}",
                })
        if block.get("jump_timestamp"):
            jump_ts = str(block["jump_timestamp"]).strip() or None
        if block.get("jump_machine_id"):
            jump_mid = str(block["jump_machine_id"]).strip() or None
        es = block.get("sources")
        if isinstance(es, list):
            extra_sources = es
        return jump_ts, jump_mid, table_data, extra_sources

    async def chat_stream(self, question: str, session_id: str = None, machine_id: str = None,
                          context: Dict = None, user_role: str = "user", config_id: int = None):
        """流式聊天入口（异步生成器），逐帧 yield SSE data 行字符串。

        Dify 路由：_stream_dify() 逐 chunk 透传，自管会话保存与 usage 日志；
        非 Dify 路由：委托 chat() 同步执行（它自管会话/日志），结果包装单帧。
        收尾总是发 final 帧 + [DONE]。
        """
        if not session_id:
            session_id = f"sess_{uuid.uuid4().hex[:16]}"

        # ---- 路由判定（不改状态）：机台专属 Dify 命中 或 全局 dify/hybrid ----
        machine_dify = None
        if not config_id and machine_id:
            machine_dify = self._get_machine_dify_config(machine_id)
        route_is_dify = bool(machine_dify) or self.provider in ("dify", "hybrid")

        if not route_is_dify:
            # 非 Dify：同步 chat() 仅在短任务期间占用工作线程，不阻塞事件循环
            result = None
            try:
                result = await asyncio.to_thread(
                    self.chat, question, session_id, machine_id, context, user_role, config_id
                )
            except Exception as e:
                yield self._sse_line({"event": "error", "message": str(e)[:300]})
                yield self._sse_line({
                    "event": "final", "session_id": session_id,
                    "answer": f"抱歉，AI 服务暂时不可用。\n错误详情：{str(e)[:200]}",
                    "success": False,
                })
                yield "data: [DONE]\n\n"
                return
            answer = result.get("answer", "")
            if answer:
                yield self._sse_line({"event": "agent_message", "answer": answer})
            yield self._sse_line({
                "event": "final",
                "session_id": result.get("session_id", session_id),
                "answer": answer,
                "sql": result.get("sql", ""),
                "jump_timestamp": result.get("jump_timestamp"),
                "jump_machine_id": result.get("jump_machine_id"),
                "machine_online": result.get("machine_online"),
                "table_data": result.get("table_data"),
                "tool_calls": result.get("tool_calls", []),
                "sources": result.get("sources", []),
                "usage": result.get("usage", {}),
                "provider": result.get("provider"),
                "provider_name": result.get("provider_name"),
                "model": result.get("model"),
                "config_id": result.get("config_id"),
                "success": True,
            })
            yield "data: [DONE]\n\n"
            return

        # ==================== Dify 流式分支（自管会话与日志） ====================
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        tool_calls_record = []
        execution_log = [{"step": "start_stream", "provider": "dify", "timestamp": datetime.now().isoformat()}]
        success = True
        error_msg = None

        # 路由配置（test31：请求级，不再改写 self —— 见 chat() 同名注释）
        if machine_dify:
            dify_cfg = {
                "enabled": True,
                "base_url": machine_dify.get("dify_base_url", ""),
                "api_key": machine_dify.get("dify_api_key", ""),
                "provider_name": machine_dify.get("config_name", "Dify"),
                "model": f"dify-{machine_dify.get('config_name', '')}",
            }
            route_provider = "dify"
            execution_log.append({"step": "route", "decision": "machine_dify", "config": dify_cfg["provider_name"]})
            print(f"[AI-stream] 机台 {machine_id} 命中专属 Dify: {dify_cfg['provider_name']}")
        else:
            dify_cfg = None
            route_provider = self.provider  # dify / hybrid

        # 会话：保存用户消息
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "messages": [],
                "created_at": datetime.now().isoformat(),
                "machine_id": machine_id,
            }
        session = self.sessions[session_id]
        session["messages"].append({
            "role": "user", "content": question, "timestamp": datetime.now().isoformat(),
        })

        # 逐 chunk 透传
        execution_log.append({"step": "call_dify_stream"})
        stream_result = {}
        try:
            async for evt in self._stream_dify(
                question, session_id, machine_id, user_role,
                stream_result=stream_result,
                dify_cfg=dify_cfg,
            ):
                yield self._sse_line(evt)
        except Exception as e:
            print(f"[AI-stream] Dify 流式调用失败: {e}")
            execution_log.append({"step": "error", "error": str(e)[:200]})
            success = False
            error_msg = str(e)
            if route_provider == "hybrid":
                # hybrid：回退本地规则（与 chat() 一致）
                execution_log.append({"step": "fallback", "reason": f"Dify失败: {str(e)[:100]}"})
                try:
                    lr = self._local_rule_engine(
                        question, machine_id, user_role,
                        execution_log=execution_log, tool_calls_record=tool_calls_record,
                        usage_tracker=usage,
                    )
                    lr = self._normalize_response(lr)
                    stream_result["answer"] = lr.get("answer", "")
                    if stream_result["answer"]:
                        yield self._sse_line({"event": "agent_message", "answer": stream_result["answer"]})
                except Exception as e2:
                    stream_result["answer"] = f"抱歉，AI 服务暂时不可用。\n错误详情：{str(e)[:200]}"
                    error_msg = f"双重失败: Dify={str(e)[:100]}, 本地={str(e2)[:100]}"
            else:
                # 纯 Dify：不兜底本地规则，直接错误帧（与 chat() 行为一致）
                err_text = (
                    f"❌ Dify 调用失败，未做本地兜底。\n"
                    f"错误详情：{str(e)[:300]}\n\n"
                    f"请检查 Dify 服务状态、API Key、Base URL 是否正确。"
                )
                stream_result["answer"] = err_text
                yield self._sse_line({"event": "error", "message": str(e)[:300]})
                yield self._sse_line({"event": "agent_message", "answer": err_text})

        # ---- 收尾：会话映射 / usage 截获 / FABTWIN 与旧标记解析 ----
        # 整段包 try：任何收尾异常（日志编码、FABTWIN 解析、session 保存等）
        # 都不允许阻断下面的 final 帧 + [DONE]，否则前端永远卡在"思考中"。
        dify_returned_cid = stream_result.get("conversation_id")
        answer = stream_result.get("answer", "")
        jump_ts = jump_mid = None
        table_data = None
        sources = [{"type": "dify", "app_id": self.dify_app_id}]
        try:
            sid_key = str(session_id).strip()
            if sid_key and dify_returned_cid:
                self._conv_put(sid_key, dify_returned_cid, machine_id=machine_id)
                print(f"[Dify-stream] [OK] 会话映射已保存: {sid_key} -> {dify_returned_cid}")

            mu = stream_result.get("usage") or {}
            if isinstance(mu, dict):
                usage["prompt_tokens"] = int(mu.get("prompt_tokens") or mu.get("input_tokens") or 0)
                usage["completion_tokens"] = int(mu.get("completion_tokens") or mu.get("output_tokens") or 0)
                usage["total_tokens"] = int(mu.get("total_tokens") or 0)
                if usage["total_tokens"] == 0:
                    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

            # 去复述：首行完全等于用户问题时删该行（与 _call_dify 一致）
            q_norm = (question or "").strip()
            if q_norm and answer:
                a_norm = answer.strip()
                first_line = a_norm.split("\n")[0].strip() if a_norm else ""
                if first_line == q_norm:
                    rest = a_norm[len(first_line):].lstrip("\n").strip()
                    if len(rest) >= 2:
                        answer = rest

            extra_sources = None
            if stream_result.get("fab_text"):
                jump_ts, jump_mid, table_data, extra_sources = self._parse_fab_block(
                    stream_result["fab_text"], tool_calls_record)
            # 旧 [JUMP]/[MACHINE] 标记兜底：流式透传未过滤（正文可能已展示），
            # final 帧给出剔除后的干净版，前端用 final.answer 整体校正
            jm = re.search(r'\[JUMP:\s*([^\]]+)\]', answer)
            if jm:
                jump_ts = jump_ts or jm.group(1).strip()
                answer = re.sub(r'\[JUMP:\s*[^\]]+\]', '', answer).strip()
            mm = re.search(r'\[MACHINE:\s*([^\]]+)\]', answer)
            if mm:
                jump_mid = jump_mid or mm.group(1).strip()
                answer = re.sub(r'\[MACHINE:\s*[^\]]+\]', '', answer).strip()

            # sources：Dify 应用 + RAG 引用 + FABTWIN 扩展来源
            for i, doc in enumerate((stream_result.get("rag_records") or [])[:10]):
                score = doc.get("score") or doc.get("rerank_score")
                sources.append({
                    "type": "rag",
                    "doc_id": doc.get("id") or doc.get("document_id") or doc.get("segment_id") or f"rag_{i}",
                    "doc_name": doc.get("name") or doc.get("document_name") or doc.get("title") or f"文档{i+1}",
                    "content": (doc.get("content") or doc.get("text") or doc.get("segment_content") or "")[:500],
                    "page": doc.get("page") or doc.get("page_number"),
                    "score": float(score) if score is not None else None,
                })
            if isinstance(extra_sources, list) and extra_sources:
                sources.extend([s for s in extra_sources if isinstance(s, dict)])

            tool_calls_record.append({
                "tool": "dify_chat",
                "status": "success" if success else "error",
                "conversation_id": dify_returned_cid or session_id,
                "input_tokens": usage["prompt_tokens"],
                "output_tokens": usage["completion_tokens"],
                "streamed": True,
            })

            # 保存 AI 回复 + 截断历史
            session["messages"].append({
                "role": "assistant", "content": answer, "timestamp": datetime.now().isoformat(),
                "metadata": {"streamed": True},
            })
            if len(session["messages"]) > 100:
                session["messages"] = session["messages"][-100:]

            # 使用量与执行日志
            try:
                self._log_usage(
                    session_id=session_id,
                    config_id=None if machine_dify else self.current_config_id,
                    provider=route_provider,
                    provider_name=(dify_cfg or {}).get("provider_name") or self.provider_name or self._infer_provider_name(),
                    model=(dify_cfg or {}).get("model") or self.model,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    question_preview=question[:500],
                    answer_preview=answer[:500],
                    success=success,
                    error_msg=error_msg,
                    tool_calls=tool_calls_record,
                    execution_log=execution_log,
                )
            except Exception as e:
                print(f"[AI-stream] 使用量记录失败: {e}")
        except Exception as e:
            # 收尾段异常：answer 可能已被部分处理（JUMP 标记剔除等），
            # 但仍必须把已收到的内容通过 final 帧交付，绝不让前端裸等。
            print(f"[AI-stream] 收尾处理异常（final 帧仍发送）: {type(e).__name__}: {e}")
            execution_log.append({"step": "finalize_error", "error": str(e)[:200]})

        yield self._sse_line({
            "event": "final",
            "session_id": session_id,
            "answer": answer,
            "sql": "",
            "jump_timestamp": jump_ts,
            "jump_machine_id": jump_mid or machine_id,
            "machine_online": None,
            "table_data": table_data,
            "tool_calls": tool_calls_record,
            "sources": sources,
            "usage": usage,
            "provider": route_provider,
            "provider_name": (dify_cfg or {}).get("provider_name") or self.provider_name or self._infer_provider_name(),
            "model": (dify_cfg or {}).get("model") or self.model,
            "config_id": None if machine_dify else self.current_config_id,
            "success": success,
        })
        yield "data: [DONE]\n\n"

    def _build_system_prompt(self, machine_id: str = None, context: Dict = None,
                             user_role: str = "user") -> str:
        """构建系统提示词"""
        prompt = """你是一个半导体工厂数字孪生平台的AI助手，名为FabTwin AI。
你可以回答关于机台状态、生产数据、报警信息、Lot追踪、工艺配方等问题。

重要说明：
- 当前系统采集的是VFEI事件流（POD开盖/关盖/端口锁定等），不含温度/压力/RF等传感器数据
- 但已接入 MES 系统（通过 N8N MCP），可查询 Lot 的产品/工艺/步骤/状态/晶圆数量等真实数据
- 不要编造任何数据，所有数据必须通过工具调用获取
- 如果工具返回的数据不足以回答问题，请如实告知用户

可用工具及调用策略：

1. get_mes_lot_info: 查询 MES 系统 Lot 信息（产品/工艺/步骤/状态/晶圆数量/花篮）
   - 必填参数：lot (Lot ID)
   - 适用：用户提到具体 Lot ID（如 PC00H.29、NT938、VC001）并询问产品、状态、晶圆数量、工艺信息

2. get_lot_info: 查询 Lot 完整追溯信息（MES + FabTwin 设备事件融合）
   - 参数：lot_id (Lot ID)
   - 适用：用户问"Lot 追溯"、"Lot 走过哪些机台"、"Lot 在哪台机台上"、"Lot 完整信息"

3. get_machine_status: 查询机台实时状态（最新VFEI事件、运行模式、当前Lot）
   - 参数：machine_id (机台ID，如 PODOPENER-1)

4. get_machine_alarms: 查询告警记录（从事件流中提取 alarm_code 非空的事件）

5. get_event_timeline: 查询机台事件时间线（事件类型分布和运行模式分布）

6. get_yield_stats: 查询产量统计（Lot数量、晶圆总数）

7. get_recipe_info: 查询工艺配方（当前返回提示信息）

OXE 机台专用工具（仅适用于 OXE 系列机台，如 OXE-51/OXE-61/OXE-65A）：

8. get_wafer_flow: 查询 OXE 机台某 Lot 的晶圆流向（25片晶圆在 PORT→PA→CHAMBER 间的加工流转）
   - 必填参数：machine_id (OXE机台ID)
   - 可选参数：lot_id (不传则查最新Lot)
   - 适用：用户问"晶圆流向"、"第几片在加工"、"晶圆进度"、"W07加工了多久"

9. get_chamber_status: 查询 OXE 机台 3 个 Chamber 的实时状态
   - 必填参数：machine_id
   - 适用：用户问"Chamber状态"、"3个腔体在做什么"、"当前加工情况"

10. get_oxe_lot_summary: 查询 OXE 机台某日加工汇总（多Lot对比、产量趋势、利用率）
    - 必填参数：machine_id
    - 可选参数：date (YYYY-MM-DD)、lot_id
    - 适用：用户问"今天加工了几个Lot"、"产量汇总"、"机台利用率"

Lot ID 格式说明：
- 主 Lot：N 或 V 开头，如 NT938, VC001
- 控片/测试 Lot：P 开头，如 P0093
- 分片 Lot：主Lot.序号，如 NT938.15（从 25 片中分出第 15 片）
- 其他格式：PC00H.29 等

回答要求：
1. 语言简洁专业，使用中文回答
2. 数据准确，不要编造数据
3. 如果工具返回中包含 jump_timestamp 和 jump_machine_id，系统会自动处理跳转。你不需要输出任何特殊标记。
4. 对于 Lot 查询，优先调用 get_lot_info（含 MES+设备事件融合）
5. 如果工具返回 table_data，你可以在回答中引用表格内容，但不要重复输出完整表格

重要：请基于工具返回的数据进行分析和推理，而不是简单复述。
- 对于机台状态：分析机台是否正常运行，是否有异常迹象
- 对于Lot查询：如果Lot经过多台机台，分析其加工路径和进度
- 对于告警：如有告警，分析可能的原因和建议
- 对于产量：如有数据，分析产量趋势
"""
        # ========== 2026-10-30 AI 真相专项：把「库里到底有什么」真正告诉模型 ==========
        # 此前 system prompt 是纯静态的十个工具描述，模型看不到任何表结构，
        # 遇到「上月按天分组产量」这类问题只能凭印象瞎答，返回的 sql 也是从未执行的装饰字符串。
        # 这里注入从 ORM 实时反射的真实数据字典，并开放受限 SQL 通道。
        if os.getenv("FABTWIN_AI_SCHEMA_INJECT", "1") not in ("0", "false", "False"):
            try:
                from services.ai.schema import schema_catalog
                prompt += (
                    "\n\n【真实数据查询能力（务必优先使用）】\n"
                    "除上面的固定工具外，你可以直接查询工厂数据库取真实数据：\n"
                    "1) describe_fab_table —— 写 SQL 前先查目标表有哪些字段；不要凭印象猜列名\n"
                    "2) query_fab_data —— 执行一条只读 SELECT，返回真实结果行\n"
                    "凡是需要按时间/按机台/按批次分组统计、排行 TOP N、跨表关联、明细清单的问题，"
                    "都必须通过这两个工具取到真实数据后再回答。工具没返回的数字，禁止编造。\n\n"
                    + schema_catalog.to_prompt_text()
                )
            except Exception as exc:
                logger.warning("注入数据字典失败（不影响主链路）：%s", exc)

        if machine_id:
            prompt += (
                f"\n\n【重要】当前关联机台: {machine_id}\n"
                f"- 用户在该机台详情页提问，所有涉及机台的查询都应使用此 machine_id，无需再向用户索要\n"
                f"- 如果用户问题涉及 Chamber/Lot/晶圆/告警/状态/流向 等，直接用此 machine_id 调用对应工具\n"
                f"- 只有当用户明确提到其他机台 ID 时，才使用用户指定的 ID"
            )

        if context:
            prompt += f"\n上下文数据: {json.dumps(context, ensure_ascii=False, default=str)}"

        if user_role == "admin":
            prompt += "\n用户角色: 管理员"
        else:
            prompt += "\n用户角色: 普通用户"

        return prompt

    def _normalize_response(self, result: Any) -> Dict[str, Any]:
        """统一响应格式"""
        if isinstance(result, dict):
            return {
                "answer": result.get("answer", result.get("content", "")),
                "sql": result.get("sql", ""),
                "jump_timestamp": result.get("jump_timestamp", result.get("jumpTs", None)),
                "jump_machine_id": result.get("jump_machine_id", result.get("jumpMachineId", None)),
                "machine_online": result.get("machine_online", None),
                "table_data": result.get("table_data", result.get("tableData", None)),
                "tool_calls": result.get("tool_calls", []),
                "sources": result.get("sources", []),
            }
        return {
            "answer": str(result),
            "sql": "",
            "jump_timestamp": None,
            "jump_machine_id": None,
            "machine_online": None,
            "table_data": None,
            "tool_calls": [],
            "sources": [],
        }

    # ==================== Provider: 本地规则引擎 ====================

    def _local_rule_engine(self, question: str, machine_id: str = None,
                           user_role: str = "user", execution_log: list = None, 
                           tool_calls_record: list = None,
                           usage_tracker: Dict = None) -> Dict[str, Any]:
        """本地规则引擎 - 关键字匹配路由到 ai_tools 数据访问层"""
        db = _get_db()
        try:
            q = question.lower()

            # 记录执行步骤
            if execution_log is not None:
                execution_log.append({"step": "parse_question", "question_preview": question[:100]})

            # N8N 指令识别（仅管理员）
            if user_role == "admin" and self._is_n8n_command(q):
                if execution_log is not None:
                    execution_log.append({"step": "match_intent", "intent": "n8n_command"})
                result = self._trigger_n8n_workflow(
                    question, machine_id, user_role,
                    usage_tracker=usage_tracker, tool_calls_recorder=tool_calls_record,
                )
                return result

            # 从问题中提取机台ID（支持 PODOPENER-1 / OXE-1 / VPO-01 等格式）
            extracted_mid = self._extract_machine_id(question) or machine_id

            # 从问题中提取 Lot ID
            extracted_lot = self._extract_lot_id(question)

            if execution_log is not None:
                execution_log.append({
                    "step": "extract_entities",
                    "machine_id": extracted_mid,
                    "lot_id": extracted_lot
                })

            # Lot 查询
            if extracted_lot or any(k in q for k in ["lot", "批次"]):
                if execution_log is not None:
                    execution_log.append({"step": "match_intent", "intent": "get_lot_info", "lot_id": extracted_lot})
                result = get_lot_info(db, lot_id=extracted_lot, machine_id=extracted_mid)
                if tool_calls_record is not None:
                    tool_calls_record.append({"tool": "get_lot_info", "args": {"lot_id": extracted_lot, "machine_id": extracted_mid}, "status": "success"})
                return result

            # 报警/告警
            if any(k in q for k in ["报警", "告警", "alarm", "异常"]):
                if user_role == "admin" and ("导出" in q or "报表" in q):
                    if execution_log is not None:
                        execution_log.append({"step": "match_intent", "intent": "n8n_export_alarm"})
                    result = self._trigger_n8n_workflow(
                        question, machine_id, user_role, "export_alarm_report",
                        usage_tracker=usage_tracker, tool_calls_recorder=tool_calls_record,
                    )
                    return result
                if execution_log is not None:
                    execution_log.append({"step": "match_intent", "intent": "get_machine_alarms", "machine_id": extracted_mid})
                result = get_machine_alarms(db, machine_id=extracted_mid)
                if tool_calls_record is not None:
                    tool_calls_record.append({"tool": "get_machine_alarms", "args": {"machine_id": extracted_mid}, "status": "success"})
                return result

            # 事件时间线（替代温度趋势，因为DB无传感器数据）
            if any(k in q for k in ["温度", "temperature", "temp", "趋势", "事件", "event", "时间线"]):
                if execution_log is not None:
                    execution_log.append({"step": "match_intent", "intent": "get_event_timeline", "machine_id": extracted_mid})
                result = get_event_timeline(db, machine_id=extracted_mid)
                if tool_calls_record is not None:
                    tool_calls_record.append({"tool": "get_event_timeline", "args": {"machine_id": extracted_mid}, "status": "success"})
                return result

            # 产量/晶圆
            if any(k in q for k in ["产量", "晶圆", "wafer", "yield", "加工多少", "生产了多少"]):
                if execution_log is not None:
                    execution_log.append({"step": "match_intent", "intent": "get_yield_stats", "machine_id": extracted_mid})
                result = get_yield_stats(db, machine_id=extracted_mid)
                if tool_calls_record is not None:
                    tool_calls_record.append({"tool": "get_yield_stats", "args": {"machine_id": extracted_mid}, "status": "success"})
                return result

            # 工艺/配方
            if any(k in q for k in ["工艺", "配方", "recipe", "步骤"]):
                if execution_log is not None:
                    execution_log.append({"step": "match_intent", "intent": "get_recipe_info", "machine_id": extracted_mid})
                result = get_recipe_info(db, machine_id=extracted_mid)
                if tool_calls_record is not None:
                    tool_calls_record.append({"tool": "get_recipe_info", "args": {"machine_id": extracted_mid}, "status": "success"})
                return result

            # 工单/故障（管理员）
            if user_role == "admin" and any(k in q for k in ["工单", "work order", "故障单"]):
                if execution_log is not None:
                    execution_log.append({"step": "match_intent", "intent": "n8n_generate_work_order"})
                result = self._trigger_n8n_workflow(
                    question, machine_id, user_role, "generate_work_order",
                    usage_tracker=usage_tracker, tool_calls_recorder=tool_calls_record,
                )
                return result

            # 状态/运行情况（默认）
            if execution_log is not None:
                execution_log.append({"step": "match_intent", "intent": "get_machine_status", "machine_id": extracted_mid})
            result = get_machine_status(db, machine_id=extracted_mid)
            if tool_calls_record is not None:
                tool_calls_record.append({"tool": "get_machine_status", "args": {"machine_id": extracted_mid}, "status": "success"})
            return result
        finally:
            db.close()

    def _extract_machine_id(self, question: str) -> str:
        """从自然语言中提取机台ID

        匹配格式：PODOPENER-1 / OXE-01 / VPO-2200-01 / WAT-01
        注意：使用负向查找替代 \b，因为 Python 3 中 CJK 字符属于 \w，
              \b 在 "1狀" 之间不会产生词边界。
        """
        q = question.upper()
        # 机台ID：至少2个字母 + 连字符/下划线 + 数字（必须有分隔符，与Lot ID区分）
        match = re.search(r'(?<![A-Z0-9_-])([A-Z]{2,}[-_]\d+)(?![A-Z0-9_-])', q)
        if match:
            return match.group(1)
        return None

    def _extract_lot_id(self, question: str) -> str:
        """从自然语言中提取 Lot ID

        支持格式：
        - 分片 Lot：NT938.15, PC00H.29（带点号）
        - 主 Lot：NT938, VC001, P0093, V3WTG, PN70C（字母数字混合）
        注意：使用负向查找替代 \b，避免中文环境下失效。
        """
        q = question.upper()
        # 优先匹配带点号的分片 Lot
        match = re.search(r'(?<![A-Z0-9])[A-Z0-9]+\.[0-9]+(?![A-Z0-9])', q)
        if match:
            return match.group(0)
        # 再匹配主 Lot：至少一个字母后跟数字，支持字母数字混合格式
        match = re.search(r'(?<![A-Z0-9])[A-Z]+\d+[A-Z0-9]*(?![A-Z0-9])', q)
        if match:
            lot = match.group(0)
            # 排除纯数字和过短的字符串（<4位一般不是Lot ID）
            if not lot.isdigit() and len(lot) >= 4:
                return lot
        return None

    def _is_n8n_command(self, question: str) -> bool:
        """判断是否为N8N自动化指令"""
        keywords = ["导出", "报表", "工单", "批量", "自动", "推送", "生成报告", "生成工单"]
        return any(k in question for k in keywords)

    # ==================== Provider: OpenAI 兼容模型 ====================



# 全局单例（旧路径 services.ai_middleware 为兼容 shim）
ai_middleware = AIMiddleware()
