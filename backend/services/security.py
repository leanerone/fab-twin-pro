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
import os
import secrets
import time

PBKDF2_ITERATIONS = 120_000
TOKEN_TTL_SECONDS = 7 * 24 * 3600  # 7 天

# 生产部署务必通过环境变量覆盖
_TOKEN_SECRET = os.getenv("FABTWIN_TOKEN_SECRET", "fabtwin-dev-token-secret-v1").encode("utf-8")


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
