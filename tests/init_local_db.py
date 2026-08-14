"""用 sqlplus + 正确 NLS_LANG 初始化本地 DB（解决中文编码问题）

通过 subprocess 调用 sqlplus 执行脚本文件，避免：
1. PowerShell @ 符号冲突
2. PowerShell 管道中文编码损坏
3. Python split_sql 拆分不完整
"""
import os
import subprocess
import oracledb

# 关键：设置 NLS_LANG 匹配数据库字符集 AL32UTF8
os.environ['NLS_LANG'] = 'SIMPLIFIED CHINESE_CHINA.AL32UTF8'
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

# Oracle 客户端路径
ORACLE_HOME = r"C:\oracle\WINDOWS.X64_193000_db_home"
os.environ['PATH'] = os.path.join(ORACLE_HOME, 'bin') + ';' + os.environ.get('PATH', '')

DSN = "//C01ONB1023:1521/orclpdb"
USER = "fabtwin"
PWD = "fabtwin"
CONN_STR = f"{USER}/{PWD}@{DSN}"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_sqlplus(script_path, label):
    """用 sqlplus 执行 SQL 脚本文件"""
    print(f"\n{'='*60}")
    print(f"执行: {label}")
    print(f"文件: {script_path}")
    print(f"{'='*60}")

    if not os.path.exists(script_path):
        print(f"[SKIP] 文件不存在")
        return False

    # sqlplus @ 方式执行脚本文件
    cmd = ['sqlplus', '-L', '-S', CONN_STR, '@' + script_path]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding='gbk',  # sqlplus 输出用 GBK 编码（Windows 中文环境）
        errors='replace'
    )

    output = result.stdout or ''
    # 统计成功/失败
    ok_count = output.count('已创建') + output.count('已创建 1 行') + output.count('提交完成')
    err_count = output.count('ERROR:')
    ora_errors = output.count('ORA-')

    # 打印关键输出（截断过长内容）
    lines = output.splitlines()
    # 只打印含 ERROR/ORA/创建/成功 的行
    key_lines = [l for l in lines if any(k in l for k in ['ERROR', 'ORA-', '创建', '提交', '成功', '失败', 'SP2-'])]
    for l in key_lines[:30]:
        print(f"  {l}")
    if len(key_lines) > 30:
        print(f"  ... 共 {len(key_lines)} 行关键输出")

    print(f"结果: exit_code={result.returncode}, ORA错误={ora_errors}次")
    return ora_errors == 0


def verify_data():
    """验证关键表数据"""
    print(f"\n{'='*60}")
    print("验证关键表数据")
    print(f"{'='*60}")

    # Thick 模式连接
    oracledb.init_oracle_client(lib_dir=os.path.join(ORACLE_HOME, 'bin'))
    conn = oracledb.connect(user=USER, password=PWD, dsn=DSN)
    cur = conn.cursor()

    checks = [
        ("USERS", "SELECT username, display_name, role FROM users ORDER BY username"),
        ("ROLES", "SELECT id, name FROM roles ORDER BY id"),
        ("MACHINES", "SELECT id, name, model FROM machines WHERE ROWNUM<=3 ORDER BY id"),
        ("AI_PROVIDER_CONFIGS", "SELECT id, name, provider, model FROM ai_provider_configs ORDER BY id"),
        ("AI_CONFIGS", "SELECT config_key, description FROM ai_configs ORDER BY config_key"),
        ("TRIGGERS", "SELECT trigger_name, status FROM user_triggers WHERE trigger_name LIKE 'TRG_%'"),
    ]
    all_ok = True
    for label, sql in checks:
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            print(f"\n[{label}] ({len(rows)} 行)")
            for r in rows[:5]:
                print(f"  {r}")
            if len(rows) > 5:
                print(f"  ... 共 {len(rows)} 行")
            if label in ("USERS", "ROLES", "AI_PROVIDER_CONFIGS") and len(rows) == 0:
                all_ok = False
        except Exception as e:
            print(f"\n[{label}] 查询失败: {e}")
            all_ok = False

    cur.close()
    conn.close()
    return all_ok


def main():
    # 1. 执行 init_oracle_aqua.sql（平台基础表）
    init_path = os.path.join(BASE_DIR, "sql", "init_oracle_aqua.sql")
    run_sqlplus(init_path, "平台基础表初始化")

    # 2. 执行 create_ai_tables.sql（AI 相关表）
    ai_path = os.path.join(BASE_DIR, "sql", "create_ai_tables.sql")
    run_sqlplus(ai_path, "AI 相关表初始化")

    # 3. 验证数据
    ok = verify_data()

    print(f"\n{'='*60}")
    if ok:
        print("初始化完成! 所有关键表数据正常")
    else:
        print("初始化完成(部分数据可能缺失，请检查上方输出)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
