# -*- coding: utf-8 -*-
"""TEL Synapse（SPT 200mm fpD）等角视图建模：SVG + Motion JSON。

照参考图表现六组高柜式 PM（顶部控制/排气柜 + 前侧圆形工艺腔）、中央圆形
Transport Module、前侧 EFEM 与独立 UI 站。保留共享 26 步动画契约。
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
W, H = 1200, 920
TM = (550, 510)
ATM_HUB = (425, 665)
PM_LAYOUT = {
    "PM2": (430, 265, 170),
    "PM3": (650, 250, 180),
    "PM1": (265, 405, 175),
    "PM4": (895, 440, 175),
    "PM5": (835, 665, 160),
    "PM6": (610, 745, 150),
}

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
        '<ellipse cx="590" cy="690" rx="520" ry="150" fill="#1e293b" opacity="0.11" filter="url(#isoShadow)"/>'
        + P.iso_box(None, 600, 650, 1100, 500, 18, top="#f1f4f7", left="#cbd5df", right="#b6c2cf")
    ))
    out.append(P.signal_tower("TOWER", 1120, 55))
    out.append(P.title_block("TITLE", 46, 888, "TEL SYNAPSE SPT",
                             "6x High-cabinet Process Modules / Circular Transport Module / EFEM / UI"))

    tx, ty = TM
    # 真空连接位于腔体底层，先画通道再由柜体与 TM 覆盖端部。
    for name, (cx, cy, _) in PM_LAYOUT.items():
        out.append(P.vacuum_channel(f"{name}_CHANNEL", tx, ty, cx, cy, 26))

    for name in ("PM2", "PM3", "PM1"):
        cx, cy, h = PM_LAYOUT[name]
        out.append(P.iso_cabinet_chamber(name, cx, cy, w=120, d=86, h=h, name=name))

    # 中央圆形 Transport Module，带法兰螺栓和圆形传输接口。
    tm_parts = [P.iso_cylinder(None, tx, ty, 122, 72, 55, top=P.T("metal.light"))]
    tm_parts.append(f'<ellipse cx="{tx}" cy="{ty-55}" rx="91" ry="52" fill="{P.T("metal.panel")}" stroke="{P.T("metal.dark")}" stroke-width="3"/>')
    tm_parts.append(f'<ellipse cx="{tx}" cy="{ty-55}" rx="67" ry="37" fill="{P.T("metal.deep")}" stroke="{P.T("metal.light")}" stroke-width="5"/>')
    for i in range(14):
        a = math.radians(i * 360 / 14)
        tm_parts.append(P.circle(None, tx + 105 * math.cos(a), ty - 55 + 61 * math.sin(a), 3,
                                 fill=P.T("metal.bolt"), sw=0.8))
    tm_parts.append(P.label(None, tx, ty - 142, "TRANSPORT MODULE", size=11, weight="700"))
    out.append(P.group("TM", "\n".join(tm_parts)))
    out.append(P.robot_arm("VTM_ARM", tx, ty - 55, upper_len=78, fore_len=58, wrist_r=30))

    out.append(P.iso_cabinet_chamber("PM4", *PM_LAYOUT["PM4"][:2], w=120, d=86,
                                      h=PM_LAYOUT["PM4"][2], name="PM4"))

    # 前侧 EFEM 柜体：双开门、通风区与状态面板。
    ex, ey = 290, 665
    efem = [P.iso_box(None, ex, ey, 260, 160, 170)]
    efem.extend([
        '<polygon points="185,543 290,603 290,715 185,655" fill="none" stroke="#64748b" stroke-width="2"/>',
        '<polygon points="290,603 395,543 395,655 290,715" fill="none" stroke="#64748b" stroke-width="2"/>',
        '<polygon points="210,558 267,590 267,617 210,585" fill="#1e293b" stroke="#94a3b8" stroke-width="2"/>',
        P.label(None, ex, 625, "EFEM", size=13, fill=P.T("text.inverse"), weight="700"),
    ])
    for i in range(7):
        efem.append(f'<line x1="{330+i*7}" y1="574" x2="{330+i*7}" y2="617" stroke="#475569" stroke-width="3"/>')
    out.append(P.group("EFEM", "\n".join(efem)))

    for name in ("PM5", "PM6"):
        cx, cy, h = PM_LAYOUT[name]
        out.append(P.iso_cabinet_chamber(name, cx, cy, w=120, d=86, h=h, name=name))

    # 左前 Load Port、Aligner 与 ATM 臂
    for i, (lpx, lpy) in enumerate(((120, 710), (220, 785)), start=1):
        pid = f"LP{i}"
        out.append(P.iso_load_port(pid, lpx, lpy, w=94, d=66, h=108, name=pid))
        out.append(P.cassette(f"{pid}_CST", lpx - 33, lpy - 96, 66, 90))
    out.append(P.group("ALIGNER",
        P.iso_cylinder(None, 425, 770, 40, 23, 45, top=P.T("metal.light"))
        + P.wafer("ALIGNER_WAFER", 425, 725, 14)
    ))
    out.append(P.robot_arm("ATM_ARM", ATM_HUB[0], ATM_HUB[1], upper_len=58, fore_len=44, wrist_r=24))
    out.append(P.circle("ATM_HUB", ATM_HUB[0], ATM_HUB[1], 11, fill=P.T("metal.dark")))

    # 独立 User Interface：显示器、键盘、立柱和脚轮底座。
    ui = [
        P.iso_box(None, 490, 855, 105, 65, 22),
        '<path d="M490 835 L490 735" stroke="#64748b" stroke-width="12"/>',
        '<rect x="442" y="690" width="96" height="66" rx="5" fill="#cbd5e1" stroke="#334155" stroke-width="4"/>',
        '<rect x="451" y="699" width="78" height="47" rx="2" fill="#0f172a" stroke="#22d3ee" stroke-width="1.5"/>',
        '<polygon points="450,770 525,770 550,790 475,790" fill="#94a3b8" stroke="#334155" stroke-width="2"/>',
        P.circle(None, 450, 866, 7, fill=P.T("metal.dark")),
        P.circle(None, 530, 866, 7, fill=P.T("metal.dark")),
        P.label(None, 490, 675, "USER INTERFACE", size=9, weight="700"),
    ]
    out.append(P.group("UI_STATION", "\n".join(ui)))

    out.append(P.wafer("WAFER_MOVE", ATM_HUB[0], ATM_HUB[1], 11))
    out.append(P.wafer("WAFER_VTM", tx, ty - 55, 11))
    out.append(P.svg_close())
    return "".join(out)


def build_motion() -> dict:
    return CM.build_cluster_motion(
        machine_type="TEL-SYNAPSE",
        name="TEL Synapse SPT 等角视图",
        src="tel-synapse-topview.svg",
        deriver="synapse",
        description="TEL Synapse SPT 等角动画：EFEM 取片 → 圆形 Transport Module → 6×高柜式 PM → 独立 UI 站",
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
