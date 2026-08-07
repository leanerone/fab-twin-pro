import os
import subprocess

from .router import broadcast_to_frontend
from .store import build_frontend_event, build_source_message_id, persist_rv_message

SERVICE = os.environ.get("RV_SERVICE", "")
NETWORK = os.environ.get("RV_NETWORK", "")
DAEMON = os.environ.get("RV_DAEMON", "")
SUBJECT = os.environ.get("RV_SUBJECT", "HJTC.CIM.OXE.TWIN")
SELF_INBOX = os.environ.get("RV_SELF_INBOX", "HJTC.CIM.OXE.TWIN")
RV_LISTEN_CMD = os.environ.get("RV_LISTEN_CMD", "tibrvlisten")
RV_SEND_CMD = os.environ.get("RV_SEND_CMD", "rvsend")
RV_OUTPUT_ENCODINGS = ["utf-8", "gb18030", "gbk"]

RV_MESSAGE_FIELDS = [
    "COMMAND_ID",
    "SUBJECT_ID",
    "MSG_ID",
    "EQP_ID",
    "LOT_ID",
    "EVENT_TYPE",
    "EVENT_NAME",
    "EVENT_VALUE",
    "RUN_MODE",
    "PORT_ID",
    "CASSETTE_ID",
    "CHAMBER_ID",
    "SMIF_ID",
    "BATCH_ID",
    "UNIT_ID",
    "SLOT_ID",
]

QUOTE_PAIRS = {
    '"': '"',
    "'": "'",
    "\u201c": "\u201d",
}


def strip_outer_quotes(value):
    if value is None:
        return None
    normalized = str(value).strip()
    if len(
            normalized) >= 2 and normalized[0] in QUOTE_PAIRS and normalized[-1] == QUOTE_PAIRS[normalized[0]]:
        normalized = normalized[1:-1].strip()
    return normalized or None


def normalize_rv_field_value(value):
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    normalized = strip_outer_quotes(normalized) or ""
    normalized = normalized.lstrip(
        "\"'\u201c\u201d").rstrip("\"'\u201c\u201d").strip()
    return normalized or None


def decode_rv_output_line(raw_line):
    if raw_line is None:
        return ""
    if isinstance(raw_line, str):
        return raw_line
    for encoding in RV_OUTPUT_ENCODINGS:
        try:
            return raw_line.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_line.decode(RV_OUTPUT_ENCODINGS[0], errors="replace")


def strip_wrapping_quotes(value):
    if value is None:
        return ""
    return strip_outer_quotes(value) or ""


def extract_rv_payload_text(line):
    payload_text = line.strip()
    if not payload_text:
        return ""

    if "_data_=" in payload_text:
        payload_text = payload_text.split("_data_=", 1)[1].strip()
        # 去除开头和结尾的多余引号及结尾的 }
        payload_text = payload_text.lstrip("\"'\u201c\u201d")
        if payload_text.endswith('"}'):
            payload_text = payload_text[:-2].strip()
        elif payload_text.endswith('}'):
            payload_text = payload_text[:-1].strip()
        payload_text = payload_text.rstrip("\"'\u201c\u201d")
        return payload_text

    if "DATA=" in payload_text:
        payload_text = payload_text.split("DATA=", 1)[1].strip()
        # 去除开头和结尾的多余引号及结尾的 }
        payload_text = payload_text.lstrip("\"'\u201c\u201d")
        if payload_text.endswith('"}'):
            payload_text = payload_text[:-2].strip()
        elif payload_text.endswith('}'):
            payload_text = payload_text[:-1].strip()
        payload_text = payload_text.rstrip("\"'\u201c\u201d")
        return payload_text

    if "message=" in payload_text:
        payload_text = payload_text.split("message=", 1)[1].strip()
        # 去除开头和结尾的多余引号
        payload_text = payload_text.lstrip("\"'\u201c\u201d")
        payload_text = payload_text.rstrip("\"'\u201c\u201d")
        return payload_text

    if "message={" in payload_text:
        payload_text = payload_text.split("message={", 1)[1].strip()
        if payload_text.endswith("}"):
            payload_text = payload_text[:-1].strip()
        return strip_wrapping_quotes(payload_text)

    if "subject=" in payload_text and "{" in payload_text and "}" in payload_text:
        payload_text = payload_text.split("{", 1)[1].rsplit("}", 1)[0].strip()
        return strip_wrapping_quotes(payload_text)

    return ""


def parse_space_delimited_rv_message(line):
    payload_text = extract_rv_payload_text(line)
    if not payload_text:
        return None, "empty payload"

    raw_parts = payload_text.split()
    if len(raw_parts) < 4:
        return None, f"field count too short: got {len(raw_parts)}"

    fixed_fields = RV_MESSAGE_FIELDS[:-1]
    if len(raw_parts) < len(fixed_fields):
        return None, f"field count too short: got {len(raw_parts)}"

    parsed = {}
    for index, field_name in enumerate(fixed_fields):
        parsed[field_name] = normalize_rv_field_value(raw_parts[index])
    parsed[RV_MESSAGE_FIELDS[-1]
           ] = normalize_rv_field_value(" ".join(raw_parts[len(fixed_fields):]))
    return parsed, None


def parse_query_inbox(line):
    payload_text = extract_rv_payload_text(line)
    if not payload_text:
        return None, None
    parts = payload_text.split()
    if len(parts) < 3:
        return None, None
    if parts[0].upper() != "QUERY_INBOX":
        return None, None
    return parts[1], parts[2]


def extract_reply_inbox(line):
    """从 RV 原始报文中提取 reply= 后面的 inbox 地址。"""
    if "reply=" not in line:
        return None
    # 找到 reply= 的位置
    idx = line.find("reply=")
    rest = line[idx + 6:]
    # 取到下一个逗号或空格为止
    for sep in [",", " "]:
        if sep in rest:
            rest = rest.split(sep, 1)[0]
            break
    return rest.strip() or None


def extract_msg_id_from_line(line):
    """从解析后的字段或原始行中提取 MSG_ID (TID.xxx)。"""
    # 先尝试从标准解析中获取
    raw_fields, _ = parse_space_delimited_rv_message(line)
    if raw_fields and raw_fields.get("MSG_ID"):
        return raw_fields.get("MSG_ID")
    # 回退：从 payload 文本中找 TID.xxx
    payload = extract_rv_payload_text(line)
    if payload:
        parts = payload.split()
        for p in parts:
            if p.upper().startswith("TID."):
                return p
    return None


def build_query_inbox_reply():
    if not SELF_INBOX:
        return None
    return f"//QUERY_INBOX {SUBJECT} {SUBJECT} {SELF_INBOX}"


def send_query_inbox_reply(reply_inbox):
    reply_message = build_query_inbox_reply()
    if not reply_message:
        print("[错误] 未配置 RV_SELF_INBOX，无法构造 QUERY_INBOX 回复。")
        return False
    cmd = [
        RV_SEND_CMD,
        "-service", SERVICE,
        "-network", NETWORK,
        "-daemon", DAEMON,
        reply_inbox,
        reply_message,
    ]
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        print(f"[RV回复] 已发送到 {reply_inbox}: {reply_message}")
        return True
    except FileNotFoundError:
        print(f"[错误] 找不到 {RV_SEND_CMD} 命令，无法发送 QUERY_INBOX 回复。")
        return False
    except subprocess.CalledProcessError as exc:
        print(f"[错误] QUERY_INBOX 回复发送失败: {exc}")
        return False


def build_twin_status_reply(msg_id):
    """构造 //TWIN_STATUS 0 <msg_id> 回复。"""
    if not msg_id:
        return None
    return f"//TWIN_STATUS 0 {msg_id}"


def send_twin_status_reply(reply_inbox, msg_id):
    """发送 //TWIN_STATUS 0 <msg_id> 到指定 inbox。"""
    reply_message = build_twin_status_reply(msg_id)
    if not reply_message:
        print("[错误] 无法构造 TWIN_STATUS 回复，msg_id 为空。")
        return False
    cmd = [
        RV_SEND_CMD,
        "-service", SERVICE,
        "-network", NETWORK,
        "-daemon", DAEMON,
        reply_inbox,
        reply_message,
    ]
    try:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        print(f"[RV回复] 已发送 TWIN_STATUS 到 {reply_inbox}: {reply_message}")
        return True
    except FileNotFoundError:
        print(f"[错误] 找不到 {RV_SEND_CMD} 命令，无法发送 TWIN_STATUS 回复。")
        return False
    except subprocess.CalledProcessError as exc:
        print(f"[错误] TWIN_STATUS 回复发送失败: {exc}")
        return False


def handle_rv_message(line):
    # 过滤 RV 系统 advisory / rvd 错误消息
    if line.startswith(
            "{ mtype=") or "_RV.ERROR" in line or "_RV.INFO" in line:
        return
    if "Rendezvous Error Not Handled" in line or " rvd: " in line:
        return

    print(f"[RV原始报文] {line}")

    reply_inbox, sender_subject = parse_query_inbox(line)
    if reply_inbox and sender_subject:
        print(
            f"[RV请求] 收到 QUERY_INBOX: inbox={reply_inbox}, subject={sender_subject}")
        send_query_inbox_reply(reply_inbox)
        return

    # 非 QUERY_INBOX 消息：如果有 reply inbox，则发送 //TWIN_STATUS 0 <msg_id>
    twin_reply_inbox = extract_reply_inbox(line)
    msg_id = extract_msg_id_from_line(line)
    if twin_reply_inbox and msg_id:
        print(
            f"[RV请求] 收到 TWIN_STATUS 类消息，reply inbox={twin_reply_inbox}, msg_id={msg_id}")
        send_twin_status_reply(twin_reply_inbox, msg_id)
        # 继续走原有解析流程（不 return）

    raw_fields, parse_error = parse_space_delimited_rv_message(line)
    if SUBJECT not in line and "subject=" not in line and (
            parse_error or not raw_fields or not raw_fields.get("EVENT_TYPE")):
        return

    if parse_error:
        persist_rv_message(
            line,
            {"source_system": "RV"},
            parse_status="ERROR",
            error_message=parse_error,
            subject=SUBJECT,
        )
        return

    eqp_id = raw_fields.get("EQP_ID")
    lot_id = raw_fields.get("LOT_ID")
    cassette_id = raw_fields.get("CASSETTE_ID")
    event_type = raw_fields.get("EVENT_TYPE")
    event_name = raw_fields.get("EVENT_NAME")
    event_value = raw_fields.get("EVENT_VALUE")
    run_mode = raw_fields.get("RUN_MODE")
    port_id = raw_fields.get("PORT_ID")
    chamber_id = raw_fields.get("CHAMBER_ID")
    smif_id = raw_fields.get("SMIF_ID")
    batch_id = raw_fields.get("BATCH_ID")
    unit_id = raw_fields.get("UNIT_ID")
    slot_id = raw_fields.get("SLOT_ID")
    source_message_id = raw_fields.get("MSG_ID")
    status = event_name

    parsed_fields = {
        "tool_id": eqp_id or "UNKNOWN_EQP",
        "msg_id": source_message_id,
        "lot_id": lot_id,
        "event_type": event_type,
        "event_name": event_name,
        "event_value": event_value,
        "status": status,
        "machine_state": status,
        "machine_mode": run_mode,
        "run_mode": run_mode,
        "alarm_code": None,
        "alarm_id": None,
        "alarm_text": event_value,
        "event_ts_utc": None,
        "source_system": "RV",
        "source_message_id": source_message_id,
        "port_id": port_id,
        "cassette_id": cassette_id,
        "pod_id": cassette_id,
        "wafer_id": None,
        "smif_id": smif_id,
        "chamber_id": chamber_id,
        "batch_id": batch_id,
        "unit_id": unit_id,
        "slot_id": slot_id,
    }

    if not event_type:
        persist_rv_message(
            line,
            parsed_fields,
            parse_status="ERROR",
            error_message="EVENT_TYPE missing",
            subject=SUBJECT,
        )
        return

    parsed_fields["source_message_id"] = build_source_message_id(
        line, parsed_fields)
    persist_rv_message(
        line,
        parsed_fields,
        parse_status="PARSED",
        subject=SUBJECT)

    print(
        f"\n[收到RV数据] 设备: {eqp_id} | 批次: {lot_id} | 事件: {event_type} | 状态: {event_name}")

    if event_type == "HEARTBEAT":
        print(f" -> 动作: 设备 {eqp_id} 保持心跳连接。")

    broadcast_to_frontend(build_frontend_event(parsed_fields))


def run_rv_listener():
    cmd = [
        RV_LISTEN_CMD,
        "-service", SERVICE,
        "-network", NETWORK,
        "-daemon", DAEMON,
        SUBJECT,
    ]
    print("====== RV 数字孪生 Python 网桥启动 ======")
    print(f"RV 监听主题: {SUBJECT}")
    print("HTTP Web 服务将由 runtime.router 启动")
    print(f"RV 输出解码顺序: {', '.join(RV_OUTPUT_ENCODINGS)}")
    print(f"RV 监听命令: {RV_LISTEN_CMD}")
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0)
        for raw_line in iter(process.stdout.readline, b""):
            if not raw_line:
                break
            line = decode_rv_output_line(raw_line).rstrip("\r\n")
            if line:
                handle_rv_message(line)
    except FileNotFoundError:
        print(
            f"\n[错误] 找不到 {RV_LISTEN_CMD} 命令。请检查 RV_LISTEN_CMD 环境变量或确保 rvlisten/tibrvlisten 在 PATH 中。")
    except Exception as exc:
        print(f"\nRV 监听异常: {exc}")
