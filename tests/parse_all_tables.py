# -*- coding: utf-8 -*-
"""
完整解析 DOCX 提取的 raw 文件，按表名分段，输出每张表的 JSONL 文件。

支持嵌套 JSON（payload_json 等字段可能包含 {} 字符）。
"""
import os
import sys
import json
import re

RAW = os.path.join(os.path.dirname(__file__), "AI_CONFIGS_raw.txt")
OUT_DIR = os.path.join(os.path.dirname(__file__), "prod_export_20260910")

# 项目目标 32 张表（与 export_from_prod.py 一致）
TARGET_TABLES = {
    "AI_CONFIGS", "AI_INSIGHTS", "AI_PROVIDER_CONFIGS", "AI_USAGE_LOGS",
    "ALARMS", "CHAMBER_SNAPSHOTS", "DASHBOARD_KPI", "DT_ALARM_EVENT",
    "DT_EVENT_RAW", "DT_EVENT_RAW_CUR", "DT_EVENT_REALTIMELOT",
    "DT_EVENT_STD", "DT_RTLOT_EVENT_RULE", "DT_RTLOT_TOOL_PORT_RULE",
    "DT_STATE_SNAPSHOT", "EVENT_ACTION_MAPPINGS", "FLOOR_AREAS", "FLOORS",
    "LOTS", "MACHINE_DIFY_CONFIGS", "MACHINE_EVENTS", "MACHINE_MODEL_CONFIGS",
    "MACHINE_TOOL_MAPPINGS", "MACHINES", "OHT_POSITIONS", "PERM_DATA",
    "RECIPES", "ROLE_PERMISSIONS", "ROLES", "TRACKS", "USERS", "VEHICLES",
}


def parse_sections(content: str):
    """按 TABLENAME.jsonl 分段，返回 [(table_name, content), ...]"""
    pattern = re.compile(r'([A-Z_][A-Z0-9_]+)\.jsonl\s*')
    matches = list(pattern.finditer(content))
    sections = []
    for i, m in enumerate(matches):
        next_start = matches[i+1].start() if i+1 < len(matches) else len(content)
        section_content = content[m.end():next_start]
        sections.append((m.group(1).upper(), section_content))
    return sections


def parse_json_objects(text: str):
    """从文本中提取所有 JSON 对象（支持嵌套）"""
    records = []
    depth = 0
    start_idx = None
    in_string = False
    escape = False
    for i, c in enumerate(text):
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
                obj_str = text[start_idx:i+1]
                try:
                    obj = json.loads(obj_str)
                    records.append(obj)
                except Exception:
                    pass
                start_idx = None
    return records


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    with open(RAW, "r", encoding="utf-8") as f:
        content = f.read()

    sections = parse_sections(content)
    print(f"=== 共 {len(sections)} 段 ===\n")

    # 合并同表数据（DOCX 中可能有重复段，有些是空的）
    # 注意：PODOPENERDT_EVENT_RAW_CUR 段实际是 DT_EVENT_RAW_CUR 的数据
    # （前面 MACHINE_MODEL_CONFIGS 数据中含 "PODOPENER" 字符串污染了表名识别）
    ALIAS_MAP = {
        "PODOPENERDT_EVENT_RAW_CUR": "DT_EVENT_RAW_CUR",
    }
    table_records = {}
    for name, sec in sections:
        real_name = ALIAS_MAP.get(name, name)
        if real_name not in TARGET_TABLES:
            print(f"[跳过] {name} -> {real_name} (非目标表)")
            continue
        records = parse_json_objects(sec)
        if real_name not in table_records:
            table_records[real_name] = []
        table_records[real_name].extend(records)
        if records:
            tag = f" (别名自 {name})" if name != real_name else ""
            print(f"[OK] {real_name:30s} +{len(records):4d} 条 (段总长 {len(sec):6d} 字符){tag}")

    print(f"\n=== 合并后统计 ===")
    summary = []
    for name in sorted(table_records.keys()):
        records = table_records[name]
        in_target = name in TARGET_TABLES
        status = "目标表" if in_target else "非目标"
        print(f"  {name:30s} {len(records):4d} 条 [{status}]")
        summary.append({"table": name, "rows": len(records), "in_target": in_target})

    # 列出缺失的目标表
    missing = TARGET_TABLES - set(table_records.keys())
    if missing:
        print(f"\n=== 缺失的目标表（DOCX 中未出现）===")
        for t in sorted(missing):
            print(f"  - {t}")

    # 写出每张表的 JSONL
    print(f"\n=== 写出到 {OUT_DIR} ===")
    for name, records in table_records.items():
        if not records:
            continue
        out_path = os.path.join(OUT_DIR, f"{name}.jsonl")
        with open(out_path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  {out_path} ({len(records)} 条)")

    # 摘要
    summary_path = os.path.join(OUT_DIR, "docx_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n[摘要] {summary_path}")

    # 特别检查 DT_EVENT_RAW
    print(f"\n=== DT_EVENT_RAW 检查 ===")
    dt_raw_records = table_records.get("DT_EVENT_RAW", [])
    print(f"DT_EVENT_RAW 记录数: {len(dt_raw_records)}")
    if not dt_raw_records:
        print("[警告] DT_EVENT_RAW 在 DOCX 中没有数据！")
        # 看看原始内容里有没有相关信息
        for name, sec in sections:
            if "DT_EVENT_RAW" in name and "CUR" not in name:
                print(f"  段 '{name}' 内容前200字符: {sec[:200]}")

    # 检查 PODOPENERDT_EVENT_RAW_CUR
    print(f"\n=== PODOPENERDT_EVENT_RAW_CUR 检查 ===")
    for name, sec in sections:
        if "PODOPENER" in name:
            records = parse_json_objects(sec)
            print(f"段 '{name}': {len(records)} 条记录")
            if records:
                print(f"  第1条字段: {list(records[0].keys())}")


if __name__ == "__main__":
    main()
