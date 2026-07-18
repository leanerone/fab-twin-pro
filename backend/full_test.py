"""完整功能测试"""
import json
import urllib.request

BASE = "http://localhost:8002"

def get(path):
    req = urllib.request.Request(BASE + path)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, json.loads(resp.read().decode())

print("=" * 60)
print("FabTwin 完整功能测试")
print("=" * 60)

tests = []

# 1. 健康检查
print("\n✅ 1. 健康检查: ", end="")
try:
    code, _ = get("/health")
    ok = code == 200
    print(f"PASS (code={code})")
except Exception as e:
    ok = False
    print(f"FAIL ({e})")
tests.append(("健康检查", ok))

# 2. 机台列表
print("\n✅ 2. 机台列表API: ", end="")
try:
    code, data = get("/api/machines")
    ok = code == 200 and isinstance(data, list) and len(data) > 0
    print(f"PASS ({len(data)}台机台)")
    pod = [m for m in data if m.get('process_type') == 'PODOPENER']
    if pod:
        print(f"   PODOPENER机台: {pod[0]['id']} - {pod[0]['name']}")
except Exception as e:
    ok = False
    print(f"FAIL ({e})")
tests.append(("机台列表API", ok))

# 3. PODOPENER-1机台详情
print("\n✅ 3. PODOPENER-1机台详情: ", end="")
try:
    code, data = get("/api/machines/PODOPENER-1")
    ok = code == 200 and data.get("id") == "PODOPENER-1"
    print(f"PASS" if ok else f"FAIL (code={code})")
    if ok:
        print(f"   名称: {data.get('name')}")
        print(f"   工艺: {data.get('process_type')}")
except Exception as e:
    ok = False
    print(f"FAIL ({e})")
tests.append(("PODOPENER-1机台详情", ok))

# 4. 历史事件查询
print("\n✅ 4. 历史事件查询: ", end="")
try:
    code, data = get("/api/history/PODOPENER-1?limit=50")
    ok = code == 200 and data.get("total", 0) > 1000
    print(f"PASS (共{data.get('total')}条)" if ok else f"FAIL (code={code})")
    if ok and data.get("events"):
        cats = set(e['event_category'] for e in data['events'])
        names = [e['event_name'] for e in data['events'][:5]]
        print(f"   分类: {cats}")
        print(f"   前5事件: {names}")
except Exception as e:
    ok = False
    print(f"FAIL ({e})")
tests.append(("历史事件查询", ok))

# 5. 单日时间轴
print("\n✅ 5. 单日时间轴: ", end="")
try:
    import datetime
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    code, data = get(f"/api/history/PODOPENER-1/timeline?date={yesterday}")
    ok = code == 200 and "timeline" in data
    print(f"PASS" if ok else f"FAIL (code={code})")
    if ok:
        tl = data['timeline']
        total = sum(t['total_count'] for t in tl)
        hours = sum(1 for t in tl if t['has_events'])
        print(f"   日期: {data.get('date')}")
        print(f"   总事件: {total}, 有事件小时数: {hours}")
except Exception as e:
    ok = False
    print(f"FAIL ({e})")
tests.append(("单日时间轴", ok))

# 6. 告警历史
print("\n✅ 6. 告警历史: ", end="")
try:
    code, data = get("/api/history/PODOPENER-1/alarms?limit=20")
    ok = code == 200
    print(f"PASS" if ok else f"FAIL (code={code})")
    if ok and isinstance(data, list):
        print(f"   告警数量: {len(data)}")
except Exception as e:
    ok = False
    print(f"FAIL ({e})")
tests.append(("告警历史", ok))

# 7. 楼层列表
print("\n✅ 7. 楼层列表: ", end="")
try:
    code, data = get("/api/floors")
    ok = code == 200 and isinstance(data, list) and len(data) >= 4
    print(f"PASS ({len(data)}层)" if ok else f"FAIL (code={code})")
except Exception as e:
    ok = False
    print(f"FAIL ({e})")
tests.append(("楼层列表", ok))

# 8. 机台型号配置
print("\n✅ 8. 机台型号配置: ", end="")
try:
    code, data = get("/api/models")
    ok = code == 200
    print(f"PASS" if ok else f"FAIL (code={code})")
    if ok and isinstance(data, list):
        print(f"   型号数量: {len(data)}")
        for m in data[:3]:
            print(f"   - {m.get('model_id')}: {m.get('model_name')}")
except Exception as e:
    ok = False
    print(f"FAIL ({e})")
tests.append(("机台型号配置", ok))

# 9. 机台KPI
print("\n✅ 9. 机台KPI: ", end="")
try:
    code, data = get("/api/machines/PODOPENER-1/kpi")
    ok = code == 200
    print(f"PASS" if ok else f"FAIL (code={code})")
    if ok:
        print(f"   KPI: {json.dumps(data, ensure_ascii=False)[:100]}")
except Exception as e:
    ok = False
    print(f"FAIL ({e})")
tests.append(("机台KPI", ok))

# 10. 批次列表
print("\n✅ 10. 批次列表: ", end="")
try:
    code, data = get("/api/lots?limit=10")
    ok = code == 200
    print(f"PASS" if ok else f"FAIL (code={code})")
    if ok and isinstance(data, list):
        print(f"   批次数量: {len(data)}")
except Exception as e:
    ok = False
    print(f"FAIL ({e})")
tests.append(("批次列表", ok))

# 测试总结
print("\n" + "=" * 60)
print("测试总结")
print("=" * 60)
passed = sum(1 for _, ok in tests if ok)
total = len(tests)
for name, ok in tests:
    status = "✅ PASS" if ok else "❌ FAIL"
    print(f"  {status} - {name}")
print(f"\n通过率: {passed}/{total} ({passed*100//total}%)")

if passed == total:
    print("\n🎉 所有测试通过！")
else:
    print(f"\n⚠️  {total - passed} 项测试失败")
