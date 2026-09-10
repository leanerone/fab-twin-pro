# -*- coding: utf-8 -*-
"""检查 DOCX 中的 tables_schema.json 部分，看 DT_EVENT_RAW 的列类型"""
import os
import json
import re

RAW = os.path.join(os.path.dirname(__file__), "AI_CONFIGS_raw.txt")

with open(RAW, "r", encoding="utf-8") as f:
    content = f.read()

# 找 tables_schema.json 段
idx = content.find("tables_schema.json")
if idx < 0:
    print("未找到 tables_schema.json")
    exit()

# 段后内容
sec = content[idx + len("tables_schema.json"):]

# 解析所有表结构
# 格式: "TABLE_NAME": [ { "column": "X", "type": "Y", "length": N, "nullable": "Z" }, ... ]
# 简单提取 DT_EVENT_RAW 段
for tbl in ["DT_EVENT_RAW", "DT_EVENT_RAW_CUR", "DT_EVENT_STD"]:
    pat = re.compile(r'"' + tbl + r'":\s*\[([^\]]+)\]')
    m = pat.search(sec)
    if m:
        cols_str = m.group(1)
        print(f"\n=== {tbl} 列信息 ===")
        # 解析每个 {column/type/length/nullable}
        col_pat = re.compile(r'\{[^{}]*?"column":\s*"([^"]+)"[^{}]*?"type":\s*"([^"]+)"[^{}]*?\}')
        for cm in col_pat.finditer(cols_str):
            print(f"  {cm.group(1):25s} {cm.group(2)}")
    else:
        print(f"\n=== {tbl}: 未找到 schema ===")
