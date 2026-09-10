# -*- coding: utf-8 -*-
"""查看 DOCX raw 文件中各段的实际分隔情况"""
import os
import re

RAW = os.path.join(os.path.dirname(__file__), "AI_CONFIGS_raw.txt")

with open(RAW, "r", encoding="utf-8") as f:
    content = f.read()

# 找 PODOPENERDT 出现位置
idx = content.find("PODOPENERDT")
if idx >= 0:
    print(f"找到 PODOPENERDT 在位置 {idx}")
    # 看前后 200 字符
    start = max(0, idx - 100)
    end = min(len(content), idx + 300)
    print(f"前后内容（位置 {start}-{end}）:")
    print(repr(content[start:end]))
else:
    print("未找到 PODOPENERDT")

# 看下 DT_EVENT_RAW 段
print("\n=== 查找所有 'DT_EVENT_RAW' 出现位置 ===")
for m in re.finditer(r'DT_EVENT_RAW', content):
    print(f"位置 {m.start()}: 前后 50 字符 = {repr(content[max(0,m.start()-30):m.start()+50])}")

# 看下 export_summary 部分（如果有）
print("\n=== 查找 export_summary 出现位置 ===")
for m in re.finditer(r'export_summary', content, re.IGNORECASE):
    print(f"位置 {m.start()}: {repr(content[max(0,m.start()-30):m.start()+200])}")

# 看 DOCX 开头
print(f"\n=== 文件开头 500 字符 ===")
print(repr(content[:500]))

# 看结尾
print(f"\n=== 文件结尾 500 字符 ===")
print(repr(content[-500:]))
