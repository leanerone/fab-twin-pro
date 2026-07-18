"""快速测试：发送一个事件验证实时模式响应"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from winform_simulator import write_event_to_db, _init_event_counter

_init_event_counter()

print("发送 POD_PLACED 事件...")
write_event_to_db("POD_PLACED", "PACKING", "TEST01", "TESTCST")
time.sleep(2)

print("发送 COMPLETED_PORT_LOCK 事件...")
write_event_to_db("COMPLETED_PORT_LOCK", "PACKING", "TEST01", "TESTCST")
time.sleep(2)

print("发送 READ_TAG 事件...")
write_event_to_db("READ_TAG", "PACKING", "TEST01", "TESTCST")
time.sleep(2)

print("发送 OPEN_POD 事件...")
write_event_to_db("OPEN_POD", "PACKING", "TEST01", "TESTCST")

print("\n✅ 测试事件已发送，请检查前端画面是否实时更新")
