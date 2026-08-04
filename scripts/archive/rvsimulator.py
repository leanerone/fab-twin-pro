import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tkinter as tk
from tkinter import ttk, messagebox
import json
import requests
from datetime import datetime

API_BASE = "http://localhost:8002"

EVENT_TYPES = [
    ("POD穿入", "ATTACH_POD_PLACE"),
    ("POD脱出", "DETACH_POD_PLACE"),
    ("POD上锁", "POD_LOCK"),
    ("POD解锁", "POD_UNLOCK"),
    ("读取标签", "READ_TAG"),
    ("写入标签", "WRITE_TAG"),
    ("开始映射", "StartMapping_LEFT"),
    ("结束映射", "EndMapping"),
    ("报警-电池电压", "EC_ALARM_REPORT_0201"),
    ("报警-测试时间", "EC_ALARM_REPORT_9003"),
    ("报警-清洗到期", "EC_ALARM_REPORT_0411"),
    ("报警-DirtyBit", "EC_ALARM_REPORT_20011"),
]

LOT_POOL = ["V3NL8", "V394K", "PG0R3", "V39S5", "V3QS6", "PG0R4", "V394L"]

class RVMessageSimulator:
    def __init__(self, root):
        self.root = root
        self.root.title("RV消息模拟器 - PODOPENER-1")
        self.root.geometry("600x500")
        self.root.resizable(False, False)

        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="PODOPENER-1 RV消息模拟器", font=("微软雅黑", 14, "bold")).pack(pady=(0, 15))

        ttk.Label(main_frame, text="事件类型：").pack(anchor=tk.W)
        self.event_var = tk.StringVar()
        self.event_combo = ttk.Combobox(main_frame, textvariable=self.event_var, 
                                       values=[e[0] for e in EVENT_TYPES], width=30)
        self.event_combo.current(0)
        self.event_combo.pack(pady=(0, 10), fill=tk.X)

        ttk.Label(main_frame, text="Lot ID：").pack(anchor=tk.W)
        self.lot_var = tk.StringVar()
        self.lot_combo = ttk.Combobox(main_frame, textvariable=self.lot_var,
                                      values=LOT_POOL, width=30)
        self.lot_combo.current(0)
        self.lot_combo.pack(pady=(0, 10), fill=tk.X)

        ttk.Label(main_frame, text="Cassette ID：").pack(anchor=tk.W)
        self.cassette_var = tk.StringVar(value="12345A")
        ttk.Entry(main_frame, textvariable=self.cassette_var, width=35).pack(pady=(0, 10), fill=tk.X)

        ttk.Label(main_frame, text="消息内容预览：").pack(anchor=tk.W)
        self.payload_text = tk.Text(main_frame, height=8, width=60)
        self.payload_text.pack(pady=(0, 10), fill=tk.X)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="发送消息", command=self.send_message).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="刷新预览", command=self.update_preview).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="查看当前状态", command=self.check_status).pack(side=tk.LEFT)

        self.log_text = tk.Text(main_frame, height=10, width=60)
        self.log_text.pack(pady=(10, 0), fill=tk.BOTH, expand=True)

        self.update_preview()

    def update_preview(self):
        event_name = dict(EVENT_TYPES)[self.event_var.get()]
        lot_id = self.lot_var.get()
        cassette_id = self.cassette_var.get()
        
        payload = {
            "lot_id": lot_id,
            "run_mode": "NULL",
            "event_type": "VFEI",
            "event_name": event_name.replace("EC_ALARM_REPORT_", "EC_ALARM_REPORT"),
            "port_id": "1",
            "cassette_id": cassette_id,
            "chamber_id": "1",
            "smif_id": "1",
            "batch_id": lot_id,
            "unit_id": "1",
            "slot_id": "NULL",
            "alarm_id": "NULL",
            "alarm_text": "NULL"
        }

        if event_name.startswith("EC_ALARM_REPORT_"):
            alarm_id = event_name.replace("EC_ALARM_REPORT_", "")
            payload["alarm_id"] = alarm_id
            alarm_texts = {
                "0201": f"SERIAL_ID={cassette_id},电池电压异常！",
                "9003": "温馨提示测机时间快到了!",
                "0411": "此POD尚余3天到清洗日期，请尽速更换新POD",
                "20011": "Pod DirtyBit <> Cassette DirtyBit!"
            }
            payload["alarm_text"] = alarm_texts.get(alarm_id, "Alarm")

        self.payload_text.delete(1.0, tk.END)
        self.payload_text.insert(1.0, json.dumps(payload, indent=2, ensure_ascii=False))

    def send_message(self):
        event_name = dict(EVENT_TYPES)[self.event_var.get()]
        lot_id = self.lot_var.get()
        cassette_id = self.cassette_var.get()
        
        payload = {
            "lot_id": lot_id,
            "run_mode": "NULL",
            "event_type": "VFEI",
            "event_name": event_name.replace("EC_ALARM_REPORT_", "EC_ALARM_REPORT"),
            "port_id": "1",
            "cassette_id": cassette_id,
            "chamber_id": "1",
            "smif_id": "1",
            "batch_id": lot_id,
            "unit_id": "1",
            "slot_id": "NULL",
            "alarm_id": "NULL",
            "alarm_text": "NULL"
        }

        if event_name.startswith("EC_ALARM_REPORT_"):
            alarm_id = event_name.replace("EC_ALARM_REPORT_", "")
            payload["alarm_id"] = alarm_id
            alarm_texts = {
                "0201": f"SERIAL_ID={cassette_id},电池电压异常！",
                "9003": "温馨提示测机时间快到了!",
                "0411": "此POD尚余3天到清洗日期，请尽速更换新POD",
                "20011": "Pod DirtyBit <> Cassette DirtyBit!"
            }
            payload["alarm_text"] = alarm_texts.get(alarm_id, "Alarm")

        now = datetime.now().isoformat()
        data = {
            "tool_id": "PODOPENER-1",
            "source_system": "RV",
            "source_message_id": f"TID.{int(datetime.now().timestamp())}",
            "received_ts_utc": now,
            "event_ts_utc": now,
            "payload_json": json.dumps(payload, ensure_ascii=False),
            "parse_status": "PARSED"
        }

        try:
            response = requests.post(f"{API_BASE}/api/rv_message", json=data)
            if response.status_code == 200:
                self.log(f"✓ 消息发送成功: {self.event_var.get()}")
                self.log(f"  Lot: {lot_id}, Cassette: {cassette_id}")
            else:
                self.log(f"✗ 发送失败: {response.status_code}")
        except Exception as e:
            self.log(f"✗ 连接失败: {str(e)}")
            self.log(f"  请确保后端服务已启动: {API_BASE}")

    def check_status(self):
        try:
            response = requests.get(f"{API_BASE}/health")
            if response.status_code == 200:
                self.log("✓ 后端服务正常运行")
            
            rv_cur = requests.get(f"{API_BASE}/api/rv/current/PODOPENER-1")
            if rv_cur.status_code == 200:
                data = rv_cur.json()
                self.log(f"✓ 当前状态: {data.get('event_name', 'N/A')}")
            else:
                self.log("✓ 当前状态: 暂无数据")
        except Exception as e:
            self.log(f"✗ 检查失败: {str(e)}")

    def log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {msg}\n")
        self.log_text.see(tk.END)


if __name__ == "__main__":
    root = tk.Tk()
    app = RVMessageSimulator(root)
    root.mainloop()
