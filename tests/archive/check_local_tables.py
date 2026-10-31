# -*- coding: utf-8 -*-
"""检查本机 Oracle 连接和表清单"""
import oracledb
oracledb.defaults.fetch_lobs = False
conn = oracledb.connect(
    user="fabtwin", password="fabtwin",
    dsn=oracledb.makedsn("localhost", 1521, service_name="orclpdb"))
print("连接成功, DB版本:", conn.version)
cur = conn.cursor()
cur.execute("SELECT table_name FROM user_tables ORDER BY table_name")
tabs = [r[0] for r in cur.fetchall()]
print("表数量:", len(tabs))
for t in tabs:
    print(" ", t)
cur.close()
conn.close()
