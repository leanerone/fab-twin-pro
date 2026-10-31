# -*- coding: utf-8 -*-
"""逐条检查 USERS / MACHINE_MODEL_CONFIGS 插入，定位失败行"""
import os
import json
import oracledb

oracledb.defaults.fetch_lobs = False

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(HERE, "prod_export_20260910")

conn = oracledb.connect(
    user="fabtwin", password="fabtwin",
    dsn=oracledb.makedsn("localhost", 1521, service_name="orclpdb"))
cur = conn.cursor()

for table in ["USERS", "MACHINE_MODEL_CONFIGS"]:
    print(f"\n===== {table} =====")
    p = os.path.join(EXPORT_DIR, f"{table}.jsonl")
    with open(p, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    # 检查重复主键
    pk = "ID" if table == "USERS" else "MODEL_ID"
    seen = {}
    for r in rows:
        v = r.get(pk)
        seen[v] = seen.get(v, 0) + 1
    dups = {k: v for k, v in seen.items() if v > 1}
    print(f"总行数: {len(rows)}, 主键 {pk}")
    if dups:
        print(f"  重复主键: {dups}")
    else:
        print(f"  无重复主键")

    cur.execute(f"DELETE FROM {table}")
    cols = list(rows[0].keys())
    col_list = ", ".join(f'"{c}"' for c in cols)
    bind_list = ", ".join(f":{i+1}" for i in range(len(cols)))
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({bind_list})"

    ok = 0
    fail = 0
    for i, r in enumerate(rows):
        vals = [None if r.get(c) == "" else r.get(c) for c in cols]
        try:
            cur.execute(sql, vals)
            ok += 1
        except oracledb.DatabaseError as e:
            fail += 1
            print(f"  行{i} 失败: {e}")
            print(f"    数据: {json.dumps(r, ensure_ascii=False)[:200]}")
            if fail > 3:
                print("  ...更多失败省略")
                break
    print(f"成功 {ok}, 失败 {fail}")
    conn.rollback()

conn.close()
