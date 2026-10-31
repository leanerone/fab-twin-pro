# -*- coding: utf-8 -*-
"""重构前后通用冒烟测试：一条命令验证核心功能链路无缺失。

用法（后端服务需已启动）：
    python tests/smoke_baseline.py                 # 默认 http://localhost:8002
    BASE=http://localhost:8002 python tests/smoke_baseline.py

覆盖：健康检查 / 登录 / 机台列表 / 历史事件与时间轴 / 七机型视图配置 / 告警与批次。
全部通过输出 SMOKE PASS 并退出码 0；任何一项失败输出 SMOKE FAIL 与明细，退出码 1。
"""
import os
import sys

import httpx

BASE = os.environ.get("BASE", "http://localhost:8002")
EXPECTED_MODELS = {
    "PODOPENER-2200": "motion2d",
    "TEL-DRM-UNIT": "motion2d",
    "AMAT-METSPUT": "motion2d",
    "LAM2300": "motion2d",
    "TEL-SYNAPSE": "motion2d",
    "AMAT-CENTRIS-SYM3": "motion2d",
    "GENERIC-ETCH": "threejs",
}

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def main():
    client = httpx.Client(timeout=20)
    # 1. 健康检查
    r = client.get(f"{BASE}/health")
    body = r.json() if r.status_code == 200 else {}
    check("健康检查", body.get("status") == "ok", f"status={body.get('status')}")
    # 2. 登录
    r = client.post(f"{BASE}/api/auth/login-password",
                    json={"username": "admin", "password": "admin123"})
    token = (r.json() or {}).get("token", "") if r.status_code == 200 else ""
    check("登录", bool(token), "admin/admin123")
    headers = {"Authorization": f"Bearer {token}"}
    # 3. 机台列表
    r = client.get(f"{BASE}/api/machines", headers=headers)
    machines = r.json() if r.status_code == 200 else []
    if isinstance(machines, dict):
        machines = machines.get("machines", [])
    check("机台列表", r.status_code == 200 and len(machines) >= 40, f"{len(machines)} 台")
    # 4. 历史事件 + 时间轴
    r = client.get(f"{BASE}/api/history/OXE-51?limit=3", headers=headers)
    evs = (r.json() or {}).get("events", []) if r.status_code == 200 else []
    check("历史事件", r.status_code == 200 and len(evs) > 0, f"{len(evs)} 条")
    r = client.get(f"{BASE}/api/history/OXE-51/timeline", headers=headers)
    check("历史时间轴", r.status_code == 200, f"HTTP {r.status_code}")
    # 5. 七机型视图配置
    for model_id, expect_mode in EXPECTED_MODELS.items():
        r = client.get(f"{BASE}/api/models/{model_id}", headers=headers)
        d = r.json() if r.status_code == 200 else {}
        mode = d.get("view_mode")
        vc = d.get("views_config") or {}
        svg = bool((vc.get("view_2d") or {}).get("svg_source")) or model_id in (
            "GENERIC-ETCH", "TEL-DRM-UNIT", "PODOPENER-2200")
        motion = bool(d.get("animation_config")) or model_id == "GENERIC-ETCH"
        check(f"机型 {model_id}", mode == expect_mode and svg and motion,
              f"view_mode={mode}")
    # 6. 告警 / 批次
    r = client.get(f"{BASE}/api/alarms", headers=headers)
    check("告警接口", r.status_code == 200)
    r = client.get(f"{BASE}/api/lots", headers=headers)
    check("批次接口", r.status_code == 200)

    failed = [x for x in results if not x[1]]
    print(f"\nSMOKE {'PASS' if not failed else 'FAIL'}  "
          f"({len(results) - len(failed)}/{len(results)} 项通过)")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
