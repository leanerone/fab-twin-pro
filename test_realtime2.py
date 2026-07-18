"""发送单个事件测试实时模式响应"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from winform_simulator import write_event_to_db, _init_event_counter

_init_event_counter()

print("发送 POD_PLACED 事件...")
write_event_to_db("POD_PLACED", "PACKING", "TEST02", "TESTCST2")
time.sleep(2)

print("发送 COMPLETED_PORT_LOCK 事件...")
write_event_to_db("COMPLETED_PORT_LOCK", "PACKING", "TEST02", "TESTCST2")
time.sleep(2)

print("发送 READ_TAG 事件...")
write_event_to_db("READ_TAG", "PACKING", "TEST02", "TESTCST2")
time.sleep(2)

print("发送 OPEN_POD 事件...")
write_event_to_db("OPEN_POD", "PACKING", "TEST02", "TESTCST2")

print("\n✅ 测试事件已发送")
