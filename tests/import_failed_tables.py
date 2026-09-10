# -*- coding: utf-8 -*-
"""增强导入脚本 - 处理污染行、identity列、TIMESTAMP转换"""
import os
import json
import re
from datetime import datetime
import oracledb

oracledb.defaults.fetch_lobs = False

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(HERE, "prod_export_20260910")

conn = oracledb.connect(
    user="fabtwin", password="fabtwin",
    dsn=oracledb.makedsn("localhost", 1521, service_name="orclpdb"))
cur = conn.cursor()


def clean_row(row, table):
    """过滤污染行"""
    if not row or not isinstance(row, dict):
        return None
    if table == "USERS" and "USERNAME" not in row and "ID" not in row:
        return None
    if table == "MACHINE_MODEL_CONFIGS" and "MODEL_ID" not in row:
        return None
    return row


def parse_dt(val):
    """把字符串转成 datetime 或保持原样"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val
    s = str(val).strip()
    # 匹配 'YYYY-MM-DD HH:MM:SS' 或带微秒
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(\.\d+)?$", s)
    if m:
        dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                      int(m.group(4)), int(m.group(5)), int(m.group(6)))
        return dt
    return val


# 需要 TIMESTAMP 转换的表和列（DATETIME 类型）
TIMESTAMP_COLS = {
    "DT_EVENT_REALTIMELOT": ["LAST_EVENT_TS_UTC", "START_TS_UTC", "UPDATED_TS_UTC"],
    "DT_RTLOT_TOOL_PORT_RULE": ["UPDATED_TS_UTC"],
    "DT_RTLOT_EVENT_RULE": ["UPDATED_TS_UTC"],
}

# identity 列，剔除让其自动生成
IDENTITY_DROP = {"DT_STATE_SNAPSHOT": ["SNAPSHOT_ID"]}


def import_one(table, jsonl_path):
    with open(jsonl_path, "r", encoding="utf-8") as f:
        raw_rows = [json.loads(line) for line in f if line.strip()]

    rows = []
    for r in raw_rows:
        c = clean_row(r, table)
        if c is not None:
            rows.append(c)

    if not rows:
        print(f"  [SKIP] {table}: 0 行有效")
        return 0

    # identity 列剔除
    drop_cols = set(IDENTITY_DROP.get(table, []))

    # 清空
    try:
        cur.execute(f"DELETE FROM {table}")
    except oracledb.DatabaseError as e:
        print(f"  [ERROR] {table}: 清空失败 - {e}")
        return 0

    cols = [c for c in rows[0].keys() if c not in drop_cols]
    col_list = ", ".join(f'"{c}"' for c in cols)
    bind_list = ", ".join(f":{i+1}" for i in range(len(cols)))

    sql = f"INSERT INTO {table} ({col_list}) VALUES ({bind_list})"

    ts_cols = set(TIMESTAMP_COLS.get(table, []))

    ok = 0
    fail = 0
    for r in rows:
        vals = []
        for c in cols:
            v = r.get(c)
            if v == "":
                v = None
            if c in ts_cols:
                v = parse_dt(v)
            vals.append(v)
        try:
            cur.execute(sql, vals)
            ok += 1
        except oracledb.DatabaseError as e:
            fail += 1
            print(f"  [FAIL] {table} 记录失败: {e}")
            if fail <= 2:
                print(f"     {json.dumps(r, ensure_ascii=False)[:200]}")

    conn.commit()
    if fail:
        print(f"  [WARN] {table}: 导入 {ok}/{len(rows)} 行，失败 {fail}")
    else:
        print(f"  [OK] {table}: 导入 {ok} 行")
    return ok


# 只导 6 张失败的表
FAILED = [
    "USERS", "MACHINE_MODEL_CONFIGS", "DT_STATE_SNAPSHOT",
    "DT_EVENT_REALTIMELOT", "DT_RTLOT_TOOL_PORT_RULE", "DT_RTLOT_EVENT_RULE",
]

print("===== 导入失败的 6 张表 =====")
total = 0
for t in FAILED:
    p = os.path.join(EXPORT_DIR, f"{t}.jsonl")
    total += import_one(t, p)

conn.close()
print(f"\n[DONE] 共导入 {total} 行")
