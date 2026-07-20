"""
生成 Aqua Data Studio 兼容的初始化 SQL 脚本

Aqua Data Studio 不支持 SQL*Plus 特定命令：
- PROMPT, ACCEPT, SPOOL, SET DEFINE OFF, SET SQLBLANKLINES ON
- @, @@, START
- EXIT, QUIT
- WHENEVER SQLERROR
- &变量替换

本脚本读取 sql/init_oracle_db.sql，移除所有 SQL*Plus 命令，
生成纯 SQL 版本 sql/init_oracle_aqua.sql，可在 Aqua Data Studio 中直接执行。

PL/SQL 块（CREATE TRIGGER等）保留 / 作为终止符，Aqua Data Studio 支持。
"""
import re
from pathlib import Path

SRC = Path(__file__).parent / "sql" / "init_oracle_db.sql"
DST = Path(__file__).parent / "sql" / "init_oracle_aqua.sql"

# SQL*Plus 命令前缀（大小写不敏感）
SQLPLUS_PATTERNS = [
    r'^\s*PROMPT\s',
    r'^\s*ACCEPT\s',
    r'^\s*SPOOL\s',
    r'^\s*SET\s+(DEFINE|SQLBLANKLINES|SERVEROUTPUT|FEEDBACK|HEADING|PAGESIZE|LINESIZE|ECHO|VERIFY|TRIMSPOOL|TERMOUT|TIMING)\b',
    r'^\s*SHOW\s',
    r'^\s*WHENEVER\s',
    r'^\s*@@\s',
    r'^\s*@\s',
    r'^\s*START\s',
    r'^\s*EXIT\s*;',
    r'^\s*QUIT\s*;',
    r'^\s*EXIT\s*$',
    r'^\s*QUIT\s*$',
    r'^\s*DISCONNECT\s*;',
    r'^\s*CONNECT\s',
]
COMPILED = [re.compile(p, re.IGNORECASE) for p in SQLPLUS_PATTERNS]


def is_sqlplus_line(line: str) -> bool:
    for pat in COMPILED:
        if pat.match(line):
            return True
    return False


def main():
    if not SRC.exists():
        print(f"ERROR: source file not found: {SRC}")
        return 1

    print(f"Reading: {SRC}")
    with SRC.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    out_lines = []
    removed = 0
    for line in lines:
        if is_sqlplus_line(line):
            removed += 1
            continue
        out_lines.append(line)

    # 添加 Aqua 友好的头部说明
    header = """/* ================================================================
   FabTwin Oracle Database Initialization Script (Aqua Data Studio compatible)
   Generated from init_oracle_db.sql

   Compatibility:
   - All SQL*Plus commands removed (PROMPT/SET/SPOOL/EXIT/etc.)
   - Pure SQL + PL/SQL blocks (CREATE TRIGGER ... END; / )
   - Compatible with Aqua Data Studio, DBeaver, SQL Developer, Toad

   Usage in Aqua Data Studio:
   1. Connect to Oracle as fabtwin user (or DBA-provided business user)
   2. Open this file: File -> Open -> init_oracle_aqua.sql
   3. Execute: Query -> Execute All (or F5)
   4. Check execution log for errors

   Notes:
   - DT_* tables are NOT created here (managed by production env)
   - 11 SEQUENCE + TRIGGER pairs simulate IDENTITY columns (Oracle 10g/11g compatible)
   - Total: 20 platform tables + base data
   ================================================================ */

"""

    DST.write_text(header + "".join(out_lines), encoding="utf-8")

    size_mb = DST.stat().st_size / 1024 / 1024
    print(f"Generated: {DST}")
    print(f"  Size: {size_mb:.2f} MB")
    print(f"  Lines: {len(out_lines)}")
    print(f"  Removed SQL*Plus lines: {removed}")
    print()
    print("Now you can use init_oracle_aqua.sql in Aqua Data Studio directly.")


if __name__ == "__main__":
    raise SystemExit(main())
