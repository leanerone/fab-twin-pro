# -*- coding: utf-8 -*-
"""
解析用户粘贴的 DT_EVENT_RAW 制表符分隔文本，生成 JSONL 文件。

输入：raw_raw_input.txt - 用户粘贴的表格文本
输出：prod_export_20260910/DT_EVENT_RAW.jsonl

格式：每行一条记录，字段用空格/制表符分隔
首行是表头：RAW_ID TOOL_ID SOURCE_SYSTEM SOURCE_MESSAGE_ID RECEIVED_TS_UTC EVENT_TS_UTC PAYLOAD_JSON PARSE_STATUS ERROR_MESSAGE
"""
import os
import json
import re
from datetime import datetime

HERE = os.path.dirname(__file__)
IN_FILE = os.path.join(HERE, "raw_raw_input.txt")
OUT_FILE = os.path.join(HERE, "prod_export_20260910", "DT_EVENT_RAW.jsonl")

with open(IN_FILE, "r", encoding="utf-8") as f:
    lines = f.read().splitlines()

# 解析每行：RAW_ID 开头，PAYLOAD_JSON 是 {} 包裹的 JSON，PARSE_STATUS 在末尾
records = []
seen_ids = set()

for line in lines:
    line = line.strip()
    if not line or not line[0].isdigit():
        continue

    # 用正则提取各字段
    # 格式：RAW_ID TOOL_ID SOURCE_SYSTEM SOURCE_MESSAGE_ID RECEIVED_TS_UTC EVENT_TS_UTC PAYLOAD_JSON PARSE_STATUS ERROR_MESSAGE
    # PAYLOAD_JSON 是完整的 JSON 对象

    # 先找到 PAYLOAD_JSON 的起始位置（第一个 {）
    json_start = line.find('{')
    if json_start < 0:
        continue

    # 前半部分：RAW_ID TOOL_ID SOURCE_SYSTEM SOURCE_MESSAGE_ID RECEIVED_TS_UTC EVENT_TS_UTC
    prefix = line[:json_start].strip()
    parts = prefix.split()

    if len(parts) < 6:
        continue

    raw_id = int(parts[0])
    tool_id = parts[1]
    source_system = parts[2]
    source_message_id = parts[3]
    received_ts = parts[4] + ' ' + parts[5]  # 2026-9-10 PM4:26:48
    event_ts = parts[6] + ' ' + parts[7] if len(parts) > 7 and parts[6] != 'null' else None

    # 转换时间格式 2026-9-10 PM4:26:48 -> 2026-09-10 16:26:48
    def convert_ts(ts_str):
        if not ts_str or ts_str == 'null':
            return None
        # 处理 2026-9-10 PM4:26:48 格式
        m = re.match(r'(\d+)-(\d+)-(\d+)\s+(AM|PM)(\d+):(\d+):(\d+)', ts_str)
        if m:
            y, mo, d, ap, h, mi, s = m.groups()
            y, mo, d = int(y), int(mo), int(d)
            h = int(h)
            if ap == 'PM' and h != 12:
                h += 12
            elif ap == 'AM' and h == 12:
                h = 0
            return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi}:{s}"
        return ts_str

    received_ts = convert_ts(received_ts)
    event_ts = convert_ts(event_ts)

    # 找 JSON 的结束位置（最后一个 }）
    json_end = line.rfind('}')
    if json_end < json_start:
        continue
    payload_str = line[json_start:json_end+1]

    # JSON 后面是 PARSE_STATUS 和 ERROR_MESSAGE
    suffix = line[json_end+1:].strip()
    suffix_parts = suffix.split()
    parse_status = suffix_parts[0] if suffix_parts else 'PARSED'
    error_message = ' '.join(suffix_parts[1:]) if len(suffix_parts) > 1 else None

    # 解析 payload JSON
    try:
        payload = json.loads(payload_str)
    except Exception:
        payload = None

    if raw_id in seen_ids:
        continue
    seen_ids.add(raw_id)

    records.append({
        "RAW_ID": raw_id,
        "TOOL_ID": tool_id,
        "SOURCE_SYSTEM": source_system,
        "SOURCE_MESSAGE_ID": source_message_id,
        "RECEIVED_TS_UTC": received_ts,
        "EVENT_TS_UTC": event_ts,
        "PAYLOAD_JSON": json.dumps(payload, ensure_ascii=False) if payload else payload_str,
        "PARSE_STATUS": parse_status,
        "ERROR_MESSAGE": error_message,
    })

# 按 RAW_ID 排序
records.sort(key=lambda r: r["RAW_ID"])

# 写出
with open(OUT_FILE, "w", encoding="utf-8") as f:
    for r in records:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

print(f"解析出 {len(records)} 条 DT_EVENT_RAW 记录")
print(f"已保存到 {OUT_FILE}")

# 统计
tools = {}
for r in records:
    t = r["TOOL_ID"]
    tools[t] = tools.get(t, 0) + 1
print(f"\n按 TOOL_ID 统计:")
for t, c in sorted(tools.items()):
    print(f"  {t:20s} {c} 条")

# 时间范围
times = [r["RECEIVED_TS_UTC"] for r in records if r["RECEIVED_TS_UTC"]]
if times:
    print(f"\n时间范围: {min(times)} ~ {max(times)}")
