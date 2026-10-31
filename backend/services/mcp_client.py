"""兼容 shim（批次2）：实现已迁至 services/ai/mcp_client.py，旧 import 路径保持可用。"""
from services.ai import mcp_client as _impl  # noqa: F401
globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
del _impl
