"""验证Lot数据和事件分类"""
import json
import urllib.request

BASE = "http://localhost:8002"

def get(path):
    req = urllib.request.Request(BASE + path)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, json.loads(resp.read().decode())

# 1. 检查PODOPENER-1的Lot
print("=== 1. PODOPENER-1的Lot ===")
code, data = get("/api/lots?limit=10")
if isinstance(data, list):
    pod_lots = [l for l in data if l.get("machine_id") == "PODOPENER-1"]
    print(f"总Lot数: {len(data)}, PODOPENER-1 Lot数: {len(pod_lots)}")
    for lot in pod_lots[:5]:
        print(f"  {lot['id']}: machine={lot['machine_id']}, product={lot['product']}, status={lot['status']}")

# 2. 检查事件分类
print("\n=== 2. 事件分类验证 ===")
code, data = get("/api/history/PODOPENER-1?limit=20")
if code == 200:
    print(f"total: {data.get('total')}")
    for e in data.get("events", [])[:20]:
        lot_str = str(e.get("lot_id") or "None")
        print(f"  {e['event_name']:30s} cat={e['event_category']:8s} lot={lot_str:10s} cassette={e.get('cassette_id')}")

# 3. 检查时间轴
print("\n=== 3. 今天的时间轴 ===")
code, data = get("/api/history/PODOPENER-1/timeline")
if code == 200:
    tl = data.get("timeline", [])
    has_events = [t for t in tl if t["has_events"]]
    print(f"有事件的小时数: {len(has_events)}")
    for h in has_events[:5]:
        print(f"  {h['hour']:02d}点: alarm={h['alarm_count']}, pod={h['pod_count']}, process={h['process_count']}, other={h['total_count']-h['alarm_count']-h['pod_count']-h['process_count']}, total={h['total_count']}")
