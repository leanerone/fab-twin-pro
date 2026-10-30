# -*- coding: utf-8 -*-
"""TEL Synapse（SPT 200mm fpD）顶视图建模：SVG + Motion JSON

用法：
    python models/build_synapse.py

设计依据：
  · 布局照 docs/assets/machine-references/SPT.jpg（Synapse Process Tool 标注图）：
    Transport Module 居中 + 6×PM 环绕（PM1..PM6）+ User Interface
  · 风格降级说明：原计划为等角视图（PLAN 任务2 §风险：单台超 6h 先降级俯视
    并留档）。本期用俯视平面图落地，结构（TM 居中 / 6 腔六角环 / LP 左置 /
    UI 站右上）按参考图，等角 iso 件留待后续打磨。
  · 事件词表复用 cluster 共享 26 步集（cluster_motion.py），与 LAM2300 一致，
    不发明新事件名。
  · 改模型改本脚本重跑，不要手改产物。
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

OUT_SVG = os.path.join(_HERE, "user", "tel-synapse-topview.svg")
OUT_MOTION = os.path.join(_HERE, "user", "tel-synapse-topview.motion.json")

W, H = 1040, 820

LP_X = [40, 175]                 # 2×Load Port
LP_Y, LP_W, LP_H = 90, 120, 130
ALIGNER = (250, 330, 40)         # 寻边（ATM 通道侧）
UI_STATION = (925, 70, 170, 110)
TM = (560, 470, 115)             # Transport Module（居中，含真空臂）
PM_RING = 250
PM_R = 58
# 六角环：右、右上、左上、左、左下、右下（避开左侧 LP 通道）
PM_ANGLES = {"PM1": 0, "PM2": -55, "PM3": -125, "PM4": 180, "PM5": 125, "PM6": 55}


def pm_center(name: str):
    a = math.radians(PM_ANGLES[name])
    return TM[0] + PM_RING * math.cos(a), TM[1] + PM_RING * math.sin(a)


def _hex_points(cx, cy, r, rot_deg=30):
    """尖顶六边形顶点串（rot 30° → 左右为尖点，贴合 SPT 腔位朝向）。"""
    pts = []
    for k in range(6):
        a = math.radians(rot_deg + k * 60)
        pts.append(f"{cx + r * math.cos(a):.1f},{cy + r * math.sin(a):.1f}")
    return " ".join(pts)


def hex_chamber(pid, cx, cy, r, name=""):
    """六边形工艺腔 + 法兰边 + 腔名 + 三色状态灯（id 约定同 P.chamber）。"""
    inner = _hex_points(cx, cy, r * 0.72)
    body = (
        f'<polygon id="{pid}" data-pid="{pid}" points="{_hex_points(cx, cy, r)}" '
        f'fill="{P.T("metal.panel")}" stroke="{P.T("stroke.default_color")}" '
        f'stroke-width="{P.T("stroke.default_width")}"/>'
        f'<polygon points="{inner}" fill="{P.T("metal.dark")}" '
        f'stroke="{P.T("stroke.default_color")}" stroke-width="{P.T("stroke.thin_width")}"/>'
    )
    if name:
        body += P.label(None, cx, cy + 4, name, size=11, fill=P.T("text.inverse"))
    lamps = ""
    for i, (s, c) in enumerate((
        ("run", P.T("state.run")), ("alarm", P.T("state.alarm")),
        ("unload", P.T("state.unload")),
    )):
        lx = cx - 24 + i * 18
        ly = cy - r - 14
        lamps += (f'<circle id="{pid}_{s}" data-pid="{pid}_{s}" cx="{lx}" cy="{ly}" r="5" '
                  f'fill="{c}" stroke="{P.T("stroke.default_color")}" stroke-width="1"/>')
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
                             "TEL SYNAPSE SPT", "EFEM / Transport Module / 6xPM"))

    # ── 左置 Load Port ──
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

    # ── User Interface 站（参考图右上）──
    ux, uy, uw, uh = UI_STATION
    out.append(P.rect("UI_STATION", ux, uy, uw, uh, fill=P.T("metal.panel"), rx=6))
    out.append(P.rect(None, ux + 12, uy + 14, uw - 24, uh - 40,
                      fill=P.T("port.inner_fill"), rx=3))
    out.append(P.label(None, ux + uw / 2, uy + uh - 12, "USER INTERFACE", size=10))

    # ── EFEM 通道（LP → TM 之间的大气柜体，置于 LP 与 Aligner 之间的上通道，
    #     避开 PM4 左伸范围）──
    out.append(P.rect("EFEM", 300, 150, 150, 150, fill=P.T("metal.panel"), rx=8))
    out.append(P.label(None, 375, 175, "EFEM", size=11))
    out.append(P.robot_arm("ATM_ARM", 375, 235, upper_len=70, fore_len=56, wrist_r=30))

    # ── Transport Module（中央，真空臂）──
    tx, ty, tr = TM
    ttm = (
        f'<circle cx="{tx}" cy="{ty}" r="{tr}" fill="{P.T("metal.panel")}" '
        f'stroke="{P.T("stroke.default_color")}" stroke-width="{P.T("stroke.default_width")}"/>'
        f'<circle cx="{tx}" cy="{ty}" r="{tr * 0.82:.1f}" fill="{P.T("metal.dark")}" '
        f'stroke="{P.T("stroke.default_color")}" stroke-width="{P.T("stroke.thin_width")}"/>'
        + P.bolt_circle(tx, ty, tr * 0.93, 12)
        + P.label(None, tx, ty - tr + 22, "TRANSPORT MODULE", size=10, fill=P.T("text.inverse"))
    )
    out.append(P.group("TM", ttm))
    out.append(P.robot_arm("VTM_ARM", tx, ty, upper_len=88, fore_len=68, wrist_r=38))

    # ── 6×PM 六角环 ──
    for name in ("PM1", "PM2", "PM3", "PM4", "PM5", "PM6"):
        cx, cy = pm_center(name)
        out.append(hex_chamber(name, cx, cy, PM_R, name=name))

    # 搬运晶圆
    out.append(P.wafer("WAFER_MOVE", 375, 235, 11))
    out.append(P.wafer("WAFER_VTM", tx, ty, 11))

    out.append(P.svg_close())
    return "".join(out)


def build_motion() -> dict:
    return CM.build_cluster_motion(
        machine_type="TEL-SYNAPSE",
        name="TEL Synapse SPT 顶视图",
        src="tel-synapse-topview.svg",
        deriver="synapse",
        description="TEL Synapse SPT 顶视动画（俯视降级版）：EFEM 取片 → Transport Module → 6×PM 六角环加工 → 回程",
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
