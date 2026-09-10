# -*- coding: utf-8 -*-
"""查看 DT_EVENT_RAW 主键现状和表结构"""
import oracledb

oracledb.defaults.fetch_lobs = False

conn = oracledb.connect(
    user="fabtwin", password="fabtwin",
    dsn=oracledb.makedsn("localhost", 1521, service_name="orclpdb"))
cur = conn.cursor()

# DT_EVENT_RAW 主键
print("=== DT_EVENT_RAW 结构 ===")
cur.execute("SELECT column_name, data_type FROM user_tab_columns WHERE table_name='DT_EVENT_RAW' ORDER BY column_id")
for r in cur.fetchall():
    print(f"  {r[0]:25s} {r[1]}")

print("\n=== DT_EVENT_RAW 最大 RAW_ID ===")
cur.execute("SELECT MAX(RAW_ID), COUNT(*) FROM DT_EVENT_RAW")
print(" ", cur.fetchone())

# 查看 RAW_ID 是字符串还是数字
cur.execute("SELECT RAW_ID FROM DT_EVENT_RAW WHERE ROWNUM<=3")
for r in cur.fetchall():
    print("  样本 RAW_ID:", repr(r[0]), type(r[0]).__name__)

# DT_EVENT_RAW_CUR 结构
print("\n=== DT_EVENT_RAW_CUR 结构 ===")
cur.execute("SELECT column_name, data_type FROM user_tab_columns WHERE table_name='DT_EVENT_RAW_CUR' ORDER BY column_id")
for r in cur.fetchall():
    print(f"  {r[0]:25s} {r[1]}")

print("\n=== DT_EVENT_RAW_CUR 最大 RAW_ID ===")
cur.execute("SELECT MAX(RAW_ID), COUNT(*) FROM DT_EVENT_RAW_CUR")
print(" ", cur.fetchone())

cur.close()
conn.close()
