"""
FabTwin DB Proxy — 独立数据库代理服务
用于 Dify/n8n 查询 Oracle 和 Informix，与 FabTwin 网站后端解耦

启动方式：
  pip install fastapi uvicorn oracledb pyodbc
  python db_proxy.py

环境变量：
  # Oracle (FabTwin 数据)
  ORACLE_HOST=localhost
  ORACLE_PORT=1521
  ORACLE_SERVICE=orcl
  ORACLE_USER=fabtwin
  ORACLE_PASSWORD=xxx

  # Informix (RCMS/MES)
  INFORMIX_SERVER=rcms_server
  INFORMIX_HOST=localhost
  INFORMIX_PORT=9088
  INFORMIX_DATABASE=rcms
  INFORMIX_USER=admin
  INFORMIX_PASSWORD=xxx

  # 安全
  DB_PROXY_PORT=8010
  DB_PROXY_TOKEN=your-secret-token-here
"""

import os
import json
import traceback
from datetime import datetime

import oracledb

# ============================================================
# 配置
# ============================================================
ORACLE_HOST = os.getenv("ORACLE_HOST", "localhost")
ORACLE_PORT = int(os.getenv("ORACLE_PORT", "1521"))
ORACLE_SERVICE = os.getenv("ORACLE_SERVICE", "orcl")
ORACLE_USER = os.getenv("ORACLE_USER", "fabtwin")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "")

INFORMIX_SERVER = os.getenv("INFORMIX_SERVER", "")
INFORMIX_HOST = os.getenv("INFORMIX_HOST", "localhost")
INFORMIX_PORT = int(os.getenv("INFORMIX_PORT", "9088"))
INFORMIX_DATABASE = os.getenv("INFORMIX_DATABASE", "")
INFORMIX_USER = os.getenv("INFORMIX_USER", "")
INFORMIX_PASSWORD = os.getenv("INFORMIX_PASSWORD", "")

DB_PROXY_PORT = int(os.getenv("DB_PROXY_PORT", "8010"))
DB_PROXY_TOKEN = os.getenv("DB_PROXY_TOKEN", "")

# Oracle Thick 模式（10g/11g 需要）
ORACLE_CLIENT_DIR = os.getenv("ORACLE_CLIENT_DIR", "")
if ORACLE_CLIENT_DIR:
    oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_DIR)

# ============================================================
# Oracle 连接
# ============================================================
def get_oracle_conn():
    dsn = oracledb.makedsn(ORACLE_HOST, ORACLE_PORT, service_name=ORACLE_SERVICE)
    return oracledb.connect(user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=dsn)

def oracle_query(sql, params=None):
    """执行 Oracle 查询，返回 dict 列表"""
    conn = get_oracle_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or {})
        cols = [c[0].lower() for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        # 序列化 datetime
        for r in rows:
            for k, v in r.items():
                if isinstance(v, datetime):
                    r[k] = v.strftime("%Y-%m-%d %H:%M:%S")
        return rows
    finally:
        conn.close()

# ============================================================
# Informix 连接（使用 pyodbc + Informix ODBC 驱动）
# ============================================================
def get_informix_conn():
    import pyodbc
    conn_str = (
        f"DRIVER={{IBM INFORMIX ODBC DRIVER}};"
        f"SERVER={INFORMIX_SERVER};"
        f"HOST={INFORMIX_HOST};"
        f"SERVICE={INFORMIX_PORT};"
        f"DATABASE={INFORMIX_DATABASE};"
        f"UID={INFORMIX_USER};"
        f"PWD={INFORMIX_PASSWORD};"
    )
    return pyodbc.connect(conn_str)

def informix_query(sql, params=None):
    """执行 Informix 查询，返回 dict 列表"""
    conn = get_informix_conn()
    try:
        cur = conn.cursor()
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        cols = [c[0].lower() for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        for r in rows:
            for k, v in r.items():
                if isinstance(v, datetime):
                    r[k] = v.strftime("%Y-%m-%d %H:%M:%S")
        return rows
    finally:
        conn.close()

# ============================================================
# API 端点
# ============================================================
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="FabTwin DB Proxy", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def check_token(authorization: str = Header(None)):
    """验证请求 token"""
    if not DB_PROXY_TOKEN:
        return  # 未配置 token 则跳过验证
    if not authorization or authorization != f"Bearer {DB_PROXY_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.get("/health")
def health():
    """健康检查"""
    return {"status": "ok", "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

# ---------- Oracle 查询 ----------

@app.post("/alarms")
async def query_alarms(req: Request, authorization: str = Header(None)):
    """查询机台告警 (DT_EVENT_RAW)"""
    check_token(authorization)
    body = await req.json()
    machine_id = body.get("machine_id", "")
    limit = int(body.get("limit", 20))
    sql = """
        SELECT event_ts_utc AS event_time, machine_id, event_name, event_value
        FROM DT_EVENT_RAW
        WHERE machine_id = :machine_id
          AND parse_status = 'PARSED'
          AND (UPPER(event_name) LIKE '%ALARM%' OR UPPER(event_name) LIKE '%ERROR%')
        ORDER BY event_ts_utc DESC
        FETCH FIRST :limit ROWS ONLY
    """
    rows = oracle_query(sql, {"machine_id": machine_id, "limit": limit})
    return {"alarms": rows, "count": len(rows), "machine_id": machine_id}

@app.post("/status")
async def query_machine_status(req: Request, authorization: str = Header(None)):
    """查询机台状态 (MACHINES)"""
    check_token(authorization)
    body = await req.json()
    machine_id = body.get("machine_id", "")
    sql = """
        SELECT id, model, status, current_lot_id, last_event_ts
        FROM MACHINES WHERE id = :machine_id
    """
    rows = oracle_query(sql, {"machine_id": machine_id})
    return {"machine": rows[0] if rows else None, "machine_id": machine_id}

@app.post("/events")
async def query_events(req: Request, authorization: str = Header(None)):
    """查询机台事件时间线 (DT_EVENT_RAW)"""
    check_token(authorization)
    body = await req.json()
    machine_id = body.get("machine_id", "")
    limit = int(body.get("limit", 50))
    sql = """
        SELECT event_ts_utc AS event_time, machine_id, event_name, event_value
        FROM DT_EVENT_RAW
        WHERE machine_id = :machine_id
          AND parse_status = 'PARSED'
        ORDER BY event_ts_utc DESC
        FETCH FIRST :limit ROWS ONLY
    """
    rows = oracle_query(sql, {"machine_id": machine_id, "limit": limit})
    return {"events": rows, "count": len(rows), "machine_id": machine_id}

@app.post("/lots")
async def query_lots(req: Request, authorization: str = Header(None)):
    """查询 Lot 信息 (LOTS)"""
    check_token(authorization)
    body = await req.json()
    machine_id = body.get("machine_id", "")
    lot_id = body.get("lot_id", "")
    if lot_id:
        sql = "SELECT * FROM LOTS WHERE lot_id = :lot_id"
        rows = oracle_query(sql, {"lot_id": lot_id})
    else:
        sql = "SELECT * FROM LOTS WHERE machine_id = :machine_id ORDER BY start_time DESC FETCH FIRST 20 ROWS ONLY"
        rows = oracle_query(sql, {"machine_id": machine_id})
    return {"lots": rows, "count": len(rows)}

@app.post("/yield")
async def query_yield(req: Request, authorization: str = Header(None)):
    """查询产量统计"""
    check_token(authorization)
    body = await req.json()
    machine_id = body.get("machine_id", "")
    if machine_id:
        sql = """
            SELECT machine_id,
                   COUNT(*) AS lot_count,
                   SUM(wafer_qty) AS total_wafers
            FROM LOTS
            WHERE machine_id = :machine_id AND status = 'COMPLETED'
            GROUP BY machine_id
        """
        rows = oracle_query(sql, {"machine_id": machine_id})
    else:
        sql = """
            SELECT machine_id,
                   COUNT(*) AS lot_count,
                   SUM(wafer_qty) AS total_wafers
            FROM LOTS
            WHERE status = 'COMPLETED'
            GROUP BY machine_id
        """
        rows = oracle_query(sql)
    return {"yield_stats": rows}

# ---------- Informix 查询 (RCMS/MES) ----------

@app.post("/rcms-maintenance")
async def query_rcms_maintenance(req: Request, authorization: str = Header(None)):
    """查询 RCMS 维修记录 (Informix)
    注意：表名和字段名需按实际 RCMS 数据库结构调整
    """
    check_token(authorization)
    body = await req.json()
    machine_id = body.get("machine_id", "")
    # ⚠️ 以下 SQL 需要按实际 RCMS 表结构调整
    sql = """
        SELECT FIRST 10 pm_type, pm_date, technician, description
        FROM maintenance_log
        WHERE machine_id = ?
        ORDER BY pm_date DESC
    """
    try:
        rows = informix_query(sql, [machine_id])
        return {"records": rows, "count": len(rows), "machine_id": machine_id}
    except Exception as e:
        return {"error": str(e), "hint": "请确认 RCMS 表名和字段名是否正确"}

@app.post("/mes-lot")
async def query_mes_lot(req: Request, authorization: str = Header(None)):
    """查询 MES Lot 信息 (Informix)
    注意：表名和字段名需按实际 MES 数据库结构调整
    """
    check_token(authorization)
    body = await req.json()
    lot_id = body.get("lot_id", "")
    # ⚠️ 以下 SQL 需要按实际 MES 表结构调整
    sql = """
        SELECT FIRST 1 lot_id, product_id, current_step, status, wafer_qty
        FROM lot_info
        WHERE lot_id = ?
    """
    try:
        rows = informix_query(sql, [lot_id])
        return {"lot_info": rows[0] if rows else None, "lot_id": lot_id}
    except Exception as e:
        return {"error": str(e), "hint": "请确认 MES 表名和字段名是否正确"}

# ============================================================
# 启动
# ============================================================
if __name__ == "__main__":
    import uvicorn
    print(f"[DB Proxy] 启动中... 端口 {DB_PROXY_PORT}")
    print(f"[DB Proxy] Oracle: {ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}")
    print(f"[DB Proxy] Informix: {INFORMIX_HOST}:{INFORMIX_PORT}/{INFORMIX_DATABASE}" if INFORMIX_HOST else "[DB Proxy] Informix: 未配置")
    uvicorn.run(app, host="0.0.0.0", port=DB_PROXY_PORT)
