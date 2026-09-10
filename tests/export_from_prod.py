# -*- coding: utf-8 -*-
"""
FabTwin 量产 DB 导出脚本

用途：
    从量产 Oracle DB 导出数据到 JSONL 文件，供本机测试 DB 导入。
    - DT_EVENT_RAW 表只导最近 2 天数据（数据量大）
    - 其他表全量导出
    - CLOB 字段自动转字符串

用法：
    python export_from_prod.py
    python export_from_prod.py --days 3          # DT_EVENT_RAW 改为 3 天
    python export_from_prod.py --out D:\\export  # 指定输出目录
    python export_from_prod.py --tables MACHINES,DT_EVENT_RAW_CUR  # 只导指定表

配置：
    量产 DB 参数从 fab-twin-pro/deploy/env.bat 自动读取，
    也可通过环境变量覆盖（ORACLE_HOST / ORACLE_USER 等）。

输出：
    在输出目录（默认 ./prod_export_YYYYMMDD）下：
    - 每张表一个 .jsonl 文件（每行一条 JSON）
    - export_summary.json：导出摘要（表名/行数/文件）
    - tables_schema.json：表结构快照（列名/类型）

导入端：
    把整个输出目录拷到本机，运行 import_to_local.py 即可。
"""
import os
import sys
import json
import argparse
import re
from datetime import datetime, timedelta

try:
    import oracledb
    oracledb.defaults.fetch_lobs = False
except ImportError:
    print("[ERROR] 未安装 oracledb，请: pip install oracledb")
    sys.exit(1)


# ================================================================
#  初始化 Thick 模式（Oracle 11g 必需）
# ================================================================
def init_thick_mode(env: dict):
    """初始化 python-oracledb Thick 模式，连接 Oracle 11g 及更早版本必需。

    优先从 env.bat 读 ORACLE_CLIENT_DIR；
    也支持环境变量 ORACLE_CLIENT_DIR 覆盖。
    """
    client_dir = os.getenv("ORACLE_CLIENT_DIR", env.get("ORACLE_CLIENT_DIR", ""))
    if not client_dir:
        # 常见默认路径
        for candidate in (
            r"C:\app\client\c11463\product\19.0.0\client_1",
            r"C:\app\client\product\19.0.0\client_1",
            r"C:\oracle\product\19.0.0\client_1",
        ):
            if os.path.exists(candidate):
                client_dir = candidate
                break
    try:
        if client_dir and os.path.exists(client_dir):
            oracledb.init_oracle_client(lib_dir=client_dir)
            print(f"[INFO] oracledb Thick 模式已启用，Oracle Client: {client_dir}")
        else:
            oracledb.init_oracle_client()
            print(f"[INFO] oracledb Thick 模式已启用（自动检测 Oracle Client）")
    except Exception as e:
        # 已经初始化过会抛错，忽略
        if "has already been initialized" not in str(e):
            print(f"[WARN] 启用 Thick 模式失败: {e}")
            print(f"       Oracle 11g 连接需要 Thick 模式。")
            print(f"       请设置 ORACLE_CLIENT_DIR 环境变量指向 Oracle Client 目录。")
        # else: 已经初始化，正常


# ================================================================
#  要导出的表清单（顺序 = 导入顺序，外键依赖在前）
# ================================================================
EXPORT_TABLES = [
    # 基础配置表
    "PERM_DATA",
    "ROLES",
    "USERS",
    "ROLE_PERMISSIONS",
    "FLOORS",
    "FLOOR_AREAS",
    "MACHINES",
    "RECIPES",
    "MACHINE_MODEL_CONFIGS",
    "MACHINE_TOOL_MAPPINGS",
    "EVENT_ACTION_MAPPINGS",
    "TRACKS",
    "VEHICLES",
    "OHT_POSITIONS",
    "DASHBOARD_KPI",
    # AI 相关表
    "AI_CONFIGS",
    "AI_PROVIDER_CONFIGS",
    "AI_INSIGHTS",
    "AI_USAGE_LOGS",
    "MACHINE_DIFY_CONFIGS",
    # 时序业务表
    "ALARMS",
    "LOTS",
    "MACHINE_EVENTS",
    "CHAMBER_SNAPSHOTS",
    # DT 表
    "DT_EVENT_RAW",            # 特殊：只导最近 N 天
    "DT_EVENT_RAW_CUR",
    "DT_EVENT_STD",
    "DT_STATE_SNAPSHOT",
    "DT_ALARM_EVENT",
    "DT_EVENT_REALTIMELOT",
    "DT_RTLOT_TOOL_PORT_RULE",
    "DT_RTLOT_EVENT_RULE",
]

# 只导最近 N 天的表
PARTIAL_TABLES = {"DT_EVENT_RAW"}
# 时间过滤列（按这些列过滤最近 N 天）
TIME_FILTER_COL = {
    "DT_EVENT_RAW": "EVENT_TS_UTC",
}


# ================================================================
#  解析 env.bat
# ================================================================
def parse_env_bat(path: str) -> dict:
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = re.match(r"\s*set\s+(\w+)=(.*?)\s*$", line, re.IGNORECASE)
            if m:
                env[m.group(1)] = m.group(2)
    return env


# ================================================================
#  连接
# ================================================================
def connect(label, host, port, service, user, password, dsn_type="sid"):
    if dsn_type.lower() == "service_name":
        dsn = oracledb.makedsn(host, port, service_name=service)
    else:
        dsn = oracledb.makedsn(host, port, sid=service)
    print(f"[{label}] 连接 {user}@{host}:{port}/{service} ({dsn_type})")
    try:
        # Thick 模式下使用 oracledb.connect（默认即可）
        conn = oracledb.connect(user=user, password=password, dsn=dsn)
        print(f"[{label}] 连接成功，DB 版本: {conn.version}")
        return conn
    except Exception as e:
        print(f"[{label}] 连接失败: {e}")
        if "DPY-3010" in str(e):
            print(f"\n[HINT] Oracle 11g 需要 Thick 模式。")
            print(f"  请确认本机已安装 Oracle Client (19c+)，并设置 ORACLE_CLIENT_DIR 环境变量。")
            print(f"  或在 env.bat 里配置 ORACLE_CLIENT_DIR=C:\\app\\client\\...\\client_1")
        return None


# ================================================================
#  导出
# ================================================================
def get_columns(conn, table):
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name, data_type FROM user_tab_columns
        WHERE table_name = UPPER(:t) ORDER BY column_id
    """, t=table)
    return [(r[0], r[1]) for r in cur.fetchall()]


def row_to_json(row, cols):
    """把一行转成 dict，处理 LOB/bytes/datetime"""
    out = {}
    for (name, dtype), val in zip(cols, row):
        if val is None:
            out[name] = None
            continue
        if hasattr(val, "read"):
            try:
                val = val.read()
            except Exception:
                val = str(val)
        if isinstance(val, (bytes, bytearray)):
            try:
                val = val.decode("utf-8")
            except Exception:
                val = val.hex()
        if isinstance(val, datetime):
            val = val.strftime("%Y-%m-%d %H:%M:%S")
        out[name] = val
    return out


def export_table(conn, table, out_dir, days_filter=None):
    """导出单张表到 JSONL 文件"""
    cols = get_columns(conn, table)
    if not cols:
        print(f"  [SKIP] {table}: 表不存在或无列")
        return 0

    col_names = [c[0] for c in cols]
    col_list = ", ".join(col_names)
    where = ""
    params = {}

    if days_filter and table in PARTIAL_TABLES:
        tcol = TIME_FILTER_COL.get(table, "EVENT_TS_UTC")
        # 兼容字符列和时间戳列：尝试 TO_TIMESTAMP
        # 用近 N 天
        since = (datetime.utcnow() - timedelta(days=days_filter)).strftime("%Y-%m-%d")
        # 先尝试字符比较（EVENT_TS_UTC 是 VARCHAR2）
        where = f"WHERE {tcol} >= :since"
        params = {"since": since + " 00:00:00"}
        print(f"  [INFO] {table}: 过滤 {tcol} >= {since} (最近 {days_filter} 天)")

    # 用 ROWNUM 限制 DT_EVENT_RAW（数据量大）
    sql = f"SELECT {col_list} FROM {table} {where}"
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
    except oracledb.DatabaseError as e:
        # 如果时间过滤列类型不匹配，回退到全量
        if days_filter and "ORA-00932" in str(e) or "ORA-01861" in str(e):
            print(f"  [WARN] {table}: 时间过滤失败 ({e.args[0].message if hasattr(e,'args') and e.args else e})，回退全量")
            where = ""
            params = {}
            sql = f"SELECT {col_list} FROM {table}"
            cur.execute(sql, params)
        else:
            raise

    out_file = os.path.join(out_dir, f"{table}.jsonl")
    cnt = 0
    with open(out_file, "w", encoding="utf-8") as f:
        while True:
            rows = cur.fetchmany(500)
            if not rows:
                break
            for r in rows:
                f.write(json.dumps(row_to_json(r, cols), ensure_ascii=False) + "\n")
                cnt += 1
    cur.close()
    print(f"  [OK] {table}: {cnt} 行 -> {os.path.basename(out_file)}")
    return cnt


def export_schema_snapshot(conn, out_dir):
    """导出表结构快照"""
    cur = conn.cursor()
    cur.execute("""
        SELECT table_name, column_name, data_type, data_length, nullable
        FROM user_tab_columns
        ORDER BY table_name, column_id
    """)
    schema = {}
    for r in cur.fetchall():
        t = r[0]
        if t not in schema:
            schema[t] = []
        schema[t].append({
            "column": r[1], "type": r[2], "length": r[3], "nullable": r[4]
        })
    cur.close()
    with open(os.path.join(out_dir, "tables_schema.json"), "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
    print(f"  [OK] 表结构快照 -> tables_schema.json ({len(schema)} 张表)")


# ================================================================
#  主流程
# ================================================================
def main():
    parser = argparse.ArgumentParser(description="FabTwin 量产 DB 导出脚本")
    parser.add_argument("--days", type=int, default=2,
                        help="DT_EVENT_RAW 只导最近 N 天（默认 2）")
    parser.add_argument("--out", type=str, default="",
                        help="输出目录（默认 prod_export_YYYYMMDD）")
    parser.add_argument("--tables", type=str, default="",
                        help="只导指定表（逗号分隔），默认全部")
    args = parser.parse_args()

    # 找 env.bat
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_bat = os.path.normpath(os.path.join(script_dir, "..", "deploy", "env.bat"))

    env = parse_env_bat(env_bat)

    # 初始化 Thick 模式（Oracle 11g 必需）
    init_thick_mode(env)

    host = os.getenv("ORACLE_HOST", env.get("ORACLE_HOST", ""))
    port = int(os.getenv("ORACLE_PORT", env.get("ORACLE_PORT", "1521")))
    service = os.getenv("ORACLE_SERVICE", env.get("ORACLE_SERVICE", ""))
    user = os.getenv("ORACLE_USER", env.get("ORACLE_USER", ""))
    password = os.getenv("ORACLE_PASSWORD", env.get("ORACLE_PASSWORD", ""))
    dsn_type = os.getenv("ORACLE_DSN_TYPE", env.get("ORACLE_DSN_TYPE", "sid"))

    if not host:
        print(f"[ERROR] 未找到量产 DB 配置（{env_bat}）")
        sys.exit(1)

    conn = connect("量产", host, port, service, user, password, dsn_type)
    if not conn:
        sys.exit(1)

    # 输出目录
    if args.out:
        out_dir = args.out
    else:
        out_dir = os.path.join(script_dir, f"prod_export_{datetime.now().strftime('%Y%m%d')}")
    os.makedirs(out_dir, exist_ok=True)
    print(f"\n[INFO] 输出目录: {out_dir}\n")

    # 表清单
    tables = EXPORT_TABLES
    if args.tables:
        tables = [t.strip().upper() for t in args.tables.split(",") if t.strip()]

    # 1. 表结构快照
    print("===== 导出表结构 =====")
    export_schema_snapshot(conn, out_dir)

    # 2. 逐表导出
    print(f"\n===== 导出数据（{len(tables)} 张表）=====")
    summary = {"export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "days_filter": args.days, "tables": {}}
    for t in tables:
        cnt = export_table(conn, t, out_dir, days_filter=args.days)
        summary["tables"][t] = {"rows": cnt, "file": f"{t}.jsonl"}

    # 3. 摘要
    with open(os.path.join(out_dir, "export_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n===== 导出摘要 -> export_summary.json =====")
    total = sum(v["rows"] for v in summary["tables"].values())
    print(f"[DONE] 共 {len(summary['tables'])} 张表，{total} 行")
    print(f"\n下一步：把整个目录 {out_dir} 拷到本机，运行 import_to_local.py 导入")

    conn.close()


if __name__ == "__main__":
    main()
