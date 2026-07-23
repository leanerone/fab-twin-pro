"""AI 中间适配层：统一请求/返回结构，兼容多模型、Dify、N8N、MCP协议

架构：
  前端请求 → AI中间层 → 路由分发 → [本地规则引擎 / OpenAI兼容模型 / Dify / N8N]
                       ↑
                   统一结构体

所有AI请求统一走 ai/chat 接口，返回统一格式：
{
  "answer": "AI回答内容",
  "sql": "查询SQL（可选）",
  "jump_timestamp": "跳转时间戳（可选）",
  "table_data": "表格数据（可选）",
  "tool_calls": "工具调用记录（可选）",
  "sources": "参考来源（可选）"
}
"""
import re
import json
import time
import uuid
import requests
from typing import Optional, List, Dict, Any
from datetime import datetime

from config import (
    AI_MCP_ENABLED, AI_MCP_URL, AI_MCP_API_KEY,
    AI_PROVIDER, AI_BASE_URL, AI_API_KEY, AI_MODEL,
    AI_TEMPERATURE, AI_MAX_TOKENS,
    DIFY_ENABLED, DIFY_BASE_URL, DIFY_API_KEY, DIFY_APP_ID,
    N8N_ENABLED, N8N_BASE_URL, N8N_WEBHOOK_SECRET,
)

# 统一数据访问层（本地规则引擎 + OpenAI Function Calling 共用）
from services.ai_tools import (
    get_machine_status,
    get_machine_alarms,
    get_event_timeline,
    get_yield_stats,
    get_lot_info,
    get_recipe_info,
    TOOL_DEFINITIONS,
    TOOL_HANDLERS,
)

# DB Session（延迟导入避免循环依赖）
_db_session = None


def _get_db():
    """获取数据库 Session"""
    global _db_session
    if _db_session is None:
        from database import SessionLocal
        _db_session = SessionLocal
    return _db_session()


class AIMiddleware:
    """AI 中间适配层 - 统一调度入口"""

    def __init__(self):
        self.provider = AI_PROVIDER  # local / openai / dify / hybrid
        self.base_url = AI_BASE_URL
        self.api_key = AI_API_KEY
        self.model = AI_MODEL
        self.temperature = AI_TEMPERATURE
        self.max_tokens = AI_MAX_TOKENS

        # Dify配置
        self.dify_enabled = DIFY_ENABLED
        self.dify_base_url = DIFY_BASE_URL
        self.dify_api_key = DIFY_API_KEY
        self.dify_app_id = DIFY_APP_ID

        # N8N配置
        self.n8n_enabled = N8N_ENABLED
        self.n8n_base_url = N8N_BASE_URL
        self.n8n_webhook_secret = N8N_WEBHOOK_SECRET

        # 会话存储（内存中，后续可接DB）
        self.sessions = {}  # session_id -> { messages: [...], created_at: ... }

    def chat(self, question: str, session_id: str = None, machine_id: str = None,
             context: Dict = None, user_role: str = "user") -> Dict[str, Any]:
        """统一聊天入口

        Args:
            question: 用户问题
            session_id: 会话ID，不传则新建
            machine_id: 关联机台ID
            context: 额外上下文数据
            user_role: 用户角色（user/admin）

        Returns:
            统一响应结构体
        """
        if not session_id:
            session_id = f"sess_{uuid.uuid4().hex[:16]}"

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
        result = None
        try:
            if self.provider == "openai" and self.base_url and self.api_key:
                result = self._call_openai_compatible(question, system_prompt, session["messages"], machine_id)
            elif self.provider == "openai":
                # provider设为openai但未配置base_url/api_key，回退本地
                print(f"[AI] provider=openai 但未配置 base_url 或 api_key，回退本地规则")
                result = self._local_rule_engine(question, machine_id, user_role)
            elif self.provider == "dify":
                result = self._call_dify(question, session_id, machine_id, user_role)
            elif self.provider == "hybrid":
                try:
                    result = self._call_dify(question, session_id, machine_id, user_role)
                except Exception as e:
                    print(f"[AI] Dify调用失败，回退本地规则: {e}")
                    result = self._local_rule_engine(question, machine_id, user_role)
            else:
                result = self._local_rule_engine(question, machine_id, user_role)
        except Exception as e:
            print(f"[AI] 调用失败，回退本地规则: {e}")
            result = self._local_rule_engine(question, machine_id, user_role)

        # 确保返回格式统一
        result = self._normalize_response(result)

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
        return result

    def _build_system_prompt(self, machine_id: str = None, context: Dict = None,
                             user_role: str = "user") -> str:
        """构建系统提示词"""
        prompt = """你是一个半导体工厂数字孪生平台的AI助手，名为FabTwin AI。
你可以回答关于机台状态、生产数据、报警信息、工艺配方、Lot追踪等问题。

重要说明：
- 当前系统采集的是VFEI事件流（POD开盖/关盖/端口锁定等），不含温度/压力/RF等传感器数据
- 不要编造任何数据，所有数据必须通过工具调用获取
- 如果工具返回的数据不足以回答问题，请如实告知用户

回答要求：
1. 语言简洁专业，使用中文回答
2. 数据准确，不要编造数据
3. 如果涉及时间跳转，在回答最后标注 [JUMP: 时间戳]
4. 你可以通过 function calling 调用以下工具查询真实数据：
   - get_machine_status: 查询机台实时状态（最新VFEI事件、运行模式、当前Lot）
   - get_machine_alarms: 查询告警记录（从事件流中提取 alarm_code 非空的事件）
   - get_event_timeline: 查询事件时间线（事件类型分布和运行模式分布）
   - get_yield_stats: 查询产量统计（Lot数量、晶圆总数）
   - get_lot_info: 查询Lot批次详情
   - get_recipe_info: 查询工艺配方（温度/压力/RF功率等参数）
"""
        if machine_id:
            prompt += f"\n当前关联机台: {machine_id}"

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
                "table_data": result.get("table_data", result.get("tableData", None)),
                "tool_calls": result.get("tool_calls", []),
                "sources": result.get("sources", []),
            }
        return {
            "answer": str(result),
            "sql": "",
            "jump_timestamp": None,
            "table_data": None,
            "tool_calls": [],
            "sources": [],
        }

    # ==================== Provider: 本地规则引擎 ====================

    def _local_rule_engine(self, question: str, machine_id: str = None,
                           user_role: str = "user") -> Dict[str, Any]:
        """本地规则引擎 - 关键字匹配路由到 ai_tools 数据访问层"""
        db = _get_db()
        try:
            q = question.lower()

            # N8N 指令识别（仅管理员）
            if user_role == "admin" and self._is_n8n_command(q):
                return self._trigger_n8n_workflow(question, machine_id, user_role)

            # 从问题中提取机台ID（支持 PODOPENER-1 / OXE-1 / VPO-01 等格式）
            extracted_mid = self._extract_machine_id(question) or machine_id

            # 从问题中提取 Lot ID
            extracted_lot = self._extract_lot_id(question)

            # Lot 查询
            if extracted_lot or any(k in q for k in ["lot", "批次"]):
                return get_lot_info(db, lot_id=extracted_lot, machine_id=extracted_mid)

            # 报警/告警
            if any(k in q for k in ["报警", "告警", "alarm", "异常"]):
                if user_role == "admin" and ("导出" in q or "报表" in q):
                    return self._trigger_n8n_workflow(question, machine_id, user_role, "export_alarm_report")
                return get_machine_alarms(db, machine_id=extracted_mid)

            # 事件时间线（替代温度趋势，因为DB无传感器数据）
            if any(k in q for k in ["温度", "temperature", "temp", "趋势", "事件", "event", "时间线"]):
                return get_event_timeline(db, machine_id=extracted_mid)

            # 产量/晶圆
            if any(k in q for k in ["产量", "晶圆", "wafer", "yield", "加工多少", "生产了多少"]):
                return get_yield_stats(db, machine_id=extracted_mid)

            # 工艺/配方
            if any(k in q for k in ["工艺", "配方", "recipe", "步骤"]):
                return get_recipe_info(db, machine_id=extracted_mid)

            # 工单/故障（管理员）
            if user_role == "admin" and any(k in q for k in ["工单", "work order", "故障单"]):
                return self._trigger_n8n_workflow(question, machine_id, user_role, "generate_work_order")

            # 状态/运行情况（默认）
            return get_machine_status(db, machine_id=extracted_mid)
        finally:
            db.close()

    def _extract_machine_id(self, question: str) -> str:
        """从自然语言中提取机台ID"""
        # 匹配 PODOPENER-1 / OXE-01 / VPO-2200-01 / WAT-01 等格式
        match = re.search(r'\b([A-Z]{2,}[-_]?\d+)\b', question.upper())
        if match:
            return match.group(1)
        return None

    def _extract_lot_id(self, question: str) -> str:
        """从自然语言中提取 Lot ID"""
        # 匹配 LOT12345 / V3TY2 / V3FYS 等格式
        match = re.search(r'\b(LOT[A-Z0-9]+|V\d[A-Z0-9]+)\b', question.upper())
        if match:
            return match.group(1)
        return None

    def _is_n8n_command(self, question: str) -> bool:
        """判断是否为N8N自动化指令"""
        keywords = ["导出", "报表", "工单", "批量", "自动", "推送", "生成报告", "生成工单"]
        return any(k in question for k in keywords)

    # ==================== Provider: OpenAI 兼容模型 ====================

    def _call_openai_compatible(self, question: str, system_prompt: str,
                                history_messages: List[Dict], machine_id: str = None) -> Dict[str, Any]:
        """调用OpenAI兼容接口（支持GLM、GPT等），带 Function Calling 工具调用"""
        if not self.base_url or not self.api_key:
            return self._local_rule_engine(question, machine_id)

        # 构建消息列表
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history_messages[-40:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        url = f"{self.base_url.rstrip('/')}/v1/chat/completions"

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

        try:
            for round_idx in range(max_tool_rounds):
                resp = requests.post(url, json=payload, headers=headers, timeout=60)
                resp.raise_for_status()
                data = resp.json()

                msg = data["choices"][0]["message"]

                # 如果没有 tool_calls，说明 LLM 已经生成最终回答
                if not msg.get("tool_calls"):
                    answer = msg.get("content", "")

                    # 提取 jump_timestamp
                    jump_ts = None
                    jump_match = re.search(r'\[JUMP:\s*([^\]]+)\]', answer)
                    if jump_match:
                        jump_ts = jump_match.group(1).strip()
                        answer = answer.replace(jump_match.group(0), "").strip()

                    return {
                        "answer": answer,
                        "sql": "",
                        "jump_timestamp": jump_ts,
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
                        finally:
                            db.close()

                        tool_call_records.append({
                            "tool": func_name,
                            "args": func_args,
                            "status": "success",
                        })

                        # 把工具结果作为 tool 角色消息回传给 LLM
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps(result, ensure_ascii=False, default=str),
                        })
                    else:
                        # 未知工具
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": json.dumps({"error": f"未知工具: {func_name}"}, ensure_ascii=False),
                        })
                        tool_call_records.append({
                            "tool": func_name,
                            "args": func_args,
                            "status": "unknown_tool",
                        })

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

    def _call_dify(self, question: str, session_id: str, machine_id: str = None,
                   user_role: str = "user") -> Dict[str, Any]:
        """调用Dify应用"""
        if not self.dify_enabled or not self.dify_base_url or not self.dify_api_key:
            return self._local_rule_engine(question, machine_id, user_role)

        try:
            url = f"{self.dify_base_url.rstrip('/')}/v1/chat-messages"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.dify_api_key}",
            }
            payload = {
                "inputs": {
                    "machine_id": machine_id or "",
                    "user_role": user_role,
                },
                "query": question,
                "response_mode": "blocking",
                "conversation_id": session_id,
                "user": f"fabtwin_{user_role}",
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()

            answer = data.get("answer", "")
            conversation_id = data.get("conversation_id", session_id)

            # 提取表格数据
            table_data = None
            if "table_data" in str(data):
                # Dify返回中可能包含结构化数据
                pass

            return {
                "answer": answer,
                "sql": "",
                "jump_timestamp": None,
                "table_data": table_data,
                "sources": [{"type": "dify", "app_id": self.dify_app_id}],
            }
        except Exception as e:
            print(f"[AI] Dify调用失败: {e}")
            raise

    # ==================== N8N 工作流联动 ====================

    def _trigger_n8n_workflow(self, question: str, machine_id: str = None,
                              user_role: str = "user", workflow_type: str = None) -> Dict[str, Any]:
        """触发N8N工作流（MCP协议转发）"""
        if user_role != "admin":
            return {
                "answer": "抱歉，自动化流程操作需要管理员权限。请联系管理员。",
                "sql": "",
            }

        if not self.n8n_enabled or not self.n8n_base_url:
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
            webhook_url = f"{self.n8n_base_url.rstrip('/')}/webhook/{workflow_type}"
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

            table_data = None
            if "data" in result_data and isinstance(result_data["data"], list):
                if result_data["data"] and isinstance(result_data["data"][0], dict):
                    headers = list(result_data["data"][0].keys())
                    rows = [list(item.values()) for item in result_data["data"][:20]]
                    table_data = {"headers": headers, "rows": rows}

            return {
                "answer": f"🤖 [N8N自动化] {answer}",
                "sql": result_data.get("sql", ""),
                "table_data": table_data,
                "tool_calls": [{"tool": "n8n", "workflow": workflow_type, "status": "success"}],
                "sources": [{"type": "n8n", "workflow": workflow_type}],
            }
        except Exception as e:
            print(f"[AI] N8N调用失败: {e}")
            return {
                "answer": f"⚠️ N8N 工作流调用失败：{str(e)}\n\n请检查 N8N 服务配置和网络连接。",
                "sql": "",
                "tool_calls": [{"tool": "n8n", "workflow": workflow_type, "status": "failed", "error": str(e)}],
            }

    # ==================== 配置管理 ====================

    def get_config(self) -> Dict[str, Any]:
        """获取当前AI配置（脱敏）"""
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url_masked": self._mask_url(self.base_url),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "dify_enabled": self.dify_enabled,
            "dify_base_url_masked": self._mask_url(self.dify_base_url),
            "dify_app_id_masked": self._mask_key(self.dify_app_id) if self.dify_app_id else "",
            "n8n_enabled": self.n8n_enabled,
            "n8n_base_url_masked": self._mask_url(self.n8n_base_url),
        }

    def update_config(self, config: Dict[str, Any]) -> bool:
        """更新AI配置（运行时更新，不持久化到配置文件）"""
        try:
            if "provider" in config:
                self.provider = config["provider"]
            if "base_url" in config:
                self.base_url = config["base_url"]
            if "api_key" in config:
                self.api_key = config["api_key"]
            if "model" in config:
                self.model = config["model"]
            if "temperature" in config:
                self.temperature = float(config["temperature"])
            if "max_tokens" in config:
                self.max_tokens = int(config["max_tokens"])

            if "dify_enabled" in config:
                self.dify_enabled = bool(config["dify_enabled"])
            if "dify_base_url" in config:
                self.dify_base_url = config["dify_base_url"]
            if "dify_api_key" in config:
                self.dify_api_key = config["dify_api_key"]
            if "dify_app_id" in config:
                self.dify_app_id = config["dify_app_id"]

            if "n8n_enabled" in config:
                self.n8n_enabled = bool(config["n8n_enabled"])
            if "n8n_base_url" in config:
                self.n8n_base_url = config["n8n_base_url"]
            if "n8n_webhook_secret" in config:
                self.n8n_webhook_secret = config["n8n_webhook_secret"]

            return True
        except Exception as e:
            print(f"[AI] 更新配置失败: {e}")
            return False

    def test_connection(self, provider_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """测试连接"""
        try:
            if provider_type == "openai":
                # 用最小 chat completions 请求测试（兼容所有 OpenAI 兼容接口）
                base_url = config.get('base_url', '').rstrip('/')
                url = f"{base_url}/v1/chat/completions"
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {config.get('api_key', '')}",
                }
                payload = {
                    "model": config.get('model', 'gpt-4o-mini'),
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 5,
                    "stream": False,
                }
                resp = requests.post(url, json=payload, headers=headers, timeout=15)
                if resp.status_code == 200:
                    return {"success": True, "message": "连接成功，模型可正常响应"}
                return {"success": False, "message": f"连接失败: HTTP {resp.status_code} - {resp.text[:200]}"}

            elif provider_type == "dify":
                url = f"{config.get('base_url', '').rstrip('/')}/v1/parameters"
                headers = {"Authorization": f"Bearer {config.get('api_key', '')}"}
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    return {"success": True, "message": "Dify连接成功"}
                return {"success": False, "message": f"Dify连接失败: HTTP {resp.status_code}"}

            elif provider_type == "n8n":
                url = f"{config.get('base_url', '').rstrip('/')}/healthz"
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    return {"success": True, "message": "N8N连接成功"}
                return {"success": False, "message": f"N8N连接失败: HTTP {resp.status_code}"}

            return {"success": False, "message": "未知的provider类型"}
        except Exception as e:
            return {"success": False, "message": f"连接测试失败: {str(e)}"}

    def _mask_url(self, url: str) -> str:
        """脱敏URL"""
        if not url:
            return ""
        if len(url) > 20:
            return url[:10] + "..." + url[-5:]
        return url

    def _mask_key(self, key: str) -> str:
        """脱敏密钥"""
        if not key:
            return ""
        if len(key) > 10:
            return key[:4] + "****" + key[-4:]
        return "****"

    # ==================== 会话管理 ====================

    def get_session(self, session_id: str) -> Optional[Dict]:
        """获取会话"""
        return self.sessions.get(session_id)

    def clear_session(self, session_id: str) -> bool:
        """清除会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False

    def list_sessions(self, limit: int = 20) -> List[Dict]:
        """列出所有会话（最近的）"""
        sessions = list(self.sessions.values())
        return sorted(sessions, key=lambda s: s.get("created_at", ""), reverse=True)[:limit]


# 全局单例
ai_middleware = AIMiddleware()
