"""
OXE 集成 Step 0 · 量产 DB 资料采集脚本
============================================
用途: 为 OXE 机台接入平台采集 DB 结构/样例数据(只读,不改DB)
运行方式: 由同目录的 run_oxe_db_probe.bat 自动调用
依赖: python-oracledb (pip install oracledb)
环境变量: 由 ../../deploy/env.bat 统一配置(ORACLE_HOST/PORT/SERVICE/USER/PASSWORD/DSN_TYPE/CLIENT_DIR)
============================================
"""

import json
import os
import sys
from datetime import datetime

# ============ 读取 env.bat 配置的环境变量 ============
ORACLE_USER = os.environ.get("ORACLE_USER", "emuuser")
ORACLE_PASSWORD = os.environ.get("ORACLE_PASSWORD", "apcuser")
ORACLE_HOST = os.environ.get("ORACLE_HOST", "10.30.8.119")
ORACLE_PORT = os.environ.get("ORACLE_PORT", "1521")
ORACLE_SERVICE = os.environ.get("ORACLE_SERVICE", "APCDB")
ORACLE_DSN_TYPE = os.environ.get("ORACLE_DSN_TYPE", "sid")  # sid 或 service_name
ORACLE_CLIENT_DIR = os.environ.get("ORACLE_CLIENT_DIR", "")

# ============ 需要探查的表名(可改) ============
TABLE_EVENT_RAW_CUR = os.environ.get("T_RAW_CUR", "DT_EVENT_RAW_CUR")
TABLE_EVENT_RAW = os.environ.get("T_RAW_HIS", "DT_EVENT_RAW")
TABLE_REALTIMELOT = os.environ.get("T_RTLOT", "DT_EVENT_REALTIMELOT")
TABLE_RTLOT_EVENT_RULE = os.environ.get("T_RTLOT_EV_RULE", "DT_RTLOT_EVENT_RULE")
TABLE_RTLOT_PORT_RULE = os.environ.get("T_RTLOT_PORT_RULE", "DT_RTLOT_TOOL_PORT_RULE")
TABLE_MACHINES = os.environ.get("T_MACHINES", "MACHINES")
TABLE_MACHINE_TOOL_MAPPINGS = os.environ.get("T_MAPPINGS", "MACHINE_TOOL_MAPPINGS")

SNAPSHOT = {
    "probe_time_utc": datetime.utcnow().isoformat() + "Z",
    "oracle_config": {
        "host": ORACLE_HOST,
        "port": ORACLE_PORT,
        "service": ORACLE_SERVICE,
        "user": ORACLE_USER,
        "dsn_type": ORACLE_DSN_TYPE,
        "client_dir": ORACLE_CLIENT_DIR,
    },
}


def _find_lib_dir(client_dir):
    """与 backend/database.py 一致: 返回直接包含 oci.dll 的目录。"""
    if not client_dir:
        return ''
    bin_dir = os.path.join(client_dir, 'bin')
    if os.path.exists(os.path.join(bin_dir, 'oci.dll')):
        return bin_dir
    if os.path.exists(os.path.join(client_dir, 'oci.dll')):
        return client_dir
    return ''


def _init_thick_driver():
    """与 backend/database.py 一致的 Thick 模式初始化逻辑。"""
    if not ORACLE_CLIENT_DIR:
        print("[INFO] 未设置 ORACLE_CLIENT_DIR, 使用 Thin 模式 (仅支持 Oracle 12.1+)")
        return
    lib_dir = _find_lib_dir(ORACLE_CLIENT_DIR)
    if not lib_dir:
        print(f"[WARN] ORACLE_CLIENT_DIR={ORACLE_CLIENT_DIR} 下未找到 oci.dll, 退回 Thin 模式")
        return
    try:
        import oracledb
        oracledb.init_oracle_client(lib_dir=lib_dir)
        print(f"[OK] Thick 模式已启用 (lib_dir={lib_dir})")
    except Exception as exc:
        if "DPI-1072" in str(exc):
            print("[OK] Thick 模式已启用 (之前已初始化)")
        else:
            print(f"[WARN] Thick 模式初始化失败: {exc}")


def _build_dsn(oracledb_module):
    """与 backend/database.py 一致: 用 makedsn 生成 DSN。"""
    if ORACLE_DSN_TYPE.lower() == "sid":
        return oracledb_module.makedsn(ORACLE_HOST, int(ORACLE_PORT), sid=ORACLE_SERVICE)
    return oracledb_module.makedsn(ORACLE_HOST, int(ORACLE_PORT), service_name=ORACLE_SERVICE)


def _read_lob(value):
    if value is None:
        return None
    if hasattr(value, "read"):
        return value.read()
    return value


def oracle_probe(cursor):
    """主探查流程(全部只读 SELECT)"""

    # ===== 1. 表是否存在 + 表结构 + 行数 =====
    SNAPSHOT["tables"] = {}
    for tbl in [
        TABLE_EVENT_RAW_CUR,
        TABLE_EVENT_RAW,
        TABLE_REALTIMELOT,
        TABLE_RTLOT_EVENT_RULE,
        TABLE_RTLOT_PORT_RULE,
        TABLE_MACHINES,
        TABLE_MACHINE_TOOL_MAPPINGS,
    ]:
        info = {"exists": False, "count": None, "columns": []}
        try:
            cursor.execute(
                "SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, NULLABLE "
                "FROM USER_TAB_COLUMNS WHERE TABLE_NAME = UPPER(:1) "
                "ORDER BY COLUMN_ID",
                [tbl],
            )
            cols = cursor.fetchall()
            if cols:
                info["exists"] = True
                info["columns"] = [
                    {"name": r[0], "type": r[1], "len": r[2], "nullable": r[3]}
                    for r in cols
                ]
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
                info["count"] = cursor.fetchone()[0]
            except Exception as e:
                info["count_error"] = str(e)[:200]
        except Exception as e:
            info["error"] = str(e)[:300]
        SNAPSHOT["tables"][tbl] = info

    # ===== 2. DT_EVENT_RAW 里 OXE 机台的 tool_id 去重列表(前50) =====
    tbl = TABLE_EVENT_RAW
    SNAPSHOT["oxe_tool_ids_in_raw"] = []
    try:
        cursor.execute(
            f"""
            SELECT * FROM (
                SELECT DISTINCT tool_id FROM {tbl}
                WHERE UPPER(tool_id) LIKE 'OXE%'
                ORDER BY tool_id
            ) WHERE ROWNUM <= 50
            """
        )
        SNAPSHOT["oxe_tool_ids_in_raw"] = [r[0] for r in cursor.fetchall() if r[0]]
    except Exception as e:
        SNAPSHOT["oxe_tool_ids_in_raw_error"] = str(e)[:300]

    # ===== 3. 每个 OXE tool_id 的最近一条记录样例 =====
    SNAPSHOT["oxe_latest_samples"] = {}
    for tid in SNAPSHOT["oxe_tool_ids_in_raw"]:
        try:
            cursor.execute(
                f"""
                SELECT * FROM (
                    SELECT raw_id, tool_id, source_system, source_message_id,
                           received_ts_utc, event_ts_utc, parse_status, payload_json
                    FROM {tbl}
                    WHERE tool_id = :1
                    ORDER BY received_ts_utc DESC NULLS LAST, raw_id DESC
                ) WHERE ROWNUM = 1
                """,
                [tid],
            )
            r = cursor.fetchone()
            if r:
                payload = _read_lob(r[7])
                parsed_payload = None
                if isinstance(payload, str):
                    try:
                        parsed_payload = json.loads(payload)
                    except Exception:
                        parsed_payload = payload[:500]
                SNAPSHOT["oxe_latest_samples"][tid] = {
                    "raw_id": r[0],
                    "tool_id": r[1],
                    "source_system": r[2],
                    "source_message_id": r[3],
                    "received_ts_utc": str(r[4]) if r[4] else None,
                    "event_ts_utc": str(r[5]) if r[5] else None,
                    "parse_status": r[6],
                    "payload": parsed_payload,
                }
        except Exception as e:
            SNAPSHOT["oxe_latest_samples"][tid] = {"error": str(e)[:300]}

    # ===== 4. OXE 某台(取第一个)最近 50 条事件样例 =====
    SNAPSHOT["oxe_recent_events_sample"] = []
    first_tid = SNAPSHOT["oxe_tool_ids_in_raw"][0] if SNAPSHOT["oxe_tool_ids_in_raw"] else None
    if first_tid:
        try:
            cursor.execute(
                f"""
                SELECT * FROM (
                    SELECT raw_id, tool_id, received_ts_utc, event_ts_utc,
                           parse_status, payload_json
                    FROM {tbl}
                    WHERE tool_id = :1 AND parse_status = 'PARSED'
                    ORDER BY received_ts_utc DESC NULLS LAST, raw_id DESC
                ) WHERE ROWNUM <= 50
                """,
                [first_tid],
            )
            for r in cursor.fetchall():
                payload = _read_lob(r[5])
                try:
                    parsed = json.loads(payload) if isinstance(payload, str) else payload
                except Exception:
                    parsed = {"_raw": str(payload)[:300]}
                ev = {
                    "raw_id": r[0],
                    "tool_id": r[1],
                    "received_ts_utc": str(r[2]) if r[2] else None,
                    "event_ts_utc": str(r[3]) if r[3] else None,
                    "parse_status": r[4],
                    "payload": parsed,
                }
                if isinstance(parsed, dict):
                    for k in [
                        "event_type", "event_name", "lot_id", "port_id",
                        "chamber_id", "smif_id", "wafer_id", "batch_id",
                        "cassette_id", "alarm_text",
                    ]:
                        ev[k] = parsed.get(k)
                SNAPSHOT["oxe_recent_events_sample"].append(ev)
        except Exception as e:
            SNAPSHOT["oxe_recent_events_sample_error"] = str(e)[:300]
        SNAPSHOT["oxe_sample_tool_id"] = first_tid

    # ===== 5. OXE 事件类型分布(最近1万条, Python解析CLOB, 兼容Oracle 11g) =====
    SNAPSHOT["oxe_event_name_distribution"] = []
    if first_tid:
        try:
            cursor.execute(
                f"""
                SELECT * FROM (
                    SELECT payload_json FROM {tbl}
                    WHERE tool_id = :1 AND parse_status = 'PARSED'
                    ORDER BY received_ts_utc DESC NULLS LAST, raw_id DESC
                ) WHERE ROWNUM <= 10000
                """,
                [first_tid],
            )
            from collections import Counter
            event_counter = Counter()
            for row in cursor.fetchall():
                payload = _read_lob(row[0])
                if isinstance(payload, str):
                    try:
                        parsed = json.loads(payload)
                        if isinstance(parsed, dict):
                            en = parsed.get("event_name") or parsed.get("event_type") or "UNKNOWN"
                            event_counter[en] += 1
                    except Exception:
                        pass
            SNAPSHOT["oxe_event_name_distribution"] = [
                {"event_name": k, "count": v}
                for k, v in event_counter.most_common(50)
            ]
        except Exception as e:
            SNAPSHOT["oxe_event_name_distribution_error"] = str(e)[:300]

    # ===== 6. 平台机台表: machines + machine_tool_mappings =====
    SNAPSHOT["oxe_machines_in_platform"] = []
    # 6a. machines 表里 OXE 机台
    try:
        cursor.execute(
            f"""
            SELECT * FROM (
                SELECT id, name, model, line, floor, chamber_count, process_type, state
                FROM {TABLE_MACHINES}
                WHERE UPPER(id) LIKE 'OXE%' OR UPPER(name) LIKE '%OXE%'
                ORDER BY id
            ) WHERE ROWNUM <= 100
            """
        )
        cols = [d[0] for d in cursor.description]
        for r in cursor.fetchall():
            SNAPSHOT["oxe_machines_in_platform"].append(dict(zip(cols, [
                str(v) if v is not None else None for v in r
            ])))
    except Exception as e:
        SNAPSHOT["oxe_machines_in_platform_error"] = str(e)[:300]

    # 6b. machine_tool_mappings 表里 OXE 相关映射
    SNAPSHOT["oxe_tool_mappings"] = []
    try:
        cursor.execute(
            f"""
            SELECT * FROM (
                SELECT machine_id, tool_id, description, is_primary
                FROM {TABLE_MACHINE_TOOL_MAPPINGS}
                WHERE UPPER(machine_id) LIKE 'OXE%' OR UPPER(tool_id) LIKE 'OXE%'
                ORDER BY machine_id
            ) WHERE ROWNUM <= 100
            """
        )
        cols = [d[0] for d in cursor.description]
        for r in cursor.fetchall():
            SNAPSHOT["oxe_tool_mappings"].append(dict(zip(cols, [
                str(v) if v is not None else None for v in r
            ])))
    except Exception as e:
        SNAPSHOT["oxe_tool_mappings_error"] = str(e)[:300]


def main():
    try:
        import oracledb
    except ImportError:
        print("[ERROR] 需要安装 python-oracledb: pip install oracledb")
        sys.exit(1)

    _init_thick_driver()

    dsn = _build_dsn(oracledb)
    print(f"[INFO] 连接 Oracle: {ORACLE_USER}@{ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE} (dsn_type={ORACLE_DSN_TYPE})")

    connection = None
    try:
        connection = oracledb.connect(
            user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=dsn
        )
        print(f"[OK] 已连接数据库")
        with connection.cursor() as cursor:
            oracle_probe(cursor)
    finally:
        if connection is not None:
            connection.close()

    out_file = f"oxe_db_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(SNAPSHOT, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[DONE] 快照已写入: {out_file}")
    print("请把这个 JSON 文件发给我。")


if __name__ == "__main__":
    main()
