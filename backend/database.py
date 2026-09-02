"""数据库初始化与连接管理（Oracle + SQLite 本地测试双兼容）"""
import os
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

from config import (
    DATABASE_URL,
    ORACLE_HOST, ORACLE_PORT, ORACLE_SERVICE,
    ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN_TYPE,
)

logger = logging.getLogger(__name__)


def _find_lib_dir(client_dir):
    """返回直接包含 oci.dll 的目录。

    - Full Client 安装：client_dir\\bin\\oci.dll -> 返回 client_dir\\bin
    - Instant Client：client_dir\\oci.dll       -> 返回 client_dir
    - 未找到：返回 ''
    """
    if not client_dir:
        return ''
    bin_dir = os.path.join(client_dir, 'bin')
    if os.path.exists(os.path.join(bin_dir, 'oci.dll')):
        return bin_dir
    if os.path.exists(os.path.join(client_dir, 'oci.dll')):
        return client_dir
    return ''


def _find_tns_admin(client_dir, lib_dir):
    """查找 tnsnames.ora 所在目录。返回 '' 表示未找到。"""
    # TNS_ADMIN 环境变量优先
    env_tns = os.environ.get('TNS_ADMIN', '')
    if env_tns and os.path.exists(env_tns):
        return env_tns
    # Full Client: client_dir\\network\\admin
    candidates = []
    if client_dir:
        candidates.append(os.path.join(client_dir, 'network', 'admin'))
    if lib_dir:
        candidates.append(os.path.join(os.path.dirname(lib_dir), 'network', 'admin'))
    for c in candidates:
        if os.path.exists(c):
            return c
    return ''


# Oracle Thick 模式初始化
try:
    import oracledb

    # 通过环境变量 ORACLE_CLIENT_DIR 指定 Oracle Client 路径
    # 注意：oracledb.init_oracle_client 的 lib_dir 参数需要指向 oci.dll 所在目录
    # 对于 Full Client 安装，oci.dll 在 client_1\\bin 下，不是 client_1 根目录
    client_dir = os.getenv("ORACLE_CLIENT_DIR", "")
    lib_dir = _find_lib_dir(client_dir)

    # 自动设置 TNS_ADMIN（Thick 模式下若连接串是 TNS 别名需要此变量；
    # 使用 EZCONNECT/makedsn 不需要，但设置后可作为兜底）
    if lib_dir and not os.environ.get("TNS_ADMIN"):
        tns_admin = _find_tns_admin(client_dir, lib_dir)
        if tns_admin:
            os.environ["TNS_ADMIN"] = tns_admin
            logger.info(f"TNS_ADMIN 自动设置为: {tns_admin}")

    try:
        if lib_dir:
            oracledb.init_oracle_client(lib_dir=lib_dir)
            logger.info(f"oracledb Thick 模式已启用 (lib_dir={lib_dir})，支持 Oracle 9.2+")
        elif client_dir:
            # client_dir 设置但 oci.dll 未找到，明确报错
            logger.error(
                f"ORACLE_CLIENT_DIR={client_dir} 但未找到 oci.dll "
                f"(已检查 client_dir 和 client_dir\\bin)，使用 Thin 模式"
            )
            logger.error("请确认 ORACLE_CLIENT_DIR 指向 Oracle Client 根目录")
        else:
            # 未指定 client_dir，尝试自动初始化（需 Oracle Client 在 PATH 中）
            try:
                oracledb.init_oracle_client()
                logger.info("oracledb Thick 模式已启用（自动检测），支持 Oracle 9.2+")
            except Exception as e:
                if "DPI-1072" in str(e):
                    logger.info("oracledb Thick 模式已启用（之前已初始化）")
                else:
                    logger.info(f"Thick 模式不可用，使用 Thin 模式（仅支持 12.1+）: {e}")
    except Exception as e:
        if "DPI-1072" in str(e):
            logger.info("oracledb Thick 模式已启用（之前已初始化）")
        else:
            logger.warning(f"oracledb Thick 模式初始化失败，使用 Thin 模式: {e}")
            logger.warning("如连接 10g/11g 报错 ORA-03134/ORA-28040，请安装 Oracle Client 并设置 ORACLE_CLIENT_DIR")
            logger.warning(f"  当前 ORACLE_CLIENT_DIR={client_dir}")
            logger.warning(f"  检测到 lib_dir={lib_dir or '(未找到 oci.dll)'}")
            logger.warning("  建议：pip install oracledb==2.4.0（4.x 版本有 DPI-1047 bug）")
except ImportError:
    logger.warning("未安装 oracledb 包，Oracle 模式不可用")

# Oracle: 绕过 SQLAlchemy URL 解析，直接用 oracledb.makedsn 生成 DSN
# 原因：sqlalchemy-oracledb 对 ?sid= 查询参数解析在部分版本有问题，
# 导致 ORA-12504 (listener 未收到 SERVICE_NAME)。
# 使用 creator 函数直接调用 oracledb.connect()，DSN 完全由 makedsn 控制。
import oracledb as _oracledb

if ORACLE_DSN_TYPE == "sid":
    _oracle_dsn = _oracledb.makedsn(ORACLE_HOST, ORACLE_PORT, sid=ORACLE_SERVICE)
else:
    _oracle_dsn = _oracledb.makedsn(ORACLE_HOST, ORACLE_PORT, service_name=ORACLE_SERVICE)

logger.info(f"Oracle DSN: {_oracle_dsn}")


def _oracle_creator():
    return _oracledb.connect(user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=_oracle_dsn)


engine = create_engine(
    "oracle+oracledb://",
    creator=_oracle_creator,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db():
    """根据模型定义创建所有数据表，并幂等补齐历史遗漏的列。

    注意：AI 相关表（ai_configs / ai_provider_configs / ai_usage_logs）
    不在代码中自动创建，由 DBA 手动执行 sql/create_ai_tables.sql 完成。
    """
    ai_table_names = {'ai_configs', 'ai_provider_configs', 'ai_usage_logs'}
    tables_to_create = [
        t for t in Base.metadata.sorted_tables
        if t.name not in ai_table_names
    ]
    Base.metadata.create_all(bind=engine, tables=tables_to_create)
    # 在 create_all 之后做"缺列补 ALTER"——只对历史表有效。
    # SQLite 本地测试通常经 create_all 新表不会缺列，这里也走一遍不会出错。
    try:
        _ensure_missing_columns(engine)
    except Exception as e:
        logger.warning(f"[database] 补齐缺失列时出错（忽略，降级处理）：{e}")


def _has_column(conn, table_name: str, column_name: str) -> bool:
    """跨数据库幂等列存在性检查。"""
    url = str(conn.engine.url) if hasattr(conn, 'engine') else str(engine.url)
    lower = url.startswith('sqlite:')
    if lower:
        # SQLite PRAGMA table_info('machines') 返回行：cid name type notnull dflt_value pk
        rows = conn.execute(text(f"PRAGMA table_info('{table_name}')")).all()
        col_names = [r[1].lower() for r in rows]
        return column_name.lower() in col_names
    # Oracle：USER_TAB_COLUMNS 是当前 schema 下所有表列
    sql = text("SELECT COUNT(*) FROM USER_TAB_COLUMNS WHERE TABLE_NAME = UPPER(:t) AND COLUMN_NAME = UPPER(:c)")
    r = conn.execute(sql, {"t": table_name, "c": column_name}).scalar()
    return r and r > 0


def _ensure_missing_columns(eng):
    """对 D 批新增的 display_order 做幂等列补齐（Oracle + SQLite）。"""
    specs = [
        # (table, column, oracle_ddl_type, sqlite_ddl_type, default_value_sql_oracle_for_existing_rows)
        ("machines",      "display_order", "NUMBER(10)",  "INTEGER DEFAULT 0", "DEFAULT 0"),
        ("floor_areas",   "display_order", "NUMBER(10)",  "INTEGER DEFAULT 0", "DEFAULT 0"),
    ]
    with eng.connect() as conn:
        for table, column, ora_dtype, lite_dtype, ora_default in specs:
            if _has_column(conn, table, column):
                logger.info(f"[database] {table}.{column} 列已存在，跳过")
                continue
            url = str(eng.url)
            if url.startswith("sqlite:"):
                ddl = f"ALTER TABLE {table} ADD COLUMN {column} {lite_dtype}"
            else:
                # Oracle 对已有行添加 NOT NULL 列必须给默认值。我们这里允许 NULL，默认 0 即可；
                # 若要安全起见，不写 NOT NULL 约束，模型里也是 nullable。
                ddl = f"ALTER TABLE {table} ADD ({column} {ora_dtype} {ora_default})"
            logger.warning(f"[database] 列 {table}.{column} 不存在，自动执行 ALTER：{ddl}")
            conn.execute(text(ddl))
            conn.commit()
            logger.info(f"[database] {table}.{column} 已自动补齐。")


def get_db():
    """FastAPI 依赖：获取数据库会话，请求结束自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
