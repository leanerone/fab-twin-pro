# -*- coding: utf-8 -*-
"""灌库脚本：dt_event_raw 灌至 1000 万行，模拟量产数据规模。

用途：换机/新环境性能验收——小数据量下性能实测严重失真（1.5 万行
冷态 420ms 的错觉，真 1000 万下是 33.8s），性能验收必须以量产同量级
数据为准。本地 Oracle XE 实测灌满约 43 分钟（4000-6000 行/s）。

- 57 台真实 tool_id 均匀分布（取自库内 distinct tool_id）
- 时间跨最近 30 天
- payload 250~400B VFEI 风格（信封/平铺混合）
- 每批 5 万 executemany，每 10 万 commit，进度写本目录 seed_progress.txt
- 安全阀：user_segments 超 10GB 即中止（XE 上限 12GB）
- 幂等：按现有行数补足到 TARGET_TOTAL，可中断重跑

连接参数与 backend/config.py 默认值一致，可用同名环境变量覆盖。
"""
import oracledb, json, random, time, datetime, os

PROGRESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_progress.txt")
TARGET_TOTAL = 10_000_000
BATCH = 50_000
COMMIT_EVERY = 100_000
SIZE_GUARD_GB = 10.0

ORACLE_USER = os.getenv("ORACLE_USER", "fabtwin")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "fabtwin")
ORACLE_HOST = os.getenv("ORACLE_HOST", "localhost")
ORACLE_PORT = os.getenv("ORACLE_PORT", "1521")
ORACLE_SERVICE = os.getenv("ORACLE_SERVICE", "ORCLPDB")
DSN = f"{ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}"

def log(msg):
    with open(PROGRESS, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now():%H:%M:%S} {msg}\n")

random.seed(42)
conn = oracledb.connect(user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=DSN)
conn.autocommit = False
cur = conn.cursor()

cur.execute("select count(*) from dt_event_raw")
base = cur.fetchone()[0]
need = TARGET_TOTAL - base
cur.execute("select distinct tool_id from dt_event_raw")
tools = [r[0] for r in cur.fetchall()]
log(f"START base={base} need={need} tools={len(tools)}")
if need <= 0:
    log("ALREADY_DONE")
    raise SystemExit

now = datetime.datetime.now()
span_days = 30
# ver2.13: 直写 SQL 不触发 ORM before_insert 监听器，物化列在此显式填
#（lot_id 取自 body；event_name/alarm_code 灌库数据本无此键，留 NULL）
sql = ("insert into dt_event_raw "
       "(raw_id, tool_id, source_system, source_message_id, received_ts_utc, event_ts_utc, payload_json, parse_status, error_message, lot_id, event_name, alarm_code) "
       "values (:1, :2, :3, :4, :5, :6, :7, :8, :9, :10, :11, :12)")

EVENT_TYPES = ["STATE", "SENSOR", "TRANSFER", "ALARM"]
STATES = ["RUN", "IDLE", "DOWN", "PM", "SETUP"]

def make_row(i):
    tool = random.choice(tools)
    ts = now - datetime.timedelta(seconds=random.uniform(0, span_days * 86400))
    ts_s = ts.strftime("%Y-%m-%d %H:%M:%S")
    evt_ts = None if random.random() < 0.3 else (ts - datetime.timedelta(milliseconds=random.randint(50, 900))).strftime("%Y-%m-%d %H:%M:%S")
    et = random.choices(EVENT_TYPES, weights=[40, 40, 15, 5])[0]
    body = {
        "event_type": et,
        "tool_id": tool,
        "state": random.choice(STATES),
        "lot_id": f"LOT{random.randint(100000, 999999)}",
        "recipe": f"RCP-{random.randint(1, 120)}",
        "step": random.randint(1, 40),
        "chamber": random.choice(["A", "B", "C", "D"]),
        "temp": round(random.uniform(20, 450), 2),
        "pressure": round(random.uniform(0.1, 760), 2),
        "msg": f"{et} report from {tool} seq {i}",
    }
    if random.random() < 0.5:
        payload = json.dumps({"msg_type": "VFEI", "version": "1.0", "data": body}, separators=(",", ":"))
    else:
        payload = json.dumps(body, separators=(",", ":"))
    return (f"SEED{i:010d}", tool, "MES_SIM", f"MSG{i:010d}", ts_s, evt_ts, payload, "NEW", None,
            body.get("lot_id"), body.get("event_name"), body.get("alarm_code"))

t0 = time.time()
inserted = 0
since_commit = 0
rows = []
seq_base = base + 1
try:
    while inserted < need:
        rows.clear()
        n = min(BATCH, need - inserted)
        for k in range(n):
            rows.append(make_row(seq_base + inserted + k))
        cur.executemany(sql, rows)
        inserted += n
        since_commit += n
        if since_commit >= COMMIT_EVERY:
            conn.commit()
            since_commit = 0
            rate = inserted / max(time.time() - t0, 0.1)
            cur.execute("select round(sum(bytes)/1024/1024/1024,2) from user_segments")
            gb = cur.fetchone()[0]
            log(f"progress inserted={inserted} total={base+inserted} rate={rate:.0f}/s gb={gb}")
            print(f"progress inserted={inserted} rate={rate:.0f}/s gb={gb}", flush=True)
            if gb and gb > SIZE_GUARD_GB:
                log(f"ABORT size guard {gb}GB > {SIZE_GUARD_GB}GB")
                break
    conn.commit()
    cur.execute("select count(*) from dt_event_raw")
    final = cur.fetchone()[0]
    log(f"DONE final={final} elapsed={time.time()-t0:.0f}s")
    print(f"DONE final={final} elapsed={time.time()-t0:.0f}s")
except Exception as e:
    conn.rollback()
    log(f"ERROR {type(e).__name__}: {e}")
    raise
