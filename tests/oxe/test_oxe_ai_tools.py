"""测试3个OXE专用AI工具"""
import sys, json
sys.path.insert(0, r'C:\Users\A\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a558d0e1709fecd225c0cc2\fab-twin-pro\backend')
from database import SessionLocal
from services.ai_tools import get_wafer_flow, get_chamber_status, get_oxe_lot_summary, _resolve_tool_ids

db = SessionLocal()

print("=" * 60)
print("测试1: _resolve_tool_ids OXE前缀匹配")
print("=" * 60)
tool_ids = _resolve_tool_ids(db, 'OXE-61')
print(f"OXE-61 -> {tool_ids}")

print("\n" + "=" * 60)
print("测试2: get_chamber_status")
print("=" * 60)
result = get_chamber_status(db, 'OXE-61')
print(f"answer:\n{result['answer']}")
if result.get('table_data'):
    print(f"\ntable headers: {result['table_data']['headers']}")
    print(f"table rows: {len(result['table_data']['rows'])} 行")
    for row in result['table_data']['rows'][:3]:
        print(f"  {row}")
print(f"jump_timestamp: {result.get('jump_timestamp')}")
print(f"jump_machine_id: {result.get('jump_machine_id')}")

print("\n" + "=" * 60)
print("测试3: get_wafer_flow (最新Lot)")
print("=" * 60)
result = get_wafer_flow(db, 'OXE-61')
print(f"answer:\n{result['answer']}")
if result.get('table_data'):
    print(f"\ntable headers: {result['table_data']['headers']}")
    print(f"table rows: {len(result['table_data']['rows'])} 行")
    for row in result['table_data']['rows'][:5]:
        print(f"  {row}")

print("\n" + "=" * 60)
print("测试4: get_oxe_lot_summary (2026-08-08)")
print("=" * 60)
result = get_oxe_lot_summary(db, 'OXE-61', date='2026-08-08')
print(f"answer:\n{result['answer']}")
if result.get('table_data'):
    print(f"\ntable headers: {result['table_data']['headers']}")
    print(f"table rows: {len(result['table_data']['rows'])} 行")
    for row in result['table_data']['rows']:
        print(f"  {row}")

print("\n" + "=" * 60)
print("测试5: get_oxe_lot_summary (不指定日期，取最新)")
print("=" * 60)
result = get_oxe_lot_summary(db, 'OXE-61')
print(f"answer:\n{result['answer']}")

db.close()
print("\n✅ 全部测试完成")
