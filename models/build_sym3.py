# -*- coding: utf-8 -*-
"""AMAT Centris Sym3 等角视图建模：SVG + Motion JSON。

照参考图表现六组蓝色金属圆角工艺腔、孔阵顶盖、铜色中央传输框板、
右侧大型银色 EFEM 与前侧三组金色/银色泵模块。动画部件契约保持不变。
"""
from __future__ import annotations

import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "svg_kit"))

import primitives as P  # noqa: E402
import cluster_motion as CM  # noqa: E402

OUT_SVG = os.path.join(_HERE, "user", "centris-sym3-topview.svg")
OUT_MOTION = os.path.join(_HERE, "user", "centris-sym3-topview.motion.json")
W, H = 1200, 900

# 按参考图的后排 → 中央 → 前排层次布局，而非俯视正六边形。
PM_LAYOUT = {
    "PM2": (420, 235, 155),
    "PM3": (630, 245, 155),
    "PM1": (255, 330, 155),
    "PM6": (690, 450, 150),
    "PM4": (240, 535, 150),
    "PM5": (430, 570, 150),
}
CLUSTER = (510, 440)
ATM_HUB = (350, 665)

BASE_HIDDEN = (
    [f"LP{i}_CST" for i in (1, 2)]
    + ["WAFER_MOVE", "WAFER_VTM", "ALIGNER_WAFER"]
    + [f"PM{i}_{s}" for i in range(1, 7) for s in ("run", "alarm", "unload")]
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
    out.append(P.group("BASEPLATE",
        '<ellipse cx="590" cy="650" rx="520" ry="170" fill="#1e293b" opacity="0.12" filter="url(#isoShadow)"/>'
        + P.iso_box(None, 565, 700, 1040, 500, 18, top="#eef2f6", left="#cbd5df", right="#b6c2cf")
    ))
    out.append(P.signal_tower("TOWER", 1120, 55))
    out.append(P.title_block("TITLE", 46, 852, "CENTRIS SYM3",
                             "6x Blue Process Modules / Copper Transfer Frame / EFEM / 3x Vacuum Pumps"))

    # 后排工艺腔
    for name in ("PM2", "PM3", "PM1"):
        cx, cy, h = PM_LAYOUT[name]
        out.append(P.iso_process_chamber(name, cx, cy, w=150, d=94, h=h, name=name))

    # 中央铜色框板与圆形传输开口
    cx, cy = CLUSTER
    esc = [P.iso_box(None, cx, cy, 245, 150, 45,
                     top=P.T("iso.copper_top"), left="url(#isoCopperBody)", right=P.T("iso.copper_right"))]
    esc.append(f'<ellipse cx="{cx}" cy="{cy-45}" rx="70" ry="43" fill="{P.T("iso.copper_right")}" stroke="#f2c18d" stroke-width="5"/>')
    esc.append(f'<ellipse cx="{cx}" cy="{cy-48}" rx="55" ry="32" fill="{P.T("metal.deep")}" stroke="#8b4e25" stroke-width="4"/>')
    esc.append(P.label(None, cx, cy - 112, "ESC / TRANSFER", size=10, weight="700"))
    out.append(P.group("ESC", "\n".join(esc)))
    out.append(P.robot_arm("VTM_ARM", cx, cy - 45, upper_len=70, fore_len=52, wrist_r=28))

    # 前排与右侧工艺腔
    for name in ("PM6", "PM4", "PM5"):
        pcx, pcy, ph = PM_LAYOUT[name]
        out.append(P.iso_process_chamber(name, pcx, pcy, w=150, d=94, h=ph, name=name))

    # 右侧大型银色 EFEM：顶盖通风、前门、侧门和绿色真空/电气接口。
    ex, ey = 875, 555
    efem = [P.iso_box(None, ex, ey, 310, 190, 250)]
    for i in range(9):
        efem.append(f'<line x1="{790+i*10}" y1="300" x2="{850+i*10}" y2="337" stroke="{P.T("metal.dark")}" stroke-width="3" opacity="0.8"/>')
    efem.extend([
        '<polygon points="755,342 838,385 838,447 755,404" fill="#273444" stroke="#8e9bad" stroke-width="3"/>',
        '<polygon points="768,355 824,384 824,407 768,378" fill="#0d1420" stroke="#64748b" stroke-width="2"/>',
        '<polygon points="900,430 1000,365 1000,510 900,575" fill="none" stroke="#64748b" stroke-width="2"/>',
        '<path d="M705 438 L740 456 L740 474 L705 456 Z" fill="#22c55e" stroke="#166534" stroke-width="2"/>',
        P.label(None, 875, 510, "EFEM", size=15, fill=P.T("text.inverse"), weight="700"),
    ])
    out.append(P.group("EFEM", "\n".join(efem)))

    # 左前侧 Load Port、Aligner 与 ATM 机构
    for i, (lpx, lpy) in enumerate(((120, 625), (230, 695)), start=1):
        pid = f"LP{i}"
        out.append(P.iso_load_port(pid, lpx, lpy, w=96, d=68, h=110, name=pid))
        out.append(P.cassette(f"{pid}_CST", lpx - 34, lpy - 98, 68, 92))

    out.append(P.group("ALIGNER",
        P.iso_cylinder(None, 350, 735, 43, 25, 48, top=P.T("metal.light"))
        + P.wafer("ALIGNER_WAFER", 350, 687, 15)
    ))
    out.append(P.label(None, 350, 650, "ALIGNER", size=9, weight="700"))
    out.append(P.robot_arm("ATM_ARM", ATM_HUB[0], ATM_HUB[1], upper_len=58, fore_len=44, wrist_r=24))
    out.append(P.circle("ATM_HUB", ATM_HUB[0], ATM_HUB[1], 11, fill=P.T("metal.dark")))

    # 参考图前侧三组金色泵头 + 银色真空泵基座
    for i, (px, py) in enumerate(((800, 770), (920, 785), (1040, 800)), start=1):
        out.append(P.pump_module(f"PUMP{i}", px, py, scale=1.05))
        out.append(P.label(None, px, py + 30, f"PUMP {i}", size=9, weight="700"))

    out.append(P.wafer("WAFER_MOVE", ATM_HUB[0], ATM_HUB[1], 11))
    out.append(P.wafer("WAFER_VTM", cx, cy - 45, 11))
    out.append(P.svg_close())
    return "".join(out)


def build_motion() -> dict:
    return CM.build_cluster_motion(
        machine_type="CENTRIS-SYM3",
        name="AMAT Centris Sym3 等角视图",
        src="centris-sym3-topview.svg",
        deriver="sym3",
        description="AMAT Centris Sym3 等角动画：EFEM 取片 → 铜色中央传输框板 → 6×蓝色工艺腔 → 前侧真空泵",
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
