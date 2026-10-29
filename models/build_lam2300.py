# -*- coding: utf-8 -*-
"""LAM2300 顶视图建模：SVG + Motion JSON 生成

用法：
    python models/build_lam2300.py

产出：
    models/user/lam2300-topview.svg
    models/user/lam2300-topview.motion.json

设计依据：
  · 布局照 docs/assets/machine-references/LAM2300.jpg（Lam 2300 平台俯视图）
    ATM 大气端（3×Load Port + Aligner + 2×Buffer + Control Rack + ATM 机器人）
    → 2×Airlock → 中央圆形 VTM（含机器人）→ 4×PM 放射
  · 事件词表**复用 OXE 的 26 步标准集**，不发明新事件名，
    这样现有 DB 数据 / 调试注入流程 / AI 链路天然就能驱动它
  · 所有部件 id + data-pid 双写（引擎按 id 定位，编辑器按 data-pid 检视）

改模型请改本脚本再重跑，不要手改产物（与 build_oxe_motion.py 同约定）。
"""
from __future__ import annotations

import json
import math
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "svg_kit"))

import primitives as P  # noqa: E402
import motion as M  # noqa: E402

OUT_SVG = os.path.join(_HERE, "user", "lam2300-topview.svg")
OUT_MOTION = os.path.join(_HERE, "user", "lam2300-topview.motion.json")

W, H = 1080, 880

# ── 布局坐标（改这里即可调整排布）────────────────────────────────
LP_X = [90, 225, 360]           # 三个 Load Port 左上角 x
LP_Y, LP_W, LP_H = 70, 120, 130
ALIGNER = (620, 110, 44)        # cx, cy, r
BUF1 = (620, 250, 40)           # Metrology buffer
BUF2 = (890, 290, 36)           # 右侧 buffer
CTRL_RACK = (880, 70, 130, 180)
ATM_HUB = (430, 250)            # ATM 机器人回转中心

AL_A = (700, 340, 120, 100)     # Airlock A（右）
AL_B = (330, 340, 120, 100)     # Airlock B（左）

VTM = (540, 570, 118)           # cx, cy, r
PM_RING = 265                   # PM 到 VTM 中心的距���
PM_R = 62
# PM 角度（度，0=右，逆时针为正；SVG y 向下，故用 -sin）
PM_ANGLES = {"PM1": 0, "PM2": -45, "PM3": -135, "PM4": 180}


def pm_center(name: str):
    a = math.radians(PM_ANGLES[name])
    return VTM[0] + PM_RING * math.cos(a), VTM[1] + PM_RING * math.sin(a)


# ============================ SVG ============================
def build_svg() -> str:
    out = [P.svg_open(W, H), P.defs()]

    out.append(P.baseplate("BASEPLATE", 30, 30, W - 60, H - 60))
    out.append(P.signal_tower("TOWER", W - 110, 56))
    out.append(P.title_block("TITLE", 46, H - 34,
                             "LAM 2300 TOPVIEW", "ATM / 2xAirlock / VTM / 4xPM"))

    # ── ATM 大气端 ──
    for i, x in enumerate(LP_X, start=1):
        pid = f"LP{i}"
        out.append(P.port_box(pid, x, LP_Y, w=LP_W, h=LP_H, name=f"LP{i}"))
        out.append(P.cassette(f"{pid}_CST", x + 12, LP_Y + 12, LP_W - 24, LP_H - 34))
        out.append(P.label(None, x + LP_W / 2, LP_Y - 8, f"STATION {i}", size=10))

    # Aligner（晶圆寻边：带可旋转卡盘）
    ax, ay, ar = ALIGNER
    aligner = (
        f'<circle cx="{ax}" cy="{ay}" r="{ar}" fill="{P.T("metal.panel")}" '
        f'stroke="{P.T("stroke.default_color")}" stroke-width="{P.T("stroke.default_width")}"/>'
        f'<circle cx="{ax}" cy="{ay}" r="{ar * 0.62:.1f}" fill="{P.T("metal.dark")}" '
        f'stroke="{P.T("stroke.default_color")}" stroke-width="{P.T("stroke.thin_width")}"/>'
        + P.bolt_circle(ax, ay, ar * 0.86, 8)
        + P.wafer(f"ALIGNER_WAFER", ax, ay, ar * 0.34)
    )
    out.append(P.group("ALIGNER", aligner))
    out.append(P.label(None, ax, ay - ar - 10, "ALIGNER  ST7", size=10))

    # Buffer 站
    for pid, (bx, by, br) in (("BUF1", BUF1), ("BUF2", BUF2)):
        body = (
            f'<circle cx="{bx}" cy="{by}" r="{br}" fill="{P.T("metal.panel")}" '
            f'stroke="{P.T("stroke.default_color")}" stroke-width="{P.T("stroke.default_width")}"/>'
            f'<circle cx="{bx}" cy="{by}" r="{br * 0.7:.1f}" fill="{P.T("metal.dark")}" '
            f'stroke="{P.T("stroke.default_color")}" stroke-width="{P.T("stroke.thin_width")}"/>'
        )
        out.append(P.group(pid, body))
        out.append(P.label(None, bx, by + 4, "BUF", size=10, fill=P.T("text.inverse")))

    # Control Rack
    crx, cry, crw, crh = CTRL_RACK
    out.append(P.rect("CTRL_RACK", crx, cry, crw, crh, fill=P.T("metal.panel"), rx=6))
    out.append(P.label(None, crx + crw / 2, cry + crh / 2, "CONTROL\nRACK", size=11))

    # ATM 机器人
    out.append(P.robot_arm("ATM_ARM", ATM_HUB[0], ATM_HUB[1],
                           upper_len=86, fore_len=68, wrist_r=38))
    out.append(P.circle("ATM_HUB", ATM_HUB[0], ATM_HUB[1], 14,
                        fill=P.T("metal.dark")))

    # ── Airlock（ATM↔VTM 真空隔离通道）──
    for pid, (alx, aly, alw, alh) in (("AL_A", AL_A), ("AL_B", AL_B)):
        body = [
            P.rect(None, alx, aly, alw, alh, fill=P.T("metal.panel"), rx=5),
            P.rect(f"{pid}_DOOR", alx + 8, aly + 8, alw - 16, alh - 16,
                   fill=P.T("port.inner_fill"), rx=3),
        ]
        out.append(P.group(pid, "\n".join(body)))
        out.append(P.label(None, alx + alw / 2, aly - 6,
                           "AIRLOCK A" if pid == "AL_A" else "AIRLOCK B", size=10))

    # ── VTM 真空传输腔（圆形，与工艺腔区分）──
    vx, vy, vr = VTM
    vtm = (
        f'<circle cx="{vx}" cy="{vy}" r="{vr}" fill="{P.T("metal.panel")}" '
        f'stroke="{P.T("stroke.default_color")}" stroke-width="{P.T("stroke.default_width")}"/>'
        f'<circle cx="{vx}" cy="{vy}" r="{vr * 0.82:.1f}" fill="{P.T("metal.dark")}" '
        f'stroke="{P.T("stroke.default_color")}" stroke-width="{P.T("stroke.thin_width")}"/>'
        + P.bolt_circle(vx, vy, vr * 0.93, 12)
        + P.label(None, vx, vy - vr + 20, "VTM", size=13, fill=P.T("text.inverse"))
    )
    out.append(P.group("VTM", vtm))

    out.append(P.robot_arm("VTM_ARM", vx, vy, upper_len=92, fore_len=72, wrist_r=40))
    out.append(P.circle("VTM_HUB", vx, vy, 16, fill=P.T("metal.dark")))

    # ── 4 个工艺腔（放射状）──
    for name in ("PM1", "PM2", "PM3", "PM4"):
        cx, cy = pm_center(name)
        out.append(P.chamber(name, cx, cy, PM_R, name=name))

    # ── 随臂搬运的晶圆（deriver 用 snap 把它送到各单元）──
    out.append(P.wafer("WAFER_MOVE", ATM_HUB[0], ATM_HUB[1], 11))
    out.append(P.wafer("WAFER_VTM", vx, vy, 11))

    out.append(P.svg_close())
    return "".join(out)


# ============================ Motion ============================
def build_motion() -> dict:
    b = M.MotionBuilder(
        machine_type="LAM2300",
        name="LAM 2300 顶视图",
        src="lam2300-topview.svg",
        deriver="lam2300",
        version="1.0",
        description="Lam 2300 cluster 顶视动画：ATM 取片 → Aligner 寻边 → Airlock 过渡 → VTM 送片 → PM 加工 → 回程",
    )
    b.param_defaults(PORT="LP1", CH="PM1", SLOT=1, STATE="RUN")
    b.part_aliases(POD="{PORT}_CST", DOOR="{PORT}_DOOR", ARM="ATM_ARM")

    V = "VTM_ARM"

    # 1) POD 放置：晶舟出现，25 槽置为「等待」
    b.add("POD_PLACED", [
        M.rule("{PORT}_CST", [M.visibility(True, 0)]),
        M.rule("{PORT}_DOOR", [M.visibility(True, 0)]),
    ], description="晶舟放到 Load Port")

    # 2~4) 端口锁定 / 解锁
    b.add("COMPLETED_PORT_LOCK", [
        M.rule("{PORT}_DOOR", [M.visibility(True, 0)]),
    ], description="端口锁定完成")
    b.add("LOCK_PORT_COMPLETED", [
        M.rule("{PORT}_DOOR", [M.visibility(True, 0)]),
    ])
    b.add("UNLOCK_PORT_COMPLETED", [
        M.rule("{PORT}_DOOR", [M.visibility(True, 0)]),
    ])

    # 5) 晶圆移入 EFEM
    b.add("MVIN", [
        M.rule("WAFER_MOVE", [M.visibility(True, 0), M.snap("{PORT}_CST", 0)]),
    ], description="晶圆从晶舟取出，进入大气端")

    # 6~7) 门开合
    b.add("DOOR_OPEN", [
        M.rule("{PORT}_DOOR", [M.offset(0, -8, 300)]),
    ])
    b.add("DOOR_CLOSE", [
        M.rule("{PORT}_DOOR", [M.offset(0, 0, 300)]),
    ])

    # 8~10) 装载循环
    b.add("LOAD_CYCLE_STARTED", [
        M.rule("ATM_ARM", [M.rotate(0, 300)]),
        M.rule("WAFER_MOVE", [M.visibility(True, 0)]),
    ], description="ATM 机械臂开始取片循环")
    b.add("LOAD_CYCLE_COMPLETED", [
        M.rule("ALIGNER_WAFER", [M.visibility(True, 0)]),
    ], description="取片完成，晶圆到 Aligner")
    b.add("UNLOAD_CYCLE_COMPLETED", [
        M.rule("WAFER_MOVE", [M.visibility(False, 200)]),
    ])

    # 11~13) 寻边（Aligner 旋转）
    b.add("STARTMAPPING", [
        M.rule("ALIGNER", [M.rotate(0, 200)]),
    ], description="开始寻边，Aligner 卡盘回零")
    b.add("WAFER_MAPPING", [
        M.rule("ALIGNER", [M.rotate(180, 900)]),
        M.rule("ALIGNER_WAFER", [M.visibility(True, 0), M.rotate(180, 900)]),
    ], description="晶圆寻边：卡盘带动晶圆旋转")
    b.add("ENDMAPPING", [
        M.rule("ALIGNER", [M.rotate(0, 200)]),
    ])

    # 14) 批次信息
    b.add("BATCH_INFO_FROM_ECUI", [
        M.rule("TITLE", [M.visibility(True, 0)]),
    ])

    # 15~16) 进出工艺腔（核心：ATM 臂 → Airlock → VTM 臂 → PM）
    b.add("WAFERLOADED", [
        M.rule("WAFER_MOVE", [M.visibility(True, 0)]),
        M.rule("ATM_ARM", [M.rotate(0, 350)]),
        M.rule("WAFER_VTM", [M.visibility(False, 0)]),
        M.rule("{CH}", [M.opacity(1.0, 200)]),
        M.rule("{CH}_run", [M.visibility(True, 0)]),
    ], description="晶圆经 ATM 臂送入 Airlock，VTM 臂接手送进工艺腔")
    b.add("WAFERUNLOADED", [
        M.rule("WAFER_VTM", [M.visibility(True, 0), M.snap("{CH}", 350)]),
        M.rule(V, [M.rotate(0, 350)]),
        M.rule("{CH}_run", [M.visibility(False, 0)]),
        M.rule("{CH}_unload", [M.visibility(True, 0)]),
    ], description="加工完成，晶圆由 VTM 臂取回")

    # 17~21) 工艺过程
    b.add("START", [
        M.rule("{CH}_run", [M.visibility(True, 0)]),
        M.rule("{CH}", [M.opacity(1.0, 200)]),
    ], description="工艺腔开始加工")
    b.add("PS", [
        M.rule("{CH}_run", [M.visibility(True, 0)]),
    ], description="工艺进行中")
    b.add("PE", [
        M.rule("{CH}_run", [M.visibility(False, 0)]),
        M.rule("{CH}_unload", [M.visibility(True, 0)]),
    ], description="工艺结束，转入取片态")
    b.add("MVOU", [
        M.rule("WAFER_VTM", [M.visibility(True, 0)]),
        M.rule(V, [M.rotate(0, 350)]),
    ], description="晶圆移出工艺腔")
    b.add("READYTOUNLOAD", [
        M.rule("{CH}_unload", [M.visibility(True, 0)]),
    ])

    # 22) 告警
    b.add("ALARM_REPORT", [
        M.rule("TOWER_alarm", [M.opacity(1.0, 0)]),
        M.rule("{CH}_alarm", [M.visibility(True, 0)]),
    ], description="告警：塔灯红灯点亮 + 对应腔体告警灯")

    # 23) 状态刷新（塔灯）
    b.add("STATE", [
        M.rule("TOWER_run", [M.opacity(1.0, 0)]),
    ])

    # 24) 传输中
    b.add("TRANSFER", [
        M.rule(V, [M.rotate(0, 400)]),
        M.rule("ATM_ARM", [M.rotate(0, 400)]),
    ], description="双臂联动传输")

    # 25) FDC 清上下文
    b.add("FDC_CLEARCONTEXT", [
        M.rule("WAFER_MOVE", [M.visibility(False, 0)]),
        M.rule("WAFER_VTM", [M.visibility(False, 0)]),
    ])

    # 26) 晶舟取走
    b.add("POD_REMOVED", [
        M.rule("{PORT}_CST", [M.visibility(False, 0)]),
        M.rule("{PORT}_DOOR", [M.visibility(True, 0)]),
    ], description="晶舟移走")

    return b.build()


def main() -> int:
    os.makedirs(os.path.dirname(OUT_SVG), exist_ok=True)
    with open(OUT_SVG, "w", encoding="utf-8") as f:
        f.write(build_svg())
    with open(OUT_MOTION, "w", encoding="utf-8") as f:
        json.dump(build_motion(), f, ensure_ascii=False, indent=2)
    print(f"已生成:\n  {OUT_SVG}\n  {OUT_MOTION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
