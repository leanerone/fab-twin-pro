# -*- coding: utf-8 -*-
r"""
为 OXE-1 补充指定日期的告警演示数据（写入 DT_EVENT_RAW）
==================================================================
背景：量产 OXE 的 ALARM_REPORT 报文里 alarm_text 只有 "P2"、alarm_id 为 null，
      回放面板的 Alarm 页签列出来看不出所以然。本脚本补一批带**中文告警描述**
      和**告警编号**的数据，用于查看告警页签的排版、严重等级配色与内容换行效果。

写入范围（严格限定，不动其他数据）：
  - 表    ：DT_EVENT_RAW
  - 机台  ：OXE-1
  - 标记  ：source_message_id 以 "SEEDALM." 开头
  - raw_id：9900001 起（现有数据 max = 9001502，留足间隔不冲突）

幂等：每次运行先删除本脚本此前写入的行（按 SEEDALM. 标记），再重新插入。

payload 形态照抄真实 OXE ALARM_REPORT 报文（port_id/smif_id/chamber_id 等字段
是 bridge 误填的告警描述词，保持原样以免影响 OXE 看板的动画解析），
仅 alarm_text / event_value / alarm_id / alarm_code / lot_id 为演示内容。

严重等级由 backend/routers/history.py 按 alarm_id 映射：
  9004 / 0201 → crit(严重)   9003 / 20011 → warn(警告)   0411 → info(提示)

用法：
  python tests\generate_oxe_alarms.py                 # 写入（默认 2026-09-11）
  python tests\generate_oxe_alarms.py --date 2026-09-11
  python tests\generate_oxe_alarms.py --clean         # 只清理本脚本写入的数据
"""
import argparse
import json

import oracledb

DSN = "localhost:1521/orclpdb"
USER = "fabtwin"
PWD = "fabtwin"

TOOL_ID = "OXE-1"
MSG_PREFIX = "SEEDALM."
RAW_ID_BASE = 9900000

# (时间, 关联 Lot（NULL 表示当时无在跑批次）, alarm_id, 告警内容)
# Lot 取自当天 OXE-1 实际在跑的批次，告警时间落在该批次的运行区间内
ALARMS = [
    ("06:12:20", "V3WCT", "9003", "SMIF异常：Load Port 1 片盒感应器信号抖断，已自动重试"),
    ("06:33:45", "V3NL8", "0411", "机台异常：Chamber A 温度偏离设定值 2.3℃，已自动补偿"),
    ("06:52:10", "V46F7", "9004", "SPC异常：膜厚量测超出管制上限，需工程确认后方可续跑"),
    ("07:08:33", "V39S5", "20011", "机台异常：EFEM 机械手臂取片重试 3 次，请检查教点位置"),
    ("07:29:50", "PG0R3", "0201", "SMIF异常：POD 未完成锁附，基于安全联锁已禁止取片"),
    ("08:05:12", "PG0R4", "9003", "SPC异常：Etch Rate 连续 3 片低于管制下限，建议停机检查"),
    ("08:32:05", "V394L", "0411", "机台异常：冷却水回温速率偏慢，请留意 Chiller 工况"),
    ("13:26:44", "NULL", "9004", "SPC异常：CD 量测均值偏移超 3σ，已触发自动停线"),
    ("13:49:52", "NULL", "0411", "机台异常：真空压力回升偏慢，疑似管路微漏"),
    ("14:08:37", "NULL", "9003", "SMIF异常：片盒对位偏移，Load Port 2 自动重试成功"),
]


def build_payload(msg_id, lot_id, alarm_id, alarm_text):
    """按真实 OXE ALARM_REPORT 报文形态构造 payload"""
    return {
        "tool_id": TOOL_ID, "msg_id": msg_id, "lot_id": lot_id,
        "event_type": "ALARM", "event_name": "ALARM_REPORT",
        "event_value": alarm_text, "status": "ALARM_REPORT",
        "machine_state": "ALARM_REPORT", "machine_mode": "EPD202",
        "run_mode": "EPD202", "alarm_code": alarm_id, "alarm_id": alarm_id,
        "alarm_text": alarm_text, "event_ts_utc": None,
        "source_system": "RV", "source_message_id": msg_id,
        "port_id": "AGC", "cassette_id": "Time", "pod_id": "Time",
        "wafer_id": None, "smif_id": "Sensor-3", "chamber_id": "Out",
        "batch_id": "NULL", "unit_id": "NULL",
        "slot_id": "NULL NULL NULL NULL NULL NULL",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2026-09-11", help="日期 YYYY-MM-DD")
    ap.add_argument("--clean", action="store_true", help="只清理本脚本写入的数据")
    args = ap.parse_args()

    oracledb.defaults.fetch_lobs = False
    conn = oracledb.connect(user=USER, password=PWD, dsn=DSN)
    cur = conn.cursor()

    # ---------- 幂等：只删本脚本写入的行，按 SEEDALM. 标记识别 ----------
    cur.execute(
        "delete from DT_EVENT_RAW where tool_id = :tid and source_message_id like :mk",
        {"tid": TOOL_ID, "mk": MSG_PREFIX + "%"})
    removed = cur.rowcount
    conn.commit()
    print("清理旧演示告警: %d 行" % removed)

    if args.clean:
        print("已按 --clean 退出，未写入新数据")
        return

    # ---------- 写入 ----------
    rows = []
    for i, (hm, lot_id, alarm_id, alarm_text) in enumerate(ALARMS, start=1):
        msg_id = "%s%03d" % (MSG_PREFIX, i)
        rows.append((str(RAW_ID_BASE + i), msg_id,
                     "%s %s" % (args.date, hm),
                     build_payload(msg_id, lot_id, alarm_id, alarm_text)))

    cur.executemany(
        "insert into DT_EVENT_RAW "
        "(raw_id, tool_id, source_system, source_message_id, received_ts_utc, "
        " event_ts_utc, payload_json, parse_status) "
        "values (:rid, :tid, 'RV', :msg, :ts, :ts, :pj, 'PARSED')",
        [{"rid": rid, "tid": TOOL_ID, "msg": msg, "ts": ts,
          "pj": json.dumps(p, ensure_ascii=False)} for rid, msg, ts, p in rows])
    conn.commit()

    print("写入 DT_EVENT_RAW: %d 行（机台 %s，日期 %s）" % (len(rows), TOOL_ID, args.date))
    for rid, msg, ts, p in rows:
        print("  raw_id=%-8s %s  [%s] %s" % (rid, ts, p["alarm_id"], p["alarm_text"]))

    # 校验
    cur.execute(
        "select count(*) from DT_EVENT_RAW where tool_id = :tid "
        "and source_message_id like :mk and received_ts_utc like :d",
        {"tid": TOOL_ID, "mk": MSG_PREFIX + "%", "d": args.date + "%"})
    print("库内校验: %d 行" % cur.fetchone()[0])
    conn.close()


if __name__ == "__main__":
    main()
