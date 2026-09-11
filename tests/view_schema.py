# -*- coding: utf-8 -*-
"""查看量产 schema 中关键表的结构"""
import os
import json

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(HERE, "prod_export_20260910", "tables_schema.json")

with open(SCHEMA, "r", encoding="utf-8") as f:
    schema = json.load(f)

# 打印结构概览
print("schema 顶层类型:", type(schema))
if isinstance(schema, dict):
    print("顶层 keys:", list(schema.keys())[:10])
    # 尝试各种结构
    for key in ["DT_EVENT_STD", "DT_STATE_SNAPSHOT", "ALARMS", "AI_USAGE_LOGS"]:
        if key in schema:
            print(f"\n=== {key} ===")
            print(json.dumps(schema[key], ensure_ascii=False)[:800])
