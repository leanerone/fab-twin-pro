"""PODOPENER WinForm 模拟器

通过按钮控制，向DB写入事件驱动网页实时显示。
使用 tkinter 实现（Python内置，无需额外安装）。
"""
import sys
import os
import json
import random
import threading
import time
from datetime import datetime
from tkinter import Tk, ttk, StringVar, Text, END, scrolledtext
import tkinter as tk

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from database import engine
from sqlalchemy import text

TOOL_ID = "PODOPENER-1"

# 穿入流程（14步）
PACKING_FLOW = [
    ("POD_PLACED", "POD放置到位"),
    ("COMPLETED_PORT_LOCK", "端口锁定完成"),
    ("READ_BATTERY", "读取电池状态"),
    ("READ_TAG", "读取RFID标签"),
    ("BATCH_INFO_FROM_ECUI", "获取批次信息"),
    ("OPEN_POD", "打开POD盖"),
    ("REACH_STAGE", "机械臂到达平台"),
    ("UI_CONFIRM", "操作员确认"),
    ("CLOSE_POD", "关闭POD盖"),
    ("ACK_UI_DOUBLECHECK", "二次确认"),
    ("REACH_POS", "机械臂到位"),
    ("WRITE_TAG", "写入RFID标签"),
    ("COMPLETED_PORT_UNLOCK", "端口解锁完成"),
    ("POD_REMOVED", "POD移走"),
]

# 脱出流程（6步）
UNPACKING_FLOW = [
    ("UI_CONFIRM", "操作员确认"),
    ("CLOSE_POD", "关闭POD盖"),
    ("REACH_POS", "机械臂到位"),
    ("WRITE_TAG", "写入RFID标签"),
    ("COMPLETED_PORT_UNLOCK", "端口解锁完成"),
    ("POD_REMOVED", "POD移走"),
]

# 报警选项
ALARM_OPTIONS = [
    ("9004", "POD NOT FOUND", "crit"),
    ("9003", "POD DOOR NOT LOCKED", "warn"),
    ("20011", "TAG READ FAIL", "warn"),
    ("0411", "DOOR OPEN TIMEOUT", "info"),
    ("0201", "PORT LOCK FAIL", "crit"),
]

LOT_POOL = ["V3NL8", "V394K", "PG0R3", "V39S5", "V3QS6", "PG0R4", "V394L"]

_event_counter = None


def _init_event_counter():
    """从数据库读取最大WIN.开头的RAW_ID，作为计数器初始值"""
    global _event_counter
    if _event_counter is not None:
        return
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT MAX(RAW_ID) FROM DT_EVENT_RAW 
                WHERE RAW_ID LIKE 'WIN.%'
            """))
            row = result.fetchone()
            if row and row[0]:
                max_id_str = str(row[0])
                num_str = max_id_str.replace("WIN.", "")
                try:
                    _event_counter = int(num_str)
                    print(f"[WinForm] 从数据库读取最大事件ID: {max_id_str}, 计数器初始值: {_event_counter}")
                except ValueError:
                    _event_counter = 900000
            else:
                _event_counter = 900000
                print(f"[WinForm] 数据库无WIN事件，计数器初始值: {_event_counter}")
    except Exception as e:
        print(f"[WinForm] 读取最大ID失败，使用默认值: {e}")
        _event_counter = 900000


def next_event_id():
    global _event_counter
    if _event_counter is None:
        _init_event_counter()
    _event_counter += 1
    return f"WIN.{_event_counter}"


def _gen_cassette_id():
    return f"{random.randint(10000, 99999)}{random.choice('ABCDEF')}"


def write_event_to_db(event_name, mode, lot_id, cassette_id, is_alarm=False, alarm_info=None):
    """写入事件到DB（DT_EVENT_RAW + DT_EVENT_RAW_CUR）"""
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
    raw_id = next_event_id()

    if is_alarm and alarm_info:
        alarm_id, alarm_text, severity = alarm_info
        payload = json.dumps({
            "tool_id": TOOL_ID,
            "lot_id": lot_id,
            "run_mode": mode,
            "event_type": "VFEI",
            "event_name": "EC_ALARM_REPORT",
            "event_value": alarm_id,
            "status": "ALARM",
            "machine_state": "ALARM",
            "machine_mode": mode,
            "alarm_code": alarm_id,
            "alarm_id": alarm_id,
            "alarm_text": alarm_text,
            "severity": severity,
            "source_system": "RV",
            "port_id": "1",
            "cassette_id": cassette_id,
            "pod_id": cassette_id,
            "smif_id": "1",
            "chamber_id": "NULL",
            "batch_id": f"BT_{cassette_id}",
            "unit_id": "NULL",
            "slot_id": "NULL",
        }, ensure_ascii=False)
    else:
        has_lot = event_name not in ("POD_PLACED", "COMPLETED_PORT_LOCK", "READ_BATTERY", "READ_TAG")
        event_type = "HOST" if event_name in ("BATCH_INFO_FROM_ECUI", "UI_CONFIRM", "ACK_UI_DOUBLECHECK") else "VFEI"
        payload = json.dumps({
            "tool_id": TOOL_ID,
            "lot_id": lot_id if has_lot else "NULL",
            "run_mode": mode if mode else "NULL",
            "event_type": event_type,
            "event_name": event_name,
            "event_value": event_name,
            "status": event_name,
            "machine_state": event_name,
            "machine_mode": mode if mode else "NULL",
            "alarm_code": None,
            "alarm_id": None,
            "alarm_text": event_name,
            "source_system": "RV",
            "port_id": "1",
            "cassette_id": cassette_id,
            "pod_id": cassette_id,
            "smif_id": "1",
            "chamber_id": "NULL",
            "batch_id": f"BT_{cassette_id}" if has_lot else "NULL",
            "unit_id": "NULL",
            "slot_id": "NULL",
        }, ensure_ascii=False)

    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO DT_EVENT_RAW (RAW_ID, TOOL_ID, SOURCE_SYSTEM, SOURCE_MESSAGE_ID,
                RECEIVED_TS_UTC, EVENT_TS_UTC, PAYLOAD_JSON, PARSE_STATUS, ERROR_MESSAGE)
            VALUES (:raw_id, :tool_id, :source_system, :source_message_id,
                :received_ts, :event_ts, :payload, 'PARSED', NULL)
        """), {
            "raw_id": raw_id,
            "tool_id": TOOL_ID,
            "source_system": "RV",
            "source_message_id": raw_id,
            "received_ts": ts,
            "event_ts": ts,
            "payload": payload,
        })

        # 更新CUR表
        conn.execute(text("DELETE FROM DT_EVENT_RAW_CUR WHERE TOOL_ID = :tool_id"), {"tool_id": TOOL_ID})
        conn.execute(text("""
            INSERT INTO DT_EVENT_RAW_CUR (TOOL_ID, RAW_ID, SOURCE_SYSTEM, SOURCE_MESSAGE_ID,
                RECEIVED_TS_UTC, EVENT_TS_UTC, PAYLOAD_JSON, PARSE_STATUS, ERROR_MESSAGE)
            VALUES (:tool_id, :raw_id, :source_system, :source_message_id,
                :received_ts, :event_ts, :payload, 'PARSED', NULL)
        """), {
            "tool_id": TOOL_ID,
            "raw_id": raw_id,
            "source_system": "RV",
            "source_message_id": raw_id,
            "received_ts": ts,
            "event_ts": ts,
            "payload": payload,
        })
        conn.commit()

    return raw_id


class PodopenerSimulator:
    def __init__(self, root):
        self.root = root
        self.root.title("PODOPENER 模拟器 - " + TOOL_ID)
        self.root.geometry("700x650")
        self.root.configure(bg="#f0f0f0")

        self.lot_id = StringVar(value=random.choice(LOT_POOL))
        self.cassette_id = StringVar(value=_gen_cassette_id())
        self.current_mode = StringVar(value="PACKING")
        self.auto_running = False
        self.auto_thread = None

        self._build_ui()
        self._log("模拟器启动，机台: " + TOOL_ID)

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        # 机台信息区
        info_frame = ttk.LabelFrame(self.root, text="机台信息", padding=10)
        info_frame.pack(fill="x", padx=10, pady=5)

        row1 = ttk.Frame(info_frame)
        row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="机台ID:", width=10).pack(side="left")
        ttk.Label(row1, text=TOOL_ID, font=("Arial", 10, "bold")).pack(side="left")
        ttk.Label(row1, text="   Lot ID:", width=10).pack(side="left")
        ttk.Entry(row1, textvariable=self.lot_id, width=15).pack(side="left")
        ttk.Button(row1, text="随机", width=6, command=self._random_lot).pack(side="left", padx=5)

        row2 = ttk.Frame(info_frame)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="Cassette:", width=10).pack(side="left")
        ttk.Entry(row2, textvariable=self.cassette_id, width=15).pack(side="left")
        ttk.Button(row2, text="随机", width=6, command=self._random_cassette).pack(side="left", padx=5)
        ttk.Label(row2, text="   模式:", width=10).pack(side="left")
        ttk.Combobox(row2, textvariable=self.current_mode, values=["PACKING", "UNPACKING"],
                     width=12, state="readonly").pack(side="left")

        # 穿入流程区
        pack_frame = ttk.LabelFrame(self.root, text="穿入流程 (PACKING) - 14步", padding=10)
        pack_frame.pack(fill="x", padx=10, pady=5)

        btn_row = ttk.Frame(pack_frame)
        btn_row.pack(fill="x")
        for i, (evt_name, desc) in enumerate(PACKING_FLOW):
            if i % 7 == 0 and i > 0:
                btn_row = ttk.Frame(pack_frame)
                btn_row.pack(fill="x", pady=2)
            btn = ttk.Button(btn_row, text=f"{i+1}.{desc}", width=14,
                             command=lambda e=evt_name, d=desc, m="PACKING": self._step_event(e, d, m))
            btn.pack(side="left", padx=2, pady=2)

        auto_pack_row = ttk.Frame(pack_frame)
        auto_pack_row.pack(fill="x", pady=(8, 0))
        ttk.Button(auto_pack_row, text="▶ 自动执行穿入流程", command=lambda: self._auto_run("PACKING")).pack(side="left")
        ttk.Button(auto_pack_row, text="⏹ 停止", command=self._stop_auto).pack(side="left", padx=10)

        # 脱出流程区
        unpack_frame = ttk.LabelFrame(self.root, text="脱出流程 (UNPACKING) - 6步", padding=10)
        unpack_frame.pack(fill="x", padx=10, pady=5)

        btn_row2 = ttk.Frame(unpack_frame)
        btn_row2.pack(fill="x")
        for i, (evt_name, desc) in enumerate(UNPACKING_FLOW):
            btn = ttk.Button(btn_row2, text=f"{i+1}.{desc}", width=14,
                             command=lambda e=evt_name, d=desc, m="UNPACKING": self._step_event(e, d, m))
            btn.pack(side="left", padx=2, pady=2)

        auto_unpack_row = ttk.Frame(unpack_frame)
        auto_unpack_row.pack(fill="x", pady=(8, 0))
        ttk.Button(auto_unpack_row, text="▶ 自动执行脱出流程", command=lambda: self._auto_run("UNPACKING")).pack(side="left")

        # 报警区
        alarm_frame = ttk.LabelFrame(self.root, text="报警模拟", padding=10)
        alarm_frame.pack(fill="x", padx=10, pady=5)

        for i, (alarm_id, alarm_text, sev) in enumerate(ALARM_OPTIONS):
            btn = ttk.Button(alarm_frame, text=f"{alarm_id} {alarm_text} [{sev}]",
                             command=lambda ai=alarm_id, at=alarm_text, s=sev: self._trigger_alarm(ai, at, s))
            btn.grid(row=i // 3, column=i % 3, sticky="ew", padx=3, pady=2)
        for i in range(3):
            alarm_frame.columnconfigure(i, weight=1)

        # 日志区
        log_frame = ttk.LabelFrame(self.root, text="事件日志", padding=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(END, f"[{ts}] {msg}\n")
        self.log_text.see(END)

    def _random_lot(self):
        self.lot_id.set(random.choice(LOT_POOL))
        self._log(f"新Lot ID: {self.lot_id.get()}")

    def _random_cassette(self):
        self.cassette_id.set(_gen_cassette_id())
        self._log(f"新Cassette ID: {self.cassette_id.get()}")

    def _step_event(self, event_name, desc, mode):
        try:
            raw_id = write_event_to_db(
                event_name, mode,
                self.lot_id.get(), self.cassette_id.get()
            )
            self._log(f"✓ {desc} | {event_name} | ID:{raw_id}")
        except Exception as e:
            self._log(f"✗ 错误: {e}")

    def _trigger_alarm(self, alarm_id, alarm_text, severity):
        try:
            mode = self.current_mode.get()
            raw_id = write_event_to_db(
                "EC_ALARM_REPORT", mode,
                self.lot_id.get(), self.cassette_id.get(),
                is_alarm=True, alarm_info=(alarm_id, alarm_text, severity)
            )
            self._log(f"⚠ 报警: {alarm_id} {alarm_text} [{severity}] ID:{raw_id}")
        except Exception as e:
            self._log(f"✗ 错误: {e}")

    def _auto_run(self, mode):
        if self.auto_running:
            return
        self.auto_running = True
        flow = PACKING_FLOW if mode == "PACKING" else UNPACKING_FLOW
        self._log(f"开始自动执行{mode}流程...")
        self.auto_thread = threading.Thread(target=self._auto_run_worker, args=(flow, mode), daemon=True)
        self.auto_thread.start()

    def _auto_run_worker(self, flow, mode):
        for evt_name, desc in flow:
            if not self.auto_running:
                break
            try:
                raw_id = write_event_to_db(
                    evt_name, mode,
                    self.lot_id.get(), self.cassette_id.get()
                )
                self.root.after(0, lambda d=desc, e=evt_name, r=raw_id: self._log(f"✓ {d} | {e} | ID:{r}"))
            except Exception as e:
                self.root.after(0, lambda err=e: self._log(f"✗ 错误: {err}"))
            time.sleep(1.5)
        self.auto_running = False
        self.root.after(0, lambda: self._log(f"--- {mode}流程执行完成 ---"))

    def _stop_auto(self):
        self.auto_running = False
        self._log("停止自动执行")


def main():
    root = tk.Tk()
    app = PodopenerSimulator(root)
    root.mainloop()


if __name__ == "__main__":
    main()
