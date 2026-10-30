# -*- coding: utf-8 -*-
"""AMAT Centris Sym3 顶视图建模：SVG + Motion JSON

用法：
    python models/build_sym3.py

设计依据：
  · 布局照 docs/assets/machine-references/Centris-Sym3-Etch-Chamber-Manual.jpg
    （六角 cluster：中央 ESC 卡盘腔 + 6×方形刻蚀腔 + EFEM/Load Port + 3×气体泵模块）
  · 风格降级说明：原计划为等角视图（PLAN 任务2 §风险：单台超 6h 先降级俯视
    并留档）。本期俯视落地——方形腔顶面螺栓阵列、中央卡盘晶圆、泵模块状态灯
    均保留，等角 iso_box/iso_cylinder 件留待后续打磨。
  · 事件词表复用 cluster 共享 26 步集（cluster_motion.py）。
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

OUT_SVG = os.path.join(_HERE, "user", "centris-sym3-topview.svg")
OUT_MOTION = os.path.join(_HERE, "user", "centris-sym3-topview.motion.json")

W, H = 1080, 840

LP_X = [40, 175]
LP_Y, LP_W, LP_H = 70, 120, 130
ALIGNER = (255, 300, 40)
ATM_HUB = (300, 375)
CLUSTER = (570, 470, 74)        # 中央 ESC 卡盘腔 cx,cy,r
PM_RING = 250
PM_W, PM_H = 116, 88
PM_ANGLES = {"PM1": 0, "PM2": -58, "PM3": -122, "PM4": 180, "PM5": 122, "PM6": 58}
PUMPS = [(960, 250), (960, 420), (960, 590)]   # 3×气体泵模块


def pm_center(name: str):
    a = math.radians(PM_ANGLES[name])
    return CLUSTER[0] + PM_RING * math.cos(a), CLUSTER[1] + PM_RING * math.sin(a)


def rect_chamber(pid, cx, cy, w, h, name=""):
    """方形刻蚀腔：壳体 + 顶面 2×4 螺栓阵列 + 腔名 + 三色状态灯。"""
    x, y = cx - w / 2, cy - h / 2
    bolts = ""
    for ix in range(4):
        for iy in range(2):
            bx = x + 16 + ix * ((w - 32) / 3)
            by = y + 14 + iy * (h - 28)
            bolts += f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="2.4" fill="{P.T("stroke.default_color")}"/>'
    body = (
        f'<rect id="{pid}" data-pid="{pid}" x="{x:.1f}" y="{y:.1f}" width="{w}" height="{h}" rx="7" '
        f'fill="{P.T("metal.panel")}" stroke="{P.T("stroke.default_color")}" '
        f'stroke-width="{P.T("stroke.default_width")}"/>'
        f'<rect x="{x + 10:.1f}" y="{y + h * 0.30:.1f}" width="{w - 20}" height="{h * 0.4:.1f}" rx="3" '
        f'fill="{P.T("metal.dark")}" stroke="{P.T("stroke.default_color")}" '
        f'stroke-width="{P.T("stroke.thin_width")}"/>'
        + bolts
    )
    if name:
        body += P.label(None, cx, cy + 3, name, size=11, fill=P.T("text.inverse"))
    lamps = ""
    for i, (s, c) in enumerate((
        ("run", P.T("state.run")), ("alarm", P.T("state.alarm")),
        ("unload", P.T("state.unload")),
    )):
        lamps += (f'<circle id="{pid}_{s}" data-pid="{pid}_{s}" cx="{cx - 24 + i * 18}" '
                  f'cy="{y - 12}" r="5" fill="{c}" stroke="{P.T("stroke.default_color")}" stroke-width="1"/>')
    return body + lamps


BASE_HIDDEN = (
    [f"LP{i}_CST" for i in (1, 2)]
    + ["WAFER_MOVE", "WAFER_VTM", "ALIGNER_WAFER"]
    + [f"PM{i}_{s}" for i in range(1, 7) for s in ("run", "alarm", "unload")]
    + ["TOWER_alarm"]
)


def _mark_base_hidden(svg: str) -> str:
    for pid in BASE_HIDDEN:
        pat = re.compile(r'(<\w+[^>]*\bid="%s"[^>]*?)(/?>)' % re.escape(pid))
        svg, n = pat.subn(lambda m: m.group(1) + ' data-motion-base-visibility="hidden"' + m.group(2), svg, count=1)
        if n != 1:
            raise RuntimeError(f"base-hidden 标注失败：找不到部件 {pid}")
    return svg


def build_svg() -> str:
    out = [P.svg_open(W, H), P.defs()]
    out.append(P.baseplate("BASEPLATE", 30, 30, W - 60, H - 60))
    out.append(P.signal_tower("TOWER", W - 110, H - 96))
    out.append(P.title_block("TITLE", 46, H - 34,
                             "CENTRIS SYM3", "EFEM / ESC Cluster / 6xPM / Gas Pumps"))

    # ── Load Port ──
    for i, x in enumerate(LP_X, start=1):
        pid = f"LP{i}"
        out.append(P.port_box(pid, x, LP_Y, w=LP_W, h=LP_H, name=f"LP{i}"))
        out.append(P.cassette(f"{pid}_CST", x + 12, LP_Y + 12, LP_W - 24, LP_H - 34))
        out.append(P.label(None, x + LP_W / 2, LP_Y - 8, f"LOAD PORT {i}", size=10))

    # Aligner
    ax, ay, ar = ALIGNER
    aligner = (
        f'<circle cx="{ax}" cy="{ay}" r="{ar}" fill="{P.T("metal.panel")}" '
        f'stroke="{P.T("stroke.default_color")}" stroke-width="{P.T("stroke.default_width")}"/>'
        f'<circle cx="{ax}" cy="{ay}" r="{ar * 0.62:.1f}" fill="{P.T("metal.dark")}" '
        f'stroke="{P.T("stroke.default_color")}" stroke-width="{P.T("stroke.thin_width")}"/>'
        + P.bolt_circle(ax, ay, ar * 0.86, 8)
        + P.wafer("ALIGNER_WAFER", ax, ay, ar * 0.34)
    )
    out.append(P.group("ALIGNER", aligner))
    out.append(P.label(None, ax, ay - ar - 10, "ALIGNER", size=10))

    # EFEM 大气柜体 + ATM 臂（置于 Aligner 下方，避开 PM4 左伸范围）
    out.append(P.rect("EFEM", 225, 330, 150, 95, fill=P.T("metal.panel"), rx=8))
    out.append(P.label(None, 300, 350, "EFEM", size=11))
    out.append(P.robot_arm("ATM_ARM", ATM_HUB[0], ATM_HUB[1], upper_len=60, fore_len=46, wrist_r=24))
    out.append(P.circle("ATM_HUB", ATM_HUB[0], ATM_HUB[1], 12, fill=P.T("metal.dark")))

    # ── 中央 ESC 卡盘腔 ──
    cx, cy, cr = CLUSTER
    esc = (
        f'<circle cx="{cx}" cy="{cy}" r="{cr}" fill="{P.T("metal.panel")}" '
        f'stroke="{P.T("stroke.default_color")}" stroke-width="{P.T("stroke.default_width")}"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{cr * 0.8:.1f}" fill="{P.T("metal.dark")}" '
        f'stroke="{P.T("stroke.default_color")}" stroke-width="{P.T("stroke.thin_width")}"/>'
        + P.bolt_circle(cx, cy, cr * 0.92, 12)
        # 静电卡盘（吸附晶圆时发光，本期静态呈现）
        + f'<circle cx="{cx}" cy="{cy}" r="{cr * 0.46:.1f}" fill="none" stroke="{P.T("state.run")}" '
          f'stroke-width="1.4" stroke-dasharray="4 3" opacity="0.55"/>'
        + P.label(None, cx, cy - cr + 20, "ESC", size=12, fill=P.T("text.inverse"))
    )
    out.append(P.group("ESC", esc))
    out.append(P.robot_arm("VTM_ARM", cx, cy, upper_len=86, fore_len=66, wrist_r=36))

    # ── 6×方形刻蚀腔（六角环）──
    for name in ("PM1", "PM2", "PM3", "PM4", "PM5", "PM6"):
        px, py = pm_center(name)
        out.append(rect_chamber(name, px, py, PM_W, PM_H, name=name))

    # ── 3×气体泵模块（右侧，带状态灯）──
    for i, (px, py) in enumerate(PUMPS, start=1):
        pw, ph = 76, 100
        out.append(P.rect(f"PUMP{i}", px - pw / 2, py - ph / 2, pw, ph,
                          fill=P.T("metal.panel"), rx=5))
        out.append(P.label(None, px, py - ph / 2 + 14, f"GAS PUMP {i}", size=8))
        out.append(P.circle(f"PUMP{i}_lamp", px, py + 10, 7, fill=P.T("state.run"),
                            stroke=P.T("stroke.default_color"), sw=1))

    # 搬运晶圆
    out.append(P.wafer("WAFER_MOVE", ATM_HUB[0], ATM_HUB[1], 11))
    out.append(P.wafer("WAFER_VTM", cx, cy, 11))

    out.append(P.svg_close())
    return "".join(out)


def build_motion() -> dict:
    return CM.build_cluster_motion(
        machine_type="CENTRIS-SYM3",
        name="AMAT Centris Sym3 顶视图",
        src="centris-sym3-topview.svg",
        deriver="sym3",
        description="AMAT Centris Sym3 顶视动画（俯视降级版）：EFEM 取片 → ESC 中央卡盘腔 → 6×方形刻蚀腔加工 → 回程",
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
