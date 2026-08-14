"""测试本地 Oracle 连接"""
import os
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
import oracledb

# 尝试多种连接参数
configs = [
    ("fabtwin", "fabtwin", "localhost", 1521, "orcl", "service_name"),
    ("fabtwin", "fabtwin", "localhost", 1521, "ORCLPDB", "service_name"),
    ("fabtwin", "fabtwin", "localhost", 1521, "orcl", "sid"),
    ("system", "oracle", "localhost", 1521, "orcl", "service_name"),
    ("system", "fabtwin", "localhost", 1521, "orcl", "service_name"),
]

for user, pwd, host, port, svc, dtype in configs:
    try:
        if dtype == "sid":
            dsn = f"{host}:{port}/?sid={svc}"
        else:
            dsn = f"{host}:{port}/?service_name={svc}"
        conn = oracledb.connect(user=user, password=pwd, dsn=dsn)
        cur = conn.cursor()
        cur.execute("SELECT USER, SYS_CONTEXT('USERENV','DB_NAME') FROM dual")
        row = cur.fetchone()
        print(f"[OK] {user}/{pwd}@{host}:{port}/{svc} ({dtype}) -> USER={row[0]}, DB={row[1]}")
        # 检查 fabtwin 是否有表
        cur.execute("SELECT TABLE_NAME FROM USER_TABLES ORDER BY TABLE_NAME")
        tables = [r[0] for r in cur.fetchall()]
        print(f"      tables: {tables[:10]}{'...' if len(tables)>10 else ''} (total={len(tables)})")
        conn.close()
        break
    except Exception as e:
        print(f"[FAIL] {user}/{pwd}@{host}:{port}/{svc} ({dtype}) -> {str(e)[:80]}")
