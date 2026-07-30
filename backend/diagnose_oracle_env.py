#!/usr/bin/env python3
"""
Oracle 环境诊断和数据导出脚本

用途：
1. 对比本地Oracle和量产Oracle的结构差异
2. 导出关键表结构和数据样本
3. 生成环境差异报告

运行方式：
    cd backend
    python diagnose_oracle_env.py

输出：
    - oracle_env_report_YYYYMMDD_HHMMSS.json：完整诊断报告
    - oracle_env_report_YYYYMMDD_HHMMSS.txt：可读性报告
"""
import os
import sys
import json
import hashlib
from datetime import datetime
from typing import Dict, List, Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ================================================================
# 配置区：请根据实际环境修改
# ================================================================

# 本地Oracle配置（C:\oracle）
LOCAL_ORACLE = {
    "name": "本地Oracle",
    "host": "localhost",
    "port": 1521,
    "service": "ORCL",  # 或 ORCLPDB
    "user": "fabtwin",  # 请确认本地账户
    "password": "fabtwin",  # 请确认密码
    "dsn_type": "sid",  # sid 或 service_name
    "client_dir": r"C:\oracle",  # Oracle Client 目录
}

# 量产Oracle配置（从env.bat读取，或手动填写）
PROD_ORACLE = {
    "name": "量产Oracle",
    "host": "10.30.8.119",
    "port": 1521,
    "service": "APCDB",
    "user": "emuuser",  # 生产账户
    "password": "apcuser",  # 生产密码
    "dsn_type": "sid",
    "client_dir": r"C:\app\client\c11463\product\19.0.0\client_1",  # 生产Client路径
}

# 需要检查的关键表（按功能分类）
CRITICAL_TABLES = {
    "核心业务表": [
        "DT_EVENT_RAW",      # 事件原始记录
        "MACHINES",          # 机台主表
        "MACHINE_EVENTS",    # 机台事件
        "ALARMS",            # 告警记录
        "LOTS",              # Lot信息
        "RECIPES",           # 配方
    ],
    "AI相关表": [
        "AI_CONFIGS",                    # AI键值配置
        "AI_PROVIDER_CONFIGS",           # AI Provider配置
        "AI_USAGE_LOGS",                 # AI使用日志
        "MACHINE_MODEL_CONFIGS",         # 机台模型配置
    ],
    "系统配置表": [
        "USERS",              # 用户表
        "FLOORS",             # 楼层
        "AREAS",              # 区域
        "MACHINE_TYPES",      # 机台类型
    ],
}

# 需要导出数据样本的表（限制条数）
EXPORT_SAMPLE_TABLES = [
    "MACHINES",           # 机台列表（完整导出）
    "MACHINE_TYPES",      # 机台类型（完整导出）
    "FLOORS",             # 楼层信息（完整导出）
    "AI_PROVIDER_CONFIGS", # AI配置（完整导出）
]


def print_section(title):
    """打印分节标题"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def connect_oracle(config: Dict) -> Any:
    """连接Oracle数据库"""
    import oracledb

    # 设置Oracle Client目录
    if config.get("client_dir") and os.path.exists(config["client_dir"]):
        oracledb.init_oracle_client(lib_dir=config["client_dir"])

    # 构建DSN
    if config["dsn_type"] == "sid":
        dsn = f"{config['host']}:{config['port']}/{config['service']}"
        conn_params = {"user": config["user"], "password": config["password"], "dsn": dsn, "sid": config["service"]}
    else:
        dsn = f"{config['host']}:{config['port']}/{config['service']}"
        conn_params = {"user": config["user"], "password": config["password"], "dsn": dsn}

    try:
        conn = oracledb.connect(**conn_params)
        return conn
    except Exception as e:
        print(f"[ERROR] 连接失败: {e}")
        return None


def get_table_structure(conn, table_name: str) -> Dict:
    """获取表结构信息"""
    result = {
        "exists": False,
        "columns": [],
        "indexes": [],
        "row_count": 0,
        "sample_data": [],
    }

    try:
        cur = conn.cursor()

        # 1. 检查表是否存在
        cur.execute("""
            SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME = :name
        """, {"name": table_name.upper()})
        if cur.fetchone()[0] == 0:
            return result

        result["exists"] = True

        # 2. 获取列信息
        cur.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, NULLABLE, DATA_DEFAULT
            FROM USER_TAB_COLUMNS
            WHERE TABLE_NAME = :name
            ORDER BY COLUMN_ID
        """, {"name": table_name.upper()})
        for row in cur:
            result["columns"].append({
                "name": row[0],
                "type": row[1],
                "length": row[2],
                "nullable": row[3] == "Y",
                "default": row[4],
            })

        # 3. 获取索引信息
        cur.execute("""
            SELECT INDEX_NAME, COLUMN_NAME, UNIQUENESS
            FROM USER_IND_COLUMNS
            JOIN USER_INDEXES ON USER_IND_COLUMNS.INDEX_NAME = USER_INDEXES.INDEX_NAME
            WHERE TABLE_NAME = :name
            ORDER BY INDEX_NAME, COLUMN_POSITION
        """, {"name": table_name.upper()})
        for row in cur:
            result["indexes"].append({
                "index_name": row[0],
                "column_name": row[1],
                "unique": row[2] == "UNIQUE",
            })

        # 4. 获取行数（估算）
        cur.execute(f'SELECT COUNT(*) FROM "{table_name}"')
        result["row_count"] = cur.fetchone()[0]

        # 5. 获取样本数据（前5条）
        if result["row_count"] > 0:
            cur.execute(f'SELECT * FROM "{table_name}" WHERE ROWNUM <= 5')
            columns = [desc[0] for desc in cur.description]
            for row in cur:
                row_dict = {}
                for i, col in enumerate(columns):
                    val = row[i]
                    # 处理特殊类型
                    if hasattr(val, 'read'):  # CLOB
                        val = val.read()
                    elif hasattr(val, 'isoformat'):  # datetime
                        val = val.isoformat()
                    row_dict[col] = val
                result["sample_data"].append(row_dict)

        cur.close()
    except Exception as e:
        result["error"] = str(e)

    return result


def get_all_tables(conn) -> List[str]:
    """获取数据库中所有表名"""
    cur = conn.cursor()
    cur.execute("SELECT TABLE_NAME FROM USER_TABLES ORDER BY TABLE_NAME")
    tables = [row[0] for row in cur.fetchall()]
    cur.close()
    return tables


def export_table_data(conn, table_name: str, limit: int = None) -> List[Dict]:
    """导出表的完整数据"""
    cur = conn.cursor()
    try:
        if limit:
            cur.execute(f'SELECT * FROM "{table_name}" WHERE ROWNUM <= {limit}')
        else:
            cur.execute(f'SELECT * FROM "{table_name}"')

        columns = [desc[0] for desc in cur.description]
        rows = []
        for row in cur:
            row_dict = {}
            for i, col in enumerate(columns):
                val = row[i]
                if hasattr(val, 'read'):  # CLOB
                    val = val.read()
                elif hasattr(val, 'isoformat'):  # datetime
                    val = val.isoformat()
                row_dict[col] = val
            rows.append(row_dict)
        return rows
    except Exception as e:
        print(f"[WARN] 导出 {table_name} 失败: {e}")
        return []
    finally:
        cur.close()


def compare_structures(local: Dict, prod: Dict) -> Dict:
    """对比两个环境的表结构差异"""
    diff = {
        "table_exists_local": local.get("exists", False),
        "table_exists_prod": prod.get("exists", False),
        "row_count_diff": None,
        "column_diff": [],
        "index_diff": [],
    }

    if local.get("exists") and prod.get("exists"):
        # 对比行数
        diff["row_count_diff"] = {
            "local": local.get("row_count", 0),
            "prod": prod.get("row_count", 0),
            "diff": local.get("row_count", 0) - prod.get("row_count", 0),
        }

        # 对比列
        local_cols = {c["name"]: c for c in local.get("columns", [])}
        prod_cols = {c["name"]: c for c in prod.get("columns", [])}

        for col_name in set(local_cols.keys()) | set(prod_cols.keys()):
            if col_name not in local_cols:
                diff["column_diff"].append({"name": col_name, "status": "仅在生产环境"})
            elif col_name not in prod_cols:
                diff["column_diff"].append({"name": col_name, "status": "仅在本地环境"})
            else:
                l_col = local_cols[col_name]
                p_col = prod_cols[col_name]
                if l_col["type"] != p_col["type"] or l_col["length"] != p_col["length"]:
                    diff["column_diff"].append({
                        "name": col_name,
                        "status": "类型不匹配",
                        "local": f"{l_col['type']}({l_col['length']})",
                        "prod": f"{p_col['type']}({p_col['length']})",
                    })

    return diff


def diagnose_environment(config: Dict) -> Dict:
    """诊断单个Oracle环境"""
    print(f"\n正在诊断: {config['name']} ({config['host']}:{config['port']}/{config['service']})")

    result = {
        "name": config["name"],
        "host": config["host"],
        "port": config["port"],
        "service": config["service"],
        "user": config["user"],
        "connected": False,
        "version": None,
        "tables": {},
        "all_tables": [],
        "export_data": {},
    }

    conn = connect_oracle(config)
    if not conn:
        return result

    result["connected"] = True

    try:
        # 获取版本
        cur = conn.cursor()
        cur.execute("SELECT * FROM V$VERSION WHERE BANNER LIKE 'Oracle%'")
        row = cur.fetchone()
        if row:
            result["version"] = row[0]
        cur.close()
        print(f"  ✅ 已连接: {result['version']}")

        # 获取所有表
        result["all_tables"] = get_all_tables(conn)
        print(f"  ✅ 表总数: {len(result['all_tables'])}")

        # 检查关键表
        for category, tables in CRITICAL_TABLES.items():
            print(f"  检查 [{category}]...")
            for table in tables:
                print(f"    - {table}...", end=" ")
                structure = get_table_structure(conn, table)
                result["tables"][table] = structure
                if structure["exists"]:
                    print(f"✅ ({structure['row_count']} 行)")
                else:
                    print("❌ 不存在")

        # 导出样本数据
        print(f"  导出数据样本...")
        for table in EXPORT_SAMPLE_TABLES:
            if table in result["tables"] and result["tables"][table]["exists"]:
                print(f"    - {table}...", end=" ")
                data = export_table_data(conn, table)
                result["export_data"][table] = data
                print(f"✅ ({len(data)} 行)")

    except Exception as e:
        result["error"] = str(e)
        print(f"  ❌ 诊断失败: {e}")
    finally:
        conn.close()

    return result


def generate_report(local_result: Dict, prod_result: Dict, output_dir: str):
    """生成对比报告"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSON完整报告
    report = {
        "timestamp": timestamp,
        "local": local_result,
        "production": prod_result,
        "comparison": {},
    }

    # 对比关键表
    print_section("结构对比")
    for category, tables in CRITICAL_TABLES.items():
        print(f"\n[{category}]")
        for table in tables:
            local_table = local_result["tables"].get(table, {})
            prod_table = prod_result["tables"].get(table, {})

            diff = compare_structures(local_table, prod_table)
            report["comparison"][table] = diff

            status = "✅" if diff["table_exists_local"] and diff["table_exists_prod"] else "❌"
            print(f"  {status} {table}: ", end="")
            if diff["table_exists_local"] and diff["table_exists_prod"]:
                print(f"本地 {diff['row_count_diff']['local']} 行, 生产 {diff['row_count_diff']['prod']} 行")
                if diff["column_diff"]:
                    print(f"    ⚠️ 列差异: {len(diff['column_diff'])} 项")
                    for col_diff in diff["column_diff"][:5]:  # 只显示前5个
                        print(f"      - {col_diff['name']}: {col_diff['status']}")
            elif diff["table_exists_local"]:
                print("仅本地存在")
            elif diff["table_exists_prod"]:
                print("仅生产存在")
            else:
                print("两边都不存在")

    # 保存JSON报告
    json_file = os.path.join(output_dir, f"oracle_env_report_{timestamp}.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n✅ JSON报告已保存: {json_file}")

    # 生成可读性文本报告
    txt_file = os.path.join(output_dir, f"oracle_env_report_{timestamp}.txt")
    with open(txt_file, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("Oracle 环境对比报告\n")
        f.write(f"生成时间: {timestamp}\n")
        f.write("=" * 70 + "\n\n")

        f.write("一、连接信息\n")
        f.write("-" * 70 + "\n")
        f.write(f"本地环境: {local_result['name']}\n")
        f.write(f"  主机: {local_result['host']}:{local_result['port']}/{local_result['service']}\n")
        f.write(f"  用户: {local_result['user']}\n")
        f.write(f"  连接状态: {'成功' if local_result['connected'] else '失败'}\n")
        if local_result.get("version"):
            f.write(f"  版本: {local_result['version']}\n")
        f.write(f"  表总数: {len(local_result.get('all_tables', []))}\n\n")

        f.write(f"生产环境: {prod_result['name']}\n")
        f.write(f"  主机: {prod_result['host']}:{prod_result['port']}/{prod_result['service']}\n")
        f.write(f"  用户: {prod_result['user']}\n")
        f.write(f"  连接状态: {'成功' if prod_result['connected'] else '失败'}\n")
        if prod_result.get("version"):
            f.write(f"  版本: {prod_result['version']}\n")
        f.write(f"  表总数: {len(prod_result.get('all_tables', []))}\n\n")

        f.write("二、关键表对比\n")
        f.write("-" * 70 + "\n")
        for table, diff in report["comparison"].items():
            f.write(f"\n表: {table}\n")
            if diff["table_exists_local"] and diff["table_exists_prod"]:
                f.write(f"  状态: 两边都存在\n")
                f.write(f"  行数: 本地 {diff['row_count_diff']['local']}, ")
                f.write(f"生产 {diff['row_count_diff']['prod']}, ")
                f.write(f"差异 {diff['row_count_diff']['diff']}\n")
                if diff["column_diff"]:
                    f.write(f"  列差异:\n")
                    for col_diff in diff["column_diff"]:
                        f.write(f"    - {col_diff['name']}: {col_diff['status']}\n")
                        if "local" in col_diff:
                            f.write(f"      本地: {col_diff['local']}\n")
                        if "prod" in col_diff:
                            f.write(f"      生产: {col_diff['prod']}\n")
            elif diff["table_exists_local"]:
                f.write(f"  状态: 仅本地存在 ({diff['row_count_diff']['local']} 行)\n")
            elif diff["table_exists_prod"]:
                f.write(f"  状态: 仅生产存在\n")
            else:
                f.write(f"  状态: 两边都不存在\n")

        f.write("\n三、数据样本（本地环境）\n")
        f.write("-" * 70 + "\n")
        for table, data in local_result.get("export_data", {}).items():
            f.write(f"\n表: {table} ({len(data)} 行)\n")
            if data:
                f.write(f"  列: {list(data[0].keys())}\n")
                if len(data) > 0:
                    f.write(f"  首行样本:\n")
                    for key, val in data[0].items():
                        val_str = str(val)[:50] if val else "NULL"
                        f.write(f"    {key}: {val_str}\n")

    print(f"✅ 文本报告已保存: {txt_file}")

    # 生成数据迁移建议
    print_section("数据迁移建议")
    suggestions = []

    # 检查AI配置表
    if not local_result["tables"].get("AI_CONFIGS", {}).get("exists"):
        suggestions.append("创建 AI_CONFIGS 表（参考 create_ai_tables.sql）")
    if not local_result["tables"].get("AI_PROVIDER_CONFIGS", {}).get("exists"):
        suggestions.append("创建 AI_PROVIDER_CONFIGS 表")
    if not local_result["tables"].get("AI_USAGE_LOGS", {}).get("exists"):
        suggestions.append("创建 AI_USAGE_LOGS 表")

    # 检查数据量差异
    machines_local = local_result["tables"].get("MACHINES", {}).get("row_count", 0)
    machines_prod = prod_result["tables"].get("MACHINES", {}).get("row_count", 0)
    if machines_local < machines_prod:
        suggestions.append(f"从生产导入 MACHINES 数据（本地{machines_local}条，生产{machines_prod}条）")

    events_local = local_result["tables"].get("DT_EVENT_RAW", {}).get("row_count", 0)
    events_prod = prod_result["tables"].get("DT_EVENT_RAW", {}).get("row_count", 0)
    if events_local < events_prod:
        suggestions.append(f"从生产导入 DT_EVENT_RAW 历史数据（本地{events_local}条，生产{events_prod}条）")

    if suggestions:
        for i, sug in enumerate(suggestions, 1):
            print(f"  {i}. {sug}")
    else:
        print("  ✅ 本地环境与生产环境一致，无需迁移")

    return json_file, txt_file


def main():
    print("=" * 70)
    print("  Oracle 环境诊断工具")
    print("  用途：对比本地和生产环境，导出关键数据")
    print("=" * 70)

    # 诊断本地环境
    print_section("一、诊断本地Oracle环境")
    local_result = diagnose_environment(LOCAL_ORACLE)

    # 诊断生产环境
    print_section("二、诊断生产Oracle环境")
    prod_result = diagnose_environment(PROD_ORACLE)

    # 生成对比报告
    print_section("三、生成对比报告")
    output_dir = os.path.dirname(os.path.abspath(__file__))
    json_file, txt_file = generate_report(local_result, prod_result, output_dir)

    print_section("四、后续步骤")
    print("  1. 查看生成的报告文件：")
    print(f"     - {json_file}")
    print(f"     - {txt_file}")
    print("  2. 根据迁移建议更新本地环境")
    print("  3. 将报告发给开发人员进行review")
    print("\n  提示：如需修改连接参数，请编辑脚本顶部的 LOCAL_ORACLE 和 PROD_ORACLE 配置")


if __name__ == "__main__":
    main()