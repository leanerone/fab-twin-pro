"""测试多个事件的动画触发"""
import sys
import os
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from winform_simulator import write_event_to_db, _init_event_counter

_init_event_counter()

test_events = [
    ("POD_PLACED", "POD放置到位 - 阶段0"),
    ("COMPLETED_PORT_LOCK", "端口锁定完成 - 阶段1"),
    ("READ_TAG", "读取RFID标签 - 阶段2"),
    ("OPEN_POD", "打开POD盖 - 阶段3"),
    ("UI_CONFIRM", "操作员确认 - 阶段4"),
    ("WRITE_TAG", "写入RFID标签 - 阶段5"),
    ("COMPLETED_PORT_UNLOCK", "端口解锁完成 - 阶段6"),
    ("POD_REMOVED", "POD移走 - 阶段7"),
]

print(f"[{datetime.now()}] 开始测试多个事件动画...")
print()

for i, (evt, desc) in enumerate(test_events, 1):
    print(f"[{i}/{len(test_events)}] 发送: {desc}")
    write_event_to_db(evt, "PACKING", "TEST05", "TESTCST5")
    print(f"    已发送 {evt}")
    time.sleep(4)
    print()

print(f"[{datetime.now()}] 测试完成！")
