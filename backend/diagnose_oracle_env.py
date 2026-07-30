#!/usr/bin/env python3
"""
Oracle 量产环境诊断和导出脚本

用途：在量产服务器上连接量产Oracle，导出数据库结构和关键数据样本
运行后将报告发回开发人员，用于比对本地开发环境。

运行方式：
    cd backend
    python diagnose_oracle_env.py

输出（在 backend 目录）：
    - prod_oracle_report_YYYYMMDD_HHMMSS.json  完整报告（可发回开发）
    - prod_oracle_report_YYYYMMDD_HHMMSS.txt   可读性报告
"""
import os
import sys
import json
import glob
from datetime import datetime
from typing import Dict, List, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ================================================================
# 配置区：请根据实际环境修改
# ================================================================

PROD_ORACLE = {
    "host": "10.30.8.119",
    "port": 1521,
    "service": "APCDB",
    "user": "emuuser",
    "password": "apcuser",
    "dsn_type": "sid",
}

# 需要检查的关键表
CRITICAL_TABLES = {
    "核心业务表": [
        "DT_EVENT_RAW",
        "MACHINES",
        "MACHINE_EVENTS",
        "ALARMS",
        "LOTS",
        "RECIPES",
    ],
    "AI相关表": [
        "AI_CONFIGS",
        "AI_PROVIDER_CONFIGS",
        "AI_USAGE_LOGS",
        "MACHINE_MODEL_CONFIGS",
    ],
    "系统配置表": [
        "USERS",
        "FLOORS",
        "AREAS",
        "MACHINE_TYPES",
    ],
}

# 需要完整导出数据的表
EXPORT_FULL_TABLES = [
    "MACHINES",
    "MACHINE_TYPES",
    "FLOORS",
    "AI_PROVIDER_CONFIGS",
    "AI_CONFIGS",
]

# 只需要导出样本的表（前10条）
EXPORT_SAMPLE_TABLES = [
    "DT_EVENT_RAW",
    "ALARMS",
]


def print_section(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def find_oracle_client():
    """自动查找Oracle Client目录"""
    # 尝试的候选路径
    candidates = [
        r"C:\app\client\c11463\product\19.0.0\client_1",
        r"C:\oracle",
        r"C:\oracle\instantclient_19_20",
        r"C:\oracle\instantclient_19_22",
        r"C:\oracle\product\19.0.0\client_1",
    ]

    # 从环境变量 ORACLE_CLIENT_DIR 读取
    env_client = os.environ.get("ORACLE_CLIENT_DIR")
    if env_client and os.path.exists(env_client):
        candidates.insert(0, env_client)

    # 搜索C:\oracle\instantclient_*
    for path in glob.glob(r"C:\oracle\instantclient_*"):
        candidates.insert(0, path)

    for path in candidates:
        if os.path.exists(path):
            # 检查是否有oci.dll
            oci_dll = os.path.join(path, "oci.dll")
            if os.path.exists(oci_dll):
                print(f"  [OK] 找到Oracle Client: {path}")
                return path
            # 检查是否有oci.dll在BIN目录
            oci_dll = os.path.join(path, "BIN", "oci.dll")
            if os.path.exists(oci_dll):
                print(f"  [OK] 找到Oracle Client: {path} (BIN/oci.dll)")
                return path

    print("  [WARN] 未找到Oracle Client目录，将尝试Thin模式")
    return None


def connect_oracle(config: Dict):
    """连接Oracle，自动尝试Thick/Thin模式"""
    import oracledb

    # 先尝试Thin模式（纯Python，不需要Oracle Client）
    try:
        dsn = f"{config['host']}:{config['port']}/{config['service']}"
        print(f"  尝试Thin模式连接 {dsn}...")
        conn = oracledb.connect(
            user=config["user"],
            password=config["password"],
            dsn=dsn,
        )
        print("  [OK] Thin模式连接成功")
        return conn, "thin"
    except oracledb.exceptions.DatabaseError as e:
        err_msg = str(e)
        # Thin模式失败可能是因为Oracle 10g/11g不支持Thin模式的部分功能
        # 尝试Thick模式
        print(f"  [INFO] Thin模式无法连接: {err_msg[:100]}")
        print("  尝试Thick模式...")

    # Thick模式需要Oracle Client
    client_dir = find_oracle_client()
    if client_dir:
        try:
            oracledb.init_oracle_client(lib_dir=client_dir)
            print(f"  [OK] 已初始化Oracle Client (Thick)")
        except Exception as e:
            print(f"  [WARN] Thick模式初始化失败: {e}")
            return None, None

        try:
            dsn = f"{config['host']}:{config['port']}/{config['service']}"
            conn = oracledb.connect(
                user=config["user"],
                password=config["password"],
                dsn=dsn,
            )
            print("  [OK] Thick模式连接成功")
            return conn, "thick"
        except Exception as e:
            print(f"  [ERROR] Thick模式连接失败: {e}")
            return None, None
    else:
        print("  [ERROR] 未找到Oracle Client，且Thin模式也失败")
        print("  请确认：")
        print("    1. Oracle 19c+ 客户端已安装")
        print("    2. 或者网络可连通10.30.8.119:1521")
        return None, None


def get_table_structure(conn, table_name: str) -> Dict:
    """获取表结构信息"""
    result = {"exists": False, "columns": [], "indexes": [], "row_count": 0, "sample_data": []}

    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME = :name",
                    {"name": table_name.upper()})
        if cur.fetchone()[0] == 0:
            return result

        result["exists"] = True

        # 列信息
        cur.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, DATA_PRECISION, DATA_SCALE, NULLABLE
            FROM USER_TAB_COLUMNS
            WHERE TABLE_NAME = :name
            ORDER BY COLUMN_ID
        """, {"name": table_name.upper()})
        for row in cur:
            result["columns"].append({
                "name": row[0],
                "type": row[1],
                "length": row[2],
                "precision": row[3],
                "scale": row[4],
                "nullable": row[5] == "Y",
            })

        # 索引信息
        cur.execute("""
            SELECT i.INDEX_NAME, ic.COLUMN_NAME, i.UNIQUENESS
            FROM USER_INDEXES i
            JOIN USER_IND_COLUMNS ic ON i.INDEX_NAME = ic.INDEX_NAME
            WHERE i.TABLE_NAME = :name
            ORDER BY i.INDEX_NAME, ic.COLUMN_POSITION
        """, {"name": table_name.upper()})
        for row in cur:
            result["indexes"].append({
                "index_name": row[0],
                "column_name": row[1],
                "unique": row[2] == "UNIQUE",
            })

        # 行数
        cur.execute(f'SELECT COUNT(*) FROM "{table_name}"')
        result["row_count"] = cur.fetchone()[0]

        # 样本数据
        if result["row_count"] > 0:
            cur.execute(f'SELECT * FROM "{table_name}" WHERE ROWNUM <= 3')
            columns = [desc[0] for desc in cur.description]
            for row in cur:
                row_dict = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    if hasattr(val, 'read'):  # CLOB
                        val = val.read()
                    elif hasattr(val, 'isoformat'):
                        val = val.isoformat()
                    row_dict[col] = val
                result["sample_data"].append(row_dict)

        cur.close()
    except Exception as e:
        result["error"] = str(e)

    return result


def export_table_data(conn, table_name: str, limit: int = None) -> List[Dict]:
    """导出表数据"""
    cur = conn.cursor()
    try:
        sql = f'SELECT * FROM "{table_name}"'
        if limit:
            sql += f' WHERE ROWNUM <= {limit}'
        cur.execute(sql)

        columns = [desc[0] for desc in cur.description]
        rows = []
        for row in cur:
            row_dict = {}
            for i, col in enumerate(columns):
                val = row[i]
                if hasattr(val, 'read'):
                    val = val.read()
                elif hasattr(val, 'isoformat'):
                    val = val.isoformat()
                row_dict[col] = val
            rows.append(row_dict)
        return rows
    except Exception as e:
        print(f"  [WARN] 导出 {table_name} 失败: {e}")
        return []
    finally:
        cur.close()


def diagnose_environment(config: Dict) -> Dict:
    """诊断量产Oracle环境"""
    print_section("诊断量产Oracle环境")
    print(f"目标: {config['host']}:{config['port']}/{config['service']}")
    print(f"用户: {config['user']}")

    result = {
        "host": config["host"],
        "port": config["port"],
        "service": config["service"],
        "user": config["user"],
        "connected": False,
        "version": None,
        "tables": {},
        "export_data": {},
    }

    conn, mode = connect_oracle(config)
    if not conn:
        return result

    result["connected"] = True
    result["connection_mode"] = mode

    try:
        # 版本
        cur = conn.cursor()
        cur.execute("SELECT BANNER FROM V$VERSION WHERE BANNER LIKE 'Oracle%'")
        row = cur.fetchone()
        if row:
            result["version"] = row[0]
        cur.close()
        print(f"\n[OK] 已连接: {result['version']} (模式: {mode})")

        # 检查关键表
        for category, tables in CRITICAL_TABLES.items():
            print(f"\n[{category}]")
            for table in tables:
                print(f"  - {table}...", end=" ")
                structure = get_table_structure(conn, table)
                result["tables"][table] = structure
                if structure["exists"]:
                    print(f"✅ ({structure['row_count']} 行)")
                else:
                    print("❌ 不存在")

        # 导出完整数据
        print(f"\n[导出数据]")
        for table in EXPORT_FULL_TABLES:
            if table in result["tables"] and result["tables"][table]["exists"]:
                print(f"  - {table} (完整导出)...", end=" ")
                data = export_table_data(conn, table)
                result["export_data"][table] = data
                print(f"✅ ({len(data)} 行)")

        # 导出样本数据
        for table in EXPORT_SAMPLE_TABLES:
            if table in result["tables"] and result["tables"][table]["exists"]:
                print(f"  - {table} (前10条)...", end=" ")
                data = export_table_data(conn, table, limit=10)
                result["export_data"][table] = data
                print(f"✅ ({len(data)} 行)")

    except Exception as e:
        result["error"] = str(e)
        print(f"\n[ERROR] 诊断失败: {e}")
    finally:
        conn.close()

    return result


def generate_report(result: Dict, output_dir: str):
    """生成报告文件"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSON完整报告
    json_file = os.path.join(output_dir, f"prod_oracle_report_{timestamp}.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[OK] JSON报告: {json_file}")

    # 可读性文本报告
    txt_file = os.path.join(output_dir, f"prod_oracle_report_{timestamp}.txt")
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("FabTwin 量产Oracle环境诊断报告\n")
        f.write(f"生成时间: {timestamp}\n")
        f.write(f"目标服务器: {result['host']}:{result['port']}/{result['service']}\n")
        f.write("=" * 70 + "\n\n")

        f.write("一、连接信息\n")
        f.write("-" * 70 + "\n")
        f.write(f"连接状态: {'成功' if result['connected'] else '失败'}\n")
        if result.get("connection_mode"):
            f.write(f"连接模式: {result['connection_mode']}\n")
        if result.get("version"):
            f.write(f"数据库版本: {result['version']}\n")
        f.write(f"用户: {result['user']}\n\n")

        f.write("二、表结构概览\n")
        f.write("-" * 70 + "\n")
        for category, tables in CRITICAL_TABLES.items():
            f.write(f"\n[{category}]\n")
            for table in tables:
                table_info = result["tables"].get(table, {})
                if table_info.get("exists"):
                    cols = [c["name"] for c in table_info["columns"]]
                    f.write(f"  {table}: ✅ {table_info['row_count']} 行\n")
                    f.write(f"    列: {', '.join(cols)}\n")
                else:
                    f.write(f"  {table}: ❌ 不存在\n")

        f.write("\n三、数据样本\n")
        f.write("-" * 70 + "\n")
        for table, data in result.get("export_data", {}).items():
            f.write(f"\n表: {table} ({len(data)} 行)\n")
            if data:
                f.write(f"  列: {list(data[0].keys())}\n")
                for i, row in enumerate(data[:3]):
                    f.write(f"  第{i+1}行:\n")
                    for key, val in row.items():
                        val_str = str(val)[:60] if val is not None else "NULL"
                        f.write(f"    {key}: {val_str}\n")

        f.write("\n" + "=" * 70 + "\n")
        f.write("请将上述JSON报告文件发送给开发人员，用于比对本地开发环境。\n")
        f.write("=" * 70 + "\n")

    print(f"[OK] 文本报告: {txt_file}")
    return json_file, txt_file


def main():
    print("=" * 70)
    print("  FabTwin 量产Oracle环境诊断工具")
    print("=" * 70)

    result = diagnose_environment(PROD_ORACLE)

    if not result["connected"]:
        print("\n[ERROR] 无法连接量产Oracle，请检查：")
        print("  1. 网络可连通 10.30.8.119:1521")
        print("  2. 用户名密码正确")
        print("  3. Oracle Client 19c+ 已安装（Thick模式）")
        print("  4. 或生产Oracle版本支持Thin模式（12c+）")
        sys.exit(1)

    output_dir = os.path.dirname(os.path.abspath(__file__))
    json_file, txt_file = generate_report(result, output_dir)

    print_section("完成")
    print(f"请将以下文件发送给开发人员：")
    print(f"  {json_file}")
    print(f"  （txt文件可直接查看，json文件用于程序比对）")


if __name__ == "__main__":
    main()
