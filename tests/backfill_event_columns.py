# -*- coding: utf-8 -*-
"""历史回填：DT_EVENT_RAW 物化列 lot_id / event_name / alarm_code（雷区A治理④）。

背景：ver2.13 给 DT_EVENT_RAW 加了三个物化列，ORM 新写入由 before_insert
监听器自动填充；存量历史行由本脚本回填，之后 14 处 payload_json LIKE 查询
才切换为等值过滤（lots.py / ai_tools.py）。

策略：
- 按 raw_id 字典序区间推进（PK 索引有序扫描），进度写同目录
  backfill_progress.txt，中断后可续跑
- 每批 BATCH 行：读 (raw_id, payload_json) → Python json.loads 精确提取
  （兼容 VFEI 信封 {"data":{...}} 与平铺）→ executemany 批量 UPDATE
- 不用一次性大 UPDATE：10M 行会产生数 GB undo，有撑爆表空间风险
- 每行无条件覆盖三列（幂等）；payload 非 JSON 的行置 NULL 跳过

用法：
    python tests\backfill_event_columns.py                    # 全量回填（断点续跑）
    python tests\backfill_event_columns.py --verify           # 只校验：统计未回填/不一致行数
    python tests\backfill_event_columns.py --max-batches 3    # 只跑 3 批（小批验证/分窗口执行）

连接参数与 backend/config.py 默认值一致，可用同名环境变量覆盖。
10M 行本地 XE 实测约 30~60 分钟，建议业务低峰执行。
"""
import oracledb, json, os, sys, time, datetime

# 关键：默认 fetch_lobs=True 时 payload_json 返回 LOB 对象而非 str，
# json.loads 直接失败 → 全部行被置 NULL。置 False 后 CLOB 直接取 str。
oracledb.defaults.fetch_lobs = False

PROGRESS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backfill_progress.txt")
BATCH = 20_000

ORACLE_USER = os.getenv("ORACLE_USER", "fabtwin")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "fabtwin")
ORACLE_HOST = os.getenv("ORACLE_HOST", "localhost")
ORACLE_PORT = os.getenv("ORACLE_PORT", "1521")
ORACLE_SERVICE = os.getenv("ORACLE_SERVICE", "ORCLPDB")
DSN = f"{ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}"


def log(msg):
    line = f"{datetime.datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    with open(PROGRESS, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def extract(payload_text):
    """与 backend/models.py extract_payload_fields 同逻辑（脚本独立不 import backend）。"""
    if not payload_text:
        return None, None, None
    try:
        p = json.loads(payload_text)
    except Exception:
        return None, None, None
    if not isinstance(p, dict):
        return None, None, None
    d = p.get("data") if isinstance(p.get("data"), dict) else p

    def _norm(v, maxlen):
        """归一：None/空串/'NULL'/'null' → None；其余截断到列宽。
        灌库数据存在 "lot_id": "NULL" 字符串脏数据，不能当真实 lot。"""
        if v is None:
            return None
        s = str(v).strip()
        if not s or s.upper() == "NULL":
            return None
        return s[:maxlen]

    return (
        _norm(d.get("lot_id"), 64),
        _norm(d.get("event_name"), 128),
        _norm(d.get("alarm_code"), 64),
    )


def main():
    verify_only = "--verify" in sys.argv
    max_batches = 0  # 0 = 不限
    if "--max-batches" in sys.argv:
        i = sys.argv.index("--max-batches")
        max_batches = int(sys.argv[i + 1])
    conn = oracledb.connect(user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=DSN)
    cur = conn.cursor()

    # 物化列存在性检查（须先起过后端让 init_db 幂等加列，或由 DBA 执行增量脚本）
    cur.execute(
        "SELECT COUNT(*) FROM USER_TAB_COLUMNS "
        "WHERE TABLE_NAME='DT_EVENT_RAW' AND COLUMN_NAME IN ('LOT_ID','EVENT_NAME','ALARM_CODE')"
    )
    if cur.fetchone()[0] < 3:
        log("ABORT: DT_EVENT_RAW 缺物化列，先启动一次后端（init_db 自动加列）"
            "或由 DBA 执行 sql/v2.13_add_event_extract_columns.sql")
        raise SystemExit(1)

    if verify_only:
        cur.execute("SELECT COUNT(*) FROM dt_event_raw WHERE lot_id IS NULL AND event_name IS NULL AND alarm_code IS NULL")
        null_rows = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM dt_event_raw WHERE lot_id IS NOT NULL")
        lot_rows = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM dt_event_raw WHERE event_name IS NOT NULL")
        evt_rows = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM dt_event_raw WHERE alarm_code IS NOT NULL")
        alarm_rows = cur.fetchone()[0]
        log(f"VERIFY null_all={null_rows} lot={lot_rows} event_name={evt_rows} alarm={alarm_rows}")
        log("VERIFY 说明：null_all 含 payload 本就无此三键的行（如灌库数据无 event_name），"
            "不等于未回填；判断回填完整性看进度文件是否已到末行。")
        return

    # 断点：上次推进到的 raw_id
    last = ""
    if os.path.exists(PROGRESS):
        with open(PROGRESS, "r", encoding="utf-8") as f:
            for line in f:
                if " LAST=" in line:
                    last = line.strip().rsplit(" LAST=", 1)[1]

    cur.execute("SELECT COUNT(*) FROM dt_event_raw")
    total = cur.fetchone()[0]
    log(f"START total={total} resume_from={'<begin>' if not last else last}")

    # 注意：Oracle 空字符串 = NULL，首批不能写 raw_id > ''（比较 NULL 恒为假），
    # 因此首批用无下限 SQL，有断点后才用区间 SQL。
    select_first = (
        "SELECT raw_id, payload_json FROM ("
        "  SELECT raw_id, payload_json FROM dt_event_raw ORDER BY raw_id"
        ") WHERE ROWNUM <= :batch"
    )
    select_next = (
        "SELECT raw_id, payload_json FROM ("
        "  SELECT raw_id, payload_json FROM dt_event_raw WHERE raw_id > :last ORDER BY raw_id"
        ") WHERE ROWNUM <= :batch"
    )
    update_sql = (
        "UPDATE dt_event_raw SET lot_id=:1, event_name=:2, alarm_code=:3 WHERE raw_id=:4"
    )

    t0 = time.time()
    done = 0
    batches = 0
    while True:
        if max_batches and batches >= max_batches:
            log(f"STOP max-batches={max_batches} reached done={done} LAST={last}（可再次执行续跑）")
            return
        if last:
            cur.execute(select_next, {"last": last, "batch": BATCH})
        else:
            cur.execute(select_first, {"batch": BATCH})
        rows = cur.fetchall()
        if not rows:
            break
        batches += 1
        updates = []
        for raw_id, payload in rows:
            lot, evt, alarm = extract(payload)
            updates.append((lot, evt, alarm, raw_id))
        cur.executemany(update_sql, updates)
        conn.commit()
        last = rows[-1][0]
        done += len(rows)
        if done % (BATCH * 5) == 0 or len(rows) < BATCH:
            rate = done / max(time.time() - t0, 1)
            log(f"PROGRESS done={done} rate={rate:.0f}/s LAST={last}")

    log(f"DONE backfilled={done} elapsed={time.time()-t0:.0f}s LAST={last}")
    log("下一步：① 切换 lots.py/ai_tools.py 查询（如代码已含等值过滤则直接发版）"
        "② DBA 执行 sql/v2.13_add_event_extract_columns.sql 的触发器（WinForm 直写兜底）")


if __name__ == "__main__":
    main()
