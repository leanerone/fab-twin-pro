# -*- coding: utf-8 -*-
"""快速体检：列出本地测试库所有表的行数，确认数据缺失范围"""
import sys
import oracledb

DSN = "localhost:1521/orclpdb"
USER = "fabtwin"
PWD = "fabtwin"


def main():
    conn = oracledb.connect(user=USER, password=PWD, dsn=DSN)
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM user_tables ORDER BY table_name")
    tables = [r[0] for r in cur.fetchall()]
    print(f"共 {len(tables)} 张表")
    empty = []
    for t in tables:
        try:
            cur.execute(f'SELECT COUNT(*) FROM "{t}"')
            n = cur.fetchone()[0]
        except Exception as e:
            n = f"ERR {e}"
        print(f"{t:<32} {n}")
        if n == 0:
            empty.append(t)
    print("\n空表：", ", ".join(empty) if empty else "无")
    cur.close()
    conn.close()


if __name__ == "__main__":
    sys.exit(main())
