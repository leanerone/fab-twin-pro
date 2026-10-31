# -*- coding: utf-8 -*-
"""检查并清理污染行"""
import os
import json

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT_DIR = os.path.join(HERE, "prod_export_20260910")

for table in ["USERS", "MACHINE_MODEL_CONFIGS"]:
    p = os.path.join(EXPORT_DIR, f"{table}.jsonl")
    with open(p, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    print(f"\n===== {table} ({len(lines)} 行) =====")
    for i, line in enumerate(lines):
        try:
            d = json.loads(line)
        except Exception as e:
            print(f"  行{i}: JSON解析失败 - {e}")
            print(f"    {line[:200]}")
            continue
        if not d:
            print(f"  行{i}: 空对象 {{}}")
        elif "ID" not in d and "MODEL_ID" not in d and "USERNAME" not in d:
            print(f"  行{i}: 疑似污染行 (无主键)")
            print(f"    {json.dumps(d, ensure_ascii=False)[:300]}")
        else:
            # 打印每行的主键值
            pk = d.get("ID") or d.get("MODEL_ID") or d.get("USERNAME")
            print(f"  行{i}: OK pk={pk}")
