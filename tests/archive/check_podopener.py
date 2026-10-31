# -*- coding: utf-8 -*-
"""检查 DOCX 中 PODOPENERDT_EVENT_RAW_CUR 段是否其实是 DT_EVENT_RAW_CUR 的数据"""
import os
import json
import re

RAW = os.path.join(os.path.dirname(__file__), "AI_CONFIGS_raw.txt")

with open(RAW, "r", encoding="utf-8") as f:
    content = f.read()

# 找到所有段
pattern = re.compile(r'([A-Z_][A-Z0-9_]+)\.jsonl\s*')
matches = list(pattern.finditer(content))

# 找 PODOPENERDT_EVENT_RAW_CUR 段
for i, m in enumerate(matches):
    if "PODOPENER" in m.group(1):
        next_start = matches[i+1].start() if i+1 < len(matches) else len(content)
        sec = content[m.end():next_start]
        print(f"段名: {m.group(1)}")
        print(f"段长度: {len(sec)} 字符")
        print(f"段前500字符:\n{sec[:500]}")
        print("\n---")
        # 解析 JSON
        records = []
        depth = 0
        start_idx = None
        in_string = False
        escape = False
        for i2, c in enumerate(sec):
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
                    start_idx = i2
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0 and start_idx is not None:
                    obj_str = sec[start_idx:i2+1]
                    try:
                        records.append(json.loads(obj_str))
                    except Exception:
                        pass
                    start_idx = None
        print(f"解析出 {len(records)} 条记录")
        if records:
            print(f"\n第1条:")
            print(json.dumps(records[0], ensure_ascii=False, indent=2))
            print(f"\n第1条字段:")
            print(list(records[0].keys()))
            # 看下时间字段
            for k, v in records[0].items():
                if "TS" in k or "TIME" in k or "DATE" in k:
                    print(f"  {k} = {v}")

# 看下 DT_EVENT_RAW 段详细内容（错误信息）
print("\n=== DT_EVENT_RAW 段详细 ===")
for i, m in enumerate(matches):
    if m.group(1) == "DT_EVENT_RAW":
        next_start = matches[i+1].start() if i+1 < len(matches) else len(content)
        sec = content[m.end():next_start]
        print(f"段长度: {len(sec)}")
        print(f"全部内容:\n{sec}")

# 看下 DT_EVENT_RAW_CUR 段
print("\n=== DT_EVENT_RAW_CUR 段详细 ===")
for i, m in enumerate(matches):
    if m.group(1) == "DT_EVENT_RAW_CUR":
        next_start = matches[i+1].start() if i+1 < len(matches) else len(content)
        sec = content[m.end():next_start]
        print(f"段长度: {len(sec)}")
        print(f"全部内容（前500字符）:\n{sec[:500]}")
