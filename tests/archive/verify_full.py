# -*- coding: utf-8 -*-
"""验证所有 AI 换版增量字段和表"""
import oracledb
oracledb.defaults.fetch_lobs = False

conn = oracledb.connect(user="fabtwin", password="fabtwin",
                        dsn=oracledb.makedsn("localhost", 1521, service_name="orclpdb"))
cur = conn.cursor()

print("===== 1. MACHINES 表列结构（检查 v2.6/v2.7 增量字段）=====")
cur.execute("""
    SELECT column_name FROM user_tab_columns
    WHERE table_name='MACHINES' ORDER BY column_id
""")
cols = [r[0] for r in cur.fetchall()]
print(f"共 {len(cols)} 列")
v26_cols = [c for c in cols if c in ('EXTERNAL_URL','USE_EXTERNAL_URL')]
v27_cols = [c for c in cols if c == 'DISPLAY_ORDER']
print(f"  v2.6 字段 EXTERNAL_URL/USE_EXTERNAL_URL: {v26_cols if v26_cols else '缺失'}")
print(f"  v2.7 字段 DISPLAY_ORDER: {'有' if v27_cols else '缺失'}")

print("\n===== 2. FLOOR_AREAS 表 DISPLAY_ORDER 列 =====")
cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name='FLOOR_AREAS' AND column_name='DISPLAY_ORDER'")
print(f"  {'有' if cur.fetchone() else '缺失'}")

print("\n===== 3. MACHINE_MODEL_CONFIGS v2.0 动画字段 =====")
cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name='MACHINE_MODEL_CONFIGS' AND column_name IN ('ANIMATION_CONFIG_JSON','SOURCE_FILES_JSON')")
rows = [r[0] for r in cur.fetchall()]
print(f"  {'有: ' + str(rows) if rows else '缺失'}")

print("\n===== 4. AI 相关表（AI_CONFIGS/AI_PROVIDER_CONFIGS/AI_USAGE_LOGS/MACHINE_DIFY_CONFIGS）=====")
for t in ['AI_CONFIGS','AI_PROVIDER_CONFIGS','AI_USAGE_LOGS','MACHINE_DIFY_CONFIGS']:
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    print(f"  {t}: {cur.fetchone()[0]} 行")

print("\n===== 5. AI_CONFIGS 中的 mcp_n8n_* 配置（v2.1）=====")
cur.execute("SELECT config_key FROM ai_configs WHERE config_key LIKE 'mcp_n8n_%' ORDER BY config_key")
rows = [r[0] for r in cur.fetchall()]
print(f"  共 {len(rows)} 条: {rows}")

print("\n===== 6. AI_CONFIGS 中 dify_/n8n_ 配置 =====")
cur.execute("SELECT config_key FROM ai_configs WHERE config_key LIKE 'dify_%' OR config_key LIKE 'n8n_%' ORDER BY config_key")
rows = [r[0] for r in cur.fetchall()]
print(f"  共 {len(rows)} 条: {rows}")

print("\n===== 7. 触发器状态（应全部 ENABLED/VALID）=====")
cur.execute("""
    SELECT trigger_name, status FROM user_triggers
    WHERE trigger_name LIKE 'TRG_%' ORDER BY trigger_name
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]}")

print("\n===== 8. 全部表清单 =====")
cur.execute("SELECT table_name FROM user_tables ORDER BY table_name")
all_tables = [r[0] for r in cur.fetchall()]
print(f"共 {len(all_tables)} 张表:")
for t in all_tables:
    print(f"  {t}")

cur.close()
conn.close()
