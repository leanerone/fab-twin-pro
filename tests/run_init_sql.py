# -*- coding: utf-8 -*-
"""
执行 Oracle SQL 初始化脚本（Python 版，避免 sqlplus 中文乱码）

用法：
    python run_init_sql.py <sql_file>

会按 ; 分割语句逐条执行，跳过注释和空行，
对 CREATE TRIGGER/SEQUENCE 等 PL/SQL 块（以 / 结尾）也支持。
"""
import sys
import os
import re

import oracledb

# 让 oracledb 直接返回字符串而非 LOB 对象
try:
    oracledb.defaults.fetch_lobs = False
except Exception:
    pass

# 连接配置（本机 orclpdb）
USER = "fabtwin"
PASSWORD = "fabtwin"
HOST = "localhost"
PORT = 1521
SERVICE = "orclpdb"


def read_sql_blocks(sql_text: str):
    """把 SQL 文件切成可执行的块。

    规则：
    - 以 '/' 单独一行作为 PL/SQL 块边界（触发器、存储过程等），整块一条
    - CREATE TRIGGER/PROCEDURE/TYPE 等 PL/SQL 块内部的 ; 不分割
    - 其他以 ';' 结尾的语句作为一条
    - 跳过 REM 注释、-- 行注释、空行、/* 块注释 */
    """
    blocks = []
    current = []
    in_plsql = False  # 是否在 PL/SQL 块中
    in_block_comment = False

    for raw_line in sql_text.splitlines():
        line = raw_line.rstrip()

        # 跳过空行
        if not line.strip():
            continue

        stripped = line.strip()

        # 块注释处理
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
            continue
        if stripped.startswith("/*"):
            if "*/" not in stripped[2:]:
                in_block_comment = True
            continue

        # 跳过注释
        if stripped.startswith("REM") or stripped.startswith("--"):
            continue

        # 检测进入 PL/SQL 块
        if not in_plsql:
            upper = stripped.upper()
            if any(upper.startswith(kw) for kw in (
                "CREATE TRIGGER", "CREATE OR REPLACE TRIGGER",
                "CREATE PROCEDURE", "CREATE OR REPLACE PROCEDURE",
                "CREATE TYPE", "CREATE OR REPLACE TYPE",
                "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION",
                "CREATE PACKAGE", "CREATE OR REPLACE PACKAGE",
                "BEGIN", "DECLARE"
            )):
                in_plsql = True

        current.append(line)

        # PL/SQL 块结束（/ 单独一行）
        if stripped == "/":
            blocks.append("\n".join(current))
            current = []
            in_plsql = False
            continue
        # 普通 SQL 结束（不在 PL/SQL 块中）
        if stripped.endswith(";") and not in_plsql:
            blocks.append("\n".join(current))
            current = []

    if current:
        blocks.append("\n".join(current))
    return blocks


def run_sql_file(conn, sql_file: str):
    """读取 SQL 文件并逐条执行"""
    with open(sql_file, "r", encoding="utf-8") as f:
        sql_text = f.read()

    blocks = read_sql_blocks(sql_text)
    print(f"[INFO] {sql_file}: 共 {len(blocks)} 个语句块")

    cur = conn.cursor()
    ok_cnt = 0
    err_cnt = 0
    for i, block in enumerate(blocks, 1):
        block_text = block.strip()
        if not block_text:
            continue
        # PL/SQL 块以 / 结尾，去掉 /（Python 不需要它）
        if block_text.endswith("/"):
            block_text = block_text[:-1].strip()
        # 去掉普通 SQL 末尾分号
        if block_text.endswith(";"):
            # 但 PL/SQL 块内部的 ; 不能去，只去最后一行的 ;
            # 如果包含 BEGIN/END，是 PL/SQL，保留 ;
            if not any(kw in block_text.upper() for kw in
                       ("BEGIN", "DECLARE", "CREATE TRIGGER", "CREATE OR REPLACE TRIGGER",
                        "CREATE PROCEDURE", "CREATE OR REPLACE PROCEDURE")):
                block_text = block_text[:-1]

        # 跳过 SET 命令
        if block_text.upper().startswith("SET "):
            continue

        # 提取第一行做日志
        first_line = block_text.split("\n")[0][:80]
        try:
            cur.execute(block_text)
            # DDL/DML 不需要 fetch
            ok_cnt += 1
        except oracledb.DatabaseError as e:
            err_msg = str(e).split("\n")[0][:200]
            # 如果是"表或视图不存在"（DROP 表时报错），忽略
            if "ORA-00942" in err_msg and "DROP" in block_text.upper():
                continue
            print(f"[{i:3d}] ERROR: {err_msg}")
            print(f"      SQL: {first_line}")
            err_cnt += 1

    conn.commit()
    print(f"[DONE] 成功 {ok_cnt} 条，失败 {err_cnt} 条")
    cur.close()


def main():
    if len(sys.argv) < 2:
        print("用法: python run_init_sql.py <sql_file> [sql_file2 ...]")
        sys.exit(1)

    dsn = oracledb.makedsn(HOST, PORT, service_name=SERVICE)
    print(f"[INFO] 连接 {USER}@{HOST}:{PORT}/{SERVICE}")
    try:
        conn = oracledb.connect(user=USER, password=PASSWORD, dsn=dsn)
    except Exception as e:
        print(f"[ERROR] 连接失败: {e}")
        sys.exit(1)

    print(f"[INFO] 连接成功，数据库版本: {conn.version}")
    for sql_file in sys.argv[1:]:
        print(f"\n========== 执行 {sql_file} ==========")
        if not os.path.exists(sql_file):
            print(f"[ERROR] 文件不存在: {sql_file}")
            continue
        run_sql_file(conn, sql_file)

    conn.close()
    print("\n[INFO] 全部完成")


if __name__ == "__main__":
    main()
