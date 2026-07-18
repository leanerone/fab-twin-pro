"""发送单个事件测试"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from winform_simulator import write_event_to_db, _init_event_counter

_init_event_counter()

print("发送 POD_PLACED 事件...")
write_event_to_db("POD_PLACED", "PACKING", "TEST03", "TESTCST3")
print("\n✅ 已发送")
