# -*- coding: utf-8 -*-
r"""
生成 PODOPENER-1 / OXE-1 / OXE-51 "今天" 的完整动画流程演示数据
==================================================================
用途：本地演示库补数。生成的事件流严格对齐前端动画驱动契约，
      保证 3D/2D 动画、Wafer Map、LOT 面板、回放页签都有完整表现。

事件契约来源（勿随意改动事件名）：
  - OXE   : frontend/src/components/MachineOxeView.vue  applyEvent()
            * toolHasSmif(): OXE-数字>=50 才有 SMIF 外壳
              -> OXE-1  使用 MIC / MOC        （无外壳）
              -> OXE-51 使用 POD_PLACED / POD_REMOVED（有外壳）
            * ENDMAPPING 会被归一化成 WAFER_MAPPING，
              wafer map 取自 payload.event_value（25 位字符串）
  - PODOPENER : frontend/src/configs/machine-animations/podopener.json

后端读取契约：
  - backend/routers/oxe.py      : 只取 parse_status == 'PARSED'，按 raw_id DESC
  - backend/routers/history.py  : ts = event_ts_utc or received_ts_utc

写入表：DT_EVENT_RAW / DT_EVENT_RAW_CUR / DT_EVENT_REALTIMELOT / DT_STATE_SNAPSHOT

用法：
  python tests\db_backup.py backup --tag before_gen_today   # 先备份！
  python tests\generate_today_demo.py
  python tests\generate_today_demo.py --date 2026-09-11
"""
import argparse
import json
import random
from datetime import datetime, timedelta

import oracledb

DSN = "localhost:1521/orclpdb"
USER = "fabtwin"
PWD = "fabtwin"

RAW_ID_BASE = 9000000
LOT_POOL = ["V3NL8", "V394K", "PG0R3", "V39S5", "V3QS6", "PG0R4",
            "V394L", "V3R30", "V3CKS", "V46F7", "V3WCT", "V3W9T"]
RECIPE_POOL = ["ETCH_STD_A1", "ETCH_STD_B2", "POLY_MAIN_03", "OXIDE_FIN_07"]

random.seed(20260911)

_raw_seq = RAW_ID_BASE


def next_raw_id():
    global _raw_seq
    _raw_seq += 1
    return str(_raw_seq)


def gen_cassette():
    return "%05d%s" % (random.randint(10000, 99999), random.choice("ABCDEFGHJKLMNPZ"))


def ts_str(d):
    return d.strftime("%Y-%m-%d %H:%M:%S")


# ==================== payload 模板（22 字段，与量产一致）====================
def base_payload(tool_id, event_name, event_type, msg_id):
    return {
        "tool_id": tool_id, "msg_id": msg_id, "lot_id": "NULL",
        "event_type": event_type, "event_name": event_name,
        "event_value": "NULL", "status": event_name,
        "machine_state": event_name, "machine_mode": "NULL",
        "run_mode": "NULL", "alarm_code": None, "alarm_id": None,
        "alarm_text": "NULL", "event_ts_utc": None,
        "source_system": "RV", "source_message_id": msg_id,
        "port_id": "NULL", "cassette_id": "NULL", "pod_id": "NULL",
        "wafer_id": None, "smif_id": "NULL", "chamber_id": "NULL",
        "batch_id": "NULL", "unit_id": "NULL", "slot_id": "NULL",
    }


def oxe_alarm_payload(tool_id, msg_id):
    """ALARM_REPORT：量产 bridge 会把描述词错填进 port_id 等字段，此处照抄该形态"""
    sensor_no = random.randint(1, 3)
    variants = [
        {"port_id": "AGC", "cassette_id": "Time", "pod_id": "Time",
         "smif_id": "Sensor-%d" % sensor_no, "chamber_id": "Out",
         "slot_id": "NULL NULL NULL NULL NULL NULL", "text": "P2"},
        {"port_id": "Light", "cassette_id": "Intensity", "pod_id": "Intensity",
         "smif_id": "(Lack)%d" % sensor_no, "chamber_id": "Error",
         "slot_id": "NULL NULL NULL NULL NULL NULL", "text": "P2"},
    ]
    v = random.choice(variants)
    p = base_payload(tool_id, "ALARM_REPORT", "ALARM", msg_id)
    p.update({
        "event_value": v["text"], "alarm_text": v["text"],
        "machine_mode": "EPD202", "run_mode": "EPD202",
        "port_id": v["port_id"], "cassette_id": v["cassette_id"],
        "pod_id": v["pod_id"], "smif_id": v["smif_id"],
        "chamber_id": v["chamber_id"], "slot_id": v["slot_id"],
    })
    return p


# ==================== OXE 完整流程 ====================
def oxe_cycle(tool_id, has_smif, port, start_dt, lot, cassette, recipe,
              wafer_slots, msg_seq, finished=True, cut_at=None):
    """生成一个 OXE 完整上下料周期

    finished=False 时表示"进行中"（不产出 POD_REMOVED），
    cut_at 为整数时在第 N 个事件处截断，用于制造正在跑货的现场。
    """
    place_name = "POD_PLACED" if has_smif else "MIC"
    remove_name = "POD_REMOVED" if has_smif else "MOC"
    port_s = str(port)
    smif_s = port_s if has_smif else "NULL"
    chamber = "A" if port == 1 else "B"
    mapping = "".join("1" if (i + 1) in wafer_slots else "0" for i in range(25))

    out = []
    t = start_dt

    def emit(event_name, event_type="VFEI", gap=(3, 10), **over):
        nonlocal t, msg_seq
        msg = "TID.%d" % msg_seq
        msg_seq += 1
        p = base_payload(tool_id, event_name, event_type, msg)
        p["port_id"] = port_s
        p["smif_id"] = smif_s
        p["cassette_id"] = cassette
        p["pod_id"] = cassette
        p.update(over)
        out.append((t, p, msg))
        t += timedelta(seconds=random.randint(*gap))

    emit(place_name, gap=(5, 12))
    emit("LOCK_PORT_COMPLETED", gap=(3, 8))
    emit("MVIN", gap=(4, 9))
    emit("DOOR_OPEN", gap=(4, 9))
    emit("LOAD_CYCLE_STARTED", gap=(6, 14))
    emit("LOAD_CYCLE_COMPLETED", gap=(3, 8))
    emit("DOOR_CLOSE", gap=(3, 8))
    emit("BATCH_INFO_FROM_ECUI", "HOST", gap=(3, 8),
         lot_id=lot, batch_id="BT_%s" % cassette, event_value=lot)
    emit("STARTMAPPING_LEFT" if port == 1 else "STARTMAPPING_RIGHT", gap=(5, 11))
    emit("ENDMAPPING", gap=(4, 9), lot_id=lot, event_value=mapping,
         batch_id="BT_%s" % cassette)
    emit("START", gap=(4, 10), lot_id=lot, event_value=recipe,
         machine_mode=recipe, run_mode=recipe)

    for idx, slot in enumerate(wafer_slots):
        emit("PS", gap=(6, 12), lot_id=lot, slot_id=str(slot),
             chamber_id=chamber, event_value=recipe)
        emit("WAFERLOADED", gap=(20, 40), lot_id=lot, slot_id=str(slot),
             wafer_id=str(slot), chamber_id=chamber)
        emit("WAFERUNLOADED", gap=(8, 16), lot_id=lot, slot_id=str(slot),
             wafer_id=str(slot), chamber_id=chamber)
        emit("PE", gap=(5, 12), lot_id=lot, slot_id=str(slot), chamber_id=chamber)
        # 每 5 片穿插一条告警，模拟真实产线噪声
        if idx > 0 and idx % 5 == 4:
            msg = "TID.%d" % msg_seq
            msg_seq += 1
            out.append((t, oxe_alarm_payload(tool_id, msg), msg))
            t += timedelta(seconds=random.randint(4, 10))

    emit("READYTOUNLOAD", gap=(5, 11), lot_id=lot, chamber_id=chamber)
    emit("DOOR_OPEN", gap=(4, 9), lot_id=lot)
    emit("UNLOAD_CYCLE_COMPLETED", gap=(6, 13), lot_id=lot)
    emit("DOOR_CLOSE", gap=(3, 8), lot_id=lot)
    emit("MVOU", gap=(4, 9), lot_id=lot)
    emit("UNLOCK_PORT_COMPLETED", gap=(3, 8), lot_id=lot)
    emit(remove_name, gap=(5, 12), lot_id=lot)
    emit("FDC_CLEARCONTEXT", gap=(3, 8))

    if cut_at is not None:
        out = out[:cut_at]
    elif not finished:
        out = out[:-8]
    return out, msg_seq, mapping


# ==================== PODOPENER 完整流程 ====================
PACKING_SEQ = [
    ("POD_PLACED", "VFEI", False), ("COMPLETED_PORT_LOCK", "VFEI", False),
    ("READ_BATTERY", "VFEI", False), ("READ_TAG", "VFEI", False),
    ("BATCH_INFO_FROM_ECUI", "HOST", True), ("OPEN_POD", "VFEI", True),
    ("REACH_STAGE", "VFEI", True), ("UI_CONFIRM", "HOST", True),
    ("CLOSE_POD", "VFEI", True), ("ACK_UI_DOUBLECHECK", "HOST", True),
    ("REACH_POS", "VFEI", True), ("WRITE_TAG", "VFEI", True),
    ("COMPLETED_PORT_UNLOCK", "VFEI", True), ("POD_REMOVED", "VFEI", True),
]
UNPACKING_SEQ = [
    ("POD_PLACED", "VFEI", False), ("COMPLETED_PORT_LOCK", "VFEI", False),
    ("READ_TAG", "VFEI", False), ("BATCH_INFO_FROM_ECUI", "HOST", True),
    ("OPEN_POD", "VFEI", True), ("REACH_STAGE", "VFEI", True),
    ("UI_CONFIRM", "HOST", True), ("CLOSE_POD", "VFEI", True),
    ("REACH_POS", "VFEI", True), ("WRITE_TAG", "VFEI", True),
    ("COMPLETED_PORT_UNLOCK", "VFEI", True), ("POD_REMOVED", "VFEI", True),
]


def podopener_cycle(tool_id, start_dt, mode, lot, cassette, msg_seq, cut_at=None):
    seq = PACKING_SEQ if mode == "PACKING" else UNPACKING_SEQ
    out = []
    t = start_dt
    for ev_name, ev_type, has_lot in seq:
        msg = "TID.%d" % msg_seq
        msg_seq += 1
        p = base_payload(tool_id, ev_name, ev_type, msg)
        p.update({
            "lot_id": lot if has_lot else "NULL",
            "event_value": ev_name, "alarm_text": ev_name,
            "machine_mode": mode, "run_mode": mode,
            "port_id": "1", "smif_id": "1",
            "cassette_id": cassette if has_lot else "NULL",
            "pod_id": cassette if has_lot else "NULL",
            "batch_id": ("BT_%s" % cassette) if has_lot else "NULL",
        })
        out.append((t, p, msg))
        t += timedelta(seconds=random.randint(4, 18))
    if cut_at is not None:
        out = out[:cut_at]
    return out, msg_seq


# ==================== 主流程 ====================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="生成日期 YYYY-MM-DD，默认今天")
    ap.add_argument("--raw-base", type=int, default=RAW_ID_BASE,
                    help="raw_id 起始值，默认 %d。补历史日期时必须换一段不冲突的区间，"
                         "且应小于已有数据的最小 raw_id，以保持「raw_id 随时间递增」这一约定"
                         % RAW_ID_BASE)
    ap.add_argument("--history-only", action="store_true",
                    help="只写 DT_EVENT_RAW（补历史日期用）：不碰 DT_EVENT_RAW_CUR、"
                         "DT_EVENT_REALTIMELOT、DT_STATE_SNAPSHOT，也不改 machines 状态")
    args = ap.parse_args()

    now = datetime.now().replace(microsecond=0)
    if args.date:
        day = datetime.strptime(args.date, "%Y-%m-%d")
        if day.date() != now.date():
            now = day.replace(hour=17, minute=30, second=0)
    day0 = now.replace(hour=0, minute=0, second=0)

    # 演示窗口：当天 06:00 起，直到"此刻"，最后一个周期停在 now-2min（进行中）
    win_start = day0 + timedelta(hours=6)
    if win_start > now - timedelta(hours=1):
        win_start = now - timedelta(hours=2, minutes=30)

    print("生成日期     : %s" % day0.strftime("%Y-%m-%d"))
    print("演示时间窗   : %s ~ %s" % (ts_str(win_start), ts_str(now)))

    oracledb.defaults.fetch_lobs = False
    conn = oracledb.connect(user=USER, password=PWD, dsn=DSN)
    cur = conn.cursor()

    tools = ["PODOPENER-1", "OXE-1", "OXE-51"]
    day_like = day0.strftime("%Y-%m-%d") + "%"

    # ---------- 幂等：只清当天这三台机台的数据，绝不动其他 ----------
    for t in tools:
        cur.execute(
            "delete from DT_EVENT_RAW where tool_id = :tid "
            "and (received_ts_utc like :day or event_ts_utc like :day)",
            {"tid": t, "day": day_like})
        print("  清理 DT_EVENT_RAW %-12s %d 行" % (t, cur.rowcount))
        if args.history_only:
            continue
        cur.execute("delete from DT_EVENT_RAW_CUR where tool_id = :tid", {"tid": t})
        cur.execute("delete from DT_EVENT_REALTIMELOT where tool_id = :tid", {"tid": t})
        cur.execute(
            "delete from DT_STATE_SNAPSHOT where tool_id = :tid "
            "and snapshot_ts_utc like :day", {"tid": t, "day": day_like})
    conn.commit()

    all_rows = []       # (raw_id, tool, msg, ts, payload)
    last_of_tool = {}   # tool -> (ts, payload, msg, raw_id)
    rtlot_rows = []     # DT_EVENT_REALTIMELOT

    # ============ PODOPENER-1 ============
    tool = "PODOPENER-1"
    msg_seq = random.randint(2000, 9000)
    t = win_start
    pod_cycles = 0
    while t < now - timedelta(minutes=6):
        mode = "PACKING" if pod_cycles % 2 == 0 else "UNPACKING"
        lot = random.choice(LOT_POOL)
        cass = gen_cassette()
        evs, msg_seq = podopener_cycle(tool, t, mode, lot, cass, msg_seq)
        for d, p, m in evs:
            all_rows.append((next_raw_id(), tool, m, d, p))
        t = evs[-1][0] + timedelta(minutes=random.randint(6, 12))
        pod_cycles += 1
    # 收尾：一个进行中的周期，最后事件落在 now-2min 附近，触发实时动画
    lot = random.choice(LOT_POOL)
    cass = gen_cassette()
    live_start = now - timedelta(minutes=5)
    evs, msg_seq = podopener_cycle(tool, live_start, "PACKING", lot, cass, msg_seq, cut_at=8)
    shift = (now - timedelta(minutes=2)) - evs[-1][0]
    for d, p, m in evs:
        all_rows.append((next_raw_id(), tool, m, d + shift, p))
    pod_cycles += 1
    rtlot_rows.append(dict(
        tool_id=tool, port_id="1", lot_id=lot, batch_id="BT_%s" % cass,
        cassette_id=cass, smif_id="1", wafer_mapping="1" * 25,
        last_event_name=evs[-1][1]["event_name"], last_ts=evs[-1][0] + shift,
        start_ts=evs[0][0] + shift, msg=evs[-1][2]))
    print("  %-12s %d 个周期" % (tool, pod_cycles))

    # ============ OXE-1（line1，无 SMIF：MIC/MOC）============
    # ============ OXE-51（line2，有 SMIF：POD_PLACED/POD_REMOVED）============
    for tool, has_smif, ports in [("OXE-1", False, [1]), ("OXE-51", True, [1, 2])]:
        msg_seq = random.randint(20000, 80000)
        cycles = 0
        for port in ports:
            t = win_start + timedelta(minutes=port * 4)
            while t < now - timedelta(minutes=35):
                lot = random.choice(LOT_POOL)
                cass = gen_cassette()
                recipe = random.choice(RECIPE_POOL)
                slots = sorted(random.sample(range(1, 26), random.randint(8, 13)))
                evs, msg_seq, _ = oxe_cycle(tool, has_smif, port, t, lot, cass,
                                            recipe, slots, msg_seq)
                for d, p, m in evs:
                    all_rows.append((next_raw_id(), tool, m, d, p))
                t = evs[-1][0] + timedelta(minutes=random.randint(3, 8))
                cycles += 1

        # 收尾：PORT1 留一个进行中的周期（POD 在位、已 mapping、部分 wafer 跑完）
        lot = random.choice(LOT_POOL)
        cass = gen_cassette()
        recipe = random.choice(RECIPE_POOL)
        slots = sorted(random.sample(range(1, 26), 12))
        evs, msg_seq, mapping = oxe_cycle(tool, has_smif, 1, now - timedelta(minutes=40),
                                          lot, cass, recipe, slots, msg_seq, cut_at=27)
        shift = (now - timedelta(minutes=2)) - evs[-1][0]
        for d, p, m in evs:
            all_rows.append((next_raw_id(), tool, m, d + shift, p))
        cycles += 1
        done = sum(1 for _, p, _ in evs if p["event_name"] == "WAFERUNLOADED")
        slot_set = set(slots)
        done_set = set(slots[:done])
        live_map = "".join(
            ("3" if (i + 1) in done_set else "1") if (i + 1) in slot_set else "0"
            for i in range(25))
        rtlot_rows.append(dict(
            tool_id=tool, port_id="1", lot_id=lot, batch_id="BT_%s" % cass,
            cassette_id=cass, smif_id="1" if has_smif else "NULL",
            wafer_mapping=live_map, last_event_name=evs[-1][1]["event_name"],
            last_ts=evs[-1][0] + shift, start_ts=evs[0][0] + shift, msg=evs[-1][2]))
        print("  %-12s %d 个周期（在制 LOT=%s，已完成 %d 片）" % (tool, cycles, lot, done))

    # ---------- 按时间排序后重新编号 raw_id，保证 raw_id 与时间同序 ----------
    all_rows.sort(key=lambda r: (r[3], r[0]))
    _seq = args.raw_base
    final_rows = []
    for _, tool, msg, d, p in all_rows:
        _seq += 1
        final_rows.append((str(_seq), tool, msg, d, p))
        last_of_tool[tool] = (d, p, msg, str(_seq))

    # ---------- 写 DT_EVENT_RAW ----------
    cur.executemany(
        "insert into DT_EVENT_RAW "
        "(raw_id, tool_id, source_system, source_message_id, received_ts_utc, "
        " event_ts_utc, payload_json, parse_status) "
        "values (:rid, :tid, 'RV', :msg, :ts, :ts, :pj, 'PARSED')",
        [{"rid": rid, "tid": tool, "msg": msg, "ts": ts_str(d),
          "pj": json.dumps(p, ensure_ascii=False)}
         for rid, tool, msg, d, p in final_rows])

    # 以下 4 段都是「实时画面」的数据源，补历史日期时绝对不能碰，
    # 否则实时看板会变成历史那天的状态。--history-only 时全部跳过。
    if args.history_only:
        print("\n[history-only] 跳过 DT_EVENT_RAW_CUR / REALTIMELOT / SNAPSHOT / machines 更新")
    else:
        # ---------- 写 DT_EVENT_RAW_CUR ----------
        for tool, (d, p, msg, rid) in last_of_tool.items():
            cur.execute(
                "insert into DT_EVENT_RAW_CUR "
                "(tool_id, raw_id, source_system, source_message_id, received_ts_utc, "
                " event_ts_utc, payload_json, parse_status) "
                "values (:tid, :rid, 'RV', :msg, :ts, :ts, :pj, 'PARSED')",
                {"tid": tool, "rid": rid, "msg": msg, "ts": ts_str(d),
                 "pj": json.dumps(p, ensure_ascii=False)})

        # ---------- 写 DT_EVENT_REALTIMELOT ----------
        cur.execute("select nvl(max(rt_id), 0) from DT_EVENT_REALTIMELOT")
        rt_id = cur.fetchone()[0]
        for r in rtlot_rows:
            rt_id += 1
            cur.execute(
                "insert into DT_EVENT_REALTIMELOT "
                "(rt_id, tool_id, port_id, lot_key_mode, lot_biz_key, lot_id, batch_id, "
                " cassette_id, smif_id, wafer_mapping, last_event_name, last_event_ts_utc, "
                " start_ts_utc, updated_ts_utc, source_system, source_message_id, active_flag) "
                "values (:1, :2, :3, 'SINGLE_LOT_PER_PORT', :4, :5, :6, :7, :8, :9, :10, "
                "        :11, :12, :13, 'RV', :14, 'Y')",
                [rt_id, r["tool_id"], r["port_id"],
                 "SINGLE::%s::%s" % (r["tool_id"], r["port_id"]),
                 r["lot_id"], r["batch_id"], r["cassette_id"], r["smif_id"],
                 r["wafer_mapping"], r["last_event_name"], r["last_ts"],
                 r["start_ts"], r["last_ts"], r["msg"]])

        # ---------- 写 DT_STATE_SNAPSHOT（SNAPSHOT_ID 为 IDENTITY，不指定）----------
        for tool, (d, p, msg, rid) in last_of_tool.items():
            cur.execute(
                "insert into DT_STATE_SNAPSHOT "
                "(tool_id, snapshot_ts_utc, machine_state, machine_mode, "
                " current_alarm_code, current_lot_id, pod_position, snapshot_json) "
                "values (:1, :2, :3, :4, null, :5, :6, :7)",
                [tool, ts_str(d), p.get("machine_state"), p.get("machine_mode"),
                 None if p.get("lot_id") == "NULL" else p.get("lot_id"),
                 p.get("port_id"), json.dumps(p, ensure_ascii=False)])

        # ---------- 同步 MACHINES 状态 ----------
        for tool in tools:
            cur.execute(
                "update machines set state = 'run', updated_at = :1 where id = :2",
                [ts_str(now), tool])

    conn.commit()

    # ---------- 校验 ----------
    print("\n生成结果：")
    for t in tools:
        cur.execute(
            "select count(*), min(event_ts_utc), max(event_ts_utc) "
            "from DT_EVENT_RAW where tool_id = :1 and event_ts_utc like :2",
            [t, day_like])
        c, mn, mx = cur.fetchone()
        print("  %-12s %4d 条   %s ~ %s" % (t, c, mn, mx))
    cur.execute(
        "select count(*) from DT_EVENT_RAW where event_ts_utc like :1", [day_like])
    print("  当天合计     %d 条" % cur.fetchone()[0])
    conn.close()


if __name__ == "__main__":
    main()
