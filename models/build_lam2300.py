# -*- coding: utf-8 -*-
"""LAM2300 顶视图建模：SVG + Motion JSON 生成。

布局照 docs/assets/machine-references/LAM2300.jpg：3×Load Port、Aligner、
2×Buffer、Control Rack、双斜置 Airlock、中央 VTM 与四个放射 PM。
改模型请改本脚本再重跑，不要手改产物。
"""
from __future__ import annotations

import json
import math
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "svg_kit"))

import primitives as P  # noqa: E402
import cluster_motion as CM  # noqa: E402

OUT_SVG = os.path.join(_HERE, "user", "lam2300-topview.svg")
OUT_MOTION = os.path.join(_HERE, "user", "lam2300-topview.motion.json")

W, H = 1080, 900
LP_X = [120, 260, 400]
LP_Y, LP_W, LP_H = 70, 120, 130
ALIGNER = (680, 145, 42)
BUF1 = (190, 280, 36)
BUF2 = (840, 285, 36)
CTRL_RACK = (720, 70, 150, 175)
ATM_HUB = (400, 280)
AL_A = (650, 380)
AL_B = (430, 380)
VTM = (540, 565, 110)
PM_RING = 240
# SVG y 向下：右、右下、左下、左，与参考图一致；上方两位留给 Airlock。
PM_ANGLES = {"PM1": 0, "PM2": 48, "PM3": 132, "PM4": 180}


def pm_center(name: str):
    a = math.radians(PM_ANGLES[name])
    return VTM[0] + PM_RING * math.cos(a), VTM[1] + PM_RING * math.sin(a)


def facing_angle(cx, cy, tx, ty):
    """top_process_chamber 的本地正面为 -Y，旋转后指向目标。"""
    return math.degrees(math.atan2(ty - cy, tx - cx)) + 90


BASE_HIDDEN = (
    [f"LP{i}_CST" for i in (1, 2, 3)]
    + ["WAFER_MOVE", "WAFER_VTM", "ALIGNER_WAFER"]
    + [f"PM{i}_{s}" for i in (1, 2, 3, 4) for s in ("run", "alarm", "unload")]
    + ["TOWER_alarm"]
)


def _mark_base_hidden(svg: str) -> str:
    for pid in BASE_HIDDEN:
        pat = re.compile(r'(<\w+[^>]*\bid="%s"[^>]*?)(/?>)' % re.escape(pid))
        svg, n = pat.subn(
            lambda m: m.group(1) + ' data-motion-base-visibility="hidden"' + m.group(2),
            svg, count=1,
        )
        if n != 1:
            raise RuntimeError(f"base-hidden 标注失败：找不到部件 {pid}")
    return svg


def build_svg() -> str:
    out = [P.svg_open(W, H), P.defs()]
    out.append(P.baseplate("BASEPLATE", 30, 30, W - 60, H - 60))
    out.append(P.signal_tower("TOWER", W - 90, 55))
    out.append(P.title_block("TITLE", 46, H - 42,
                             "LAM 2300 TOPVIEW", "ATM / 2x Airlock / VTM / 4x PM"))

    for i, x in enumerate(LP_X, start=1):
        pid = f"LP{i}"
        out.append(P.port_box(pid, x, LP_Y, w=LP_W, h=LP_H, name=pid))
        out.append(P.cassette(f"{pid}_CST", x + 12, LP_Y + 12, LP_W - 24, LP_H - 34))
        out.append(P.label(None, x + LP_W / 2, LP_Y - 9, f"ATM STATION {4-i}", size=9))

    ax, ay, ar = ALIGNER
    out.append(P.aligner("ALIGNER", ax, ay, ar))
    out.append(P.label(None, ax, ay - ar - 10, "ALIGNER  ST7", size=10))
    for pid, (bx, by, br) in (("BUF1", BUF1), ("BUF2", BUF2)):
        out.append(P.buffer_station(pid, bx, by, br))
    out.append(P.control_rack("CTRL_RACK", *CTRL_RACK))

    # 封闭传输通道必须先于腔体绘制，确保端部被法兰覆盖而非裸露。
    for pid, (alx, aly) in (("AL_A", AL_A), ("AL_B", AL_B)):
        out.append(P.vacuum_channel(f"{pid}_ATM_CHANNEL", ATM_HUB[0], ATM_HUB[1], alx, aly, 28))
        out.append(P.vacuum_channel(f"{pid}_VTM_CHANNEL", alx, aly, VTM[0], VTM[1], 30))
    for name in PM_ANGLES:
        px, py = pm_center(name)
        out.append(P.vacuum_channel(f"{name}_CHANNEL", VTM[0], VTM[1], px, py, 30))

    out.append(P.robot_arm("ATM_ARM", ATM_HUB[0], ATM_HUB[1],
                           upper_len=82, fore_len=64, wrist_r=36))
    out.append(P.circle("ATM_HUB", ATM_HUB[0], ATM_HUB[1], 14, fill=P.T("metal.dark")))

    for pid, (alx, aly), angle, text in (
        ("AL_A", AL_A, -45, "AIRLOCK A"),
        ("AL_B", AL_B, 45, "AIRLOCK B"),
    ):
        out.append(P.top_airlock(pid, alx, aly, w=96, h=112, angle=angle, name=pid))
        out.append(P.label(None, alx, aly - 72, text, size=10))

    vx, vy, vr = VTM
    vtm = (
        f'<circle cx="{vx}" cy="{vy}" r="{vr}" fill="url(#edgeMetal)" stroke="{P.T("iso.edge")}" stroke-width="2.2"/>'
        f'<circle cx="{vx}" cy="{vy}" r="{vr*.82:.1f}" fill="{P.T("metal.dark")}" stroke="{P.T("metal.bolt")}" stroke-width="1.4"/>'
        + P.bolt_circle(vx, vy, vr * 0.92, 12)
        + f'<circle cx="{vx}" cy="{vy}" r="{vr*.38:.1f}" fill="none" stroke="{P.T("metal.light")}" stroke-width="5"/>'
        + P.label(None, vx, vy - vr + 20, "VTM", size=13, fill=P.T("text.inverse"))
    )
    out.append(P.group("VTM", vtm))
    out.append(P.robot_arm("VTM_ARM", vx, vy, upper_len=82, fore_len=62, wrist_r=34))
    out.append(P.circle("VTM_HUB", vx, vy, 16, fill=P.T("metal.dark")))

    for name in PM_ANGLES:
        cx, cy = pm_center(name)
        out.append(P.top_process_chamber(
            name, cx, cy, w=122, h=132,
            angle=facing_angle(cx, cy, vx, vy), name=name,
        ))

    out.append(P.wafer("WAFER_MOVE", ATM_HUB[0], ATM_HUB[1], 11))
    out.append(P.wafer("WAFER_VTM", vx, vy, 11))
    out.append(P.svg_close())
    return "".join(out)


def build_motion() -> dict:
    return CM.build_cluster_motion(
        machine_type="LAM2300",
        name="LAM 2300 顶视图",
        src="lam2300-topview.svg",
        deriver="lam2300",
        description="Lam 2300 cluster 顶视动画：ATM 取片 → Aligner 寻边 → 双 Airlock → VTM 送片 → PM 加工 → 回程",
    )


def main() -> int:
    os.makedirs(os.path.dirname(OUT_SVG), exist_ok=True)
    with open(OUT_SVG, "w", encoding="utf-8") as f:
        f.write(_mark_base_hidden(build_svg()))
    with open(OUT_MOTION, "w", encoding="utf-8") as f:
        json.dump(build_motion(), f, ensure_ascii=False, indent=2)
    print(f"已生成:\n  {OUT_SVG}\n  {OUT_MOTION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
