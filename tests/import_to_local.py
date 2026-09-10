# -*- coding: utf-8 -*-
"""
FabTwin 本机 DB 导入脚本（配套 export_from_prod.py）

用途：
    把 export_from_prod.py 导出的 JSONL 文件导入本机 Oracle。
    - 自动清空目标表（DELETE FROM）再插入，避免主键冲突
    - CLOB 字段自动处理
    - 按外键依赖顺序导入

用法：
    python import_to_local.py --in D:\\prod_export_20260910
    python import_to_local.py --in prod_export_20260910 --tables MACHINES,DT_EVENT_RAW
    python import_to_local.py --in prod_export_20260910 --dry-run  # 只看行数，不导入

配置：
    本机 DB 固定：fabtwin/fabtwin@localhost:1521/orclpdb
"""
import os
import sys
import json
import argparse

try:
    import oracledb
    oracledb.defaults.fetch_lobs = False
except ImportError:
    print("[ERROR] 未安装 oracledb")
    sys.exit(1)


# 导入顺序（外键依赖在前）
IMPORT_ORDER = [
    "PERM_DATA", "ROLES", "USERS", "ROLE_PERMISSIONS",
    "FLOORS", "FLOOR_AREAS", "MACHINES", "RECIPES",
    "MACHINE_MODEL_CONFIGS", "MACHINE_TOOL_MAPPINGS", "EVENT_ACTION_MAPPINGS",
    "TRACKS", "VEHICLES", "OHT_POSITIONS", "DASHBOARD_KPI",
    "AI_CONFIGS", "AI_PROVIDER_CONFIGS", "AI_INSIGHTS", "AI_USAGE_LOGS",
    "MACHINE_DIFY_CONFIGS",
    "ALARMS", "LOTS", "MACHINE_EVENTS", "CHAMBER_SNAPSHOTS",
    "DT_EVENT_RAW", "DT_EVENT_RAW_CUR", "DT_EVENT_STD",
    "DT_STATE_SNAPSHOT", "DT_ALARM_EVENT",
    "DT_EVENT_REALTIMELOT", "DT_RTLOT_TOOL_PORT_RULE", "DT_RTLOT_EVENT_RULE",
]


def read_jsonl(path):
    """读 JSONL 文件，返回 list of dict"""
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def import_table(conn, table, jsonl_path, dry_run=False):
    """导入单张表"""
    if not os.path.exists(jsonl_path):
        print(f"  [SKIP] {table}: 文件不存在 {jsonl_path}")
        return 0

    rows = read_jsonl(jsonl_path)
    if not rows:
        print(f"  [SKIP] {table}: 0 行")
        return 0

    if dry_run:
        print(f"  [DRY] {table}: {len(rows)} 行（未导入）")
        return len(rows)

    cur = conn.cursor()

    # 清空目标表
    try:
        cur.execute(f"DELETE FROM {table}")
    except oracledb.DatabaseError as e:
        # 表不存在
        print(f"  [ERROR] {table}: 清空失败 - {e}")
        cur.close()
        return 0

    # 列名
    cols = list(rows[0].keys())
    col_list = ", ".join(cols)
    bind_list = ", ".join(f":{i+1}" for i in range(len(cols)))
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({bind_list})"

    # 批量插入
    batch = []
    inserted = 0
    errors = 0
    for r in rows:
        vals = []
        for c in cols:
            v = r.get(c)
            # 空字符串 -> None（避免 ORA-01400）
            if v == "":
                v = None
            vals.append(v)
        batch.append(vals)

        if len(batch) >= 500:
            try:
                cur.executemany(sql, batch)
                inserted += len(batch)
            except oracledb.DatabaseError as e:
                # 逐条重试
                for b in batch:
                    try:
                        cur.execute(sql, b)
                        inserted += 1
                    except Exception:
                        errors += 1
            batch = []

    if batch:
        try:
            cur.executemany(sql, batch)
            inserted += len(batch)
        except oracledb.DatabaseError:
            for b in batch:
                try:
                    cur.execute(sql, b)
                    inserted += 1
                except Exception:
                    errors += 1

    conn.commit()
    cur.close()
    if errors:
        print(f"  [WARN] {table}: 导入 {inserted}/{len(rows)} 行，失败 {errors}")
    else:
        print(f"  [OK] {table}: 导入 {inserted} 行")
    return inserted


def main():
    parser = argparse.ArgumentParser(description="FabTwin 本机 DB 导入")
    parser.add_argument("--in", dest="in_dir", required=True,
                        help="export_from_prod.py 输出的目录")
    parser.add_argument("--tables", type=str, default="",
                        help="只导指定表（逗号分隔），默认全部")
    parser.add_argument("--dry-run", action="store_true",
                        help="只看行数，不实际导入")
    args = parser.parse_args()

    in_dir = args.in_dir
    if not os.path.isdir(in_dir):
        # 相对路径，尝试相对于脚本目录
        script_dir = os.path.dirname(os.path.abspath(__file__))
        in_dir = os.path.join(script_dir, args.in_dir)
    if not os.path.isdir(in_dir):
        print(f"[ERROR] 目录不存在: {args.in_dir}")
        sys.exit(1)

    # 连接本机
    conn = oracledb.connect(
        user="fabtwin", password="fabtwin",
        dsn=oracledb.makedsn("localhost", 1521, service_name="orclpdb"))
    print(f"[INFO] 连接本机 DB 成功，版本: {conn.version}")
    print(f"[INFO] 输入目录: {in_dir}\n")

    # 表清单
    summary_path = os.path.join(in_dir, "export_summary.json")
    if os.path.exists(summary_path):
        with open(summary_path, "r", encoding="utf-8") as f:
            summary = json.load(f)
        tables_in_export = list(summary.get("tables", {}).keys())
    else:
        # 没有摘要，扫描目录里的 .jsonl
        tables_in_export = [
            os.path.splitext(f)[0] for f in os.listdir(in_dir)
            if f.endswith(".jsonl")
        ]

    if args.tables:
        wanted = [t.strip().upper() for t in args.tables.split(",") if t.strip()]
        tables = [t for t in IMPORT_ORDER if t in wanted]
    else:
        tables = [t for t in IMPORT_ORDER if t in tables_in_export]

    # 导入前预览
    print("===== 导入预览 =====")
    total_rows = 0
    for t in tables:
        p = os.path.join(in_dir, f"{t}.jsonl")
        if os.path.exists(p):
            rows = read_jsonl(p)
            total_rows += len(rows)
            print(f"  {t}: {len(rows)} 行")
        else:
            print(f"  {t}: 文件不存在")
    print(f"合计 {len(tables)} 张表，{total_rows} 行\n")

    if args.dry_run:
        print("[DRY-RUN] 未实际导入")
        conn.close()
        return

    # 导入
    print("===== 开始导入 =====")
    imported = 0
    for t in tables:
        p = os.path.join(in_dir, f"{t}.jsonl")
        cnt = import_table(conn, t, p, dry_run=False)
        imported += cnt

    conn.close()
    print(f"\n[DONE] 共导入 {imported} 行")


if __name__ == "__main__":
    main()
