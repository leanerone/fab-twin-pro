# -*- coding: utf-8 -*-
"""诊断导入失败的表，打印具体错误"""
import os
import json
import oracledb

oracledb.defaults.fetch_lobs = False

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(HERE, "prod_export_20260910")

FAILED_TABLES = ["USERS", "MACHINE_MODEL_CONFIGS", "DT_STATE_SNAPSHOT",
                 "DT_EVENT_REALTIMELOT", "DT_RTLOT_TOOL_PORT_RULE", "DT_RTLOT_EVENT_RULE"]

conn = oracledb.connect(
    user="fabtwin", password="fabtwin",
    dsn=oracledb.makedsn("localhost", 1521, service_name="orclpdb"))
cur = conn.cursor()

for table in FAILED_TABLES:
    p = os.path.join(EXPORT_DIR, f"{table}.jsonl")
    if not os.path.exists(p):
        print(f"\n[{table}] 文件不存在")
        continue
    with open(p, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    if not rows:
        print(f"\n[{table}] 空文件")
        continue

    cols = list(rows[0].keys())
    col_list = ", ".join(f'"{c}"' for c in cols)
    bind_list = ", ".join(f":{i+1}" for i in range(len(cols)))
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({bind_list})"

    print(f"\n[{table}] 列: {cols}")
    # 尝试第一条，打印详细错误
    r = rows[0]
    vals = [None if r.get(c) == "" else r.get(c) for c in cols]
    try:
        cur.execute(sql, vals)
        print("  第一条成功!")
        conn.rollback()
    except oracledb.DatabaseError as e:
        print(f"  第一条失败: {e}")
        # 尝试字符串绑定
        try:
            str_vals = [str(v) if v is not None else None for v in vals]
            cur.execute(sql, str_vals)
            print("  转字符串后成功!")
            conn.rollback()
        except oracledb.DatabaseError as e2:
            print(f"  转字符串仍失败: {e2}")

conn.close()
