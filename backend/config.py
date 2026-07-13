"""应用配置：数据库路径、API端口、CORS来源、Redis配置等"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ========== 数据库配置 ==========
# SQLite（Demo模式，零配置）
DB_PATH = os.path.join(BASE_DIR, "fabtwin.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Oracle（生产模式，需要配置）
# ORACLE_URL = "oracle+cx_oracle://username:password@host:1521/service_name"

# ========== Redis 缓存配置 ==========
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
REDIS_ENABLED = False

# ========== API 服务配置 ==========
API_HOST = "0.0.0.0"
API_PORT = 8001

# ========== CORS 配置 ==========
CORS_ORIGINS = ["http://localhost:5173", "http://localhost:3000"]

# ========== 模拟配置 ==========
SIMULATION_ENABLED = True        # 是否启用模拟器（Demo用）
SIMULATION_INTERVAL_MS = 2000    # 模拟器事件间隔（毫秒）
HISTORY_START_HOUR = 8           # 历史数据开始时间（小时）
HISTORY_END_HOUR = 20            # 历史数据结束时间（小时）

# ========== ODS 数据同步配置 ==========
ODS_SYNC_ENABLED = False         # 是否启用ODS同步（连接真实Oracle时启用）
ODS_SYNC_INTERVAL_SEC = 30       # ODS同步间隔（秒）
ODS_ORACLE_URL = ""              # ODS Oracle连接串

# ========== AI MCP 配置 ==========
AI_MCP_ENABLED = False           # 是否启用AI MCP（连接Dify/n8n时启用）
AI_MCP_URL = ""                  # Dify/n8n API地址
AI_MCP_API_KEY = ""              # API Key
