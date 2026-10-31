"""检查本地 DB 的 OXE 机台事件数据，判断是否需要补充测试数据"""
import os
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
os.environ['NLS_LANG'] = 'SIMPLIFIED CHINESE_CHINA.AL32UTF8'

import oracledb
oracledb.init_oracle_client(lib_dir=r"C:\oracle\WINDOWS.X64_193000_db_home\bin")

conn = oracledb.connect(user="fabtwin", password="fabtwin", dsn="//C01ONB1023:1521/orclpdb")
cur = conn.cursor()

print("=" * 60)
print("1. OXE 机台列表")
print("=" * 60)
cur.execute("""
    SELECT id, name, model FROM machines
    WHERE UPPER(id) LIKE 'OXE%' OR UPPER(model) LIKE '%OXE%' OR UPPER(name) LIKE '%OXE%'
    ORDER BY id
""")
oxe_machines = cur.fetchall()
for r in oxe_machines:
    print(f"  {r}")
print(f"  共 {len(oxe_machines)} 台 OXE 机台")

print("\n" + "=" * 60)
print("2. MACHINE_EVENTS 表中 OXE 相关事件统计")
print("=" * 60)
# 先看表结构
cur.execute("""
    SELECT column_name, data_type FROM user_tab_columns
    WHERE table_name='MACHINE_EVENTS' ORDER BY column_id
""")
cols = cur.fetchall()
print("MACHINE_EVENTS 字段:")
for c in cols:
    print(f"  - {c[0]} ({c[1]})")

# 查询 OXE 机台的事件统计
cur.execute("""
    SELECT COUNT(*) FROM machine_events
    WHERE UPPER(machine_id) LIKE 'OXE%'
""")
total = cur.fetchone()[0]
print(f"\nOXE 机台事件总数: {total}")

if total > 0:
    cur.execute("""
        SELECT machine_id, COUNT(*) as cnt
        FROM machine_events
        WHERE UPPER(machine_id) LIKE 'OXE%'
        GROUP BY machine_id ORDER BY cnt DESC
    """)
    for r in cur.fetchall():
        print(f"  {r[0]}: {r[1]} 条")

    # 查看事件类型分布
    cur.execute("""
        SELECT event_name, COUNT(*) as cnt
        FROM machine_events
        WHERE UPPER(machine_id) LIKE 'OXE%'
        GROUP BY event_name ORDER BY cnt DESC
    """)
    print("\nOXE 事件类型分布:")
    for r in cur.fetchall():
        print(f"  {r[0]}: {r[1]} 条")

    # 看时间范围
    cur.execute("""
        SELECT MIN(timestamp), MAX(timestamp)
        FROM machine_events WHERE UPPER(machine_id) LIKE 'OXE%'
    """)
    ts_range = cur.fetchone()
    print(f"\n时间范围: {ts_range[0]} ~ {ts_range[1]}")

print("\n" + "=" * 60)
print("3. DT_EVENT_RAW 表（OXE 事件源）")
print("=" * 60)
try:
    cur.execute("SELECT COUNT(*) FROM DT_EVENT_RAW WHERE UPPER(tool_id) LIKE 'OXE%'")
    total_raw = cur.fetchone()[0]
    print(f"DT_EVENT_RAW OXE 事件总数: {total_raw}")

    if total_raw > 0:
        cur.execute("""
            SELECT tool_id, COUNT(*) as cnt
            FROM DT_EVENT_RAW WHERE UPPER(tool_id) LIKE 'OXE%'
            GROUP BY tool_id ORDER BY cnt DESC
        """)
        for r in cur.fetchall():
            print(f"  {r[0]}: {r[1]} 条")

        cur.execute("""
            SELECT event_name, COUNT(*) as cnt
            FROM DT_EVENT_RAW WHERE UPPER(tool_id) LIKE 'OXE%'
            GROUP BY event_name ORDER BY cnt DESC
        """)
        print("\nDT_EVENT_RAW OXE 事件类型分布:")
        for r in cur.fetchall():
            print(f"  {r[0]}: {r[1]} 条")
except Exception as e:
    print(f"DT_EVENT_RAW 查询失败: {e}")

print("\n" + "=" * 60)
print("4. ALARMS 表中 OXE 相关告警")
print("=" * 60)
cur.execute("SELECT COUNT(*) FROM alarms WHERE UPPER(machine_id) LIKE 'OXE%'")
alarm_count = cur.fetchone()[0]
print(f"OXE 告警总数: {alarm_count}")

print("\n" + "=" * 60)
print("5. LOTS 表中 OXE 相关 Lot")
print("=" * 60)
cur.execute("SELECT COUNT(*) FROM lots WHERE UPPER(machine_id) LIKE 'OXE%'")
lot_count = cur.fetchone()[0]
print(f"OXE Lot 总数: {lot_count}")

cur.close()
conn.close()
print("\n检查完成!")
