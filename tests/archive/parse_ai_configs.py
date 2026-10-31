# -*- coding: utf-8 -*-
"""
解析从 DOCX 提取的 AI_CONFIGS_raw.txt，将其拆分为标准 JSONL 并导入本机 Oracle。

输入文件 AI_CONFIGS_raw.txt 的结构（来自 DOCX word/document.xml 提取）：
    第 1 行: AI_CONFIGS.jsonl  (标题/文件名)
    第 2 行: {"ID": 8, "CONFIG_KEY": "mcp_n8n_enabled", ...}
    第 3 行: {"ID": 9, ...}
    ...

本脚本：
    1) 跳过标题行，逐行解析 JSON
    2) 校验字段
    3) 写出标准 AI_CONFIGS.jsonl
    4) 可选：直接导入本机 Oracle AI_CONFIGS 表（--import 参数）
"""
import os
import sys
import json
import argparse
from datetime import datetime

RAW_FILE = os.path.join(os.path.dirname(__file__), "AI_CONFIGS_raw.txt")
OUT_FILE = os.path.join(os.path.dirname(__file__), "AI_CONFIGS.jsonl")

# AI_CONFIGS 表的列（与 create_ai_tables.sql 一致）
COLUMNS = [
    "ID", "CONFIG_KEY", "CONFIG_VALUE", "DESCRIPTION",
    "UPDATED_AT", "UPDATED_BY"
]


def parse_raw(raw_path: str) -> list:
    """读取 raw 文本，返回 dict 列表"""
    with open(raw_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 文件可能整体是一行，也可能多行；按 JSON 对象正则拆分
    # 简单做法：找到所有 {...}
    import re
    matches = re.findall(r'\{[^{}]*\}', content)
    if not matches:
        # 回退：按行处理
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        # 跳过第一行（标题）
        if lines and lines[0].startswith("AI_CONFIGS"):
            lines = lines[1:]
        matches = lines

    records = []
    failed = []
    for i, m in enumerate(matches):
        try:
            obj = json.loads(m)
            # 字段补全
            rec = {}
            for c in COLUMNS:
                rec[c] = obj.get(c)
            # UPDATED_AT 转 YYYY-MM-DD HH:MM:SS 格式（原为 03-SEP-26）
            ua = rec.get("UPDATED_AT")
            if isinstance(ua, str) and "-" in ua and len(ua) <= 11:
                try:
                    # Oracle 默认 DD-MON-YY 格式
                    dt = datetime.strptime(ua.upper(), "%d-%b-%y")
                    rec["UPDATED_AT"] = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass
            records.append(rec)
        except Exception as e:
            failed.append((i, m[:80], str(e)))

    print(f"[解析] 成功 {len(records)} 条，失败 {len(failed)} 条")
    if failed:
        print("[失败样本] 前 5 条：")
        for i, s, e in failed[:5]:
            print(f"  #{i}: {s}... -> {e}")
    return records


def write_jsonl(records: list, out_path: str):
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[输出] {out_path} ({len(records)} 条)")


def import_to_oracle(records: list):
    """导入本机 Oracle AI_CONFIGS 表"""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    try:
        import oracledb
        oracledb.defaults.fetch_lobs = False
    except ImportError:
        print("[ERROR] 未安装 oracledb")
        return False

    # 初始化 Thick 模式
    client_dir = os.getenv("ORACLE_CLIENT_DIR", "")
    if client_dir:
        bin_dir = os.path.join(client_dir, "bin")
        if os.path.exists(os.path.join(bin_dir, "oci.dll")):
            client_dir = bin_dir
    try:
        if client_dir:
            oracledb.init_oracle_client(lib_dir=client_dir)
        else:
            oracledb.init_oracle_client()
    except Exception as e:
        if "DPI-1072" not in str(e):
            print(f"[WARN] Thick 模式初始化: {e}")

    # 读取 env.bat
    env = load_env_bat()
    host = env.get("ORACLE_HOST", "localhost")
    port = env.get("ORACLE_PORT", "1521")
    service = env.get("ORACLE_SERVICE", "orclpdb")
    user = env.get("ORACLE_USER", "fabtwin")
    pwd = env.get("ORACLE_PASSWORD", "fabtwin")
    dsn_type = env.get("ORACLE_DSN_TYPE", "service_name")

    if dsn_type.lower() == "sid":
        dsn = oracledb.makedsn(host, int(port), sid=service)
    else:
        dsn = oracledb.makedsn(host, int(port), service_name=service)

    print(f"[本机] 连接 {user}@{host}:{port}/{service} ({dsn_type})")
    try:
        conn = oracledb.connect(user=user, password=pwd, dsn=dsn)
        print(f"[本机] 连接成功，DB 版本: {conn.version}")
    except Exception as e:
        print(f"[本机] 连接失败: {e}")
        return False

    # 先清空（避免主键冲突）
    try:
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE AI_CONFIGS")
        print("[本机] 已清空 AI_CONFIGS")
    except Exception as e:
        print(f"[WARN] 清空失败: {e}")
        # 可能表不存在，尝试建表
        sql_file = os.path.join(os.path.dirname(__file__), "..", "sql", "create_ai_tables.sql")
        if os.path.exists(sql_file):
            with open(sql_file, "r", encoding="utf-8") as f:
                cur.execute(f.read())
            conn.commit()
            print("[本机] 已创建 AI_CONFIGS 表")

    # 批量插入
    col_list = ", ".join(f'"{c}"' for c in COLUMNS)
    bind_list = ", ".join(f":{i+1}" for i in range(len(COLUMNS)))
    sql = f"INSERT INTO AI_CONFIGS ({col_list}) VALUES ({bind_list})"

    ok = 0
    err = 0
    cur = conn.cursor()
    for r in records:
        try:
            vals = [r.get(c) for c in COLUMNS]
            cur.execute(sql, vals)
            ok += 1
        except Exception as e:
            err += 1
            if err <= 3:
                print(f"[插入失败] ID={r.get('ID')} -> {e}")
    conn.commit()
    print(f"[本机] 插入 {ok} 条，失败 {err} 条")

    # 验证
    cur.execute("SELECT COUNT(*) FROM AI_CONFIGS")
    cnt = cur.fetchone()[0]
    print(f"[本机] AI_CONFIGS 当前总行数: {cnt}")
    cur.close()
    conn.close()
    return True


def load_env_bat():
    """读取 fab-twin-pro/deploy/env.bat"""
    env = {}
    env_bat = os.path.join(os.path.dirname(__file__), "..", "deploy", "env.bat")
    if not os.path.exists(env_bat):
        return env
    with open(env_bat, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("set ") or line.startswith("SET "):
                parts = line[4:].split("=", 1)
                if len(parts) == 2:
                    env[parts[0].strip()] = parts[1].strip().strip('"')
    return env


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--import", dest="do_import", action="store_true",
                        help="导入本机 Oracle")
    args = parser.parse_args()

    if not os.path.exists(RAW_FILE):
        print(f"[ERROR] 输入文件不存在: {RAW_FILE}")
        sys.exit(1)

    print(f"=== 解析 DOCX 提取的 AI_CONFIGS_raw.txt ===")
    records = parse_raw(RAW_FILE)
    if not records:
        print("[ERROR] 没有解析到任何记录")
        sys.exit(1)

    write_jsonl(records, OUT_FILE)

    # 打印摘要
    print("\n=== 数据摘要 ===")
    print(f"总记录数: {len(records)}")
    print("字段示例（第1条）:")
    print(json.dumps(records[0], ensure_ascii=False, indent=2))

    print("\n所有 CONFIG_KEY:")
    for r in records:
        print(f"  ID={r.get('ID')}: {r.get('CONFIG_KEY')} = {str(r.get('CONFIG_VALUE'))[:60]}")

    if args.do_import:
        print("\n=== 导入本机 Oracle ===")
        import_to_oracle(records)
    else:
        print("\n[提示] 加 --import 参数可导入本机 Oracle")


if __name__ == "__main__":
    main()
