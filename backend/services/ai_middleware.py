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

配置持久化：AI配置存储在DB ai_configs表中，启动时从DB加载，
环境变量作为首次初始化默认值。
"""
import re
import json
import time
import uuid
import requests
from typing import Optional, List, Dict, Any, Tuple
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


# ========== 预定义 Provider 列表 ==========
PROVIDER_PRESETS = [
    {
        "id": "local",
        "name": "本地规则引擎",
        "description": "无需API，基于关键字匹配和规则引擎回答",
        "requires_key": False,
        "requires_url": False,
    },
    {
        "id": "zhipu",
        "name": "智谱AI (GLM)",
        "description": "国内大模型，支持GLM-5.2等",
        "requires_key": True,
        "requires_url": True,
        "default_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-5.2",
    },
    {
        "id": "openai",
        "name": "OpenAI 官方",
        "description": "GPT-4o、GPT-4o-mini等",
        "requires_key": True,
        "requires_url": True,
        "default_url": "https://api.openai.com",
        "default_model": "gpt-4o-mini",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "description": "国内大模型，DeepSeek-V3等",
        "requires_key": True,
        "requires_url": True,
        "default_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
    },
    {
        "id": "qwen",
        "name": "通义千问 (Qwen)",
        "description": "阿里云大模型",
        "requires_key": True,
        "requires_url": True,
        "default_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
    },
    {
        "id": "custom",
        "name": "自定义OpenAI兼容",
        "description": "任意OpenAI兼容接口（本地私有化模型等）",
        "requires_key": True,
        "requires_url": True,
    },
]


# ========== DB 配置键名映射 ==========
CONFIG_KEYS = {
    "provider": "AI使用的Provider类型",
    "base_url": "OpenAI兼容接口地址",
    "api_key": "API密钥",
    "model": "模型名称",
    "temperature": "生成温度",
    "max_tokens": "最大token数",
    "provider_name": "Provider显示名称（如智谱GLM、OpenAI官方）",
    "dify_enabled": "是否启用Dify",
    "dify_base_url": "Dify API地址",
    "dify_api_key": "Dify API密钥",
    "dify_app_id": "Dify应用ID",
    "n8n_enabled": "是否启用N8N",
    "n8n_base_url": "N8N服务地址",
    "n8n_webhook_secret": "N8N Webhook密钥",
}


class AIMiddleware:
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

        # 启动时加载配置
        self._load_dify_n8n_from_db()  # 加载Dify/N8N
        self._load_llm_config()         # 加载LLM默认配置

    def _load_dify_n8n_from_db(self):
        """从 ai_configs 键值对表加载 Dify/N8N 配置"""
        try:
            db = _get_db()
            try:
                from models import AIConfig
                configs = db.query(AIConfig).all()
                if not configs:
                    # DB中无配置，将环境变量默认值写入DB
                    print("[AI] DB中无Dify/N8N配置，将环境变量默认值写入DB")
                    self._save_dify_n8n_to_db()
                    return

                # CLOB 字段读取兼容：Oracle 的 CONFIG_VALUE 是 CLOB，
                # SQLAlchemy 读取可能返回 LOB 对象而非字符串，需 .read() 转换
                def _read_clob(val):
                    if val is None:
                        return ""
                    if hasattr(val, 'read'):  # CLOB/LOB 对象
                        try:
                            val = val.read()
                        except Exception:
                            val = str(val)
                    if isinstance(val, bytes):
                        try:
                            val = val.decode('utf-8')
                        except Exception:
                            val = str(val)
                    # 避免字符串 "None" 污染（之前 None 被存成字符串）
                    if isinstance(val, str) and val == "None":
                        val = ""
                    return val if isinstance(val, str) else str(val)

                config_map = {c.config_key: _read_clob(c.config_value) for c in configs}
                if "dify_enabled" in config_map:
                    self.dify_enabled = config_map["dify_enabled"].lower() == "true"
                if "dify_base_url" in config_map and config_map["dify_base_url"]:
                    self.dify_base_url = config_map["dify_base_url"]
                if "dify_api_key" in config_map and config_map["dify_api_key"]:
                    self.dify_api_key = config_map["dify_api_key"]
                if "dify_app_id" in config_map and config_map["dify_app_id"]:
                    self.dify_app_id = config_map["dify_app_id"]

                if "n8n_enabled" in config_map:
                    self.n8n_enabled = config_map["n8n_enabled"].lower() == "true"
                if "n8n_base_url" in config_map and config_map["n8n_base_url"]:
                    self.n8n_base_url = config_map["n8n_base_url"]
                if "n8n_webhook_secret" in config_map and config_map["n8n_webhook_secret"]:
                    self.n8n_webhook_secret = config_map["n8n_webhook_secret"]

                # 加载诊断日志：用于排查"保存后重新进入为空"问题
                _dk = "已设置(" + str(len(self.dify_api_key or "")) + "位)" if self.dify_api_key else "空"
                _nk = "已设置" if self.n8n_webhook_secret else "空"
                print(f"[AI] Dify/N8N配置加载成功: "
                      f"dify_enabled={self.dify_enabled}, "
                      f"dify_base_url={self.dify_base_url!r}, "
                      f"dify_api_key={_dk}, "
                      f"dify_app_id={self.dify_app_id!r}, "
                      f"n8n_enabled={self.n8n_enabled}, "
                      f"n8n_base_url={self.n8n_base_url!r}, "
                      f"n8n_webhook_secret={_nk}")
            finally:
                db.close()
        except Exception as e:
            print(f"[AI] Dify/N8N配置加载失败，使用环境变量默认值: {e}")

    def _get_machine_dify_config(self, machine_id):
        """按机台ID查专属 Dify 配置

        查找逻辑：
        1. 查 machines 表获取 machine.model（机型名称）
        2. 按 model 在 machine_dify_configs 表中查 is_active=1 的配置
        3. machine.model 为空时，用机台ID前缀推断（如 OXE-01 → OXE）
        """
        try:
            db = _get_db()
            try:
                from models import Machine, MachineDifyConfig

                # 1. 查机台型号
                machine = db.query(Machine).filter(Machine.id == machine_id).first()
                model_id = None
                if machine and machine.model:
                    model_id = machine.model.strip().upper()
                else:
                    # 用机台ID前缀推断（取第一个 - 前的部分）
                    mid = str(machine_id or "").strip().upper()
                    if "-" in mid:
                        model_id = mid.split("-")[0]
                    else:
                        model_id = mid

                if not model_id:
                    return None

                # 2. 查专属 Dify 配置（精确匹配 + 模糊匹配）
                # 先精确匹配
                row = db.query(MachineDifyConfig).filter(
                    MachineDifyConfig.model_id == model_id,
                    MachineDifyConfig.is_active == 1
                ).first()

                # 精确没命中，用 LIKE 模糊匹配（如 OXE 匹配 OXE-01A 等）
                if not row:
                    row = db.query(MachineDifyConfig).filter(
                        MachineDifyConfig.model_id.like(f"{model_id}%"),
                        MachineDifyConfig.is_active == 1
                    ).first()

                if row:
                    return {
                        "id": row.id,
                        "config_name": row.config_name,
                        "model_id": row.model_id,
                        "dify_base_url": row.dify_base_url,
                        "dify_api_key": row.dify_api_key,
                    }
                return None
            finally:
                db.close()
        except Exception as e:
            print(f"[AI] 查机台专属 Dify 配置失败: {e}")
            return None

    def _load_default_config(self):
        """加载默认 LLM 配置（无 config_id 时）"""
        self._load_llm_config()

    def _load_llm_config(self, config_id: int = None):
        """从 ai_provider_configs 加载LLM配置

        Args:
            config_id: 指定配置ID，None则加载默认配置
        """
        try:
            db = _get_db()
            try:
                from models import AIProviderConfig
                if config_id:
                    cfg = db.query(AIProviderConfig).filter(
                        AIProviderConfig.id == config_id,
                        AIProviderConfig.is_enabled == True
                    ).first()
                else:
                    # 先找默认配置
                    cfg = db.query(AIProviderConfig).filter(
                        AIProviderConfig.is_default == True,
                        AIProviderConfig.is_enabled == True
                    ).first()
                    if not cfg:
                        # 再找第一个启用的配置
                        cfg = db.query(AIProviderConfig).filter(
                            AIProviderConfig.is_enabled == True
                        ).order_by(AIProviderConfig.sort_order).first()

                if cfg:
                    self.provider = cfg.provider
                    self.base_url = (cfg.base_url or "").rstrip('/')
                    self.api_key = cfg.api_key
                    self.model = cfg.model
                    self.temperature = cfg.temperature
                    self.max_tokens = cfg.max_tokens
                    self.current_config_id = cfg.id
                    self.provider_name = self._infer_provider_name()
                    print(f"[AI] LLM配置加载成功: [{cfg.name}] {cfg.provider}/{cfg.model}")
                else:
                    print(f"[AI] DB中无可用LLM配置，使用环境变量默认值: {self.provider}/{self.model}")
                    self.current_config_id = None
                    self.provider_name = self._infer_provider_name()
            finally:
                db.close()
        except Exception as e:
            print(f"[AI] LLM配置加载失败，使用环境变量默认值: {e}")
            self.current_config_id = None
            self.provider_name = self._infer_provider_name()

    def _save_dify_n8n_to_db(self):
        """将Dify/N8N配置保存到 ai_configs 键值对表"""
        try:
            db = _get_db()
            try:
                from models import AIConfig
                now = datetime.now().isoformat()
                all_config = {
                    "dify_enabled": str(self.dify_enabled),
                    "dify_base_url": self.dify_base_url or "",
                    "dify_api_key": self.dify_api_key or "",
                    "dify_app_id": self.dify_app_id or "",
                    "n8n_enabled": str(self.n8n_enabled),
                    "n8n_base_url": self.n8n_base_url or "",
                    "n8n_webhook_secret": self.n8n_webhook_secret or "",
                }
                for key, value in all_config.items():
                    existing = db.query(AIConfig).filter(AIConfig.config_key == key).first()
                    if existing:
                        existing.config_value = value
                        existing.updated_at = now
                    else:
                        db.add(AIConfig(
                            config_key=key,
                            config_value=value,
                            description=CONFIG_KEYS.get(key, ""),
                            updated_at=now,
                            updated_by="system",
                        ))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"[AI] Dify/N8N配置保存失败: {e}")

    def _save_to_db(self, key: str, value: str):
        """保存单个配置项到 ai_configs 键值对表"""
        try:
            db = _get_db()
            try:
                from models import AIConfig
                now = datetime.now().isoformat()
                # None 值存空字符串，避免 DB 存入字符串 "None"
                if value is None:
                    value = ""
                existing = db.query(AIConfig).filter(AIConfig.config_key == key).first()
                if existing:
                    existing.config_value = value
                    existing.updated_at = now
                else:
                    db.add(AIConfig(
                        config_key=key,
                        config_value=value,
                        description=CONFIG_KEYS.get(key, ""),
                        updated_at=now,
                        updated_by="admin",
                    ))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"[AI] 保存配置 {key} 失败: {e}")

    def _save_dify_n8n_key(self, key: str, value: str):
        """保存单个Dify/N8N配置项到 ai_configs"""
        self._save_to_db(key, value)

    def _build_chat_url(self, base_url: str) -> str:
        """根据 base_url 构建 chat completions 完整 URL

        兼容用户填写时带或不带版本后缀的情况：
        - https://api.openai.com              → https://api.openai.com/v1/chat/completions
        - https://api.openai.com/v1           → https://api.openai.com/v1/chat/completions
        - https://api.openai.com/v1/          → https://api.openai.com/v1/chat/completions
        - https://open.bigmodel.cn/api/paas/v4 → https://open.bigmodel.cn/api/paas/v4/chat/completions
        - https://api.deepseek.com/v1         → https://api.deepseek.com/v1/chat/completions
        """
        url = (base_url or "").rstrip('/')
        if not url:
            return ""
        # 已包含版本号后缀（v1/v2/v4 等）时直接拼接，避免重复加 /v1
        if re.search(r'/v\d+$', url):
            return f"{url}/chat/completions"
        return f"{url}/v1/chat/completions"

    def _infer_provider_name(self) -> str:
        """根据base_url推断Provider名称"""
        url = (self.base_url or "").lower()
        if "bigmodel" in url or "zhipu" in url:
            return "智谱AI (GLM)"
        if "api.openai.com" in url:
            return "OpenAI 官方"
        if "deepseek" in url:
            return "DeepSeek"
        if "dashscope" in url or "qwen" in url:
            return "通义千问 (Qwen)"
        if self.provider == "local":
            return "本地规则引擎"
        if url:
            return "自定义OpenAI兼容"
        return ""

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

        # 机台专属 Dify 路由：未指定 config_id 时，按机台型号查专属 Dify 配置
        if not config_id and machine_id:
            machine_dify = self._get_machine_dify_config(machine_id)
            if machine_dify:
                self.provider = "dify"
                self.dify_enabled = True  # 【关键修复】命中专属Dify必须显式启用，否则_call_dify守卫失败
                self.dify_base_url = machine_dify.get("dify_base_url", "")
                self.dify_api_key = machine_dify.get("dify_api_key", "")
                self.model = f"dify-{machine_dify.get('config_name', '')}"
                self.provider_name = machine_dify.get("config_name", "Dify")
                self.current_config_id = None  # 机台专属配置不走 provider_configs 表
                print(f"[AI] 机台 {machine_id} 命中专属 Dify: {machine_dify.get('config_name')}, "
                      f"url={self.dify_base_url!r}, key_len={len(self.dify_api_key or '')}")
            else:
                # 没有专属配置，确保用默认配置
                if not self.current_config_id:
                    self._load_default_config()

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
        execution_log.append({"step": "start", "provider": self.provider, "timestamp": datetime.now().isoformat()})

        # 记录路由决策
        if self.provider in openai_compatible_providers and self.base_url and self.api_key:
            execution_log.append({"step": "route", "decision": "llm", "provider": self.provider, "model": self.model})
        elif self.provider in openai_compatible_providers:
            execution_log.append({"step": "route", "decision": "fallback_local", "reason": "缺少 base_url 或 api_key"})
        else:
            execution_log.append({"step": "route", "decision": "local_rule_engine", "provider": self.provider})

        try:
            if self.provider in openai_compatible_providers and self.base_url and self.api_key:
                execution_log.append({"step": "call_llm", "url": self._build_chat_url(self.base_url)})
                result = self._call_openai_compatible(
                    question, system_prompt, session["messages"], machine_id,
                    usage_tracker=usage, tool_calls_recorder=tool_calls_record
                )
                execution_log.append({"step": "llm_done", "tool_calls_count": len(tool_calls_record)})
            elif self.provider in openai_compatible_providers:
                print(f"[AI] provider={self.provider} 但未配置 base_url 或 api_key，回退本地规则")
                execution_log.append({"step": "fallback", "reason": "缺少 base_url 或 api_key"})
                result = self._local_rule_engine(question, machine_id, user_role, execution_log=execution_log, tool_calls_record=tool_calls_record, usage_tracker=usage)
            elif self.provider == "dify":
                execution_log.append({"step": "call_dify"})
                result = self._call_dify(
                    question, session_id, machine_id, user_role,
                    usage_tracker=usage, tool_calls_recorder=tool_calls_record,
                )
            elif self.provider == "hybrid":
                try:
                    execution_log.append({"step": "call_dify_hybrid"})
                    result = self._call_dify(
                        question, session_id, machine_id, user_role,
                        usage_tracker=usage, tool_calls_recorder=tool_calls_record,
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
            print(f"[AI] 调用失败，回退本地规则: {e}")
            execution_log.append({"step": "error", "error": str(e)[:200]})
            success = False
            error_msg = str(e)
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

        # 注入当前Provider信息到响应
        result["provider"] = self.provider
        result["provider_name"] = self.provider_name or self._infer_provider_name()
        result["model"] = self.model
        result["config_id"] = self.current_config_id
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
                config_id=self.current_config_id,
                provider=self.provider,
                provider_name=self.provider_name or self._infer_provider_name(),
                model=self.model,
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
                        "sql": "",
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

    def _call_dify(self, question: str, session_id: str, machine_id: str = None,
                   user_role: str = "user",
                   usage_tracker: Dict = None,
                   tool_calls_recorder: List = None) -> Dict[str, Any]:
        """调用Dify应用
        - 解析 Dify 返回的 metadata.usage 写回 usage_tracker（用于日志计费）
        - 解析 retriever_resources（RAG 知识库引用片段）放入 sources 字段
        - 支持 workflow 模式和 chatbot 模式
        """
        if not self.dify_enabled or not self.dify_base_url or not self.dify_api_key:
            if tool_calls_recorder is not None:
                tool_calls_recorder.append({
                    "tool": "fallback_local", "status": "skip",
                    "reason": "Dify未启用或缺少配置",
                })
            return self._local_rule_engine(question, machine_id, user_role)

        try:
            base = self.dify_base_url.rstrip('/')
            # 若用户填写的是 /v4 结尾的 URL，自动保留版本前缀不重复
            url = f"{base}/chat-messages" if base.endswith('/v1') else f"{base}/v1/chat-messages"
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
                "conversation_id": session_id if session_id and session_id != "" else "",
                "user": f"fabtwin_{user_role}",
                "files": [],
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=90)
            resp.raise_for_status()
            data = resp.json()

            answer = data.get("answer", "")
            conversation_id = data.get("conversation_id") or session_id

            # 解析 usage token（Dify 返回字段通常在 metadata.usage）
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            metadata = data.get("metadata") or {}
            if isinstance(metadata, dict):
                mu = metadata.get("usage") or {}
                prompt_tokens = int(mu.get("prompt_tokens") or mu.get("input_tokens") or 0)
                completion_tokens = int(mu.get("completion_tokens") or mu.get("output_tokens") or 0)
                total_tokens = int(mu.get("total_tokens") or 0)
                if total_tokens == 0:
                    total_tokens = prompt_tokens + completion_tokens

            # 兼容 dify workflow 顶层 usage 字段
            if total_tokens == 0 and isinstance(data.get("usage"), dict):
                u = data["usage"]
                prompt_tokens = int(u.get("prompt_tokens") or u.get("input_tokens") or 0)
                completion_tokens = int(u.get("completion_tokens") or u.get("output_tokens") or 0)
                total_tokens = prompt_tokens + completion_tokens

            # 回写 token 用量给日志记录层
            if usage_tracker is not None:
                usage_tracker["prompt_tokens"] = prompt_tokens
                usage_tracker["completion_tokens"] = completion_tokens
                usage_tracker["total_tokens"] = total_tokens

            # 解析 RAG 知识库引用（retriever_resources）
            sources = [{"type": "dify", "app_id": self.dify_app_id}]
            rag_refs = data.get("retriever_resources") or []
            if not rag_refs:
                # Dify 0.10+ 可能改名为 docs
                rag_refs = data.get("docs") or []
            for i, doc in enumerate(rag_refs[:10]):
                if isinstance(doc, dict):
                    score = doc.get("score") or doc.get("rerank_score")
                    sources.append({
                        "type": "rag",
                        "doc_id": doc.get("id") or doc.get("document_id") or doc.get("segment_id") or f"rag_{i}",
                        "doc_name": doc.get("name") or doc.get("document_name") or doc.get("title") or f"文档{i+1}",
                        "content": (doc.get("content") or doc.get("text") or doc.get("segment_content") or "")[:500],
                        "page": doc.get("page") or doc.get("page_number"),
                        "score": float(score) if score is not None else None,
                    })

            # 记录 Dify 工具调用（Dify 返回的 agent_thoughts 或 workflow_steps）
            if tool_calls_recorder is not None:
                tool_calls_recorder.append({
                    "tool": "dify_chat",
                    "status": "success",
                    "conversation_id": conversation_id,
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "rag_docs_count": max(0, len(sources) - 1),
                })
                # workflow 步骤
                steps = (metadata.get("workflow_steps")
                         or metadata.get("workflow_run")
                         or data.get("workflow_steps")
                         or [])
                if isinstance(steps, list) and len(steps) > 0:
                    for s in steps:
                        if isinstance(s, dict):
                            tool_calls_recorder.append({
                                "tool": f"dify_workflow_{s.get('node_type') or s.get('type') or 'step'}",
                                "status": s.get("status") or "success",
                                "node_id": s.get("node_id"),
                                "elapsed": s.get("elapsed_time") or s.get("execution_time"),
                            })

            # 从 Dify answer 中提取跳转标记（与 OpenAI 兼容模式格式一致）
            jump_ts = None
            jump_mid = None
            jump_match = re.search(r'\[JUMP:\s*([^\]]+)\]', answer)
            if jump_match:
                jump_ts = jump_match.group(1).strip()
                answer = re.sub(r'\[JUMP:\s*[^\]]+\]', '', answer).strip()
            mid_match = re.search(r'\[MACHINE:\s*([^\]]+)\]', answer)
            if mid_match:
                jump_mid = mid_match.group(1).strip()
                answer = re.sub(r'\[MACHINE:\s*[^\]]+\]', '', answer).strip()

            return {
                "answer": answer,
                "sql": "",
                "jump_timestamp": jump_ts,
                "jump_machine_id": jump_mid or machine_id,
                "table_data": None,
                "sources": sources,
                "conversation_id": conversation_id,
            }
        except requests.HTTPError as e:
            body = ""
            try:
                body = e.response.text[:500]
            except Exception:
                pass
            print(f"[AI] Dify调用失败 HTTP {e.response.status_code}: {body}")
            if tool_calls_recorder is not None:
                tool_calls_recorder.append({
                    "tool": "dify_chat", "status": "error",
                    "error": f"HTTP {e.response.status_code}: {body[:200]}",
                })
            raise
        except Exception as e:
            print(f"[AI] Dify调用失败: {e}")
            if tool_calls_recorder is not None:
                tool_calls_recorder.append({
                    "tool": "dify_chat", "status": "error",
                    "error": str(e)[:200],
                })
            raise

    # ==================== N8N 工作流联动 ====================

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

    def get_config(self) -> Dict[str, Any]:
        """获取当前AI配置（脱敏）。所有返回字段保证非 None 可安全序列化。"""
        # 本地規則引擎或未配置 LLM 时，self.model / self.temperature 可能是 None，
        # F-#1 统一降级，避免 Pydantic AIConfigOut 对 str/int 抛 ValidationError。
        try:
            temperature = float(self.temperature) if self.temperature is not None else 0.7
        except (TypeError, ValueError):
            temperature = 0.7
        try:
            max_tokens = int(self.max_tokens) if self.max_tokens is not None else 0
        except (TypeError, ValueError):
            max_tokens = 0
        dify_api_key_preview = self._mask_key(self.dify_api_key) if self.dify_api_key else ""
        dify_app_id_masked = self._mask_key(self.dify_api_key) if self.dify_api_key else ""
        n8n_secret_preview = self._mask_key(self.n8n_webhook_secret) if self.n8n_webhook_secret else ""
        return {
            "provider": self.provider or "local",
            "provider_name": self.provider_name or self._infer_provider_name() or "",
            "model": self.model or "",
            "base_url_masked": self._mask_url(self.base_url) or "",
            "has_api_key": bool(self.api_key),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "dify_enabled": bool(self.dify_enabled),
            "dify_base_url": self.dify_base_url or "",
            "dify_base_url_masked": self._mask_url(self.dify_base_url) or "",
            "dify_has_api_key": bool(self.dify_api_key),
            "dify_api_key_preview": dify_api_key_preview,
            "dify_app_id": self.dify_app_id or "",
            "dify_app_id_masked": dify_app_id_masked,
            "n8n_enabled": bool(self.n8n_enabled),
            "n8n_base_url": self.n8n_base_url or "",
            "n8n_base_url_masked": self._mask_url(self.n8n_base_url) or "",
            "n8n_has_webhook_secret": bool(self.n8n_webhook_secret),
            "n8n_webhook_secret_preview": n8n_secret_preview,
        }

    def update_config(self, config: Dict[str, Any]) -> bool:
        """更新AI配置（运行时更新 + 持久化到DB）"""
        try:
            if "provider" in config:
                self.provider = config["provider"]
                self._save_to_db("provider", self.provider)
            if "base_url" in config:
                self.base_url = (config["base_url"] or "").rstrip('/')
                self._save_to_db("base_url", self.base_url)
            if "api_key" in config:
                self.api_key = config["api_key"]
                self._save_to_db("api_key", self.api_key)
            if "model" in config:
                self.model = config["model"]
                self._save_to_db("model", self.model)
            if "temperature" in config:
                self.temperature = float(config["temperature"])
                self._save_to_db("temperature", str(self.temperature))
            if "max_tokens" in config:
                self.max_tokens = int(config["max_tokens"])
                self._save_to_db("max_tokens", str(self.max_tokens))

            # 更新provider_name（根据base_url自动推断，或手动指定）
            if "provider_name" in config:
                self.provider_name = config["provider_name"]
            elif "base_url" in config or "provider" in config:
                self.provider_name = self._infer_provider_name()
            self._save_to_db("provider_name", self.provider_name)

            if "dify_enabled" in config:
                self.dify_enabled = bool(config["dify_enabled"])
                self._save_to_db("dify_enabled", str(self.dify_enabled))
            if "dify_base_url" in config:
                self.dify_base_url = config["dify_base_url"]
                self._save_to_db("dify_base_url", self.dify_base_url)
            if "dify_api_key" in config:
                self.dify_api_key = config["dify_api_key"]
                self._save_to_db("dify_api_key", self.dify_api_key)
            if "dify_app_id" in config:
                self.dify_app_id = config["dify_app_id"]
                self._save_to_db("dify_app_id", self.dify_app_id)

            if "n8n_enabled" in config:
                self.n8n_enabled = bool(config["n8n_enabled"])
                self._save_to_db("n8n_enabled", str(self.n8n_enabled))
            if "n8n_base_url" in config:
                self.n8n_base_url = config["n8n_base_url"]
                self._save_to_db("n8n_base_url", self.n8n_base_url)
            if "n8n_webhook_secret" in config:
                self.n8n_webhook_secret = config["n8n_webhook_secret"]
                self._save_to_db("n8n_webhook_secret", self.n8n_webhook_secret)

            print(f"[AI] 配置已更新并持久化: provider={self.provider}, model={self.model}")
            return True
        except Exception as e:
            print(f"[AI] 更新配置失败: {e}")
            return False

    def test_connection(self, provider_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """测试连接"""
        try:
            if provider_type == "openai":
                # 用最小 chat completions 请求测试（兼容所有 OpenAI 兼容接口）
                url = self._build_chat_url(config.get('base_url', ''))
                if not url:
                    return {"success": False, "message": "API 地址不能为空"}
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
                try:
                    resp = requests.post(url, json=payload, headers=headers, timeout=15)
                    if resp.status_code == 200:
                        return {"success": True, "message": "连接成功，模型可正常响应"}
                    return {"success": False, "message": f"连接失败: HTTP {resp.status_code} - {resp.text[:200]} | 实际调用: {url}"}
                except requests.exceptions.ConnectionError:
                    return {"success": False, "message": f"无法连接到服务：{url}（请确认地址、端口、防火墙及服务是否启动）"}
                except requests.exceptions.Timeout:
                    return {"success": False, "message": f"连接超时（15s）：{url}（服务响应过慢或不可达）"}
                except Exception as e:
                    return {"success": False, "message": f"请求异常：{str(e)} | 实际调用: {url}"}

            elif provider_type == "dify":
                base = (config.get('base_url', '') or '').rstrip('/')
                if not base:
                    return {"success": False, "message": "Dify 地址不能为空"}
                # 如果请求没带 api_key（空字符串/None）或带了掩码预览值（含****），
                # 回退到已保存的 dify_api_key，允许用户不重新输入就能验证连通
                api_key = config.get('api_key', '') or ''
                used_saved = False
                if (not api_key) or ('****' in api_key):
                    if self.dify_api_key:
                        api_key = self.dify_api_key
                        used_saved = True
                    else:
                        return {"success": False, "message": "Dify API Key 未配置，请先保存或在测试时输入完整 Key"}
                headers = {"Authorization": f"Bearer {api_key}"}
                using_msg = "（使用已保存Key）" if used_saved else ""
                # 1. 优先用 /v1/info（兼容性最好的健康检查端点，返回应用基本信息）
                for suffix, method in [
                    ("/v1/info", "GET"),
                    ("/v1/parameters", "GET"),
                ]:
                    try:
                        url = f"{base}{suffix}"
                        resp = requests.get(url, headers=headers, timeout=10)
                        if resp.status_code == 200:
                            data = resp.json() or {}
                            app_name = data.get("app", {}).get("name") if isinstance(data.get("app"), dict) else data.get("name")
                            msg = "Dify 连接成功" + using_msg
                            if app_name:
                                msg += f"，应用：{app_name}"
                            # 额外探测知识库列表（用于确认 RAG 功能就绪）
                            try:
                                ds_resp = requests.get(
                                    f"{base}/v1/datasets?page=1&limit=3",
                                    headers=headers, timeout=10,
                                )
                                if ds_resp.status_code == 200:
                                    ds_data = ds_resp.json() or {}
                                    ds_total = ds_data.get("total") or len(ds_data.get("data") or [])
                                    msg += f"，知识库数：{ds_total}"
                            except Exception:
                                pass
                            return {"success": True, "message": msg}
                    except Exception:
                        continue
                # 2. 作为兜底，使用 chat-messages 发一条极短 hello（消耗少量token，但能真正验证链路）
                try:
                    chat_url = base.rstrip('/')
                    chat_url = f"{chat_url}/chat-messages" if chat_url.endswith('/v1') else f"{chat_url}/v1/chat-messages"
                    ping_headers = dict(headers)
                    ping_headers["Content-Type"] = "application/json"
                    resp = requests.post(
                        chat_url, headers=ping_headers, timeout=15,
                        json={
                            "query": "ping",
                            "response_mode": "blocking",
                            "user": "fabtwin_conn_test",
                            "inputs": {},
                        },
                    )
                    if resp.status_code == 200:
                        d = resp.json()
                        a = (d.get("answer") or "")[:60]
                        return {"success": True, "message": f"Dify 连接成功（对话验证）{using_msg}，回复：{a}"}
                    return {"success": False, "message": f"Dify连接失败: HTTP {resp.status_code} - {resp.text[:200]}"}
                except Exception as e2:
                    return {"success": False, "message": f"Dify连接失败: {str(e2)}"}

            elif provider_type == "n8n":
                base = (config.get('base_url', '') or '').rstrip('/')
                if not base:
                    return {"success": False, "message": "N8N 地址不能为空"}
                # 1. 健康检查
                for health_path in ["/healthz", "/health", "/"]:
                    try:
                        resp = requests.get(f"{base}{health_path}", timeout=10)
                        if resp.status_code == 200:
                            # 2. 尝试获取工作流列表（验证 API Key 权限）
                            wf_count = None
                            try:
                                # n8n public API: /api/v1/workflows
                                api_key = config.get('api_key', '') or self.n8n_webhook_secret
                                if api_key:
                                    wf_resp = requests.get(
                                        f"{base}/api/v1/workflows?limit=20",
                                        headers={"X-N8N-API-KEY": api_key},
                                        timeout=10,
                                    )
                                    if wf_resp.status_code == 200:
                                        wf_data = wf_resp.json() or {}
                                        wf_count = wf_data.get("count") or len(wf_data.get("data") or [])
                            except Exception:
                                pass
                            msg = "N8N 连接成功"
                            if wf_count is not None:
                                msg += f"，工作流数：{wf_count}"
                            # 3. 尝试 ping 已导入的 5 个 webhook 路径（若未导入则跳过）
                            webhook_paths = [
                                "export_alarm_report", "generate_work_order",
                                "export_machine_data", "push_daily_report", "general_query",
                            ]
                            active_webhooks = []
                            secret = config.get('api_key', '') or ''
                            for wf_path in webhook_paths:
                                try:
                                    url = f"{base}/webhook/{wf_path}"
                                    if secret:
                                        url += f"?secret={secret}"
                                    # 用 OPTIONS 或轻量 POST ping
                                    pr = requests.post(
                                        url, json={"ping": True, "test": True},
                                        timeout=5,
                                    )
                                    if pr.status_code in (200, 400, 422):
                                        active_webhooks.append(wf_path)
                                except Exception:
                                    pass
                            if active_webhooks:
                                msg += f"，已激活 Webhook：{len(active_webhooks)}/{len(webhook_paths)}"
                            else:
                                msg += "（Webhook 未导入或未激活，请先导入工作流模板）"
                            return {"success": True, "message": msg}
                    except Exception:
                        continue
                return {"success": False, "message": f"N8N 连接失败：服务不可达或未启动（{base}）"}

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

    # ==================== 使用量统计 ====================

    def _log_usage(self, session_id: str, config_id: int, provider: str, model: str,
                   prompt_tokens: int, completion_tokens: int, total_tokens: int,
                   question_preview: str, success: bool, error_msg: str = None,
                   provider_name: str = None, answer_preview: str = None,
                   tool_calls: list = None, execution_log: list = None):
        """记录AI调用使用量和执行详情到DB"""
        try:
            db = _get_db()
            try:
                from models import AIUsageLog
                # 将列表转为 JSON 字符串存储
                tool_calls_json = json.dumps(tool_calls, ensure_ascii=False, default=str) if tool_calls else None
                execution_log_json = json.dumps(execution_log, ensure_ascii=False, default=str) if execution_log else None
                
                db.add(AIUsageLog(
                    session_id=session_id,
                    config_id=config_id,
                    provider=provider,
                    provider_name=provider_name,
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    question_preview=question_preview,
                    answer_preview=answer_preview,
                    success=success,
                    error_msg=error_msg,
                    tool_calls=tool_calls_json,
                    execution_log=execution_log_json,
                    created_at=datetime.now().isoformat(),
                ))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            print(f"[AI] 使用量记录失败: {e}")
            import traceback
            traceback.print_exc()

    def get_usage_stats(self, days: int = 30) -> Dict[str, Any]:
        """获取使用量统计（F-#2：修复 Oracle ORA-00979 not a GROUP BY expression）

        根因：`substr(created_at, 1, 10)` 在 Oracle 中对 DATE/TIMESTAMP 列先做隐式 NLS 转字符串，
        SELECT/GROUP BY/ORDER BY 三处表达式的参数化绑定不保证列位置等价，触发 ORA-00979。
        修复：按方言选择"真实日期截断函数"并复用同一 ColumnElement 取别名 group_by。
        """
        try:
            db = _get_db()
            try:
                from models import AIUsageLog
                from sqlalchemy import func, column, select
                from datetime import datetime, timedelta

                start_date = (datetime.now() - timedelta(days=days))
                # created_at 列在 DB 里可能是 DATE/TIMESTAMP/Oracle VARCHAR2/SQLite TEXT，
                # 为兼容 Oracle DATE/TIMESTAMP + SQLite TEXT(ISO-8601) 两种历史布局：
                # Oracle 用 TRUNC(date_col)；SQLite 用 date(strftime(...))；都产出日粒度值。
                dialect = db.bind.dialect.name if db.bind else "sqlite"
                if dialect.lower().startswith("oracle"):
                    day_expr = func.TRUNC(AIUsageLog.created_at)
                    day_to_str = func.TO_CHAR(day_expr, "YYYY-MM-DD")
                else:
                    # SQLite: date(col) 对 ISO-8601 / yyyy-mm-dd hh:mm:ss 都安全
                    day_expr = func.date(AIUsageLog.created_at)
                    day_to_str = day_expr

                totals = db.query(
                    func.count(AIUsageLog.id).label("total_calls"),
                    func.coalesce(func.sum(AIUsageLog.prompt_tokens), 0).label("total_prompt"),
                    func.coalesce(func.sum(AIUsageLog.completion_tokens), 0).label("total_completion"),
                    func.coalesce(func.sum(AIUsageLog.total_tokens), 0).label("total_tokens"),
                ).filter(AIUsageLog.created_at >= start_date).first()

                provider_stats = db.query(
                    AIUsageLog.provider,
                    func.count(AIUsageLog.id).label("calls"),
                    func.coalesce(func.sum(AIUsageLog.total_tokens), 0).label("tokens"),
                ).filter(AIUsageLog.created_at >= start_date).group_by(AIUsageLog.provider).all()

                provider_breakdown = {}
                for p in provider_stats:
                    provider_breakdown[p.provider or "unknown"] = {
                        "calls": p.calls,
                        "tokens": int(p.tokens),
                    }

                # 按天统计（关键：day_expr 与 GROUP BY 使用同一个 Python 对象，避免绑定参数位置不等价）
                day_col = day_to_str.label("day")
                calls_col = func.count(AIUsageLog.id).label("calls")
                tokens_col = func.coalesce(func.sum(AIUsageLog.total_tokens), 0).label("tokens")
                daily = db.query(day_col, calls_col, tokens_col) \
                    .filter(AIUsageLog.created_at >= start_date) \
                    .group_by(day_col) \
                    .order_by(day_col.asc()) \
                    .all()

                daily_stats = []
                for d in daily:
                    # TRUNC/TO_CHAR 出来是 datetime/str 的兼容写法：统一转字符串
                    val = d.day
                    if isinstance(val, datetime):
                        day_str = val.strftime("%Y-%m-%d")
                    else:
                        day_str = str(val)[:10]
                    daily_stats.append({"date": day_str, "calls": d.calls, "tokens": int(d.tokens)})

                return {
                    "total_calls": int(totals.total_calls or 0),
                    "total_prompt_tokens": int(totals.total_prompt or 0),
                    "total_completion_tokens": int(totals.total_completion or 0),
                    "total_tokens": int(totals.total_tokens or 0),
                    "provider_breakdown": provider_breakdown,
                    "daily_stats": daily_stats,
                }
            finally:
                db.close()
        except Exception as e:
            import traceback
            print(f"[AI] 使用量统计失败: {e}")
            traceback.print_exc()
            return {
                "total_calls": 0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "provider_breakdown": {},
                "daily_stats": [],
            }

    def get_usage_logs(self, limit: int = 100, offset: int = 0, include_details: bool = True,
                       start_date: str = None, end_date: str = None,
                       provider: str = None, success: bool = None) -> Tuple[List[Dict], int]:
        """获取使用日志列表（支持筛选 + 分页）

        Args:
            limit: 返回条数上限
            offset: 偏移量
            include_details: 是否包含详细执行日志（tool_calls, execution_log, answer）
            start_date: 起始日期 YYYY-MM-DD（包含）
            end_date: 结束日期 YYYY-MM-DD（包含，内部 +1 天）
            provider: Provider 名称精确匹配（local/openai/zhipu/dify/hybrid）
            success: True 只查成功，False 只查失败
        Returns:
            (logs_list, total_count)
        """
        try:
            db = _get_db()
            try:
                from models import AIUsageLog
                from sqlalchemy import func

                query = db.query(AIUsageLog)

                # 日期筛选（created_at 存储格式为 "YYYY-MM-DD HH:MM:SS"）
                if start_date:
                    query = query.filter(AIUsageLog.created_at >= start_date)
                if end_date:
                    # end_date + 1 天以包含当天全部
                    from datetime import datetime, timedelta
                    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                    query = query.filter(AIUsageLog.created_at < end_dt.strftime("%Y-%m-%d"))

                # Provider 筛选
                if provider:
                    query = query.filter(AIUsageLog.provider == provider)

                # 成功/失败筛选
                if success is not None:
                    query = query.filter(AIUsageLog.success == success)

                # 总数
                total = query.count()

                # 分页 + 排序
                logs = query.order_by(AIUsageLog.created_at.desc()).offset(offset).limit(limit).all()

                result = []
                for log in logs:
                    item = {
                        "id": log.id,
                        "session_id": log.session_id,
                        "config_id": log.config_id,
                        "provider": log.provider,
                        "provider_name": log.provider_name,
                        "model": log.model,
                        "prompt_tokens": log.prompt_tokens,
                        "completion_tokens": log.completion_tokens,
                        "total_tokens": log.total_tokens,
                        "question_preview": log.question_preview,
                        "success": log.success,
                        "created_at": log.created_at,
                    }

                    # 解析 JSON 字段
                    if include_details:
                        item["answer_preview"] = log.answer_preview
                        item["error_msg"] = log.error_msg

                        # 解析 tool_calls
                        if log.tool_calls:
                            try:
                                item["tool_calls"] = json.loads(log.tool_calls)
                            except (json.JSONDecodeError, TypeError):
                                item["tool_calls"] = []
                        else:
                            item["tool_calls"] = []

                        # 解析 execution_log
                        if log.execution_log:
                            try:
                                item["execution_log"] = json.loads(log.execution_log)
                            except (json.JSONDecodeError, TypeError):
                                item["execution_log"] = []
                        else:
                            item["execution_log"] = []

                    result.append(item)

                return result, total
            finally:
                db.close()
        except Exception as e:
            print(f"[AI] 使用日志查询失败: {e}")
            import traceback
            traceback.print_exc()
            return [], 0

    def get_usage_log_by_id(self, log_id: int) -> Optional[Dict]:
        """获取单条使用日志详情（含全部字段）"""
        try:
            db = _get_db()
            try:
                from models import AIUsageLog
                log = db.query(AIUsageLog).filter(AIUsageLog.id == log_id).first()
                if not log:
                    return None

                # 解析 JSON 字段
                tool_calls_parsed = []
                if log.tool_calls:
                    try:
                        tool_calls_parsed = json.loads(log.tool_calls)
                    except (json.JSONDecodeError, TypeError):
                        tool_calls_parsed = []

                execution_log_parsed = []
                if log.execution_log:
                    try:
                        execution_log_parsed = json.loads(log.execution_log)
                    except (json.JSONDecodeError, TypeError):
                        execution_log_parsed = []

                return {
                    "id": log.id,
                    "session_id": log.session_id,
                    "config_id": log.config_id,
                    "provider": log.provider,
                    "provider_name": log.provider_name,
                    "model": log.model,
                    "prompt_tokens": log.prompt_tokens,
                    "completion_tokens": log.completion_tokens,
                    "total_tokens": log.total_tokens,
                    "question_preview": log.question_preview,
                    "success": log.success,
                    "error_msg": log.error_msg,
                    "answer_preview": log.answer_preview,
                    "tool_calls": tool_calls_parsed,
                    "execution_log": execution_log_parsed,
                    "created_at": log.created_at,
                }
            finally:
                db.close()
        except Exception as e:
            print(f"[AI] 使用日志详情查询失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ==================== Provider 多配置管理 ====================

    def list_provider_configs(self) -> List[Dict]:
        """列出所有LLM Provider配置"""
        try:
            db = _get_db()
            try:
                from models import AIProviderConfig
                configs = db.query(AIProviderConfig).order_by(AIProviderConfig.sort_order, AIProviderConfig.id).all()
                return [{
                    "id": c.id,
                    "name": c.name,
                    "provider": c.provider,
                    "base_url": c.base_url,
                    "has_api_key": bool(c.api_key),
                    "model": c.model,
                    "temperature": c.temperature,
                    "max_tokens": c.max_tokens,
                    "is_enabled": c.is_enabled,
                    "is_default": c.is_default,
                    "sort_order": c.sort_order,
                    "description": c.description,
                    "created_at": c.created_at,
                    "updated_at": c.updated_at,
                } for c in configs]
            finally:
                db.close()
        except Exception as e:
            print(f"[AI] 配置列表查询失败: {e}")
            return []

    def create_provider_config(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建新的LLM Provider配置"""
        try:
            db = _get_db()
            try:
                from models import AIProviderConfig
                now = datetime.now().isoformat()

                # 如果设为默认，取消其他默认
                if data.get("is_default"):
                    db.query(AIProviderConfig).filter(AIProviderConfig.is_default == True).update({"is_default": False})

                cfg = AIProviderConfig(
                    name=data["name"],
                    provider=data["provider"],
                    base_url=(data.get("base_url", "") or "").rstrip('/'),
                    api_key=data.get("api_key", ""),
                    model=data.get("model", ""),
                    temperature=float(data.get("temperature", 0.7)),
                    max_tokens=int(data.get("max_tokens", 2048)),
                    is_enabled=data.get("is_enabled", True),
                    is_default=data.get("is_default", False),
                    sort_order=int(data.get("sort_order", 0)),
                    description=data.get("description", ""),
                    created_at=now,
                    updated_at=now,
                )
                db.add(cfg)
                db.commit()
                db.refresh(cfg)

                return {"success": True, "id": cfg.id, "message": "配置创建成功"}
            finally:
                db.close()
        except Exception as e:
            return {"success": False, "message": f"创建失败: {str(e)}"}

    def update_provider_config(self, config_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """更新LLM Provider配置"""
        try:
            db = _get_db()
            try:
                from models import AIProviderConfig
                cfg = db.query(AIProviderConfig).filter(AIProviderConfig.id == config_id).first()
                if not cfg:
                    return {"success": False, "message": "配置不存在"}

                # 如果设为默认，取消其他默认
                if data.get("is_default"):
                    db.query(AIProviderConfig).filter(AIProviderConfig.is_default == True).update({"is_default": False})

                if "name" in data:
                    cfg.name = data["name"]
                if "provider" in data:
                    cfg.provider = data["provider"]
                if "base_url" in data:
                    cfg.base_url = (data["base_url"] or "").rstrip('/')
                if "api_key" in data:
                    cfg.api_key = data["api_key"]
                if "model" in data:
                    cfg.model = data["model"]
                if "temperature" in data:
                    cfg.temperature = float(data["temperature"])
                if "max_tokens" in data:
                    cfg.max_tokens = int(data["max_tokens"])
                if "is_enabled" in data:
                    cfg.is_enabled = bool(data["is_enabled"])
                if "is_default" in data:
                    cfg.is_default = bool(data["is_default"])
                if "sort_order" in data:
                    cfg.sort_order = int(data["sort_order"])
                if "description" in data:
                    cfg.description = data["description"]

                cfg.updated_at = datetime.now().isoformat()
                db.commit()

                # 如果修改的是当前使用的配置，刷新当前配置
                if self.current_config_id == config_id:
                    self._load_llm_config(config_id)

                return {"success": True, "message": "配置更新成功"}
            finally:
                db.close()
        except Exception as e:
            return {"success": False, "message": f"更新失败: {str(e)}"}

    def delete_provider_config(self, config_id: int) -> Dict[str, Any]:
        """删除LLM Provider配置"""
        try:
            db = _get_db()
            try:
                from models import AIProviderConfig
                cfg = db.query(AIProviderConfig).filter(AIProviderConfig.id == config_id).first()
                if not cfg:
                    return {"success": False, "message": "配置不存在"}

                db.delete(cfg)
                db.commit()

                # 如果删除的是当前配置，重新加载默认配置
                if self.current_config_id == config_id:
                    self.current_config_id = None
                    self._load_llm_config()

                return {"success": True, "message": "配置已删除"}
            finally:
                db.close()
        except Exception as e:
            return {"success": False, "message": f"删除失败: {str(e)}"}

    def set_default_provider_config(self, config_id: int) -> Dict[str, Any]:
        """设置默认配置"""
        try:
            db = _get_db()
            try:
                from models import AIProviderConfig
                # 取消所有默认
                db.query(AIProviderConfig).filter(AIProviderConfig.is_default == True).update({"is_default": False})
                # 设置指定为默认
                cfg = db.query(AIProviderConfig).filter(AIProviderConfig.id == config_id).first()
                if cfg:
                    cfg.is_default = True
                    cfg.is_enabled = True
                    cfg.updated_at = datetime.now().isoformat()
                    db.commit()
                    # 刷新当前配置
                    self._load_llm_config(config_id)
                    return {"success": True, "message": f"已设为默认: {cfg.name}"}
                return {"success": False, "message": "配置不存在"}
            finally:
                db.close()
        except Exception as e:
            return {"success": False, "message": f"设置失败: {str(e)}"}

    def toggle_provider_config(self, config_id: int) -> Dict[str, Any]:
        """启用/禁用配置"""
        try:
            db = _get_db()
            try:
                from models import AIProviderConfig
                cfg = db.query(AIProviderConfig).filter(AIProviderConfig.id == config_id).first()
                if not cfg:
                    return {"success": False, "message": "配置不存在"}

                cfg.is_enabled = not cfg.is_enabled
                cfg.updated_at = datetime.now().isoformat()
                db.commit()

                status = "启用" if cfg.is_enabled else "禁用"
                return {"success": True, "message": f"配置已{status}", "is_enabled": cfg.is_enabled}
            finally:
                db.close()
        except Exception as e:
            return {"success": False, "message": f"操作失败: {str(e)}"}

    def switch_config(self, config_id: int) -> Dict[str, Any]:
        """切换当前使用的配置"""
        try:
            db = _get_db()
            try:
                from models import AIProviderConfig
                cfg = db.query(AIProviderConfig).filter(
                    AIProviderConfig.id == config_id,
                    AIProviderConfig.is_enabled == True
                ).first()
                if not cfg:
                    return {"success": False, "message": "配置不存在或未启用"}

                self._load_llm_config(config_id)
                return {
                    "success": True,
                    "message": f"已切换至: {cfg.name}",
                    "provider": self.provider,
                    "provider_name": self.provider_name,
                    "model": self.model,
                    "config_id": self.current_config_id,
                }
            finally:
                db.close()
        except Exception as e:
            return {"success": False, "message": f"切换失败: {str(e)}"}

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
