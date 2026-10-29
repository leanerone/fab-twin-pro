"""应用配置：Oracle 数据库连接、API端口、CORS、Redis等

量产环境唯一数据库：Oracle。
不再支持 SQLite，避免本地/量产行为不一致。
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ========== 数据库配置（Oracle only）==========
DB_TYPE = os.getenv("DB_TYPE", "oracle").strip().lower()
if DB_TYPE != "oracle":
    print(f"[FATAL] DB_TYPE={DB_TYPE} 不支持。本项目仅支持 Oracle，请设置 DB_TYPE=oracle", file=sys.stderr)
    sys.exit(1)

# Oracle 连接参数
ORACLE_USER = os.getenv("ORACLE_USER", "fabtwin")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "fabtwin")
ORACLE_HOST = os.getenv("ORACLE_HOST", "localhost")
ORACLE_PORT = int(os.getenv("ORACLE_PORT", "1521"))
_RAW_ORACLE_SERVICE = os.getenv("ORACLE_SERVICE", "")


def _probe_service_name() -> str:
    """未显式指定服务名时，自动挑一个 listener 真正认得、且能登录的服务。

    起因（2026-10-30）：本机是 Oracle **21c XE**，其可插拔库叫 XEPDB1；而这里长期写死
    ORCLPDB，导致缺省环境下任何连库操作都拿 ORA-12514 失败——包括 AI 的真实取数链路。
    与其让人记住设环境变量，不如启动时花几百毫秒探一次。

    判定细节：ORA-01017（用户/口令不符）说明 listener 认识该服务但这份凭据进不去
    （典型是误连到 CDB 根容器 XE），要跳过而不是当成可用。
    """
    candidates = ["ORCLPDB", "XEPDB1", "FREEPDB1", "XE", "ORCL"]
    try:
        import oracledb  # type: ignore
    except Exception:
        return "ORCLPDB"
    for svc in candidates:
        try:
            conn = oracledb.connect(
                user=ORACLE_USER, password=ORACLE_PASSWORD,
                host=ORACLE_HOST, port=ORACLE_PORT, service_name=svc,
                tcp_connect_timeout=2.0,
            )
            conn.close()
            return svc
        except Exception as exc:
            if "ORA-01017" in str(exc) or "ORA-01005" in str(exc):
                continue  # listener 认得但凭据不符，继续找真正的 PDB
            continue
    return "ORCLPDB"


# 显式环境变量优先；未指定才自动探测（探测结果不再回写环境变量，避免污染子进程）
ORACLE_SERVICE = _RAW_ORACLE_SERVICE or _probe_service_name()
# DSN type: service_name (12c+ PDB) or sid (10g/11g traditional)
# Set ORACLE_DSN_TYPE=sid for Oracle 10g/11g
ORACLE_DSN_TYPE = os.getenv("ORACLE_DSN_TYPE", "service_name").lower()

if ORACLE_DSN_TYPE == "sid":
    DATABASE_URL = f"oracle+oracledb://{ORACLE_USER}:{ORACLE_PASSWORD}@{ORACLE_HOST}:{ORACLE_PORT}/?sid={ORACLE_SERVICE}"
else:
    DATABASE_URL = f"oracle+oracledb://{ORACLE_USER}:{ORACLE_PASSWORD}@{ORACLE_HOST}:{ORACLE_PORT}/?service_name={ORACLE_SERVICE}"

DB_IS_SQLITE = False  # 保留变量供兼容性检查，始终为 False

# ========== Redis 缓存配置（T7: Garnet 优先、内存兜底）==========
# 默认 127.0.0.1 而非 localhost：避免本机无监听时 IPv6+IPv4 双协议栈顺序连接、超时翻倍
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "false").strip().lower() in ("1", "true", "yes")

# ========== API 服务配置 ==========
API_HOST = "0.0.0.0"
API_PORT = 8002

# ========== CORS 配置 ==========
CORS_ORIGINS = ["http://localhost:5173", "http://localhost:5174", "http://localhost:5175", "http://localhost:5176", "http://localhost:5177", "http://localhost:3000"]

# ========== 模拟配置 ==========
SIMULATION_ENABLED = False       # 是否启用模拟器（Demo用）
SIMULATION_INTERVAL_MS = 2000    # 模拟器事件间隔（毫秒）
DB_POLLER_ENABLED = True         # 是否启用DB事件轮询（WinForm/外部系统写入DB时用）
DB_POLLER_INTERVAL_MS = 1000     # DB轮询间隔（毫秒）
HISTORY_START_HOUR = 8           # 历史数据开始时间（小时）
HISTORY_END_HOUR = 20            # 历史数据结束时间（小时）

# ========== ODS 数据同步配置 ==========
ODS_SYNC_ENABLED = False         # 是否启用ODS同步（连接真实Oracle时启用）
ODS_SYNC_INTERVAL_SEC = 30       # ODS同步间隔（秒）
ODS_ORACLE_URL = ""              # ODS Oracle连接串

# ========== 语音识别（ASR）配置 ==========
# 使用 HuggingFace 国内镜像下载 whisper 模型（避免 huggingface.co 被墙）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")
# Whisper 模型配置（环境变量优先）
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "tiny")  # tiny/base/small/medium/large-v3
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")            # cpu/cuda
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

# ========== AI 中间适配层配置 ==========
AI_MCP_ENABLED = False           # 是否启用AI MCP（连接Dify/n8n时启用）
AI_MCP_URL = ""                  # Dify/n8n API地址（旧版兼容）
AI_MCP_API_KEY = ""              # API Key（旧版兼容）

# AI Provider: local / openai / dify / hybrid
AI_PROVIDER = os.getenv("AI_PROVIDER", "local")

# ========== OpenAI 兼容模型配置（GLM-5.2、GPT系列、本地私有化模型） ==========
AI_BASE_URL = os.getenv("AI_BASE_URL", "")       # 如：https://open.bigmodel.cn/api/paas/v4
AI_API_KEY = os.getenv("AI_API_KEY", "")         # API Key
AI_MODEL = os.getenv("AI_MODEL", "glm-5.2")      # 模型名称
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.7"))
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "2048"))

# ========== Dify 配置 ==========
DIFY_ENABLED = os.getenv("DIFY_ENABLED", "False").lower() == "true"
DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", "")   # Dify API地址
DIFY_API_KEY = os.getenv("DIFY_API_KEY", "")     # Dify API Key
DIFY_APP_ID = os.getenv("DIFY_APP_ID", "")       # Dify应用ID

# ========== N8N 配置 ==========
N8N_ENABLED = os.getenv("N8N_ENABLED", "False").lower() == "true"
N8N_BASE_URL = os.getenv("N8N_BASE_URL", "")     # N8N服务地址
N8N_WEBHOOK_SECRET = os.getenv("N8N_WEBHOOK_SECRET", "")  # Webhook密钥
