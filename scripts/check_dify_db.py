#!/usr/bin/env python3
"""
Dify/N8N 配置保存问题 — DB 状态检测脚本

用途：检测 Oracle 中 AI_CONFIGS / MACHINE_DIFY_CONFIGS 表、序列、触发器状态，
      并导出当前 Dify/N8N 配置值，用于排查"保存后刷新丢失"问题。

运行方式（在 backend 目录下）：
    cd backend
    python ..\scripts\check_dify_db.py

或在项目根目录：
    python scripts\check_dify_db.py

输出：直接打印到控制台（把整段输出复制发回即可）。
"""
import os
import sys
import glob

# ================================================================
# 1. 自动加载 env.bat 环境变量（与 diagnose_oracle_env.py 一致）
# ================================================================
def load_env_bat():
    """从 backend上级目录读取 env.bat，设置环境变量"""
    # 脚本位于 scripts/ 目录，backend 在同级
    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(script_dir)  # fab-twin-pro 根
    env_bat = os.path.join(base_dir, "env.bat")
    if not os.path.exists(env_bat):
        print(f"[INFO] 未找到 env.bat: {env_bat}（将使用环境变量/默认值）")
        return
    print(f"[OK] 加载 env.bat: {env_bat}")
    with open(env_bat, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line.lower().startswith("set "):
                parts = line[4:].split("=", 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip()
                    os.environ[key] = val
                    if key in ("ORACLE_HOST", "ORACLE_PORT", "ORACLE_SERVICE",
                               "ORACLE_USER", "ORACLE_DSN_TYPE", "ORACLE_CLIENT_DIR"):
                        print(f"  [ENV] {key}={val}")

load_env_bat()

# ================================================================
# 2. Oracle 连接参数（优先环境变量，回退默认值，与 config.py 一致）
# ================================================================
ORACLE_USER = os.getenv("ORACLE_USER", "fabtwin")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "fabtwin")
ORACLE_HOST = os.getenv("ORACLE_HOST", "localhost")
ORACLE_PORT = int(os.getenv("ORACLE_PORT", "1521"))
ORACLE_SERVICE = os.getenv("ORACLE_SERVICE", "ORCLPDB")
ORACLE_DSN_TYPE = os.getenv("ORACLE_DSN_TYPE", "service_name").lower()


def _find_lib_dir(client_dir):
    if not client_dir:
        return ''
    bin_dir = os.path.join(client_dir, 'bin')
    if os.path.exists(os.path.join(bin_dir, 'oci.dll')):
        return bin_dir
    if os.path.exists(os.path.join(client_dir, 'oci.dll')):
        return client_dir
    return ''


def find_oracle_client():
    candidates = []
    env_client = os.environ.get("ORACLE_CLIENT_DIR")
    if env_client:
        candidates.insert(0, env_client)
    candidates += [
        r"C:\app\client\c11463\product\19.0.0\client_1",
        r"C:\oracle\instantclient_19_20",
        r"C:\oracle\instantclient_19_22",
        r"C:\oracle\product\19.0.0\client_1",
    ]
    for path in glob.glob(r"C:\oracle\instantclient_*"):
        candidates.insert(0, path)
    for path in candidates:
        if os.path.exists(path):
            lib_dir = _find_lib_dir(path)
            if lib_dir:
                return path, lib_dir
    return None, None


def connect_oracle():
    import oracledb
    # Thin 模式优先
    try:
        dsn = f"{ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}"
        print(f"  尝试 Thin 模式连接 {dsn}...")
        conn = oracledb.connect(user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=dsn)
        print("  [OK] Thin 模式连接成功")
        return conn, "thin"
    except Exception as e:
        print(f"  [INFO] Thin 模式失败: {str(e)[:120]}")
    # Thick 模式
    client_dir, lib_dir = find_oracle_client()
    if lib_dir:
        try:
            oracledb.init_oracle_client(lib_dir=lib_dir)
            print(f"  [OK] 已初始化 Oracle Client (lib={lib_dir})")
        except Exception as e:
            if "already" in str(e).lower() or "已初始化" in str(e):
                pass
            else:
                print(f"  [WARN] Thick 初始化失败: {e}")
        try:
            if ORACLE_DSN_TYPE == "sid":
                dsn = oracledb.makedsn(ORACLE_HOST, ORACLE_PORT, sid=ORACLE_SERVICE)
            else:
                dsn = oracledb.makedsn(ORACLE_HOST, ORACLE_PORT, service_name=ORACLE_SERVICE)
            conn = oracledb.connect(user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=dsn)
            print("  [OK] Thick 模式连接成功")
            return conn, "thick"
        except Exception as e:
            print(f"  [ERROR] Thick 模式连接失败: {e}")
    print("  [ERROR] 无法连接 Oracle，请检查 env.bat / 环境变量 / Oracle Client")
    return None, None


def sep(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def check_table_exists(conn, table_name):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME = :n", {"n": table_name.upper()})
    return cur.fetchone()[0] > 0


def check_sequence_exists(conn, seq_name):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM USER_SEQUENCES WHERE SEQUENCE_NAME = :n", {"n": seq_name.upper()})
    return cur.fetchone()[0] > 0


def check_trigger(conn, trg_name):
    """返回 (exists, status) status 可能: ENABLED/DISABLED, 另查 INVALID"""
    cur = conn.cursor()
    cur.execute("""
        SELECT t.TRIGGER_NAME, t.STATUS, DECODE(o.STATUS, 'VALID', 'VALID', 'INVALID') AS OBJ_STATUS
        FROM USER_TRIGGERS t
        LEFT JOIN USER_OBJECTS o ON o.OBJECT_NAME = t.TRIGGER_NAME AND o.OBJECT_TYPE = 'TRIGGER'
        WHERE t.TRIGGER_NAME = :n
    """, {"n": trg_name.upper()})
    row = cur.fetchone()
    if not row:
        return False, None, None
    return True, row[1], row[2]


def main():
    sep("Dify/N8N 配置保存问题 — DB 状态检测")
    print(f"目标: {ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}  用户: {ORACLE_USER}  DSN类型: {ORACLE_DSN_TYPE}")

    conn, mode = connect_oracle()
    if not conn:
        print("\n[FATAL] 无法连接 Oracle，检测中止。")
        sys.exit(1)

    # DB 版本
    try:
        cur = conn.cursor()
        cur.execute("SELECT BANNER FROM V$VERSION WHERE BANNER LIKE 'Oracle%'")
        row = cur.fetchone()
        print(f"\n[DB 版本] {row[0] if row else '未知'} (连接模式: {mode})")
    except Exception as e:
        print(f"[WARN] 获取版本失败: {e}")

    # ================================================================
    # 检查 1: AI_CONFIGS 表（公用 Dify/N8N 配置键值对表）
    # ================================================================
    sep("1. AI_CONFIGS 表（公用 Dify/N8N 配置）")
    if not check_table_exists(conn, "AI_CONFIGS"):
        print("  [FAIL] 表 AI_CONFIGS 不存在！")
        print("         → 请执行 sql/create_ai_tables.sql 第 35~46 行建表语句")
    else:
        print("  [OK] 表 AI_CONFIGS 存在")
        cur = conn.cursor()
        # 列结构
        cur.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, NULLABLE
            FROM USER_TAB_COLUMNS WHERE TABLE_NAME='AI_CONFIGS' ORDER BY COLUMN_ID
        """)
        cols = cur.fetchall()
        print("  列结构:")
        for c in cols:
            print(f"    {c[0]:20} {c[1]:15} len={c[2]:6} nullable={'Y' if c[3]=='Y' else 'N'}")
        # 行数
        cur.execute("SELECT COUNT(*) FROM AI_CONFIGS")
        cnt = cur.fetchone()[0]
        print(f"  总行数: {cnt}")
        # 关键配置行（Dify/N8N 相关键）
        cur.execute("""
            SELECT CONFIG_KEY, CONFIG_VALUE, DESCRIPTION, UPDATED_AT, UPDATED_BY
            FROM AI_CONFIGS
            WHERE CONFIG_KEY LIKE 'dify_%' OR CONFIG_KEY LIKE 'n8n_%' OR CONFIG_KEY LIKE 'mcp_n8n_%'
            ORDER BY CONFIG_KEY
        """)
        rows = cur.fetchall()
        if not rows:
            print("  [WARN] 未找到 Dify/N8N 相关配置行！")
            print("         → 说明 _load_dify_n8n_from_db 写入默认值失败，或表为空")
        else:
            print(f"  Dify/N8N 配置行 ({len(rows)} 条):")
            print(f"    {'CONFIG_KEY':25} {'VALUE':50} {'UPDATED_AT':25} {'BY'}")
            print(f"    {'-'*25} {'-'*50} {'-'*25} {'-'*10}")
            for r in rows:
                # CONFIG_VALUE 是 CLOB，需要 .read() 转字符串
                val = r[1]
                if hasattr(val, 'read'):
                    val = val.read()
                val = (val or '') if isinstance(val, str) else str(val)
                desc = r[2]
                if hasattr(desc, 'read'):
                    desc = desc.read()
                updated_at = r[3]
                if hasattr(updated_at, 'read'):
                    updated_at = updated_at.read()
                updated_by = r[4]
                if hasattr(updated_by, 'read'):
                    updated_by = updated_by.read()
                # API Key 只显示前8位+****
                if 'api_key' in r[0].lower() or 'secret' in r[0].lower() or 'token' in r[0].lower():
                    val = (val[:8] + '****') if val else '(空)'
                print(f"    {r[0]:25} {val:50} {(updated_at or '')[:25]:25} {updated_by or ''}")
                if desc:
                    print(f"      └─ 说明: {desc}")

    # ================================================================
    # 检查 2: AI_CONFIGS 序列 + 触发器
    # ================================================================
    sep("2. AI_CONFIGS 序列 + 触发器")
    if check_sequence_exists(conn, "SEQ_AI_CONFIGS"):
        print("  [OK] 序列 SEQ_AI_CONFIGS 存在")
    else:
        print("  [FAIL] 序列 SEQ_AI_CONFIGS 不存在！")
        print("         → 请执行 sql/create_ai_tables.sql 第 106 行")

    exists, status, obj_status = check_trigger(conn, "TRG_AI_CONFIGS_ID")
    if not exists:
        print("  [FAIL] 触发器 TRG_AI_CONFIGS_ID 不存在！")
        print("         → 请执行 sql/create_ai_tables.sql 第 108~114 行")
    else:
        mark = "[OK]" if (status == "ENABLED" and obj_status == "VALID") else "[FAIL]"
        print(f"  {mark} 触发器 TRG_AI_CONFIGS_ID: status={status}, object={obj_status}")
        if obj_status == "INVALID":
            print("         → 触发器对象状态为 INVALID！INSERT 会失败。")
            print("         → 修复: ALTER TRIGGER TRG_AI_CONFIGS_ID COMPILE;")
        if status == "DISABLED":
            print("         → 触发器被禁用！自增ID不会生效。")
            print("         → 修复: ALTER TRIGGER TRG_AI_CONFIGS_ID ENABLE;")

    # ================================================================
    # 检查 3: MACHINE_DIFY_CONFIGS 表（机台专属 Dify 配置）
    # ================================================================
    sep("3. MACHINE_DIFY_CONFIGS 表（机台专属 Dify 配置）")
    if not check_table_exists(conn, "MACHINE_DIFY_CONFIGS"):
        print("  [FAIL] 表 MACHINE_DIFY_CONFIGS 不存在！")
        print("         → 请执行 sql/create_ai_tables.sql 第 216~225 行建表语句")
    else:
        print("  [OK] 表 MACHINE_DIFY_CONFIGS 存在")
        cur = conn.cursor()
        cur.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, NULLABLE
            FROM USER_TAB_COLUMNS WHERE TABLE_NAME='MACHINE_DIFY_CONFIGS' ORDER BY COLUMN_ID
        """)
        cols = cur.fetchall()
        print("  列结构:")
        for c in cols:
            print(f"    {c[0]:20} {c[1]:15} len={c[2]:6} nullable={'Y' if c[3]=='Y' else 'N'}")
        cur.execute("SELECT COUNT(*) FROM MACHINE_DIFY_CONFIGS")
        cnt = cur.fetchone()[0]
        print(f"  总行数: {cnt}")
        if cnt > 0:
            cur.execute("""
                SELECT ID, CONFIG_NAME, MODEL_ID, DIFY_BASE_URL,
                       SUBSTR(DIFY_API_KEY,1,8)||'****' AS KEY_MASK, IS_ACTIVE, UPDATED_AT
                FROM MACHINE_DIFY_CONFIGS ORDER BY ID
            """)
            rows = cur.fetchall()
            print(f"  机台专属配置行 ({len(rows)} 条):")
            print(f"    {'ID':5} {'CONFIG_NAME':20} {'MODEL_ID':15} {'DIFY_BASE_URL':40} {'KEY':14} {'ACTIVE':7} {'UPDATED'}")
            print(f"    {'-'*5} {'-'*20} {'-'*15} {'-'*40} {'-'*14} {'-'*7} {'-'*20}")
            for r in rows:
                print(f"    {str(r[0]):5} {(r[1] or ''):20} {(r[2] or ''):15} {(r[3] or ''):40} {(r[4] or ''):14} {str(r[5]):7} {(r[6] or '')[:20]}")
        else:
            print("  [INFO] 表为空（无机台专属配置）")

    # ================================================================
    # 检查 4: MACHINE_DIFY_CONFIGS 序列 + 触发器
    # ================================================================
    sep("4. MACHINE_DIFY_CONFIGS 序列 + 触发器")
    if check_sequence_exists(conn, "SEQ_MACHINE_DIFY_CONFIGS"):
        print("  [OK] 序列 SEQ_MACHINE_DIFY_CONFIGS 存在")
    else:
        print("  [FAIL] 序列 SEQ_MACHINE_DIFY_CONFIGS 不存在！")
        print("         → 请执行 sql/create_ai_tables.sql 第 229 行")

    exists, status, obj_status = check_trigger(conn, "TRG_MACHINE_DIFY_CONFIGS_ID")
    if not exists:
        print("  [FAIL] 触发器 TRG_MACHINE_DIFY_CONFIGS_ID 不存在！")
        print("         → 请执行 sql/create_ai_tables.sql 第 231~238 行")
    else:
        mark = "[OK]" if (status == "ENABLED" and obj_status == "VALID") else "[FAIL]"
        print(f"  {mark} 触发器 TRG_MACHINE_DIFY_CONFIGS_ID: status={status}, object={obj_status}")
        if obj_status == "INVALID":
            print("         → 触发器对象状态为 INVALID！新增机台配置会报错。")
            print("         → 修复: ALTER TRIGGER TRG_MACHINE_DIFY_CONFIGS_ID COMPILE;")
        if status == "DISABLED":
            print("         → 触发器被禁用！")
            print("         → 修复: ALTER TRIGGER TRG_MACHINE_DIFY_CONFIGS_ID ENABLE;")

    # ================================================================
    # 检查 5: 所有 AI 相关触发器状态汇总
    # ================================================================
    sep("5. AI 相关触发器状态汇总")
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT t.TRIGGER_NAME, t.TABLE_NAME, t.STATUS,
                   DECODE(o.STATUS,'VALID','VALID','INVALID') AS OBJ_STATUS
            FROM USER_TRIGGERS t
            LEFT JOIN USER_OBJECTS o ON o.OBJECT_NAME=t.TRIGGER_NAME AND o.OBJECT_TYPE='TRIGGER'
            WHERE t.TRIGGER_NAME LIKE 'TRG_AI%' OR t.TRIGGER_NAME LIKE 'TRG_MACHINE%'
            ORDER BY t.TRIGGER_NAME
        """)
        rows = cur.fetchall()
        if not rows:
            print("  [WARN] 未找到任何 AI 相关触发器")
        else:
            print(f"  {'TRIGGER_NAME':35} {'TABLE':25} {'TRIG_STATUS':13} {'OBJ_STATUS':12}")
            print(f"  {'-'*35} {'-'*25} {'-'*13} {'-'*12}")
            for r in rows:
                flag = "  " if (r[2] == "ENABLED" and r[3] == "VALID") else ">>"
                print(f"  {r[0]:35} {r[1]:25} {r[2]:13} {r[3]:12} {flag}")
    except Exception as e:
        print(f"  [WARN] 查询触发器汇总失败: {e}")

    # ================================================================
    # 结论提示
    # ================================================================
    sep("检测结论提示")
    print("常见问题对照：")
    print("  1. 表不存在          → 执行 sql/create_ai_tables.sql 对应建表语句")
    print("  2. 序列不存在        → 执行 sql/create_ai_tables.sql 对应 CREATE SEQUENCE")
    print("  3. 触发器不存在      → 执行 sql/create_ai_tables.sql 对应 CREATE TRIGGER（注意结尾有 /）")
    print("  4. 触发器 INVALID    → 执行: ALTER TRIGGER <触发器名> COMPILE;")
    print("  5. 触发器 DISABLED   → 执行: ALTER TRIGGER <触发器名> ENABLE;")
    print("  6. AI_CONFIGS 无配置行 → 重启后端会自动写入默认值；或手动 INSERT")
    print("  7. API_KEY 显示(空)  → 保存时前端未传值或后端 _save_to_db 失败，看后端日志")
    print("\n请把以上全部输出复制发回，我据此定位保存失败的根因。")

    conn.close()
    print("\n[完成] 数据库连接已关闭。")


if __name__ == "__main__":
    main()
