# -*- coding: utf-8 -*-
"""
FabTwin DB 对比脚本：本机 Oracle vs 量产 Oracle

用途：
    对比本机测试 DB 和量产 DB 的表结构、行数、关键数据差异。
    连不上量产 DB 时只输出本机 DB 状态。

用法：
    python db_compare.py
    python db_compare.py --remote         # 也对比量产 DB
    python db_compare.py --remote --tables MACHINES,DT_EVENT_RAW
    python db_compare.py --data MACHINES   # 对比 MACHINES 表的实际数据

配置：
    量产 DB 参数从 fab-twin-pro/deploy/env.bat 自动读取，
    也可通过环境变量覆盖（ORACLE_HOST / ORACLE_USER 等）。
"""
import os
import sys
import argparse
import re

try:
    import oracledb
    oracledb.defaults.fetch_lobs = False
except ImportError:
    print("[ERROR] 未安装 oracledb，请: pip install oracledb")
    sys.exit(1)


# ================================================================
#  连接配置
# ================================================================

def parse_env_bat(path: str) -> dict:
    """解析 env.bat，返回环境变量字典"""
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = re.match(r"\s*set\s+(\w+)=(.*?)\s*$", line, re.IGNORECASE)
            if m:
                env[m.group(1)] = m.group(2)
    return env


def make_conn(label: str, host: str, port: int, service: str,
              user: str, password: str, dsn_type: str = "sid"):
    """建立 Oracle 连接"""
    if dsn_type.lower() == "service_name":
        dsn = oracledb.makedsn(host, port, service_name=service)
    else:
        dsn = oracledb.makedsn(host, port, sid=service)
    print(f"[{label}] 连接 {user}@{host}:{port}/{service} ({dsn_type})")
    try:
        conn = oracledb.connect(user=user, password=password, dsn=dsn)
        print(f"[{label}] 连接成功，DB 版本: {conn.version}")
        return conn
    except Exception as e:
        print(f"[{label}] 连接失败: {e}")
        return None


# ================================================================
#  查询函数
# ================================================================

def get_tables(conn) -> list:
    """返回当前用户下所有表名（大写）"""
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM user_tables ORDER BY table_name")
    return [r[0] for r in cur.fetchall()]


def get_columns(conn, table: str) -> list:
    """返回表的列信息: [(column_name, data_type, nullable, data_default)]"""
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name, data_type, nullable, data_default
        FROM user_tab_columns
        WHERE table_name = UPPER(:t)
        ORDER BY column_id
    """, t=table)
    return [(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]


def get_row_count(conn, table: str) -> int:
    """返回表行数（用 COUNT(*)）"""
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        return cur.fetchone()[0]
    except Exception:
        return -1


def get_sample_rows(conn, table: str, limit: int = 5) -> list:
    """返回前 N 行数据（用 ROWNUM，兼容 11g）"""
    cur = conn.cursor()
    cur.execute(f"""
        SELECT * FROM (
            SELECT * FROM {table}
        ) WHERE ROWNUM <= :n
    """, n=limit)
    cols = [d[0].lower() for d in cur.description]
    rows = cur.fetchall()
    return cols, rows


# ================================================================
#  对比逻辑
# ================================================================

def compare_schema(local_conn, remote_conn, tables: list = None):
    """对比表结构差异"""
    print("\n" + "=" * 70)
    print("  表结构对比")
    print("=" * 70)

    local_tables = set(get_tables(local_conn))
    remote_tables = set(get_tables(remote_conn)) if remote_conn else set()

    if tables:
        # 用户指定了表
        local_tables = local_tables & set(t.upper() for t in tables)
        remote_tables = remote_tables & set(t.upper() for t in tables)

    all_tables = sorted(local_tables | remote_tables)

    # 表存在性差异
    only_local = sorted(local_tables - remote_tables)
    only_remote = sorted(remote_tables - local_tables)
    common = sorted(local_tables & remote_tables)

    if only_local:
        print(f"\n仅本机有的表（{len(only_local)}）: {', '.join(only_local)}")
    if only_remote:
        print(f"\n仅量产有的表（{len(only_remote)}）: {', '.join(only_remote)}")
    if not remote_conn:
        print(f"\n本机共有 {len(local_tables)} 张表（未连接量产 DB，跳过对比）")
        return

    print(f"\n共同表 {len(common)} 张，仅本机 {len(only_local)} 张，仅量产 {len(only_remote)} 张")

    # 列差异
    struct_diff = []
    for t in common:
        local_cols = get_columns(local_conn, t)
        remote_cols = get_columns(remote_conn, t)
        local_names = [c[0] for c in local_cols]
        remote_names = [c[0] for c in remote_cols]

        if local_names != remote_names:
            only_local_cols = set(local_names) - set(remote_names)
            only_remote_cols = set(remote_names) - set(local_names)
            order_diff = local_names != remote_names
            struct_diff.append({
                "table": t,
                "only_local_cols": only_local_cols,
                "only_remote_cols": only_remote_cols,
                "order_diff": order_diff,
            })

    if struct_diff:
        print(f"\n--- 表结构差异（{len(struct_diff)} 张表）---")
        for d in struct_diff:
            print(f"  {d['table']}:")
            if d["only_local_cols"]:
                print(f"    仅本机有的列: {d['only_local_cols']}")
            if d["only_remote_cols"]:
                print(f"    仅量产有的列: {d['only_remote_cols']}")
            if d["order_diff"] and not d["only_local_cols"] and not d["only_remote_cols"]:
                print(f"    列顺序不同")
    else:
        print("\n表结构完全一致")


def compare_row_counts(local_conn, remote_conn, tables: list = None):
    """对比行数差异"""
    print("\n" + "=" * 70)
    print("  行数对比")
    print("=" * 70)

    print(f"\n{'表名':<30} {'本机':>10} {'量产':>10} {'差异':>10}")
    print("-" * 65)

    local_tables = set(get_tables(local_conn))
    if tables:
        local_tables = local_tables & set(t.upper() for t in tables)
    local_tables = sorted(local_tables)

    total_local = 0
    total_remote = 0
    diff_count = 0

    for t in local_tables:
        lc = get_row_count(local_conn, t)
        rc = get_row_count(remote_conn, t) if remote_conn else None

        total_local += max(lc, 0)
        total_remote += max(rc, 0) if rc is not None else 0

        rc_str = str(rc) if rc is not None else "N/A"
        diff = ""
        if rc is not None and lc != rc:
            diff = f"{'+' if rc > lc else ''}{rc - lc}"
            diff_count += 1
        print(f"{t:<30} {lc:>10} {rc_str:>10} {diff:>10}")

    print("-" * 65)
    print(f"{'合计':<30} {total_local:>10} {total_remote:>10} {'' if not diff_count else f'{diff_count} 张表有差异'}")


def compare_table_data(local_conn, remote_conn, table: str, key_col: str = None):
    """对比单张表的实际数据"""
    print(f"\n" + "=" * 70)
    print(f"  数据对比: {table}")
    print("=" * 70)

    local_cols, local_rows = get_sample_rows(local_conn, table, limit=1000)
    remote_cols, remote_rows = get_sample_rows(remote_conn, table, limit=1000) if remote_conn else ([], [])

    print(f"本机列: {local_cols}")
    print(f"量产列: {remote_cols}")

    if not key_col:
        # 用第一列做 key
        key_col = local_cols[0] if local_cols else "id"
        key_idx = 0
    else:
        key_col = key_col.lower()
        key_idx = local_cols.index(key_col) if key_col in local_cols else 0

    print(f"对比键: {local_cols[key_idx] if local_cols else 'N/A'}")
    print(f"本机 {len(local_rows)} 行, 量产 {len(remote_rows)} 行")

    local_keys = set(str(r[key_idx]) for r in local_rows)
    remote_keys = set(str(r[key_idx]) for r in remote_rows)

    only_local = local_keys - remote_keys
    only_remote = remote_keys - local_keys
    common = local_keys & remote_keys

    print(f"\n仅本机有: {len(only_local)} 条")
    print(f"仅量产有: {len(only_remote)} 条")
    print(f"相同键: {len(common)} 条")

    if only_local and len(only_local) <= 10:
        print(f"  本机独有键: {sorted(only_local)[:10]}")
    if only_remote and len(only_remote) <= 10:
        print(f"  量产独有键: {sorted(only_remote)[:10]}")


# ================================================================
#  主流程
# ================================================================

def main():
    parser = argparse.ArgumentParser(description="FabTwin DB 对比脚本")
    parser.add_argument("--remote", action="store_true",
                        help="也连接量产 DB 做对比（默认只看本机）")
    parser.add_argument("--tables", type=str, default="",
                        help="指定对比的表（逗号分隔），默认全部")
    parser.add_argument("--data", type=str, default="",
                        help="对比指定表的实际数据（如 --data MACHINES）")
    parser.add_argument("--key", type=str, default="",
                        help="数据对比的主键列名（配合 --data 使用）")
    args = parser.parse_args()

    # 找 env.bat
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_bat = os.path.normpath(os.path.join(script_dir, "..", "deploy", "env.bat"))

    # 本机 DB（固定）
    local_conn = make_conn(
        "本机",
        host="localhost",
        port=1521,
        service="orclpdb",
        user="fabtwin",
        password="fabtwin",
        dsn_type="service_name",
    )
    if not local_conn:
        print("[FATAL] 本机 DB 连不上，退出")
        sys.exit(1)

    # 量产 DB（从 env.bat 读取）
    remote_conn = None
    if args.remote:
        env = parse_env_bat(env_bat)
        # 也支持环境变量覆盖
        host = os.getenv("ORACLE_HOST", env.get("ORACLE_HOST", ""))
        port = int(os.getenv("ORACLE_PORT", env.get("ORACLE_PORT", "1521")))
        service = os.getenv("ORACLE_SERVICE", env.get("ORACLE_SERVICE", ""))
        user = os.getenv("ORACLE_USER", env.get("ORACLE_USER", ""))
        password = os.getenv("ORACLE_PASSWORD", env.get("ORACLE_PASSWORD", ""))
        dsn_type = os.getenv("ORACLE_DSN_TYPE", env.get("ORACLE_DSN_TYPE", "sid"))

        if not host:
            print(f"[ERROR] 未找到量产 DB 配置（{env_bat}）")
        else:
            remote_conn = make_conn(
                "量产",
                host=host, port=port, service=service,
                user=user, password=password, dsn_type=dsn_type,
            )

    tables = [t.strip() for t in args.tables.split(",") if t.strip()] or None

    # 1. 表结构对比
    compare_schema(local_conn, remote_conn, tables)

    # 2. 行数对比
    compare_row_counts(local_conn, remote_conn, tables)

    # 3. 数据对比（指定表）
    if args.data:
        if remote_conn:
            compare_table_data(local_conn, remote_conn, args.data.upper(), args.key)
        else:
            print(f"\n[WARN] 未连接量产 DB（加 --remote 参数），无法对比 {args.data} 的数据")
            # 仍然输出本机数据
            cols, rows = get_sample_rows(local_conn, args.data.upper(), limit=5)
            print(f"\n本机 {args.data} 前 5 行:")
            print(f"  列: {cols}")
            for r in rows:
                print(f"  {r}")

    local_conn.close()
    if remote_conn:
        remote_conn.close()
    print("\n[INFO] 完成")


if __name__ == "__main__":
    main()
