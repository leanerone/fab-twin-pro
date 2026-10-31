# -*- coding: utf-8 -*-
"""
从用户粘贴的文本中提取 DT_EVENT_RAW_CUR 的 JSON 记录并保存为 JSONL。

用法：把用户粘贴的 DT_EVENT_RAW_CUR.jsonl 内容粘贴到 raw_input.txt，
然后运行此脚本。
"""
import os
import json
import re

HERE = os.path.dirname(__file__)
IN_FILE = os.path.join(HERE, "raw_cur_input.txt")
OUT_FILE = os.path.join(HERE, "prod_export_20260910", "DT_EVENT_RAW_CUR.jsonl")

with open(IN_FILE, "r", encoding="utf-8") as f:
    content = f.read()

# 用括号深度解析所有 JSON 对象
records = []
depth = 0
start_idx = None
in_string = False
escape = False

for i, c in enumerate(content):
    if escape:
        escape = False
        continue
    if c == '\\':
        escape = True
        continue
    if c == '"':
        in_string = not in_string
        continue
    if in_string:
        continue
    if c == '{':
        if depth == 0:
            start_idx = i
        depth += 1
    elif c == '}':
        depth -= 1
        if depth == 0 and start_idx is not None:
            obj_str = content[start_idx:i+1]
            try:
                obj = json.loads(obj_str)
                # 确认是 DT_EVENT_RAW_CUR 记录（有 RAW_ID 字段）
                if "RAW_ID" in obj:
                    records.append(obj)
            except Exception:
                pass
            start_idx = None

print(f"解析出 {len(records)} 条 DT_EVENT_RAW_CUR 记录")

# 按 RAW_ID 排序（去重）
seen = set()
unique = []
for r in records:
    rid = r.get("RAW_ID")
    if rid not in seen:
        seen.add(rid)
        unique.append(r)
print(f"去重后 {len(unique)} 条")

# 写出
with open(OUT_FILE, "w", encoding="utf-8") as f:
    for r in unique:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"已保存到 {OUT_FILE}")

# 统计
tools = {}
for r in unique:
    t = r.get("TOOL_ID", "?")
    tools[t] = tools.get(t, 0) + 1
print(f"\n按 TOOL_ID 统计:")
for t, c in sorted(tools.items()):
    print(f"  {t:30s} {c} 条")
