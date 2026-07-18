"""检查告警和事件API"""
import json
import urllib.request

BASE = "http://localhost:8002"

def get(path):
    req = urllib.request.Request(BASE + path)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except Exception as e:
        return None, str(e)

# 1. 告警API
print("=== 1. 告警API ===")
code, data = get("/api/alarms?machine_id=PODOPENER-1&date=2026-07-17")
print(f"状态: {code}")
if isinstance(data, list):
    print(f"告警数量: {len(data)}")
    for a in data[:3]:
        print(f"  {a}")
else:
    print(f"数据: {str(data)[:200]}")

# 2. 告警统计API
print("\n=== 2. 告警统计API ===")
code, data = get("/api/alarms/stats?machine_id=PODOPENER-1&date=2026-07-17")
print(f"状态: {code}")
print(f"数据: {str(data)[:200]}")

# 3. 最新事件API (MachineEvent表)
print("\n=== 3. 最新事件API (MachineEvent表) ===")
code, data = get("/api/events/PODOPENER-1/latest?limit=5")
print(f"状态: {code}")
if isinstance(data, list):
    print(f"事件数量: {len(data)}")
    for e in data[:3]:
        print(f"  {e.get('event_type')} {e.get('event_code')} [{e.get('timestamp')}]")
else:
    print(f"数据: {str(data)[:200]}")

# 4. Lot API
print("\n=== 4. Lot API ===")
code, data = get("/api/lots?machine_id=PODOPENER-1&date=2026-07-17")
print(f"状态: {code}")
if isinstance(data, list):
    print(f"Lot数量: {len(data)}")
    for l in data[:3]:
        print(f"  {l.get('id')}: status={l.get('status')}, product={l.get('product')}")
else:
    print(f"数据: {str(data)[:200]}")

# 5. 历史告警API (DT_EVENT_RAW表)
print("\n=== 5. 历史告警API (DT_EVENT_RAW表) ===")
code, data = get("/api/history/PODOPENER-1/alarms?limit=10")
print(f"状态: {code}")
if isinstance(data, list):
    print(f"告警数量: {len(data)}")
    for a in data[:3]:
        print(f"  {a.get('event_name')} alarm_id={a.get('alarm', {}).get('alarm_id') if isinstance(a.get('alarm'), dict) else 'N/A'}")
elif isinstance(data, dict) and "events" in data:
    print(f"告警数量: {len(data['events'])}")
else:
    print(f"数据: {str(data)[:200]}")
