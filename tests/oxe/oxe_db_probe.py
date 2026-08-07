"""
OXE 集成 Step 0 · 量产 DB 资料采集脚本
============================================
运行方式:
  1. 把本文件放到能连生产 Oracle 的机器上
  2. 修改下方 ORACLE_* 配置为生产环境值(或设置环境变量)
  3. 执行: python oxe_db_probe.py
  4. 将生成的 oxe_db_snapshot_*.json 发给我
============================================
"""

import json
import os
import sys
from datetime import datetime

# ========== 数据库配置:改这里 ==========
ORACLE_USER = os.environ.get("ORACLE_USER", "emuuser")
ORACLE_PASSWORD = os.environ.get("ORACLE_PASSWORD", "apcuser")
ORACLE_DSN = os.environ.get("ORACLE_DSN", "10.30.8.119:1521/APCDB")
ORACLE_CLIENT_LIB_DIR = os.environ.get(
    "ORACLE_CLIENT_LIB_DIR",
    "E:\\app\\client\\c09583\\product\\19.0.0\\client_1\\bin",
)
# ========================================

# 需要探查的表名(如果你那边的表名不一样,请改这里)
TABLE_EVENT_RAW_CUR = os.environ.get("T_RAW_CUR", "DT_EVENT_RAW_CUR")
TABLE_EVENT_RAW = os.environ.get("T_RAW_HIS", "DT_EVENT_RAW")
TABLE_REALTIMELOT = os.environ.get("T_RTLOT", "DT_EVENT_REALTIMELOT")
TABLE_RTLOT_EVENT_RULE = os.environ.get("T_RTLOT_EV_RULE", "DT_RTLOT_EVENT_RULE")
TABLE_RTLOT_PORT_RULE = os.environ.get("T_RTLOT_PORT_RULE", "DT_RTLOT_TOOL_PORT_RULE")
# 平台 Machine 表名(可选,如果和平台 schema 不在一个DB可以跳过)
TABLE_FAB_MACHINE = os.environ.get("T_MACHINE", "FAB_MACHINE")

SNAPSHOT = {"probe_time_utc": datetime.utcnow().isoformat() + "Z"}


def oracle_probe(cursor):
    """主探查流程"""

    # ===== 1. 表是否存在 + 表结构 =====
    SNAPSHOT["tables"] = {}
    for tbl in [
        TABLE_EVENT_RAW_CUR,
        TABLE_EVENT_RAW,
        TABLE_REALTIMELOT,
        TABLE_RTLOT_EVENT_RULE,
        TABLE_RTLOT_PORT_RULE,
        TABLE_FAB_MACHINE,
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
            # 行数(近似,百万级以下表基本准)
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
            SELECT DISTINCT tool_id FROM (
                SELECT tool_id FROM {tbl}
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
                SELECT raw_id, tool_id, source_system, source_message_id,
                       received_ts_utc, event_ts_utc, parse_status, payload_json
                FROM (
                    SELECT * FROM {tbl}
                    WHERE tool_id = :1
                    ORDER BY received_ts_utc DESC NULLS LAST, raw_id DESC
                ) WHERE ROWNUM = 1
                """,
                [tid],
            )
            r = cursor.fetchone()
            if r:
                payload = r[7]
                if payload is not None and hasattr(payload, "read"):
                    payload = payload.read()
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

    # ===== 4. OXE 某台(取第一个)最近 50 条事件样例(用于验证 applyEvent 映射) =====
    SNAPSHOT["oxe_recent_events_sample"] = []
    first_tid = SNAPSHOT["oxe_tool_ids_in_raw"][0] if SNAPSHOT["oxe_tool_ids_in_raw"] else None
    if first_tid:
        try:
            cursor.execute(
                f"""
                SELECT raw_id, tool_id, received_ts_utc, event_ts_utc,
                       parse_status, payload_json
                FROM (
                    SELECT * FROM {tbl}
                    WHERE tool_id = :1 AND parse_status = 'PARSED'
                    ORDER BY received_ts_utc DESC NULLS LAST, raw_id DESC
                ) WHERE ROWNUM <= 50
                """,
                [first_tid],
            )
            for r in cursor.fetchall():
                payload = r[5]
                if payload is not None and hasattr(payload, "read"):
                    payload = payload.read()
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
                # payload 里提取关键字段便于人工核对
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

    # ===== 5. OXE 事件类型分布(最近1万条)——用于验证 EVENT_NAME 覆盖 =====
    SNAPSHOT["oxe_event_name_distribution"] = {}
    if first_tid:
        try:
            cursor.execute(
                f"""
                SELECT event_name, cnt FROM (
                    SELECT JSON_VALUE(payload_json, '$.event_name') AS event_name,
                           COUNT(*) AS cnt
                    FROM (
                        SELECT payload_json FROM {tbl}
                        WHERE tool_id = :1 AND parse_status = 'PARSED'
                        ORDER BY received_ts_utc DESC NULLS LAST, raw_id DESC
                    ) WHERE ROWNUM <= 10000
                    GROUP BY JSON_VALUE(payload_json, '$.event_name')
                    ORDER BY cnt DESC
                ) WHERE ROWNUM <= 50
                """,
                [first_tid],
            )
            SNAPSHOT["oxe_event_name_distribution"] = [
                {"event_name": r[0], "count": r[1]} for r in cursor.fetchall()
            ]
        except Exception as e:
            try:
                # 回退:如果 JSON_VALUE 不支持(Oracle 11g 之前),跳过
                SNAPSHOT["oxe_event_name_distribution_error"] = str(e)[:300]
            except Exception:
                pass

    # ===== 6. FAB_MACHINE 表里 OXE 机型的 machine_id 列表 =====
    SNAPSHOT["oxe_machines_in_fab"] = []
    try:
        cursor.execute(
            f"""
            SELECT machine_id, tool_id, machine_name, machine_type, line_id, status
            FROM (
                SELECT * FROM {TABLE_FAB_MACHINE}
                WHERE UPPER(machine_id) LIKE 'OXE%' OR UPPER(tool_id) LIKE 'OXE%'
                ORDER BY machine_id
            ) WHERE ROWNUM <= 100
            """
        )
        cols = [d[0] for d in cursor.description]
        for r in cursor.fetchall():
            SNAPSHOT["oxe_machines_in_fab"].append(dict(zip(cols, [
                str(v) if v is not None else None for v in r
            ])))
    except Exception as e:
        SNAPSHOT["oxe_machines_in_fab_error"] = str(e)[:300]


def main():
    try:
        import oracledb
    except ImportError:
        print("[错误] 需要安装 python-oracledb: pip install oracledb")
        sys.exit(1)

    # 初始化 thick 驱动(如果配置了)
    if ORACLE_CLIENT_LIB_DIR:
        try:
            oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_LIB_DIR)
            print(f"[OK] thick 驱动: {ORACLE_CLIENT_LIB_DIR}")
        except Exception as exc:
            print(f"[WARN] thick 驱动失败,退回 thin: {exc}")

    connection = None
    try:
        connection = oracledb.connect(
            user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=ORACLE_DSN
        )
        print(f"[OK] 已连接 {ORACLE_DSN} (用户={ORACLE_USER})")
        with connection.cursor() as cursor:
            oracle_probe(cursor)
    finally:
        if connection is not None:
            connection.close()

    out_file = f"oxe_db_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(SNAPSHOT, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[完成] 快照已写入: {out_file}")
    print("请把这个 JSON 文件发给你的开发同学。")


if __name__ == "__main__":
    main()
