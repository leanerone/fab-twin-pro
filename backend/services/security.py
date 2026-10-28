"""安全基元（test31）：密码哈希 + 会话令牌签发/校验

设计约束：
- 零新依赖：PBKDF2-HMAC-SHA256 用 hashlib 标准库实现（Django 同款算法格式），
  离线部署不需要额外 pip 包
- 兼容存量：数据库无 password_hash 的用户仍可用旧规则（用户名+"123"）登录，
  登录成功后透明升级为哈希存储；旧 token（裸 user.id）在过渡期内继续可用
- token 形态："{user_id}.{expires_ms}.{hmac}"，HMAC-SHA256 签名，默认 7 天过期；
  密钥取环境变量 FABTWIN_TOKEN_SECRET，未设置时用固定开发默认值（生产应设置）
"""
import hashlib
import hmac
import logging
import os
import secrets
import time

logger = logging.getLogger("fabtwin.security")

PBKDF2_ITERATIONS = 120_000
TOKEN_TTL_SECONDS = 7 * 24 * 3600  # 7 天

# 2026-10-29 修复：原先默认密钥是仓库里的常量 "fabtwin-dev-token-secret-v1"，
# 任何人拿到源码即可伪造任意用户的 token。改为：
#   1) 显式设置 FABTWIN_TOKEN_SECRET → 直接用（生产必须这样部署）
#   2) 未设置且 FABTWIN_ENV=production → 拒绝启动（防止带默认密钥上生产）
#   3) 开发环境 → 生成随机密钥并持久化到 backend/.dev_token_secret（已 gitignore），
#      保证重启后已登录用户不掉线，同时不再是全网公开的常量
_SECRET_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".dev_token_secret")


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


def legacy_password_for(username: str) -> str:
    """旧版默认密码规则（用户名+"123"），仅用于兼容与透明升级"""
    return f"{username}123"


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
