# -*- coding: utf-8 -*-
r"""
本地测试库 全量逻辑备份 / 恢复 工具
======================================
用途：防止误删数据后无法恢复。备份为 JSONL（每表一个文件），可完整回灌。

备份：python tests\db_backup.py backup
      python tests\db_backup.py backup --tag before_cleanup
恢复：python tests\db_backup.py restore --from tests\db_backups\20260911_1030
      python tests\db_backup.py restore --from ... --tables DT_EVENT_RAW,MACHINES
列表：python tests\db_backup.py list

设计要点：
 - 备份目录带时间戳，永不覆盖历史备份
 - CLOB 自动转 str；datetime 转 ISO 字符串
 - 恢复默认「先 DELETE 再插入」，可用 --append 追加
 - 恢复按外键依赖顺序执行
 - 生成 manifest.json 记录每表行数，恢复后自动校验
"""
import argparse
import datetime as dt
import json
import os
import sys

import oracledb

DSN = os.getenv("LOCAL_ORACLE_DSN", "localhost:1521/orclpdb")
USER = os.getenv("LOCAL_ORACLE_USER", "fabtwin")
PWD = os.getenv("LOCAL_ORACLE_PASSWORD", "fabtwin")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_ROOT = os.path.join(BASE_DIR, "db_backups")

# 恢复顺序：父表在前，子表在后
RESTORE_ORDER = [
    "FLOORS", "FLOOR_AREAS", "MACHINES", "MACHINE_MODEL_CONFIGS",
    "MACHINE_TOOL_MAPPINGS", "MACHINE_DIFY_CONFIGS", "EVENT_ACTION_MAPPINGS",
    "RECIPES", "LOTS", "ROLES", "PERM_DATA", "ROLE_PERMISSIONS", "USERS",
    "AI_PROVIDER_CONFIGS", "AI_CONFIGS", "AI_INSIGHTS", "AI_USAGE_LOGS",
    "ALARMS", "MACHINE_EVENTS", "CHAMBER_SNAPSHOTS", "DASHBOARD_KPI",
    "OHT_POSITIONS", "TRACKS", "VEHICLES",
    "DT_RTLOT_TOOL_PORT_RULE", "DT_RTLOT_EVENT_RULE",
    "DT_EVENT_RAW", "DT_EVENT_RAW_CUR", "DT_EVENT_STD",
    "DT_STATE_SNAPSHOT", "DT_ALARM_EVENT", "DT_EVENT_REALTIMELOT",
]

# IDENTITY 自增列表，恢复时跳过该列
IDENTITY_COLS = {
    "DT_STATE_SNAPSHOT": ["SNAPSHOT_ID"],
    "DT_ALARM_EVENT": ["ALARM_EVENT_ID", "ID"],
}


def connect():
    oracledb.defaults.fetch_lobs = False
    return oracledb.connect(user=USER, password=PWD, dsn=DSN)


def all_tables(cur):
    cur.execute("SELECT table_name FROM user_tables ORDER BY table_name")
    return [r[0] for r in cur.fetchall()]


def table_columns(cur, table):
    cur.execute(
        "SELECT column_name FROM user_tab_columns "
        "WHERE table_name = :t ORDER BY column_id", t=table)
    return [r[0] for r in cur.fetchall()]


def norm(v):
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return v


def do_backup(args):
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{stamp}_{args.tag}" if args.tag else stamp
    out_dir = os.path.join(BACKUP_ROOT, name)
    os.makedirs(out_dir, exist_ok=True)

    conn = connect()
    cur = conn.cursor()
    tables = args.tables.split(",") if args.tables else all_tables(cur)

    manifest = {"created_at": dt.datetime.now().isoformat(),
                "dsn": DSN, "user": USER, "tag": args.tag or "",
                "tables": {}}
    total = 0
    for t in tables:
        t = t.strip().upper()
        try:
            cols = table_columns(cur, t)
            if not cols:
                print(f"  [SKIP] {t} 不存在")
                continue
            sel = ", ".join(f'"{c}"' for c in cols)
            cur.execute(f'SELECT {sel} FROM "{t}"')
            rows = cur.fetchall()
            path = os.path.join(out_dir, f"{t}.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(
                        {c: norm(v) for c, v in zip(cols, r)},
                        ensure_ascii=False) + "\n")
            manifest["tables"][t] = {"rows": len(rows), "columns": cols}
            total += len(rows)
            print(f"  [OK] {t:<28} {len(rows)} 行")
        except Exception as e:
            print(f"  [ERR] {t}: {e}")
            manifest["tables"][t] = {"rows": -1, "error": str(e)}

    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    cur.close()
    conn.close()
    print(f"\n备份完成：{out_dir}")
    print(f"共 {len(manifest['tables'])} 张表 / {total} 行")
    return 0


def do_restore(args):
    src = args.src
    if not os.path.isdir(src):
        print(f"[FATAL] 备份目录不存在：{src}")
        return 1
    mf_path = os.path.join(src, "manifest.json")
    manifest = {}
    if os.path.exists(mf_path):
        with open(mf_path, encoding="utf-8") as f:
            manifest = json.load(f)
        print(f"备份创建于 {manifest.get('created_at')}  tag={manifest.get('tag')}")

    want = {t.strip().upper() for t in args.tables.split(",")} if args.tables else None
    ordered = [t for t in RESTORE_ORDER if os.path.exists(os.path.join(src, f"{t}.jsonl"))]
    extra = sorted(fn[:-6] for fn in os.listdir(src)
                   if fn.endswith(".jsonl") and fn[:-6] not in ordered)
    targets = [t for t in ordered + extra if not want or t in want]

    if not args.yes:
        print(f"\n将恢复 {len(targets)} 张表到 {USER}@{DSN}")
        print("模式：" + ("追加" if args.append else "先清空再插入"))
        print("如需继续请加 --yes")
        return 1

    conn = connect()
    cur = conn.cursor()
    total = 0
    for t in targets:
        path = os.path.join(src, f"{t}.jsonl")
        rows = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        try:
            if not args.append:
                cur.execute(f'DELETE FROM "{t}"')
            if rows:
                skip = set(IDENTITY_COLS.get(t, []))
                cols = [c for c in rows[0].keys() if c not in skip]
                collist = ", ".join(f'"{c}"' for c in cols)
                binds = ", ".join(f":{i+1}" for i in range(len(cols)))
                sql = f'INSERT INTO "{t}" ({collist}) VALUES ({binds})'
                data = [[(None if r.get(c) == "" else r.get(c)) for c in cols]
                        for r in rows]
                ok = 0
                for i in range(0, len(data), 500):
                    batch = data[i:i + 500]
                    try:
                        cur.executemany(sql, batch)
                        ok += len(batch)
                    except Exception:
                        for row in batch:
                            try:
                                cur.execute(sql, row)
                                ok += 1
                            except Exception as e2:
                                print(f"    [ROW-ERR] {t}: {e2}")
                conn.commit()
                total += ok
                print(f"  [OK] {t:<28} {ok}/{len(rows)} 行")
            else:
                conn.commit()
                print(f"  [OK] {t:<28} 0 行（已清空）")
        except Exception as e:
            conn.rollback()
            print(f"  [ERR] {t}: {e}")

    print("\n--- 恢复后行数校验 ---")
    for t in targets:
        cur.execute(f'SELECT COUNT(*) FROM "{t}"')
        now = cur.fetchone()[0]
        exp = manifest.get("tables", {}).get(t, {}).get("rows", "?")
        flag = "OK" if now == exp else "DIFF"
        print(f"  [{flag}] {t:<28} 现有 {now} / 备份 {exp}")

    cur.close()
    conn.close()
    print(f"\n恢复完成，共写入 {total} 行")
    return 0


def do_list(args):
    if not os.path.isdir(BACKUP_ROOT):
        print("尚无任何备份")
        return 0
    for name in sorted(os.listdir(BACKUP_ROOT), reverse=True):
        d = os.path.join(BACKUP_ROOT, name)
        if not os.path.isdir(d):
            continue
        mf = os.path.join(d, "manifest.json")
        info = ""
        if os.path.exists(mf):
            with open(mf, encoding="utf-8") as f:
                m = json.load(f)
            rows = sum(v.get("rows", 0) for v in m.get("tables", {}).values()
                       if v.get("rows", 0) > 0)
            info = f"  {len(m.get('tables', {}))} 表 / {rows} 行  {m.get('created_at','')}"
        print(f"{name}{info}")
    return 0


def main():
    p = argparse.ArgumentParser(description="本地 Oracle 测试库备份/恢复")
    sub = p.add_subparsers(dest="cmd", required=True)

    pb = sub.add_parser("backup", help="全量备份到 tests/db_backups/<时间戳>")
    pb.add_argument("--tag", default="", help="备份标签，如 before_cleanup")
    pb.add_argument("--tables", default="", help="仅备份指定表，逗号分隔")
    pb.set_defaults(func=do_backup)

    pr = sub.add_parser("restore", help="从备份目录恢复")
    pr.add_argument("--from", dest="src", required=True, help="备份目录路径")
    pr.add_argument("--tables", default="", help="仅恢复指定表，逗号分隔")
    pr.add_argument("--append", action="store_true", help="追加模式（不清空）")
    pr.add_argument("--yes", action="store_true", help="确认执行")
    pr.set_defaults(func=do_restore)

    pl = sub.add_parser("list", help="列出已有备份")
    pl.set_defaults(func=do_list)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
