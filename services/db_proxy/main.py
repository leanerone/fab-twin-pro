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
    """将 rows 转为 list[dict]"""
    result = []
    for r in rows:
        item = {}
        for i, c in enumerate(cols):
            val = r[i]
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

# ─── F1: 机台状态 ───
@app.post("/query/machine_status")
async def f1_machine_status(request: Request):
    verify_key(request)
    body = await request.json()
    machine_id = body.get("machine_id", "")
    try:
        if machine_id:
            sql = """SELECT id, name, model, state, process_type, chamber_count,
                           wafer_count, alarm_count, updated_at
                    FROM machines WHERE id = :mid"""
            cols, rows = exec_query(sql, {"mid": machine_id})
            if not rows:
                return ok(f"未找到机台 {machine_id}")
            d = rows_to_list(cols, rows)[0]
            answer = f"机台 {d['id']}（{d.get('name','')}）当前状态: {d.get('state','')}，" \
                     f"型号 {d.get('model','')}，{d.get('chamber_count','')} Chamber，" \
                     f"累计加工 {d.get('wafer_count',0)} 片晶圆，告警 {d.get('alarm_count',0)} 次。"
            return ok(answer,
                      table(["机台ID","名称","状态","型号","Chamber数","晶圆数","告警数"],
                            [[d.get('id',''), d.get('name',''), d.get('state',''),
                              d.get('model',''), d.get('chamber_count',''),
                              d.get('wafer_count',0), d.get('alarm_count',0)]]),
                      jump_timestamp=d.get('updated_at'),
                      jump_machine_id=d.get('id'))
        else:
            sql = """SELECT id, name, model, state, process_type, chamber_count,
                           wafer_count, alarm_count, updated_at
                    FROM machines ORDER BY id"""
            cols, rows = exec_query(sql)
            data = rows_to_list(cols, rows)
            answer = f"全厂共 {len(data)} 台机台。" + \
                     "; ".join([f"{d['id']}={d.get('state','')}" for d in data[:5]])
            return ok(answer,
                      table(["机台ID","名称","状态","型号","Chamber数","晶圆数","告警数"],
                            [[d.get('id',''), d.get('name',''), d.get('state',''),
                              d.get('model',''), d.get('chamber_count',''),
                              d.get('wafer_count',0), d.get('alarm_count',0)] for d in data]))
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
            sql = """SELECT id, machine_id, product, wafer_count, status,
                           start_time, end_time, recipe_id
                    FROM lots WHERE machine_id = :mid ORDER BY start_time DESC FETCH FIRST 20 ROWS ONLY"""
            cols, rows = exec_query(sql, {"mid": machine_id})
        else:
            sql = """SELECT id, machine_id, product, wafer_count, status,
                           start_time, end_time, recipe_id
                    FROM lots ORDER BY start_time DESC FETCH FIRST 20 ROWS ONLY"""
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

# ─── F3: 报警统计 ───
@app.post("/query/machine_alarms")
async def f3_alarms(request: Request):
    verify_key(request)
    body = await request.json()
    machine_id = body.get("machine_id", "")
    severity = body.get("severity", "")
    days = int(body.get("days", 7))
    try:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        params = {"since": since}
        where = "timestamp >= :since"
        if machine_id:
            where += " AND machine_id = :mid"
            params["mid"] = machine_id
        if severity:
            where += ' AND "LEVEL" = :sev'
            params["sev"] = severity
        sql = f"""SELECT id, machine_id, timestamp, alarm_code, description, "LEVEL", resolved, lot_id
                 FROM alarms WHERE {where} ORDER BY timestamp DESC FETCH FIRST 200 ROWS ONLY"""
        cols, rows = exec_query(sql, params)
        data = rows_to_list(cols, rows)
        if not data:
            return ok(f"近 {days} 天无报警记录（machine_id={machine_id}, severity={severity}）")
        crit_count = sum(1 for d in data if d.get('level') == 'crit')
        answer = f"近 {days} 天共 {len(data)} 条报警（严重 {crit_count} 条）。"
        return ok(answer,
                  table(["ID","机台","时间","报警码","描述","等级","已解决","Lot"],
                        [[d.get('id',''), d.get('machine_id',''), d.get('timestamp',''),
                          d.get('alarm_code',''), d.get('description',''),
                          d.get('level',''), d.get('resolved',''), d.get('lot_id','')] for d in data]),
                  jump_timestamp=data[0].get('timestamp'),
                  jump_machine_id=machine_id or data[0].get('machine_id'))
    except Exception as e:
        logger.error(f"F3 error: {e}\n{traceback.format_exc()}")
        return fail(str(e))

# ─── F4: 事件时间线 ───
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
        sql = """SELECT id, machine_id, timestamp, event_type, event_code, description, "LEVEL", metric, value, lot_id
                 FROM machine_events
                 WHERE machine_id = :mid AND timestamp >= :since
                 ORDER BY timestamp DESC FETCH FIRST 200 ROWS ONLY"""
        cols, rows = exec_query(sql, {"mid": machine_id, "since": since})
        data = rows_to_list(cols, rows)
        if not data:
            return ok(f"机台 {machine_id} 在 {time_range} 范围内无事件记录。")
        answer = f"机台 {machine_id} 共 {len(data)} 条事件。"
        return ok(answer,
                  table(["ID","机台","时间","类型","代码","描述","等级","指标","值","Lot"],
                        [[d.get('id',''), d.get('machine_id',''), d.get('timestamp',''),
                          d.get('event_type',''), d.get('event_code',''),
                          d.get('description',''), d.get('level',''),
                          d.get('metric',''), d.get('value',''), d.get('lot_id','')] for d in data]),
                  jump_timestamp=data[0].get('timestamp'),
                  jump_machine_id=machine_id)
    except Exception as e:
        logger.error(f"F4 error: {e}\n{traceback.format_exc()}")
        return fail(str(e))

# ─── F5: 产量统计 ───
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
        since = now.strftime("%Y-%m-%d 00:00:00") if time_range == "today" else (now - timedelta(days=7)).strftime("%Y-%m-%d 00:00:00")
        sql = """SELECT COUNT(*) as lot_count,
                       COALESCE(SUM(wafer_count), 0) as total_wafers,
                       SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as done_count,
                       SUM(CASE WHEN status = 'run' THEN 1 ELSE 0 END) as running_count,
                       SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending_count
                FROM lots
                WHERE machine_id = :mid AND (start_time >= :since OR :since IS NULL)"""
        cols, rows = exec_query(sql, {"mid": machine_id, "since": since})
        d = rows_to_list(cols, rows)[0]
        total = d.get('lot_count', 0)
        wafers = d.get('total_wafers', 0)
        done = d.get('done_count', 0)
        running = d.get('running_count', 0)
        rate = round(done / total * 100, 1) if total > 0 else 0
        answer = f"机台 {machine_id} 今日共 {total} 个 Lot，{wafers} 片晶圆；完成 {done}（{rate}%），进行中 {running}。"
        return ok(answer,
                  table(["Lot总数","晶圆总数","已完成","进行中","待处理","完成率"],
                        [[total, wafers, done, running, d.get('pending_count',0), f"{rate}%"]]),
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

# ─── F7: MES Lot 详情（管理员） ───
@app.post("/query/mes_lot_info")
async def f7_mes_lot(request: Request):
    verify_key(request)
    body = await request.json()
    lot_id = body.get("lot_id", "")
    if not lot_id:
        return fail("lot_id 必填")
    try:
        # 复用 lots 表 + 关联事件
        sql = """SELECT l.id, l.machine_id, l.product, l.wafer_count, l.status,
                       l.start_time, l.end_time, l.recipe_id
                FROM lots l WHERE l.id = :lid"""
        cols, rows = exec_query(sql, {"lid": lot_id})
        data = rows_to_list(cols, rows)
        if not data:
            return ok(f"未找到 Lot {lot_id}。")
        d = data[0]
        # 查该 Lot 相关事件
        sql2 = """SELECT timestamp, event_code, description, "LEVEL"
                  FROM machine_events WHERE lot_id = :lid ORDER BY timestamp DESC FETCH FIRST 10 ROWS ONLY"""
        cols2, rows2 = exec_query(sql2, {"lid": lot_id})
        events = rows_to_list(cols2, rows2)
        answer = f"Lot {lot_id}: 产品 {d.get('product','')}，{d.get('wafer_count',0)} 片，" \
                 f"状态 {d.get('status','')}，机台 {d.get('machine_id','')}，" \
                 f"配方 {d.get('recipe_id','')}，关联事件 {len(events)} 条。"
        return ok(answer,
                  table(["Lot ID","机台","产品","晶圆数","状态","开始时间","结束时间","配方"],
                        [[d.get('id',''), d.get('machine_id',''), d.get('product',''),
                          d.get('wafer_count',0), d.get('status',''),
                          d.get('start_time',''), d.get('end_time',''), d.get('recipe_id','')]]),
                  jump_timestamp=d.get('start_time'),
                  jump_machine_id=d.get('machine_id'))
    except Exception as e:
        logger.error(f"F7 error: {e}\n{traceback.format_exc()}")
        return fail(str(e))

# ─── F8: 导出报警报表（管理员） ───
@app.post("/query/export_alarm_report")
async def f8_export(request: Request):
    verify_key(request)
    body = await request.json()
    machine_id = body.get("machine_id", "")
    days = int(body.get("days", 7))
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
        data = rows_to_list(cols, rows)
        total = len(data)
        answer = f"已生成报警报表：近 {days} 天共 {total} 条记录" + \
                 (f"（机台 {machine_id}）" if machine_id else "（全厂）") + \
                 f"，可下载 CSV 格式。"
        # 生成 CSV 下载 URL（前端可直接用 sources[0].download_url）
        download_url = f"/download/alarms?machine_id={machine_id}&days={days}"
        return ok(answer,
                  table(["ID","机台","时间","报警码","描述","等级","已解决","Lot"],
                        [[d.get('id',''), d.get('machine_id',''), d.get('timestamp',''),
                          d.get('alarm_code',''), d.get('description',''),
                          d.get('level',''), d.get('resolved',''), d.get('lot_id','')] for d in data[:50]]),
                  jump_machine_id=machine_id,
                  sources=[{"type":"db_proxy","workflow":"export_alarm_report",
                            "row_count":total,"download_url":download_url}])
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
        ["C1","机台状态/运行模式","get_machine_status"],
        ["C2","Lot 查询/追踪","get_lot_info"],
        ["C3","报警/告警/异常","get_machine_alarms"],
        ["C4","温度/趋势/事件时间线","get_event_timeline"],
        ["C5","产量/晶圆统计","get_yield_stats"],
        ["C6","工艺/配方/Recipe","get_recipe_info"],
        ["C7","MES Lot 信息（管理员）","get_mes_lot_info"],
        ["C8","导出报警报表（管理员）","export_alarm_report"],
        ["C9","生成故障工单（管理员）","generate_work_order"],
        ["C10","功能清单","list_capabilities"],
    ]
    answer = "我目前支持以下 10 类功能，请附上机台ID或Lot ID即可查询。"
    return ok(answer, table(["分类","功能描述","对应工具"], caps))

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
