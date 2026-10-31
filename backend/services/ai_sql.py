"""兼容 shim（批次2）：实现已迁至 services/ai/sql.py，旧 import 路径保持可用。"""
from services.ai import sql as _impl  # noqa: F401
globals().update({k: v for k, v in vars(_impl).items() if not k.startswith("__")})
del _impl
