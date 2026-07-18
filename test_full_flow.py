"""自动化测试脚本：两个完整流程（PACKING + UNPACKING）

模拟WinForm发送完整事件序列，验证DB写入和DB Poller推送。
"""
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from winform_simulator import (
    write_event_to_db,
    PACKING_FLOW,
    UNPACKING_FLOW,
    _init_event_counter,
    _event_counter,
    TOOL_ID,
    _gen_cassette_id,
)
from database import engine
from sqlalchemy import text
import random

LOT_POOL = ["V3NL8", "V394K", "PG0R3", "V39S5", "V3QS6", "PG0R4", "V394L"]


def get_current_max_ts():
    """获取数据库当前最新事件时间"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT MAX(EVENT_TS_UTC) FROM DT_EVENT_RAW 
            WHERE TOOL_ID = :tool_id AND RAW_ID LIKE 'WIN.%'
        """), {"tool_id": TOOL_ID})
        row = result.fetchone()
        return row[0] if row and row[0] else None


def run_flow(flow_name, flow_events, lot_id, cassette_id, mode):
    """执行一个完整流程"""
    print(f"\n{'='*60}")
    print(f"  开始执行: {flow_name}")
    print(f"  Lot ID: {lot_id} | Cassette ID: {cassette_id} | Mode: {mode}")
    print(f"{'='*60}")
    
    success_count = 0
    fail_count = 0
    
    for i, (evt_name, desc) in enumerate(flow_events, 1):
        try:
            write_event_to_db(evt_name, mode, lot_id, cassette_id)
            print(f"  [{i:2d}/{len(flow_events)}] ✅ {desc} ({evt_name})")
            success_count += 1
        except Exception as e:
            print(f"  [{i:2d}/{len(flow_events)}] ❌ {desc} ({evt_name}) - 错误: {e}")
            fail_count += 1
        
        time.sleep(2)  # 每个事件间隔2秒
    
    print(f"\n  {flow_name} 执行完成: 成功 {success_count}, 失败 {fail_count}")
    return success_count, fail_count


def main():
    print("\n" + "="*70)
    print("  WinForm 模拟器自动化测试 - 两个完整流程")
    print("="*70)
    
    # 初始化计数器
    _init_event_counter()
    print(f"\n[初始化] 当前计数器: {_event_counter}")
    
    # 获取初始状态
    initial_ts = get_current_max_ts()
    print(f"[初始化] 数据库最新事件时间: {initial_ts}")
    
    # 第一个流程: PACKING (穿入)
    lot1 = random.choice(LOT_POOL)
    cassette1 = _gen_cassette_id()
    s1, f1 = run_flow("PACKING 穿入流程", PACKING_FLOW, lot1, cassette1, "PACKING")
    
    # 等待几秒
    print("\n  等待5秒...")
    time.sleep(5)
    
    # 第二个流程: UNPACKING (脱出)
    lot2 = random.choice([l for l in LOT_POOL if l != lot1])
    cassette2 = _gen_cassette_id()
    s2, f2 = run_flow("UNPACKING 脱出流程", UNPACKING_FLOW, lot2, cassette2, "UNPACKING")
    
    # 最终统计
    print(f"\n{'='*60}")
    print(f"  测试总结")
    print(f"{'='*60}")
    print(f"  PACKING 流程:  成功 {s1}, 失败 {f1}")
    print(f"  UNPACKING 流程: 成功 {s2}, 失败 {f2}")
    print(f"  总计: 成功 {s1+s2}, 失败 {f1+f2}")
    
    final_ts = get_current_max_ts()
    print(f"\n  测试前最新时间: {initial_ts}")
    print(f"  测试后最新时间: {final_ts}")
    
    if f1 + f2 == 0:
        print("\n✅ 所有事件发送成功！请检查前端页面是否实时更新。")
    else:
        print(f"\n❌ 有 {f1+f2} 个事件发送失败，请检查错误信息。")
    
    print(f"\n  请打开浏览器访问: http://localhost:5173/#/machine/PODOPENER-1")
    print(f"  切换到实时模式，观察动画是否正常播放")


if __name__ == "__main__":
    main()
