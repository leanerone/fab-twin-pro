# -*- coding: utf-8 -*-
"""检查本机表结构 vs JSONL 列，用于导入前校验"""
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

# 1. 读取本机所有表的列结构
def get_local_cols(table):
    cur.execute(f"SELECT column_name, data_type FROM user_tab_columns WHERE table_name = '{table}' ORDER BY column_id")
    return {r[0]: r[1] for r in cur.fetchall()}

# 2. 读取 JSONL 文件的列
def get_jsonl_cols(table):
    p = os.path.join(EXPORT_DIR, f"{table}.jsonl")
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                return list(json.loads(line).keys())
    return []

print("=" * 80)
print("表结构对比: 本机列 vs JSONL 列")
print("=" * 80)

jsonl_files = [f for f in os.listdir(EXPORT_DIR) if f.endswith(".jsonl")]
for f in sorted(jsonl_files):
    table = f.replace(".jsonl", "")
    local_cols = get_local_cols(table)
    jsonl_cols = get_jsonl_cols(table)
    if jsonl_cols is None:
        print(f"\n[{table}] JSONL 文件不存在")
        continue
    if not local_cols:
        print(f"\n[{table}] 本机表不存在!")
        continue
    missing_in_local = [c for c in jsonl_cols if c not in local_cols]
    missing_in_jsonl = [c for c in local_cols if c not in jsonl_cols]
    status = "OK" if not missing_in_local else "列不匹配!"
    print(f"\n[{table}] {status}")
    if missing_in_local:
        print(f"  JSONL 有但本机缺: {missing_in_local}")
    if missing_in_jsonl:
        print(f"  本机有但 JSONL 缺: {missing_in_jsonl}")
    # 打印时间列类型
    for c in jsonl_cols:
        if c in local_cols and ("TIME" in local_cols[c] or "DATE" in local_cols[c]):
            print(f"  {c}: {local_cols[c]}")

cur.close()
conn.close()
print("\n[DONE]")
