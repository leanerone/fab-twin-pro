import hashlib
import json
import os
import threading
from datetime import datetime, timedelta, timezone

try:
    import oracledb
except ImportError:
    oracledb = None

SOURCE_SYSTEM = "RV"
ORACLE_USER = os.environ.get("ORACLE_USER", "emuuser")
ORACLE_PASSWORD = os.environ.get("ORACLE_PASSWORD", "apcuser")
ORACLE_DSN = os.environ.get("ORACLE_DSN", "10.30.8.119:1521/APCDB")
ORACLE_RAW_TABLE = os.environ.get("ORACLE_RAW_TABLE", "DT_EVENT_RAW_CUR")
ORACLE_RAW_TABLE_HIS = os.environ.get("ORACLE_RAW_TABLE_HIS", "DT_EVENT_RAW")
ORACLE_REALTIMELOT_TABLE = os.environ.get(
    "ORACLE_REALTIMELOT_TABLE", "DT_EVENT_REALTIMELOT")
ORACLE_RTLOT_EVENT_RULE_TABLE = os.environ.get(
    "ORACLE_RTLOT_EVENT_RULE_TABLE", "DT_RTLOT_EVENT_RULE")
ORACLE_RTLOT_PORT_RULE_TABLE = os.environ.get(
    "ORACLE_RTLOT_PORT_RULE_TABLE",
    "DT_RTLOT_TOOL_PORT_RULE")
ORACLE_CLIENT_LIB_DIR = os.environ.get(
    "ORACLE_CLIENT_LIB_DIR",
    "E:\\app\\client\\c09583\\product\\19.0.0\\client_1\\bin",
)
ORACLE_CONFIG_DIR = os.environ.get(
    "ORACLE_CONFIG_DIR", os.environ.get(
        "TNS_ADMIN", ""))

BEIJING_TZ = timezone(timedelta(hours=8))

oracle_pool = None
oracle_pool_lock = threading.Lock()
oracle_pool_status = "uninitialized"
oracle_client_initialized = False

DEFAULT_RTLOT_EVENT_ACTIONS = {
    "POD_PLACED": "OPEN",
    "BATCH_INFO_FROM_ECUI": "UPDATE",
    "WAFER_MAPPING": "UPDATE",
    "POD_REMOVED": "CLEAR",
}

RTLOT_MODE_SINGLE = "SINGLE_LOT_PER_PORT"
RTLOT_MODE_MULTI = "MULTI_LOT_PER_PORT"


def utc_now_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def beijing_now_naive():
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def strip_outer_quotes(value):
    if value is None:
        return None
    normalized = str(value).strip()
    quote_pairs = {'"': '"', "'": "'", "\u201c": "\u201d"}
    if len(
            normalized) >= 2 and normalized[0] in quote_pairs and normalized[-1] == quote_pairs[normalized[0]]:
        normalized = normalized[1:-1].strip()
    return normalized or None


def normalize_nullable_text(value):
    normalized = strip_outer_quotes(value)
    if normalized is None:
        return None
    upper_value = normalized.upper()
    if upper_value in {"NULL", "NIL", "NONE", "N/A"}:
        return None
    return normalized


def normalize_source_message_id(value):
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    normalized = strip_outer_quotes(normalized) or ""
    normalized = normalized.lstrip(
        "\"'\u201c\u201d").rstrip("\"'\u201c\u201d").strip()
    return normalized or None


def format_oracle_error(exc):
    message = str(exc).strip()
    full_code = getattr(exc, "full_code", None)
    if full_code:
        return f"{full_code}: {message}"
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return f"ORA-{code:05d}: {message}"
    return message


def parse_datetime_to_utc_naive(value):
    if not value:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def oracle_is_configured():
    return bool(ORACLE_USER and ORACLE_PASSWORD and ORACLE_DSN)


def init_oracle_driver():
    global oracle_client_initialized
    if oracledb is None:
        return False
    if oracle_client_initialized:
        return True
    if ORACLE_CLIENT_LIB_DIR:
        init_kwargs = {"lib_dir": ORACLE_CLIENT_LIB_DIR}
        if ORACLE_CONFIG_DIR:
            init_kwargs["config_dir"] = ORACLE_CONFIG_DIR
        try:
            oracledb.init_oracle_client(**init_kwargs)
            oracle_client_initialized = True
            print(
                f"[Oracle] 已启用 thick mode，Oracle Client: {ORACLE_CLIENT_LIB_DIR}")
            return True
        except Exception as exc:
            print(f"[Oracle] 初始化 thick mode 失败: {exc}")
            return False
    oracle_client_initialized = True
    return True


def get_oracle_pool():
    global oracle_pool, oracle_pool_status
    if oracle_pool is not None:
        return oracle_pool
    if oracle_pool_status == "disabled":
        return None
    if oracledb is None:
        print("[Oracle] 未安装 Python 包 oracledb，跳过历史入库。")
        oracle_pool_status = "disabled"
        return None
    if not oracle_is_configured():
        print("[Oracle] 未配置 ORACLE_USER / ORACLE_PASSWORD / ORACLE_DSN，跳过历史入库。")
        oracle_pool_status = "disabled"
        return None
    if not init_oracle_driver():
        oracle_pool_status = "disabled"
        return None
    with oracle_pool_lock:
        if oracle_pool is not None:
            return oracle_pool
        try:
            oracle_pool = oracledb.create_pool(
                user=ORACLE_USER,
                password=ORACLE_PASSWORD,
                dsn=ORACLE_DSN,
                min=1,
                max=4,
                increment=1,
                getmode=oracledb.POOL_GETMODE_WAIT,
            )
            oracle_pool_status = "ready"
            mode = "thick" if ORACLE_CLIENT_LIB_DIR else "thin"
            print(f"[Oracle] 连接池已建立，模式: {mode}，目标表: {ORACLE_RAW_TABLE}")
        except Exception as exc:
            message = str(exc)
            oracle_pool_status = "disabled"
            if "DPY-3010" in message:
                print(
                    "[Oracle] 当前数据库版本过老，python-oracledb thin mode 不支持。请安装 Oracle Instant Client 并设置 ORACLE_CLIENT_LIB_DIR 后重试。")
            print(f"[Oracle] 建立连接池失败，已禁用历史入库: {exc}")
            return None
    return oracle_pool


def build_source_message_id(raw_line, parsed_fields):
    msg_id = normalize_source_message_id(
        parsed_fields.get("msg_id")
        or parsed_fields.get("message_id")
        or parsed_fields.get("source_message_id")
    )
    if msg_id:
        return msg_id[:128]
    digest = hashlib.sha1(
        raw_line.encode(
            "utf-8",
            errors="replace")).hexdigest().upper()
    return f"RV-{digest[:32]}"


def build_dedup_identity(parsed_fields, raw_line):
    tool_id = normalize_source_message_id(
        parsed_fields.get("tool_id")) or "UNKNOWN_EQP"
    msg_id = normalize_source_message_id(
        parsed_fields.get("msg_id")
        or parsed_fields.get("message_id")
        or parsed_fields.get("source_message_id")
    )
    if msg_id:
        return tool_id, msg_id, f"{tool_id}::{msg_id}"
    digest = hashlib.sha1(
        raw_line.encode(
            "utf-8",
            errors="replace")).hexdigest().upper()
    fallback_message_id = f"RV-{digest[:32]}"
    return tool_id, fallback_message_id, f"{tool_id}::{fallback_message_id}"


def read_lob_text(value):
    if value is None:
        return None
    if hasattr(value, "read"):
        return value.read()
    return value


def is_oracle_table_missing(exc):
    message = str(exc)
    return "ORA-00942" in message or "table or view does not exist" in message.lower()


def is_oracle_column_missing(exc):
    message = str(exc)
    return "ORA-00904" in message or "invalid identifier" in message.lower()


def resolve_rtlot_action(cursor, tool_id, event_name):
    event_name = normalize_nullable_text(event_name)
    if not event_name:
        return "IGNORE"
    query_params = {
        "tool_id": tool_id,
        "global_tool": "*",
        "event_name": event_name,
    }
    cursor.execute(
        f"""
        SELECT action_type FROM (
            SELECT action_type, priority_no
            FROM {ORACLE_RTLOT_EVENT_RULE_TABLE}
            WHERE enabled_flag = 'Y'
              AND event_name = :event_name
              AND tool_id IN (:tool_id, :global_tool)
            ORDER BY CASE WHEN tool_id = :tool_id THEN 0 ELSE 1 END, priority_no ASC, rule_id ASC
        ) WHERE ROWNUM = 1
        """,
        query_params,
    )
    row = cursor.fetchone()
    if row and row[0]:
        return str(row[0]).strip().upper()
    return DEFAULT_RTLOT_EVENT_ACTIONS.get(event_name, "IGNORE")


def resolve_rtlot_mode(cursor, tool_id, port_id):
    query_params = {
        "tool_id": tool_id,
        "port_id": port_id,
        "global_tool": "*",
    }
    cursor.execute(
        f"""
        SELECT lot_key_mode FROM (
            SELECT lot_key_mode
            FROM {ORACLE_RTLOT_PORT_RULE_TABLE}
            WHERE enabled_flag = 'Y'
              AND tool_id IN (:tool_id, :global_tool)
              AND port_id = :port_id
            ORDER BY CASE WHEN tool_id = :tool_id THEN 0 ELSE 1 END
        ) WHERE ROWNUM = 1
        """,
        query_params,
    )
    row = cursor.fetchone()
    if row and row[0]:
        mode = str(row[0]).strip().upper()
        if mode in {RTLOT_MODE_SINGLE, RTLOT_MODE_MULTI}:
            return mode
    return RTLOT_MODE_SINGLE


def build_rtlot_business_key(
        mode,
        tool_id,
        port_id,
        lot_id,
        batch_id,
        cassette_id,
        smif_id):
    if mode == RTLOT_MODE_SINGLE:
        return f"SINGLE::{tool_id}::{port_id}"
    if lot_id and batch_id:
        return f"MULTI::{tool_id}::{port_id}::{batch_id}::{lot_id}"
    if lot_id and cassette_id:
        return f"MULTI::{tool_id}::{port_id}::CST::{cassette_id}::{lot_id}"
    if lot_id and smif_id:
        return f"MULTI::{tool_id}::{port_id}::SMIF::{smif_id}::{lot_id}"
    return None


def persist_realtime_lot(cursor, parsed_fields, source_message_id):
    tool_id = normalize_nullable_text(
        parsed_fields.get("tool_id")) or "UNKNOWN_EQP"
    event_name = normalize_nullable_text(parsed_fields.get("event_name"))
    if not event_name:
        return
    action_type = resolve_rtlot_action(cursor, tool_id, event_name)
    if action_type == "IGNORE":
        return
    port_id = normalize_nullable_text(parsed_fields.get("port_id"))
    if not port_id:
        print(
            f"[RTLOT] SKIP_AND_WARN: event={event_name} tool_id={tool_id} 缺少 port_id，跳过实时账务更新。")
        return
    lot_id = normalize_nullable_text(parsed_fields.get("lot_id"))
    batch_id = normalize_nullable_text(parsed_fields.get("batch_id"))
    smif_id = normalize_nullable_text(parsed_fields.get("smif_id"))
    cassette_id = normalize_nullable_text(
        parsed_fields.get("cassette_id") or parsed_fields.get("pod_id"))
    wafer_id = normalize_nullable_text(parsed_fields.get("wafer_id"))
    wafer_mapping = normalize_nullable_text(
        parsed_fields.get("wafer_mapping")
        or parsed_fields.get("wafer_map")
        or parsed_fields.get("WAFERMAP")
        or parsed_fields.get("mapping_data")
        or parsed_fields.get("event_value")
    )
    event_ts = parse_datetime_to_utc_naive(
        parsed_fields.get("event_ts_utc")) or utc_now_naive()
    source_system = normalize_nullable_text(
        parsed_fields.get("source_system")) or SOURCE_SYSTEM

    mode = RTLOT_MODE_SINGLE
    try:
        mode = resolve_rtlot_mode(cursor, tool_id, port_id)
    except Exception as mode_exc:
        if is_oracle_table_missing(
                mode_exc) or is_oracle_column_missing(mode_exc):
            print(
                f"[RTLOT] 端口规则不可用，回退为 {RTLOT_MODE_SINGLE}: {format_oracle_error(mode_exc)}")
            mode = RTLOT_MODE_SINGLE
        else:
            raise

    lot_biz_key = build_rtlot_business_key(
        mode, tool_id, port_id, lot_id, batch_id, cassette_id, smif_id)
    if not lot_biz_key:
        print(
            f"[RTLOT] SKIP_AND_WARN: event={event_name} tool_id={tool_id} port_id={port_id} "
            f"在 {mode} 模式下缺少 lot 业务键字段，跳过实时账务更新。")
        return

    if action_type == "OPEN":
        if mode == RTLOT_MODE_SINGLE:
            cursor.execute(
                f"DELETE FROM {ORACLE_REALTIMELOT_TABLE} WHERE tool_id = :tool_id AND port_id = :port_id", {
                    "tool_id": tool_id, "port_id": port_id}, )
        else:
            cursor.execute(
                f"""
                DELETE FROM {ORACLE_REALTIMELOT_TABLE}
                WHERE tool_id = :tool_id AND port_id = :port_id AND lot_biz_key = :lot_biz_key
                """, {"tool_id": tool_id, "port_id": port_id, "lot_biz_key": lot_biz_key}, )
        cursor.execute(
            f"""
            INSERT INTO {ORACLE_REALTIMELOT_TABLE} (
                tool_id, port_id, lot_key_mode, lot_biz_key, lot_id, batch_id,
                cassette_id, smif_id, wafer_mapping, wafer_id,
                last_event_name, last_event_ts_utc, start_ts_utc, updated_ts_utc,
                source_system, source_message_id, active_flag
            ) VALUES (
                :tool_id, :port_id, :lot_key_mode, :lot_biz_key, :lot_id, :batch_id,
                :cassette_id, :smif_id, :wafer_mapping, :wafer_id,
                :last_event_name, :last_event_ts_utc, :start_ts_utc, :updated_ts_utc,
                :source_system, :source_message_id, 'Y'
            )
            """,
            {
                "tool_id": tool_id,
                "port_id": port_id,
                "lot_key_mode": mode,
                "lot_biz_key": lot_biz_key,
                "lot_id": lot_id,
                "batch_id": batch_id,
                "cassette_id": cassette_id,
                "smif_id": smif_id,
                "wafer_mapping": wafer_mapping,
                "wafer_id": wafer_id,
                "last_event_name": event_name,
                "last_event_ts_utc": event_ts,
                "start_ts_utc": event_ts,
                "updated_ts_utc": utc_now_naive(),
                "source_system": source_system,
                "source_message_id": source_message_id,
            },
        )
        return

    if action_type == "UPDATE":
        cursor.execute(
            f"""
            UPDATE {ORACLE_REALTIMELOT_TABLE}
            SET lot_key_mode = :lot_key_mode,
                lot_id = COALESCE(:lot_id, lot_id),
                batch_id = COALESCE(:batch_id, batch_id),
                cassette_id = COALESCE(:cassette_id, cassette_id),
                smif_id = COALESCE(:smif_id, smif_id),
                wafer_mapping = COALESCE(:wafer_mapping, wafer_mapping),
                wafer_id = COALESCE(:wafer_id, wafer_id),
                last_event_name = :last_event_name,
                last_event_ts_utc = :last_event_ts_utc,
                updated_ts_utc = :updated_ts_utc,
                source_system = :source_system,
                source_message_id = :source_message_id,
                active_flag = 'Y'
            WHERE tool_id = :tool_id AND port_id = :port_id AND lot_biz_key = :lot_biz_key
            """,
            {
                "tool_id": tool_id,
                "port_id": port_id,
                "lot_key_mode": mode,
                "lot_biz_key": lot_biz_key,
                "lot_id": lot_id,
                "batch_id": batch_id,
                "cassette_id": cassette_id,
                "smif_id": smif_id,
                "wafer_mapping": wafer_mapping,
                "wafer_id": wafer_id,
                "last_event_name": event_name,
                "last_event_ts_utc": event_ts,
                "updated_ts_utc": utc_now_naive(),
                "source_system": source_system,
                "source_message_id": source_message_id,
            },
        )
        if cursor.rowcount == 0:
            print(
                f"[RTLOT] UPDATE 未命中: tool_id={tool_id} port_id={port_id} "
                f"lot_biz_key={lot_biz_key} event={event_name}"
            )
        return

    if action_type == "CLEAR":
        cursor.execute(
            f"""
            UPDATE {ORACLE_REALTIMELOT_TABLE}
            SET active_flag = 'N',
                last_event_name = :last_event_name,
                last_event_ts_utc = :last_event_ts_utc,
                updated_ts_utc = :updated_ts_utc,
                source_system = :source_system,
                source_message_id = :source_message_id
            WHERE tool_id = :tool_id AND port_id = :port_id AND lot_biz_key = :lot_biz_key
              AND active_flag = 'Y'
            """,
            {
                "tool_id": tool_id,
                "port_id": port_id,
                "lot_biz_key": lot_biz_key,
                "last_event_name": event_name,
                "last_event_ts_utc": event_ts,
                "updated_ts_utc": utc_now_naive(),
                "source_system": source_system,
                "source_message_id": source_message_id,
            },
        )
        if cursor.rowcount == 0:
            print(
                f"[RTLOT] CLEAR 未命中: tool_id={tool_id} port_id={port_id} "
                f"lot_biz_key={lot_biz_key} event={event_name}"
            )
        return

    print(f"[RTLOT] 未识别 ACTION_TYPE: {action_type}，已忽略。")


def resolve_machine_state(parsed_fields):
    return (
        parsed_fields.get("machine_state")
        or parsed_fields.get("status")
        or parsed_fields.get("event_name")
    )


def build_frontend_event(parsed_fields):
    event_type = parsed_fields.get("event_type")
    tool_id = parsed_fields.get("tool_id") or "UNKNOWN_EQP"
    source_message_id = parsed_fields.get("source_message_id")
    event_ts_utc = parsed_fields.get("event_ts_utc") or (
        datetime.now().isoformat() + "Z")
    machine_state = resolve_machine_state(parsed_fields)
    return {
        "tool_id": tool_id,
        "model_key": parsed_fields.get("model_key"),
        "event_ts_utc": event_ts_utc,
        "source_system": parsed_fields.get("source_system") or SOURCE_SYSTEM,
        "source_message_id": source_message_id,
        "machine_mode": parsed_fields.get("machine_mode") or parsed_fields.get("run_mode"),
        "run_mode": parsed_fields.get("run_mode") or parsed_fields.get("machine_mode"),
        "batch_id": parsed_fields.get("batch_id"),
        "lot_id": parsed_fields.get("lot_id"),
        "cassette_id": parsed_fields.get("cassette_id"),
        "pod_id": parsed_fields.get("pod_id") or parsed_fields.get("cassette_id"),
        "slot_id": parsed_fields.get("slot_id"),
        "wafer_id": parsed_fields.get("wafer_id"),
        "port_id": parsed_fields.get("port_id"),
        "smif_id": parsed_fields.get("smif_id"),
        "chamber_id": parsed_fields.get("chamber_id"),
        "unit_id": parsed_fields.get("unit_id"),
        "alarm_text": parsed_fields.get("alarm_text"),
        "event_type": event_type,
        "machine_state": machine_state,
        "status": parsed_fields.get("status") or parsed_fields.get("event_name"),
        "event_name": parsed_fields.get("event_name"),
        "alarm_code": parsed_fields.get("alarm_code") or parsed_fields.get("alarm_id"),
        "alarm_id": parsed_fields.get("alarm_id") or parsed_fields.get("alarm_code"),
        "alarm_action": parsed_fields.get("alarm_action"),
        "alarm_severity": parsed_fields.get("alarm_severity"),
    }


def fetch_latest_event_for_tool(tool_id):
    pool = get_oracle_pool()
    if pool is None:
        return None
    connection = None
    try:
        connection = pool.acquire()
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT payload_json FROM (
                    SELECT payload_json
                    FROM {ORACLE_RAW_TABLE}
                    WHERE tool_id = :tool_id AND parse_status = 'PARSED'
                    ORDER BY CASE WHEN event_ts_utc IS NULL THEN 1 ELSE 0 END,
                             event_ts_utc DESC, received_ts_utc DESC
                ) WHERE ROWNUM = 1
                """,
                {"tool_id": tool_id},
            )
            row = cursor.fetchone()
            if not row:
                return None
            payload_text = read_lob_text(row[0])
            if not payload_text:
                return None
            payload = json.loads(payload_text)
            if isinstance(payload, dict) and "parsed_fields" in payload:
                parsed_fields = payload.get("parsed_fields") or {}
            else:
                parsed_fields = payload if isinstance(payload, dict) else {}
            if not isinstance(parsed_fields,
                              dict) or not parsed_fields.get("event_type"):
                return None
            return build_frontend_event(parsed_fields)
    except Exception as exc:
        print(f"[Oracle] 查询设备最新事件失败: {exc}")
        return None
    finally:
        if connection is not None:
            pool.release(connection)


def persist_rv_message(
        raw_line,
        parsed_fields,
        parse_status="PARSED",
        error_message=None,
        subject=""):
    """
    将消息写入 DT_EVENT_RAW_CUR 表（每个 TOOL_ID 保留最新一条）
    同时写入 DT_EVENT_RAW 表（完整历史记录）
    """
    pool = get_oracle_pool()
    if pool is None:
        return False
    payload = parsed_fields
    source_message_id = build_source_message_id(raw_line, parsed_fields)
    dedup_tool_id, dedup_msg_id, dedup_identity = build_dedup_identity(
        parsed_fields, raw_line)
    tool_id = parsed_fields.get("tool_id") or "UNKNOWN_EQP"
    connection = None
    try:
        connection = pool.acquire()
        with connection.cursor() as cursor:
            print(
                f"[Oracle] 准备写入: dedup_identity={dedup_identity} source_message_id={source_message_id}")

            # 1. 删除该 TOOL_ID 的旧记录（保持最新一条）
            cursor.execute(
                f"DELETE FROM {ORACLE_RAW_TABLE} WHERE tool_id = :tool_id",
                {"tool_id": tool_id},
            )
            deleted_count = cursor.rowcount
            if deleted_count > 0:
                print(
                    f"[Oracle] 删除旧记录: tool_id={tool_id}, count={deleted_count}")

            # 2. 插入新记录
            cursor.execute(
                f"""
                INSERT INTO {ORACLE_RAW_TABLE} (
                    tool_id, source_system, source_message_id,
                    received_ts_utc, event_ts_utc,
                    payload_json, parse_status, error_message
                ) VALUES (
                    :tool_id, :source_system, :source_message_id,
                    :received_ts_utc, :event_ts_utc,
                    :payload_json, :parse_status, :error_message
                )
                """,
                {
                    "tool_id": tool_id,
                    "source_system": SOURCE_SYSTEM,
                    "source_message_id": source_message_id,
                    "received_ts_utc": datetime.now().replace(
                        tzinfo=None),
                    "event_ts_utc": parse_datetime_to_utc_naive(
                        parsed_fields.get("event_ts_utc")),
                    "payload_json": json.dumps(
                        payload,
                        ensure_ascii=False),
                    "parse_status": parse_status,
                    "error_message": error_message,
                },
            )
            inserted_cur_count = cursor.rowcount
            if inserted_cur_count > 0:
                print(
                    f"[Oracle] 插入当前表{ORACLE_RAW_TABLE}新记录: tool_id={tool_id}")

            if parse_status == "PARSED":
                try:
                    persist_realtime_lot(
                        cursor, parsed_fields, source_message_id)
                except Exception as rt_exc:
                    if is_oracle_table_missing(
                            rt_exc) or is_oracle_column_missing(rt_exc):
                        print(
                            f"[RTLOT] 实时账务对象未就绪，跳过实时账务更新: {format_oracle_error(rt_exc)}")
                    else:
                        raise

            # 3. 写入历史表（不删除，直接追加）
            try:
                cursor.execute(
                    f"""
                    INSERT INTO {ORACLE_RAW_TABLE_HIS} (
                        tool_id, source_system, source_message_id,
                        received_ts_utc, event_ts_utc,
                        payload_json, parse_status, error_message
                    ) VALUES (
                        :tool_id, :source_system, :source_message_id,
                        :received_ts_utc, :event_ts_utc,
                        :payload_json, :parse_status, :error_message
                    )
                    """,
                    {
                        "tool_id": tool_id,
                        "source_system": SOURCE_SYSTEM,
                        "source_message_id": source_message_id,
                        "received_ts_utc": datetime.now().replace(
                            tzinfo=None),
                        "event_ts_utc": parse_datetime_to_utc_naive(
                            parsed_fields.get("event_ts_utc")),
                        "payload_json": json.dumps(
                            payload,
                            ensure_ascii=False),
                        "parse_status": parse_status,
                        "error_message": error_message,
                    },
                )
                inserted_his_count = cursor.rowcount
                if inserted_his_count > 0:
                    print(
                        f"[Oracle] 追加历史表{ORACLE_RAW_TABLE_HIS}新记录: tool_id={tool_id}")
            except Exception as his_exc:
                # 历史表写入失败不影响主流程
                print(f"[Oracle] 写入历史表失败: {format_oracle_error(his_exc)}")

            connection.commit()
            return True
    except Exception as exc:
        if connection is not None:
            connection.rollback()
        oracle_error = format_oracle_error(exc)
        if oracledb is not None and isinstance(
                exc, getattr(oracledb, "IntegrityError", tuple())):
            print(
                f"[Oracle] 重复消息已跳过: tool_id={dedup_tool_id} msg_id={dedup_msg_id} source_message_id={source_message_id} dedup_identity={dedup_identity} | {oracle_error}")
            return False
        print(f"[Oracle] 写入历史消息失败: {oracle_error}")
        return False
    finally:
        if connection is not None:
            pool.release(connection)
