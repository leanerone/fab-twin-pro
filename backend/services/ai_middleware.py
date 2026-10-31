"""兼容 shim（批次2）：AI 中间件已拆包至 services/ai/ 包。

旧 import（from services.ai_middleware import ai_middleware, PROVIDER_PRESETS, AIMiddleware）
与测试对 ai_middleware_module.httpx 的补丁全部保持有效。
"""
import httpx  # noqa: F401  测试 monkeypatch 目标：ai_middleware_module.httpx.AsyncClient
from services.ai.middleware import (  # noqa: F401
    AIMiddleware,
    ai_middleware,
)
from services.ai.config_store import PROVIDER_PRESETS, CONFIG_KEYS  # noqa: F401
from services.ai import middleware as _impl
globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
del _impl
