# -*- coding: utf-8 -*-
"""分析 DOCX 提取的 raw 文件结构，找出所有表名段"""
import os
import re

RAW = os.path.join(os.path.dirname(__file__), "AI_CONFIGS_raw.txt")

with open(RAW, "r", encoding="utf-8") as f:
    content = f.read()

print(f"文件大小: {len(content)} 字符")
print(f"总行数: {content.count(chr(10)) + 1}")
print()

# 找出所有 .jsonl 表名标记
# 模式：TABLENAME.jsonl 后跟数据
pattern = re.compile(r'([A-Z_][A-Z0-9_]+)\.jsonl\s*', re.IGNORECASE)
matches = list(pattern.finditer(content))
print(f"找到 {len(matches)} 个 .jsonl 表名标记:")
for i, m in enumerate(matches):
    start = m.start()
    end = m.end()
    next_start = matches[i+1].start() if i+1 < len(matches) else len(content)
    section_size = next_start - end
    # 数该段内有多少 { 开头的对象（粗略）
    section = content[end:next_start]
    obj_count = section.count('{"ID"')
    print(f"  [{i+1}] {m.group(1):30s} 段长度: {section_size:8d} 字符, ~{obj_count} 条记录")

# 取第一个 AI_CONFIGS 段
ai_match = None
for m in matches:
    if m.group(1).upper() == "AI_CONFIGS":
        ai_match = m
        break

if ai_match:
    next_match = None
    for m in matches:
        if m.start() > ai_match.end():
            next_match = m
            break
    end_pos = next_match.start() if next_match else len(content)
    section = content[ai_match.end():end_pos]
    print(f"\n=== AI_CONFIGS 段 ({len(section)} 字符) ===")
    # 解析其中的 JSON 对象（支持嵌套）
    records = []
    depth = 0
    start_idx = None
    for i, c in enumerate(section):
        if c == '{':
            if depth == 0:
                start_idx = i
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0 and start_idx is not None:
                obj_str = section[start_idx:i+1]
                try:
                    import json
                    obj = json.loads(obj_str)
                    records.append(obj)
                except Exception:
                    pass
                start_idx = None
    print(f"AI_CONFIGS 实际记录数: {len(records)}")
    if records:
        print("第1条:")
        import json
        print(json.dumps(records[0], ensure_ascii=False, indent=2))
        print(f"第 {len(records)} 条 ID: {records[-1].get('ID')}")
