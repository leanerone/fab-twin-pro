# -*- coding: utf-8 -*-
"""AI 配置存储（批次2自 ai_middleware.py 拆出）：Provider 预设、DB 配置读写、
Dify/N8N 机台路由、连接测试与 Provider CRUD。归属：AI 应用线（朱明钊）。"""
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


class _ConfigMixin:
    """配置加载/保存/机台 Dify 路由/连接测试/Provider CRUD（供 AIMiddleware 组合）。"""

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

    def _get_machine_metadata(self, machine_id):
        """按机台ID查元数据：型号 model、chamber 数 chambers。
        返回 {"machine_model": str|None, "chambers": int|None, "machine_obj": Machine|None}
        机台 ID 空/查不到 → 对应字段返回 None，永远不抛。
        """
        if not machine_id:
            return {"machine_model": None, "chambers": None, "machine_obj": None}
        try:
            db = _get_db()
            try:
                from models import Machine
                m = db.query(Machine).filter(Machine.id == machine_id).first()
                if not m:
                    return {"machine_model": None, "chambers": None, "machine_obj": None}
                model_id = (m.model or "").strip().upper() or None
                # chambers 推断：优先读 Machine.chamber_count（若有字段），否则用正则从详情/名称猜测 3 作为刻蚀类默认
                chambers = getattr(m, "chamber_count", None) or getattr(m, "chambers", None)
                if chambers is None:
                    # 粗略兜底：刻蚀类 3 个 chamber；其他先留空
                    if model_id and ("OXE" in model_id or "ETCH" in model_id):
                        chambers = 3
                try:
                    chambers = int(chambers) if chambers is not None else None
                except (TypeError, ValueError):
                    chambers = None
                return {"machine_model": model_id, "chambers": chambers, "machine_obj": m}
            finally:
                try:
                    db.close()
                except Exception:
                    pass
        except Exception as e:
            print(f"[AI] 查机台元数据失败（忽略，继续）: {e}")
            return {"machine_model": None, "chambers": None, "machine_obj": None}

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

    # ---------- T5：session_id → Dify conversation_id 映射持久化 ----------
    # 读：先查内存 map，miss 再查 ai_conversations 表，命中回填内存；
    # 写：内存 + 落库 upsert。表未建/DB 异常时降级为纯内存（与旧行为一致）。


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
                        chat_url, headers=ping_headers, timeout=30, stream=True,
                        json={
                            "query": "ping",
                            "response_mode": "streaming",
                            "user": "fabtwin_conn_test",
                            "inputs": {},
                        },
                    )
                    if resp.status_code == 200:
                        # Agent 应用只支持 streaming，这里也走 SSE 聚合（与 _call_dify 一致）
                        try:
                            d = self._consume_dify_stream(resp)
                            a = (d.get("answer") or "")[:60]
                        except Exception:
                            a = ""
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

