"""检查lot资料和事件匹配情况"""
import json
import urllib.request

BASE = "http://localhost:8002"

def get(path):
    req = urllib.request.Request(BASE + path)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, json.loads(resp.read().decode())

print("=" * 60)
print("检查Lot资料和事件匹配情况")
print("=" * 60)

# 1. 检查lot列表
print("\n=== 1. Lot列表API ===")
code, data = get("/api/lots?limit=20")
if isinstance(data, list):
    print(f"Lot数量: {len(data)}")
    for lot in data[:5]:
        print(f"  - lot_id={lot.get('lot_id')}, tool_id={lot.get('tool_id')}, status={lot.get('status')}")
elif isinstance(data, dict) and "items" in data:
    print(f"Lot数量: {len(data['items'])}")
    for lot in data["items"][:5]:
        print(f"  - lot_id={lot.get('lot_id')}, tool_id={lot.get('tool_id')}, status={lot.get('status')}")
else:
    print(f"返回数据类型: {type(data)}")
    print(f"数据: {json.dumps(data, ensure_ascii=False)[:300]}")

# 2. 检查PODOPENER-1相关lot
print("\n=== 2. PODOPENER-1相关Lot ===")
try:
    code, data = get("/api/lots?tool_id=PODOPENER-1&limit=20")
    if isinstance(data, list):
        print(f"PODOPENER-1 Lot数量: {len(data)}")
        for lot in data[:5]:
            print(f"  - {lot}")
    elif isinstance(data, dict) and "items" in data:
        print(f"PODOPENER-1 Lot数量: {len(data['items'])}")
    else:
        print(f"数据: {json.dumps(data, ensure_ascii=False)[:300]}")
except Exception as e:
    print(f"错误: {e}")

# 3. 检查PODOPENER-1的当前事件（最新）
print("\n=== 3. PODOPENER-1 最新事件 ===")
code, data = get("/api/history/PODOPENER-1?limit=5")
print(f"total: {data.get('total')}")
if data.get("events"):
    for e in data["events"][-5:]:
        print(f"  - {e['event_name']} ({e['event_category']}) [{e['timestamp']}] lot={e.get('lot_id')}")

# 4. 检查当前状态 (CUR表)
print("\n=== 4. PODOPENER-1 当前状态 (CUR表) ===")
try:
    code, data = get("/api/rv/current/PODOPENER-1")
    print(f"当前状态: {json.dumps(data, ensure_ascii=False)[:300]}")
except Exception as e:
    print(f"RV current API错误: {e}")

# 5. 检查机台事件
print("\n=== 5. PODOPENER-1 机台事件 ===")
try:
    code, data = get("/api/machines/PODOPENER-1/events?limit=5")
    if isinstance(data, list):
        print(f"机台事件数量: {len(data)}")
        for ev in data[:5]:
            print(f"  - {ev}")
    else:
        print(f"数据: {json.dumps(data, ensure_ascii=False)[:300]}")
except Exception as e:
    print(f"机台事件API错误: {e}")

# 6. 检查DB当前数据接口
print("\n=== 6. DB当前数据接口 ===")
try:
    code, data = get("/api/db/current/PODOPENER-1")
    print(f"DB当前数据: {json.dumps(data, ensure_ascii=False)[:300]}")
except Exception as e:
    print(f"DB current API错误: {e}")

# 7. 检查DB事件列表接口
print("\n=== 7. DB事件列表接口 ===")
try:
    code, data = get("/api/db/events/PODOPENER-1?limit=5")
    print(f"DB事件: {json.dumps(data, ensure_ascii=False)[:300]}")
except Exception as e:
    print(f"DB events API错误: {e}")
