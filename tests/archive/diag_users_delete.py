# -*- coding: utf-8 -*-
"""诊断 USERS / MACHINE_MODEL_CONFIGS DELETE 后插入问题"""
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
    # 查看当前行数
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    print(f"DELETE 前行数: {cur.fetchone()[0]}")
    # DELETE
    try:
        cur.execute(f"DELETE FROM {table}")
        print("DELETE 成功")
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"DELETE 后行数: {cur.fetchone()[0]}")
    except oracledb.DatabaseError as e:
        print(f"DELETE 失败: {e}")
        conn.rollback()
        continue
    # 插入第一条
    p = os.path.join(EXPORT_DIR, f"{table}.jsonl")
    with open(p, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    cols = list(rows[0].keys())
    col_list = ", ".join(f'"{c}"' for c in cols)
    bind_list = ", ".join(f":{i+1}" for i in range(len(cols)))
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({bind_list})"
    r = rows[0]
    vals = [None if r.get(c) == "" else r.get(c) for c in cols]
    try:
        cur.execute(sql, vals)
        print(f"插入第一条成功: {r.get('ID') or r.get('MODEL_ID')}")
    except oracledb.DatabaseError as e:
        print(f"插入第一条失败: {e}")
        # 查看表是否有触发器
    try:
        cur.execute(f"SELECT trigger_name FROM user_triggers WHERE table_name='{table}'")
        trg = cur.fetchall()
        print(f"触发器: {trg}")
    except Exception as e:
        print(f"查触发器失败: {e}")
    conn.rollback()

# 检查外键引用 USERS 的表
print("\n===== 引用 USERS 的外键 =====")
try:
    cur.execute("""SELECT c.table_name, c.constraint_name, c.r_constraint_name
                   FROM user_constraints c
                   WHERE c.constraint_type='R' AND c.r_constraint_name IN
                     (SELECT constraint_name FROM user_constraints WHERE table_name='USERS')""")
    for r in cur.fetchall():
        print(" ", r)
except Exception as e:
    print(f"失败: {e}")

conn.close()
