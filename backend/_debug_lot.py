"""Lot 加载问题自检测脚本

对比批量建立机台（PODOPENER-1~7）和新建机台（PODOPENER-51）的数据差异
"""
import os
import sys

# 加载环境变量
env_file = os.path.join(os.path.dirname(__file__), '..', 'env.bat')
if os.path.exists(env_file):
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('set ') and '=' in line:
                parts = line[4:].split('=', 1)
                if len(parts) == 2:
                    os.environ[parts[0]] = parts[1]
    print("[OK] 环境变量已加载")
else:
    print("[WARN] env.bat 未找到")

sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal
from models import Machine, DT_EVENT_RAW
from services.time_utils import parse_ts
import json

db = SessionLocal()

def check_machine(machine_id):
    print(f"\n{'='*60}")
    print(f"检查机台: {machine_id}")
    print(f"{'='*60}")

    # 1. 检查 machines 表
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if m:
        print(f"[machines表] id={m.id}, model={m.model}, name={m.name}")
        print(f"  line={m.line}, floor_x={m.floor_x}, floor_y={m.floor_y}")
        print(f"  has_smif={m.has_smif}, view_mode={getattr(m, 'view_mode', 'N/A')}")
    else:
        print(f"[machines表] 机台 {machine_id} 不存在!")

    # 2. 检查 DT_EVENT_RAW 数据
    rows = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id == machine_id).limit(10).all()
    print(f"[DT_EVENT_RAW] tool_id='{machine_id}' 的记录数: {len(rows)}")

    if rows:
        for i, row in enumerate(rows[:3]):
            try:
                payload = json.loads(row.payload_json) if row.payload_json else {}
            except:
                payload = {}
            lot_id = payload.get("lot_id", "N/A")
            ts = row.received_ts_utc or row.event_ts_utc
            parsed = parse_ts(ts)
            print(f"  记录{i+1}: raw_id={row.raw_id}, lot_id={lot_id}, ts='{ts}', parsed={parsed}")

    # 3. 检查 lot_id 不为 NULL 的记录
    all_rows = db.query(DT_EVENT_RAW).filter(DT_EVENT_RAW.tool_id == machine_id).all()
    lot_records = []
    for row in all_rows:
        try:
            payload = json.loads(row.payload_json) if row.payload_json else {}
        except:
            payload = {}
        lot_id = payload.get("lot_id")
        if lot_id and lot_id != "NULL":
            ts = row.received_ts_utc or row.event_ts_utc
            parsed = parse_ts(ts)
            lot_records.append({
                "raw_id": row.raw_id,
                "lot_id": lot_id,
                "ts": ts,
                "parsed": parsed,
                "date": parsed.strftime("%Y-%m-%d") if parsed else "N/A"
            })

    print(f"[Lot统计] 含有效 lot_id 的记录数: {len(lot_records)}")
    if lot_records:
        dates = set(r["date"] for r in lot_records if r["date"] != "N/A")
        print(f"[Lot日期] 涉及的日期: {sorted(dates)}")
        for r in lot_records[:5]:
            print(f"  lot_id={r['lot_id']}, date={r['date']}, ts='{r['ts']}'")

    # 4. 检查今天(2026-07-23)的 Lot
    today_lots = [r for r in lot_records if r["date"] == "2026-07-23"]
    print(f"[今日Lot] 2026-07-23 的 Lot 数: {len(today_lots)}")

    return {
        "machine_id": machine_id,
        "machine_exists": m is not None,
        "model": m.model if m else None,
        "total_events": len(all_rows),
        "lot_events": len(lot_records),
        "today_lots": len(today_lots),
        "lot_dates": sorted(set(r["date"] for r in lot_records if r["date"] != "N/A"))
    }


print("开始 Lot 加载问题自检测...")
print(f"当前日期: 2026-07-23")

# 对比批量建立的旧机台和新建机台
old_machines = ["PODOPENER-1", "PODOPENER-2", "PODOPENER-3"]
new_machines = ["PODOPENER-51"]  # 用户提到的新建机台

results = []
for mid in old_machines + new_machines:
    results.append(check_machine(mid))

print(f"\n{'='*60}")
print("对比总结")
print(f"{'='*60}")
for r in results:
    print(f"{r['machine_id']}: exists={r['machine_exists']}, model={r['model']}, "
          f"events={r['total_events']}, lot_events={r['lot_events']}, "
          f"today_lots={r['today_lots']}, dates={r['lot_dates']}")

db.close()
print("\n检测完成。请检查上面的输出，特别关注:")
print("1. 批量建立的机台是否在 machines 表中存在")
print("2. model 字段是否与新建机台一致")
print("3. 今日(2026-07-23)是否有 Lot 数据")
