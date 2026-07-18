"""发送单个事件测试实时动画"""
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from winform_simulator import write_event_to_db, _init_event_counter

_init_event_counter()

print(f"[{datetime.now()}] 发送 POD_PLACED 事件...")
write_event_to_db("POD_PLACED", "PACKING", "TEST04", "TESTCST4")
print(f"[{datetime.now()}] 已发送")
