"""通用SQL执行器：从 .env 读取连接信息，执行指定SQL数据文件中的语句"""
import os
import re
import sys

import oracledb

BASE = os.path.dirname(os.path.abspath(__file__))


def load_env(path):
    env = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^\s*([A-Za-z_]+)\s*=\s*(.*?)\s*$", line)
            if m:
                env[m.group(1)] = m.group(2)
    return env


def main():
    env = load_env(os.path.join(BASE, "..", "services", "db_proxy", ".env"))
    dsn = f"{env.get('ORACLE_HOST', 'localhost')}:{env.get('ORACLE_PORT', '1521')}/{env.get('ORACLE_SERVICE', 'XEPDB1')}"
    pw = env.get("ORACLE_PASSWORD", "")

    sql_file = sys.argv[1]
    with open(sql_file, encoding="utf-8") as f:
        raw = f.read()

    statements = [s.strip() for s in raw.split(";") if s.strip() and not s.strip().startswith("--")]

    conn = oracledb.connect(user="system", password=pw, dsn=dsn)
    cur = conn.cursor()
    for stmt in statements:
        try:
            cur.execute(stmt)
            print("OK:", stmt.split()[0], stmt.split()[1] if len(stmt.split()) > 1 else "")
        except oracledb.DatabaseError as e:
            print("WARN:", str(e).split("\n")[0])
    conn.commit()

    # 验证应用账号可登录
    app_user = env.get("ORACLE_USER", "")
    conn2 = oracledb.connect(user=app_user, password=pw, dsn=dsn)
    cur2 = conn2.cursor()
    cur2.execute("SELECT user FROM dual")
    print("APP LOGIN AS:", cur2.fetchone()[0])
    conn2.close()
    conn.close()
    print("ALL_OK")


if __name__ == "__main__":
    main()
