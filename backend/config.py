"""应用配置：数据库路径、API端口、CORS来源、Redis配置等"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ========== 数据库配置 ==========
# 支持 SQLite / Oracle 一键切换
# 切换方式：设置环境变量 DB_TYPE=oracle 并配置 ORACLE_DSN
# 本地开发默认使用 SQLite，生产部署切 Oracle 无需改代码
DB_TYPE = os.getenv("DB_TYPE", "oracle").lower()

if DB_TYPE == "oracle":
    ORACLE_USER = os.getenv("ORACLE_USER", "fabtwin")
    ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "fabtwin")
    ORACLE_HOST = os.getenv("ORACLE_HOST", "localhost")
    ORACLE_PORT = int(os.getenv("ORACLE_PORT", "1521"))
    ORACLE_SERVICE = os.getenv("ORACLE_SERVICE", "ORCLPDB")
    DATABASE_URL = f"oracle+oracledb://{ORACLE_USER}:{ORACLE_PASSWORD}@{ORACLE_HOST}:{ORACLE_PORT}/?service_name={ORACLE_SERVICE}"
    DB_IS_SQLITE = False
else:
    DB_PATH = os.path.join(BASE_DIR, "fabtwin.db")
    DATABASE_URL = f"sqlite:///{DB_PATH}"
    DB_IS_SQLITE = True

# ========== Redis 缓存配置 ==========
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_ENABLED = False

# ========== API 服务配置 ==========
API_HOST = "0.0.0.0"
API_PORT = 8002

# ========== CORS 配置 ==========
CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]

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
