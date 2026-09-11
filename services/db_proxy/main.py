# -*- coding: utf-8 -*-
"""
FabTwin DB Proxy Service — 为 n8n 提供 Oracle 11g 查询代理
部署在与 FabTwin 后端同一台 server 上（共用 Oracle Client）

架构: n8n HTTP Request → 本服务(8001) → Oracle 11g (Thick mode)

启动: python main.py
"""
import os
import sys
import json
import logging
import traceback
from datetime import datetime, timedelta

# ─── FastAPI ───
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse
import uvicorn

# ─── Oracle ───
import oracledb

# 让 oracledb 直接返回字符串而非 LOB 对象（避免 payload_json 是 LOB 时无法 json.loads）
try:
    oracledb.defaults.fetch_lobs = False
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("db_proxy")

# ========== 配置 ==========
ORACLE_USER     = os.getenv("ORACLE_USER", "fabtwin")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "fabtwin")
ORACLE_HOST     = os.getenv("ORACLE_HOST", "localhost")
ORACLE_PORT     = int(os.getenv("ORACLE_PORT", "1521"))
ORACLE_SERVICE  = os.getenv("ORACLE_SERVICE", "ORCLPDB")
ORACLE_DSN_TYPE = os.getenv("ORACLE_DSN_TYPE", "sid").lower()  # 11g 默认 sid
ORACLE_CLIENT_DIR = os.getenv("ORACLE_CLIENT_DIR", "")
API_KEY         = os.getenv("DB_PROXY_API_KEY", "fabtwin-proxy-2026")
LISTEN_PORT     = int(os.getenv("DB_PROXY_PORT", "8001"))

# ========== Oracle 连接 ==========
def _init_oracle_client():
    """Thick 模式初始化（支持 Oracle 9.2+ 包括 11g）"""
    if not ORACLE_CLIENT_DIR:
        logger.warning("ORACLE_CLIENT_DIR 未设置，尝试自动检测...")
    lib_dir = ORACLE_CLIENT_DIR
    # 尝试 bin 子目录
    if lib_dir:
        bin_dir = os.path.join(lib_dir, "bin")
        if os.path.exists(os.path.join(bin_dir, "oci.dll")):
            lib_dir = bin_dir
        elif not os.path.exists(os.path.join(lib_dir, "oci.dll")):
            lib_dir = ""
    try:
        if lib_dir:
            oracledb.init_oracle_client(lib_dir=lib_dir)
            logger.info(f"Oracle Thick 模式已启用 (lib_dir={lib_dir})")
        else:
            oracledb.init_oracle_client()
            logger.info("Oracle Thick 模式已启用（自动检测）")
    except Exception as e:
        if "DPI-1072" in str(e):
            logger.info("Oracle Thick 模式已启用（之前已初始化）")
        else:
            logger.error(f"Oracle Thick 模式初始化失败: {e}")
            logger.error("请安装 Oracle Client 并设置 ORACLE_CLIENT_DIR")
            logger.error("  pip install oracledb==2.4.0（4.x 有 DPI-1047 bug）")

_init_oracle_client()

# 构造 DSN
if ORACLE_DSN_TYPE == "sid":
    _dsn = oracledb.makedsn(ORACLE_HOST, ORACLE_PORT, sid=ORACLE_SERVICE)
else:
    _dsn = oracledb.makedsn(ORACLE_HOST, ORACLE_PORT, service_name=ORACLE_SERVICE)

logger.info(f"Oracle DSN: {_dsn}")

def get_conn():
    """获取 Oracle 连接"""
    return oracledb.connect(user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=_dsn)

def exec_query(sql, params=None):
    """执行 SQL 返回 (columns, rows)"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params or {})
        cols = [d[0].lower() for d in cur.description]
        rows = cur.fetchall()
        cur.close()
        return cols, rows

def rows_to_list(cols, rows):
    """将 rows 转为 list[dict]（自动处理 Oracle LOB/CLOB → str）"""
    result = []
    for r in rows:
        item = {}
        for i, c in enumerate(cols):
            val = r[i]
            # Oracle LOB/CLOB → 读成字符串
            if hasattr(val, "read"):
                try:
                    val = val.read()
                except Exception:
                    pass
            if isinstance(val, (bytes, bytearray)):
                try:
                    val = val.decode("utf-8")
                except Exception:
                    val = str(val)
            if isinstance(val, datetime):
                val = val.strftime("%Y-%m-%d %H:%M:%S")
            item[c] = val
        result.append(item)
    return result

# ========== 标准响应 ==========
def ok(answer, table_data=None, jump_timestamp=None, jump_machine_id=None, sources=None):
    return {
        "ok": True,
        "answer": answer,
        "table_data": table_data,
        "jump_timestamp": jump_timestamp,
        "jump_machine_id": jump_machine_id,
        "sources": sources or [{"type": "db_proxy"}],
    }

def fail(msg):
    return {"ok": False, "answer": f"查询失败: {msg}", "table_data": None,
            "jump_timestamp": None, "jump_machine_id": None, "sources": []}

def _parse_payload(pj):
    """安全解析 payload_json：处理 LOB/CLOB/bytes/str 各种类型，返回 dict"""
    if not pj:
        return {}
    # LOB 对象 → 先 .read()
    if hasattr(pj, "read"):
        try:
            pj = pj.read()
        except Exception:
            return {}
    # bytes → decode
    if isinstance(pj, (bytes, bytearray)):
        try:
            pj = pj.decode("utf-8")
        except Exception:
            return {}
    # str → json.loads
    if isinstance(pj, str):
        try:
            result = json.loads(pj)
            return result if isinstance(result, dict) else {}
        except Exception:
            return {}
    # 已经是 dict
    if isinstance(pj, dict):
        return pj
    return {}

def table(headers, rows):
    return {"headers": headers, "rows": [[str(c) if c is not None else "" for c in r] for r in rows]}

# ========== FastAPI ==========
app = FastAPI(title="FabTwin DB Proxy", version="1.0.0")

def verify_key(request: Request):
    """简易 API Key 校验"""
    auth = request.headers.get("X-API-Key", "")
    if auth != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

@app.get("/health")
def health():
    try:
        cols, rows = exec_query("SELECT 1 FROM dual")
        return {"status": "ok", "db": "connected", "rows": len(rows)}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(e)})

# ─── F1: 机台状态（实时，从事件流 dt_event_raw_cur 派生） ───
# 【根因】静态 machines 表不随新消息更新 → 状态停留在旧快照（如 9.2、7.17）。
# 【方案】从 dt_event_raw_cur（每台机台最新一条 RV 消息，持续更新）解析 payload_json 派生实时状态：
#   - 告警：event_name == 'EC_ALARM_REPORT' → 状态=告警中，alarm_id/alarm_text 显示
#   - 直接用 payload.machine_state（Running/Idle，OXE 类事件自带）
#   - 否则按 event_name 映射：Start/WaferLoaded/PS → 运行中；POD_PLACED/MVIN → 装料中；
#     LotEnd/JobEnd/POD_REMOVED → 空闲；...
#   - 取 lot_id/recipe/run_mode/快照时间 event_ts_utc
@app.post("/query/machine_status")
async def f1_machine_status(request: Request):
    verify_key(request)
    body = await request.json()
    machine_id = body.get("machine_id", "").strip()

    def _derive_status(payload: dict) -> dict:
        """从事件 payload 派生机台实时状态字典"""
        event_name = str(payload.get("event_name") or payload.get("event_type") or "").upper()
        machine_state = str(payload.get("machine_state") or "").strip()
        lot_id = payload.get("lot_id") or payload.get("batch_id") or ""
        recipe = payload.get("recipe") or ""
        run_mode = payload.get("run_mode") or ""
        alarm_id = payload.get("alarm_id") or ""
        alarm_text = payload.get("alarm_text") or ""

        # 优先级1：告警事件
        if event_name == "EC_ALARM_REPORT":
            return {
                "status": "告警中",
                "status_detail": f"告警码 {alarm_id}: {alarm_text}",
                "lot_id": lot_id,
                "recipe": recipe,
                "event_name": event_name,
                "alarm_code": alarm_id,
            }
        # 优先级2：payload 自带 machine_state
        if machine_state:
            ms = machine_state.upper()
            if ms in ("RUNNING", "RUN"):
                status = "运行中"
            elif ms in ("IDLE", "IDL"):
                status = "空闲"
            elif ms in ("ALARM", "ERROR", "ERR"):
                status = "告警中"
            elif ms in ("DOWN", "MAINT", "MAINTENANCE"):
                status = "维护中"
            else:
                status = machine_state
            return {
                "status": status,
                "status_detail": f"最近事件: {event_name}",
                "lot_id": lot_id,
                "recipe": recipe,
                "event_name": event_name,
                "alarm_code": alarm_id,
            }
        # 优先级3：按 event_name 映射
        running_set = {"START", "PS", "PE", "WAFERLOADED", "WAFERUNLOADED",
                       "STARTMAPPING_LEFT", "ENDMAPPING", "LOAD_CYCLE_STARTED",
                       "LOAD_CYCLE_COMPLETED", "DOOR_OPEN", "DOOR_CLOSE"}
        loading_set = {"POD_PLACED", "LOCK_PORT_COMPLETED", "MVIN", "DETACH_POD_PLACE"}
        unloading_set = {"MVOU", "UNLOCK_PORT_COMPLETED", "POD_REMOVED",
                         "LOTEND", "JOBEND", "READYTOUNLOAD", "UNLOAD_CYCLE_COMPLETED"}
        if event_name in running_set:
            status = "运行中"
        elif event_name in loading_set:
            status = "装料中"
        elif event_name in unloading_set:
            status = "空闲"
        else:
            status = event_name or "未知"
        return {
            "status": status,
            "status_detail": f"最近事件: {event_name}" + (f"（run_mode={run_mode}）" if run_mode else ""),
            "lot_id": lot_id,
            "recipe": recipe,
            "event_name": event_name,
            "alarm_code": alarm_id,
        }

    try:
        # dt_event_raw_cur：每台机台最新一条消息（持续更新），直接拿即可
        sql = """SELECT tool_id, raw_id, event_ts_utc, received_ts_utc, payload_json
                 FROM dt_event_raw_cur
                 WHERE (:mid = '' OR tool_id = :mid)
                 ORDER BY tool_id"""
        cols, rows = exec_query(sql, {"mid": machine_id})
        data = rows_to_list(cols, rows)
        if not data:
            if machine_id:
                return ok(f"未找到机台 {machine_id} 的最新事件（dt_event_raw_cur 无记录）",
                          jump_machine_id=machine_id)
            return ok("暂无任何机台的最新事件（dt_event_raw_cur 无记录）")

        results = []
        for d in data:
            payload = _parse_payload(d.get("payload_json"))
            derived = _derive_status(payload)
            derived["tool_id"] = d.get("tool_id", "")
            derived["event_ts"] = d.get("event_ts_utc") or d.get("received_ts_utc") or ""
            results.append(derived)

        def status_rows():
            return [[r["tool_id"], r["status"], r.get("status_detail", ""),
                     r.get("lot_id") or "无", r.get("alarm_code") or "无",
                     r.get("event_ts", "")] for r in results]

        if machine_id:
            r = results[0]
            answer = (f"机台 {r['tool_id']} 当前状态: {r['status']}。"
                      f"{r.get('status_detail', '')}，"
                      f"当前Lot {r.get('lot_id') or '无'}"
                      f"{('，Recipe ' + r['recipe']) if r.get('recipe') else ''}，"
                      f"最近事件时间 {r.get('event_ts') or 'N/A'}。")
            return ok(answer,
                      table(["机台", "状态", "状态说明", "当前Lot", "告警码", "最近事件时间"], status_rows()),
                      jump_timestamp=r.get("event_ts") or None,
                      jump_machine_id=r["tool_id"])

        running = sum(1 for r in results if r["status"] == "运行中")
        alarming = sum(1 for r in results if r["status"] == "告警中")
        answer = f"全厂共 {len(results)} 台机台：运行中 {running} 台，告警中 {alarming} 台，其余空闲/其它。"
        return ok(answer,
                  table(["机台", "状态", "状态说明", "当前Lot", "告警码", "最近事件时间"], status_rows()),
                  jump_timestamp=results[0].get("event_ts") or None,
                  jump_machine_id=results[0]["tool_id"])
    except Exception as e:
        logger.error(f"F1 error: {e}\n{traceback.format_exc()}")
        return fail(str(e))

# ─── F2: Lot 信息 ───
@app.post("/query/lot_info")
async def f2_lot_info(request: Request):
    verify_key(request)
    body = await request.json()
    lot_id = body.get("lot_id", "")
    machine_id = body.get("machine_id", "")
    try:
        if lot_id:
            sql = """SELECT id, machine_id, product, wafer_count, status,
                           start_time, end_time, recipe_id
                    FROM lots WHERE id = :lid"""
            cols, rows = exec_query(sql, {"lid": lot_id})
        elif machine_id:
            sql = """SELECT * FROM (
                       SELECT id, machine_id, product, wafer_count, status,
                              start_time, end_time, recipe_id
                       FROM lots WHERE machine_id = :mid ORDER BY start_time DESC
                     ) WHERE ROWNUM <= 20"""
            cols, rows = exec_query(sql, {"mid": machine_id})
        else:
            sql = """SELECT * FROM (
                       SELECT id, machine_id, product, wafer_count, status,
                              start_time, end_time, recipe_id
                       FROM lots ORDER BY start_time DESC
                     ) WHERE ROWNUM <= 20"""
            cols, rows = exec_query(sql)
        data = rows_to_list(cols, rows)
        if not data:
            return ok(f"未找到 Lot 记录（lot_id={lot_id}, machine_id={machine_id}）")
        answer = f"共 {len(data)} 条 Lot 记录。" + \
                 "; ".join([f"{d['id']}({d.get('status','')})" for d in data[:3]])
        return ok(answer,
                  table(["Lot ID","机台","产品","晶圆数","状态","开始时间","结束时间"],
                        [[d.get('id',''), d.get('machine_id',''), d.get('product',''),
                          d.get('wafer_count',0), d.get('status',''),
                          d.get('start_time',''), d.get('end_time','')] for d in data]),
                  jump_timestamp=data[0].get('start_time'),
                  jump_machine_id=data[0].get('machine_id'))
    except Exception as e:
        logger.error(f"F2 error: {e}\n{traceback.format_exc()}")
        return fail(str(e))

# ─── F3: 报警统计（实时，从 dt_event_raw 的 EC_ALARM_REPORT 事件取） ───
# 【修复】原读静态 alarms 表（不随新消息更新）。改为 dt_event_raw 解析 payload_json 的告警事件。
@app.post("/query/machine_alarms")
async def f3_alarms(request: Request):
    verify_key(request)
    body = await request.json()
    machine_id = body.get("machine_id", "")
    severity = body.get("severity", "")
    days = int(body.get("days", 7))
    try:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        # 取时间范围内的事件，在 Python 里过滤 event_name='EC_ALARM_REPORT'
        # Oracle 11g 不支持 FETCH FIRST n ROWS ONLY（12c+语法），用 ROWNUM 替代
        sql = """SELECT * FROM (
                   SELECT tool_id, event_ts_utc, payload_json
                   FROM dt_event_raw
                   WHERE event_ts_utc >= :since AND (:mid = '' OR tool_id = :mid)
                   ORDER BY event_ts_utc DESC
                 ) WHERE ROWNUM <= 500"""
        cols, rows = exec_query(sql, {"since": since, "mid": machine_id or ""})
        data = rows_to_list(cols, rows)

        alarm_rows = []
        for d in data:
            payload = _parse_payload(d.get("payload_json"))
            if str(payload.get("event_name") or "").upper() != "EC_ALARM_REPORT":
                continue
            aid = payload.get("alarm_id") or ""
            # severity 推断：payload 可能带 severity；否则按告警码映射（与前端一致）
            sev = payload.get("severity") or ""
            if not sev:
                if str(aid) in ("9004", "0201"):
                    sev = "crit"
                elif str(aid) in ("9003", "20011"):
                    sev = "warn"
                elif str(aid) == "0411":
                    sev = "info"
                else:
                    sev = "warn"
            if severity and str(sev).lower() != str(severity).lower():
                continue
            alarm_rows.append([
                d.get("tool_id", ""),
                d.get("event_ts_utc") or "",
                aid,
                payload.get("alarm_text") or "",
                sev,
                payload.get("lot_id") or payload.get("batch_id") or "",
            ])

        if not alarm_rows:
            return ok(f"近 {days} 天无报警记录（machine_id={machine_id}, severity={severity}）")
        crit_count = sum(1 for r in alarm_rows if str(r[4]).lower() == "crit")
        answer = f"近 {days} 天共 {len(alarm_rows)} 条报警（严重 {crit_count} 条）。"
        return ok(answer,
                  table(["机台", "时间", "告警码", "描述", "等级", "Lot"], alarm_rows),
                  jump_timestamp=alarm_rows[0][1] or None,
                  jump_machine_id=machine_id or alarm_rows[0][0])
    except Exception as e:
        logger.error(f"F3 error: {e}\n{traceback.format_exc()}")
        return fail(str(e))

# ─── F4: 事件时间线（实时，从 dt_event_raw 取） ───
# 【修复】原读静态 machine_events 表（不随新消息更新）。改为 dt_event_raw 解析 payload_json。
@app.post("/query/event_timeline")
async def f4_events(request: Request):
    verify_key(request)
    body = await request.json()
    machine_id = body.get("machine_id", "")
    if not machine_id:
        return fail("machine_id 必填")
    time_range = body.get("time_range", "today")
    try:
        now = datetime.now()
        ranges = {
            "today": now.strftime("%Y-%m-%d 00:00:00"),
            "yesterday": (now - timedelta(days=1)).strftime("%Y-%m-%d 00:00:00"),
            "this_week": (now - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00"),
            "last_2h": (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
            "last_7d": (now - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00"),
            "last_30d": (now - timedelta(days=30)).strftime("%Y-%m-%d 00:00:00"),
        }
        since = ranges.get(time_range, ranges["today"])
        # dt_event_raw.event_ts_utc 是字符串（ISO 格式），按字符串比较即可过滤时间窗口
        sql = """SELECT * FROM (
                   SELECT tool_id, event_ts_utc, received_ts_utc, payload_json
                   FROM dt_event_raw
                   WHERE tool_id = :mid AND event_ts_utc >= :since
                   ORDER BY event_ts_utc DESC
                 ) WHERE ROWNUM <= 200"""
        cols, rows = exec_query(sql, {"mid": machine_id, "since": since})
        data = rows_to_list(cols, rows)
        if not data:
            return ok(f"机台 {machine_id} 在 {time_range} 范围内无事件记录。")
        event_rows = []
        for d in data:
            payload = _parse_payload(d.get("payload_json"))
            event_rows.append([
                d.get("tool_id", ""),
                d.get("event_ts_utc") or d.get("received_ts_utc", ""),
                payload.get("event_name") or payload.get("event_type") or "",
                payload.get("alarm_id") or "",
                payload.get("alarm_text") or "",
                payload.get("lot_id") or payload.get("batch_id") or "",
                payload.get("recipe") or "",
                payload.get("chamber_id") or "",
            ])
        answer = f"机台 {machine_id} 在 {time_range} 共 {len(event_rows)} 条事件（最新 {event_rows[0][1]}）。"
        return ok(answer,
                  table(["机台", "事件时间", "事件名", "告警码", "告警描述", "Lot", "Recipe", "Chamber"], event_rows),
                  jump_timestamp=event_rows[0][1] or None,
                  jump_machine_id=machine_id)
    except Exception as e:
        logger.error(f"F4 error: {e}\n{traceback.format_exc()}")
        return fail(str(e))

# ─── F5: 产量统计（实时，从 dt_event_raw 的 LotEnd 事件统计） ───
# 【修复】原读静态 lots 表（不随新消息更新）。改为统计 dt_event_raw 中 event_name='LotEnd' 的 QTY 之和。
@app.post("/query/yield_stats")
async def f5_yield(request: Request):
    verify_key(request)
    body = await request.json()
    machine_id = body.get("machine_id", "")
    if not machine_id:
        return fail("machine_id 必填")
    time_range = body.get("time_range", "today")
    try:
        now = datetime.now()
        ranges = {
            "today": now.strftime("%Y-%m-%d 00:00:00"),
            "last_7d": (now - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00"),
            "last_30d": (now - timedelta(days=30)).strftime("%Y-%m-%d 00:00:00"),
            "this_week": (now - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00"),
        }
        since = ranges.get(time_range, ranges["today"])
        # 取该机台时间范围内的所有事件，在 Python 里过滤 event_name='LotEnd' 并统计
        # （Oracle 11g 无 JSON_VALUE，且 payload_json 是 TEXT，故拉取后在 Python 解析）
        sql = """SELECT tool_id, event_ts_utc, payload_json
                 FROM dt_event_raw
                 WHERE tool_id = :mid AND event_ts_utc >= :since
                 ORDER BY event_ts_utc DESC"""
        cols, rows = exec_query(sql, {"mid": machine_id, "since": since})
        data = rows_to_list(cols, rows)

        lot_end_count = 0
        total_wafers = 0
        lot_ids = set()
        for d in data:
            payload = _parse_payload(d.get("payload_json"))
            en = str(payload.get("event_name") or "").upper()
            if en == "LOTEND":
                lot_end_count += 1
                qty = payload.get("QTY") or payload.get("qty")
                try:
                    total_wafers += int(qty) if qty not in (None, "", "NULL") else 0
                except Exception:
                    pass
                lid = payload.get("lot_id") or payload.get("batch_id")
                if lid and lid != "NULL":
                    lot_ids.add(lid)

        distinct_lots = len(lot_ids)
        if lot_end_count == 0:
            return ok(f"机台 {machine_id} 在 {time_range} 内无 LotEnd 事件（产量 0）。",
                      jump_timestamp=now.strftime("%Y-%m-%d %H:%M:%S"),
                      jump_machine_id=machine_id)
        answer = (f"机台 {machine_id} 在 {time_range} 内共完成 {lot_end_count} 次 Lot加工"
                  f"（涉及 {distinct_lots} 个 Lot），累计加工晶圆 {total_wafers} 片。")
        return ok(answer,
                  table(["时间范围", "LotEnd次数", "涉及Lot数", "累计晶圆数"],
                        [[time_range, lot_end_count, distinct_lots, total_wafers]]),
                  jump_timestamp=now.strftime("%Y-%m-%d %H:%M:%S"),
                  jump_machine_id=machine_id)
    except Exception as e:
        logger.error(f"F5 error: {e}\n{traceback.format_exc()}")
        return fail(str(e))

# ─── F6: 工艺配方 ───
@app.post("/query/recipe_info")
async def f6_recipe(request: Request):
    verify_key(request)
    body = await request.json()
    machine_id = body.get("machine_id", "")
    if not machine_id:
        return fail("machine_id 必填")
    try:
        sql = """SELECT id, name, machine_id, process_type, temperature, pressure,
                       rf_power, gas_flow, process_time, updated_at
                FROM recipes WHERE machine_id = :mid"""
        cols, rows = exec_query(sql, {"mid": machine_id})
        data = rows_to_list(cols, rows)
        if not data:
            return ok(f"机台 {machine_id} 无配方记录。")
        answer = f"机台 {machine_id} 共 {len(data)} 个配方。" + \
                 "; ".join([f"{d['id']}({d.get('process_type','')})" for d in data[:3]])
        return ok(answer,
                  table(["配方ID","名称","机台","工艺类型","温度(°C)","压力(Pa)","RF功率(W)","气体流量","工艺时间","更新时间"],
                        [[d.get('id',''), d.get('name',''), d.get('machine_id',''),
                          d.get('process_type',''), d.get('temperature',''),
                          d.get('pressure',''), d.get('rf_power',''),
                          d.get('gas_flow',''), d.get('process_time',''),
                          d.get('updated_at','')] for d in data]),
                  jump_machine_id=machine_id)
    except Exception as e:
        logger.error(f"F6 error: {e}\n{traceback.format_exc()}")
        return fail(str(e))

# ─── F7: MES Lot 详情（管理员，从 dt_event_raw 派生） ───
# 【修复】原读静态 lots/machine_events 表。改为从 dt_event_raw 解析该 Lot 的所有事件派生信息。
@app.post("/query/mes_lot_info")
async def f7_mes_lot(request: Request):
    verify_key(request)
    body = await request.json()
    lot_id = body.get("lot_id", "")
    if not lot_id:
        return fail("lot_id 必填")
    try:
        # 查该 Lot 相关事件（payload_json 里 lot_id/batch_id 匹配）
        sql = """SELECT tool_id, event_ts_utc, payload_json
                 FROM dt_event_raw
                 WHERE payload_json LIKE :lid
                 ORDER BY event_ts_utc ASC"""
        cols, rows = exec_query(sql, {"lid": f"%\"lot_id\": \"{lot_id}\"%"})
        data = rows_to_list(cols, rows)
        # 兜底：也匹配 batch_id
        if not data:
            cols, rows = exec_query(sql, {"lid": f"%\"batch_id\": \"{lot_id}\"%"})
            data = rows_to_list(cols, rows)
        if not data:
            return ok(f"未找到 Lot {lot_id} 的事件记录。")

        events = []
        machine_id = ""
        recipe = ""
        start_time = ""
        end_time = ""
        wafer_count = 0
        lot_done = False
        for d in data:
            payload = _parse_payload(d.get("payload_json"))
            en = payload.get("event_name") or ""
            ts = d.get("event_ts_utc") or ""
            if not machine_id:
                machine_id = d.get("tool_id", "")
            if not recipe and payload.get("recipe"):
                recipe = payload.get("recipe")
            if not start_time:
                start_time = ts
            end_time = ts
            if str(en).upper() == "LOTEND":
                lot_done = True
                qty = payload.get("QTY") or payload.get("qty")
                try:
                    wafer_count = int(qty) if qty not in (None, "", "NULL") else 0
                except Exception:
                    pass
            events.append([ts, en, payload.get("alarm_id") or "", d.get("tool_id", "")])

        status = "done" if lot_done else "run"
        answer = (f"Lot {lot_id}: 机台 {machine_id}，Recipe {recipe or 'N/A'}，"
                  f"晶圆数 {wafer_count}，状态 {status}，"
                  f"开始 {start_time}，结束 {end_time}，关联事件 {len(events)} 条。")
        return ok(answer,
                  table(["Lot ID", "机台", "Recipe", "晶圆数", "状态", "开始时间", "结束时间"],
                        [[lot_id, machine_id, recipe or "", wafer_count, status, start_time, end_time]]),
                  jump_timestamp=end_time or start_time,
                  jump_machine_id=machine_id)
    except Exception as e:
        logger.error(f"F7 error: {e}\n{traceback.format_exc()}")
        return fail(str(e))

# ─── F8: 导出报警报表（管理员，从 dt_event_raw 告警事件） ───
@app.post("/query/export_alarm_report")
async def f8_export(request: Request):
    verify_key(request)
    body = await request.json()
    machine_id = body.get("machine_id", "")
    days = int(body.get("days", 7))
    try:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        sql = """SELECT * FROM (
                   SELECT tool_id, event_ts_utc, payload_json
                   FROM dt_event_raw
                   WHERE event_ts_utc >= :since AND (:mid = '' OR tool_id = :mid)
                   ORDER BY event_ts_utc DESC
                 ) WHERE ROWNUM <= 1000"""
        cols, rows = exec_query(sql, {"since": since, "mid": machine_id or ""})
        data = rows_to_list(cols, rows)

        report_rows = []
        for d in data:
            payload = _parse_payload(d.get("payload_json"))
            if str(payload.get("event_name") or "").upper() != "EC_ALARM_REPORT":
                continue
            aid = payload.get("alarm_id") or ""
            sev = payload.get("severity") or ""
            if not sev:
                sev = "crit" if str(aid) in ("9004", "0201") else ("warn" if str(aid) in ("9003", "20011") else "info")
            report_rows.append([
                d.get("tool_id", ""), d.get("event_ts_utc") or "",
                aid, payload.get("alarm_text") or "", sev,
                payload.get("lot_id") or payload.get("batch_id") or "",
            ])

        total = len(report_rows)
        answer = (f"已生成报警报表：近 {days} 天共 {total} 条记录"
                  + (f"（机台 {machine_id}）" if machine_id else "（全厂）") + "，可下载 CSV 格式。")
        download_url = f"/download/alarms?machine_id={machine_id}&days={days}"
        return ok(answer,
                  table(["机台", "时间", "告警码", "描述", "等级", "Lot"], report_rows[:50]),
                  jump_machine_id=machine_id,
                  sources=[{"type": "db_proxy", "workflow": "export_alarm_report",
                            "row_count": total, "download_url": download_url}])
    except Exception as e:
        logger.error(f"F8 error: {e}\n{traceback.format_exc()}")
        return fail(str(e))

# ─── F9: 生成故障工单（管理员） ───
@app.post("/query/generate_work_order")
async def f9_work_order(request: Request):
    verify_key(request)
    body = await request.json()
    machine_id = body.get("machine_id", "")
    fault_type = body.get("fault_type", "")
    severity = body.get("severity", "medium")
    if not machine_id or not fault_type:
        return fail("machine_id 和 fault_type 必填")
    try:
        wo_id = f"WO-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 插入工单记录（复用 alarms 表，alarm_code = WORK_ORDER）
        sql = """INSERT INTO alarms (machine_id, timestamp, alarm_code, description, "LEVEL", resolved, lot_id)
                VALUES (:mid, :ts, 'WORK_ORDER', :desc, :sev, 0, NULL)"""
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(sql, {"mid": machine_id, "ts": now_str,
                              "desc": f"[{wo_id}] {fault_type}", "sev": severity})
            conn.commit()
            cur.close()
        answer = f"已生成故障工单 {wo_id}：机台 {machine_id}，故障 '{fault_type}'，" \
                 f"严重等级 {severity}。工单已写入数据库。"
        return ok(answer,
                  table(["工单号","机台","故障描述","严重等级","创建时间"],
                        [[wo_id, machine_id, fault_type, severity, now_str]]),
                  jump_machine_id=machine_id,
                  sources=[{"type":"db_proxy","workflow":"generate_work_order",
                            "wo_id":wo_id,"owner":"admin"}])
    except Exception as e:
        logger.error(f"F9 error: {e}\n{traceback.format_exc()}")
        return fail(str(e))

# ─── F10: 功能清单 ───
@app.post("/query/list_capabilities")
async def f10_capabilities(request: Request):
    verify_key(request)
    caps = [
        ["C1","机台状态/运行模式","fab_query","machine_status"],
        ["C2","Lot 查询/追踪","fab_query","lot_info"],
        ["C3","报警/告警/异常","fab_query","machine_alarms"],
        ["C4","温度/趋势/事件时间线","fab_query","event_timeline"],
        ["C5","产量/晶圆统计","fab_query","yield_stats"],
        ["C6","工艺/配方/Recipe","fab_query","recipe_info"],
        ["C7","MES Lot 信息（管理员）","fab_admin","mes_lot_info"],
        ["C8","导出报警报表（管理员）","fab_admin","export_alarm_report"],
        ["C9","生成故障工单（管理员）","fab_admin","generate_work_order"],
        ["C10","功能清单","fab_query","list_capabilities"],
    ]
    answer = "我目前支持以下 10 类功能，请附上机台ID或Lot ID即可查询。"
    return ok(answer, table(["分类","功能描述","对应工具","action"], caps))

# ========== 合并分发端点（收敛 Dify 工具位：10 → 2） ==========
# 【背景】OpenAPI 里有几个 path，Dify 就注册几个工具。原来 F1~F10 = 10 个 path，
#         一次性占满 Dify Agent 的工具位，导致 LOG 捞取等其他工具挂不上去。
# 【方案】原 10 个端点保留不动（n8n 旧工作流、自测脚本的直连层仍可用，便于回退），
#         另加 2 个分发端点，用 action 参数路由到同一批 handler：
#             读类   → /query/fab_query  （F1~F6 + F10）
#             管理类 → /query/fab_admin  （F7 F8 F9，写操作与导出）
# 【为什么能直接转交 request】FastAPI 的 Request.json() 首次读取后会把内容缓存在
#         request._body 上，同一个 Request 可被重复读取。所以分发层读一次 body 拿
#         action，再把原 request 交给下游 handler，handler 里的 await request.json()
#         命中缓存、不会因为 body 流already-consumed 而拿到空值。
#         => 业务逻辑零改动，不存在两套实现走偏的风险。

_QUERY_ACTIONS = {
    "machine_status":    f1_machine_status,
    "lot_info":          f2_lot_info,
    "machine_alarms":    f3_alarms,
    "event_timeline":    f4_events,
    "yield_stats":       f5_yield,
    "recipe_info":       f6_recipe,
    "list_capabilities": f10_capabilities,
}

_ADMIN_ACTIONS = {
    "mes_lot_info":        f7_mes_lot,
    "export_alarm_report": f8_export,
    "generate_work_order": f9_work_order,
}

async def _dispatch(request: Request, registry: dict, group: str):
    """按 action 路由到既有 handler；未知 action 走标准 fail() 而非 500，
    这样 Dify 侧能拿到可读的 answer 文本，模型可以据此自我纠正重试。"""
    verify_key(request)
    try:
        body = await request.json()
    except Exception:
        body = {}
    action = str(body.get("action") or "").strip()
    avail = "、".join(registry.keys())
    if not action:
        return fail(f"缺少 action 参数。{group} 支持的 action：{avail}")
    handler = registry.get(action)
    if handler is None:
        return fail(f"未知 action「{action}」。{group} 支持的 action：{avail}")
    logger.info(f"[dispatch] {group} action={action} body={body}")
    return await handler(request)

@app.post("/query/fab_query")
async def fab_query(request: Request):
    """厂务数据查询（读类，合并 F1~F6 + F10）"""
    return await _dispatch(request, _QUERY_ACTIONS, "fab_query")

@app.post("/query/fab_admin")
async def fab_admin(request: Request):
    """管理员操作（合并 F7 MES查询 / F8 导出报表 / F9 生成工单）"""
    return await _dispatch(request, _ADMIN_ACTIONS, "fab_admin")

# ─── CSV 下载 ───
@app.get("/download/alarms")
def download_alarms(machine_id: str = "", days: int = 7):
    """导出报警 CSV"""
    try:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        params = {"since": since}
        where = "timestamp >= :since"
        if machine_id:
            where += " AND machine_id = :mid"
            params["mid"] = machine_id
        sql = f"""SELECT id, machine_id, timestamp, alarm_code, description, "LEVEL", resolved, lot_id
                 FROM alarms WHERE {where} ORDER BY timestamp DESC"""
        cols, rows = exec_query(sql, params)
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID","机台","时间","报警码","描述","等级","已解决","Lot"])
        for r in rows:
            writer.writerow([str(c) if c is not None else "" for c in r])
        content = output.getvalue()
        return JSONResponse(content={
            "ok": True,
            "filename": f"alarms_{machine_id or 'all'}_{days}d.csv",
            "content": content,
            "row_count": len(rows),
        })
    except Exception as e:
        return JSONResponse(content={"ok": False, "detail": str(e)})

# ========== 启动 ==========
if __name__ == "__main__":
    logger.info(f"FabTwin DB Proxy 启动: port={LISTEN_PORT}, oracle={ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}")
    uvicorn.run(app, host="0.0.0.0", port=LISTEN_PORT)
