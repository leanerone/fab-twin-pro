"""数据库初始化与连接管理（支持 SQLite / Oracle 一键切换）

Oracle 兼容性说明：
- Thin 模式（默认）：仅支持 Oracle 12.1+，无需 Oracle Client
- Thick 模式：支持 Oracle 9.2+（含 10g/11g），需 Oracle Instant Client 11.2+

如需连接 10g/11g，请设置环境变量 ORACLE_CLIENT_DIR 指向 Instant Client 目录，
本模块会自动调用 init_oracle_client() 切换到 Thick 模式。
"""
import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config import DATABASE_URL, DB_IS_SQLITE

logger = logging.getLogger(__name__)

# Oracle Thick 模式初始化（仅 Oracle 类型时执行）
if not DB_IS_SQLITE:
    try:
        import oracledb

        # 通过环境变量 ORACLE_CLIENT_DIR 指定 Instant Client 路径
        # 如未指定，oracledb 会尝试从 PATH 中查找
        client_dir = os.getenv("ORACLE_CLIENT_DIR", "")
        try:
            if client_dir:
                if os.path.exists(client_dir):
                    oracledb.init_oracle_client(lib_dir=client_dir)
                    logger.info(f"oracledb Thick 模式已启用 (client_dir={client_dir})，支持 Oracle 9.2+")
                else:
                    logger.warning(f"ORACLE_CLIENT_DIR 不存在: {client_dir}，使用 Thin 模式（仅支持 12.1+）")
            else:
                # 未指定 client_dir，尝试自动初始化（需 Instant Client 在 PATH 中）
                try:
                    oracledb.init_oracle_client()
                    logger.info("oracledb Thick 模式已启用（自动检测），支持 Oracle 9.2+")
                except Exception as e:
                    # 已初始化或无 Client，保持 Thin 模式
                    if "DPI-1072" in str(e):
                        logger.info("oracledb Thick 模式已启用（之前已初始化）")
                    else:
                        logger.info(f"Thick 模式不可用，使用 Thin 模式（仅支持 12.1+）: {e}")
        except Exception as e:
            if "DPI-1072" in str(e):
                logger.info("oracledb Thick 模式已启用（之前已初始化）")
            else:
                logger.warning(f"oracledb Thick 模式初始化失败，使用 Thin 模式: {e}")
                logger.warning("如连接 10g/11g 报错 ORA-03134/ORA-28040，请安装 Oracle Instant Client 并设置 ORACLE_CLIENT_DIR")
    except ImportError:
        logger.warning("未安装 oracledb 包，Oracle 模式不可用")

_connect_args = {}
if DB_IS_SQLITE:
    _connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db():
    """根据模型定义创建所有数据表"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI 依赖：获取数据库会话，请求结束自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
