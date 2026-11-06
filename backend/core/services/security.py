"""安全基元（test31）：密码哈希 + 会话令牌签发/校验

设计约束：
- 零新依赖：PBKDF2-HMAC-SHA256 用 hashlib 标准库实现（Django 同款算法格式），
  离线部署不需要额外 pip 包
- 数据库无 password_hash 的用户不能本地登录，可由管理员显式设置初始密码；
  旧 token（裸 user.id）仅在显式开启兼容配置时可用
- token 形态："{user_id}.{expires_ms}.{hmac}"，HMAC-SHA256 签名，默认 7 天过期；
  密钥取环境变量 FABTWIN_TOKEN_SECRET，未设置时用固定开发默认值（生产应设置）
"""
import base64
import hashlib
import hmac
import logging
import os
import secrets
import time

from config import BASE_DIR

logger = logging.getLogger("fabtwin.security")

PBKDF2_ITERATIONS = 120_000
TOKEN_TTL_SECONDS = 7 * 24 * 3600  # 7 天

# 2026-10-29 修复：原先默认密钥是仓库里的常量 "fabtwin-dev-token-secret-v1"，
# 任何人拿到源码即可伪造任意用户的 token。改为：
#   1) 显式设置 FABTWIN_TOKEN_SECRET → 直接用（生产必须这样部署）
#   2) 未设置且 FABTWIN_ENV=production → 拒绝启动（防止带默认密钥上生产）
#   3) 开发环境 → 生成随机密钥并持久化到 backend/.dev_token_secret（已 gitignore），
#      保证重启后已登录用户不掉线，同时不再是全网公开的常量
_SECRET_FILE = os.path.join(BASE_DIR, ".dev_token_secret")


def _load_token_secret() -> bytes:
    env_secret = os.getenv("FABTWIN_TOKEN_SECRET", "").strip()
    if env_secret:
        return env_secret.encode("utf-8")

    if os.getenv("FABTWIN_ENV", "").strip().lower() == "production":
        raise RuntimeError(
            "FABTWIN_ENV=production 但未设置 FABTWIN_TOKEN_SECRET：拒绝以默认密钥启动。"
            "请设置 FABTWIN_TOKEN_SECRET 环境变量后重启。"
        )

    try:
        if os.path.exists(_SECRET_FILE):
            with open(_SECRET_FILE, "r", encoding="utf-8") as f:
                data = f.read().strip()
            if data:
                return data.encode("utf-8")
    except Exception as e:
        logger.warning("读取开发密钥文件失败，将重新生成: %s", e)

    generated = secrets.token_hex(32)
    try:
        with open(_SECRET_FILE, "w", encoding="utf-8") as f:
            f.write(generated)
        logger.warning(
            "[安全] 未设置 FABTWIN_TOKEN_SECRET，已生成随机开发密钥并写入 %s。"
            "生产环境必须通过环境变量配置该密钥。", _SECRET_FILE
        )
    except Exception as e:
        logger.warning("[安全] 无法持久化开发密钥（重启后已登录用户需重新登录）: %s", e)
    return generated.encode("utf-8")


_TOKEN_SECRET = _load_token_secret()


# ── 密码哈希 ────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    """生成 pbkdf2_sha256$iterations$salt$hash 格式的哈希串"""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    """校验密码与存储哈希；格式非法返回 False（恒定时间比较）"""
    try:
        algo, iterations, salt, digest = stored.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        ).hex()
        return hmac.compare_digest(calc, digest)
    except (ValueError, AttributeError):
        return False


# ── WebSocket 子协议令牌包装 ─────────────────────────────────────────────
WS_SUBPROTOCOL = "fabtwin.v1"
_WS_TOKEN_PREFIX = "fabtwin-token."


def encode_ws_token(token: str) -> str:
    """把会话令牌编码为不回显的 WebSocket 子协议元素。"""
    encoded = base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{_WS_TOKEN_PREFIX}{encoded}"


def decode_ws_token(protocols) -> str | None:
    """从客户端子协议列表解出令牌；格式不合法或重复令牌返回 None。"""
    protocols = list(protocols or [])
    if WS_SUBPROTOCOL not in protocols:
        return None
    wrapped = [p for p in protocols if p.startswith(_WS_TOKEN_PREFIX)]
    if len(wrapped) != 1:
        return None
    encoded = wrapped[0][len(_WS_TOKEN_PREFIX):]
    if not encoded or "=" in encoded:
        return None
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        token = base64.b64decode(
            padded.encode("ascii"), altchars=b"-_", validate=True
        ).decode("utf-8")
    except (ValueError, UnicodeEncodeError):
        return None
    if not token or encode_ws_token(token) != wrapped[0]:
        return None
    return token


# ── 会话令牌 ────────────────────────────────────────────────────────────
def issue_token(user_id: str) -> str:
    expires_ms = int(time.time() * 1000) + TOKEN_TTL_SECONDS * 1000
    payload = f"{user_id}.{expires_ms}"
    sig = hmac.new(_TOKEN_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def parse_token(token: str):
    """解析签名 token：有效返回 user_id，过期/伪造返回 None；非签名格式返回 None"""
    try:
        user_id, expires_ms, sig = token.split(".", 2)
        payload = f"{user_id}.{expires_ms}"
        expect = hmac.new(_TOKEN_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expect, sig):
            return None
        if int(expires_ms) < time.time() * 1000:
            return None
        return user_id
    except (ValueError, AttributeError):
        return None
