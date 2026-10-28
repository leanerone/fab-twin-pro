"""新机型 SVG + Motion 脚手架生成器

用法：
    python -m models.svg_kit.scaffold --machine NEW-ETCH --ports 2 --chambers 3 \
        --out models/user/new-etch-topview

产出两个文件（可直接上传 / 被 validate.py 校验）：
    <out>.svg              用公共部件拼装的 2D 顶视图
    <out>.motion.json      骨架（含示例规则，可直接跑通"腔体状态灯 + 机械臂取放片"）

设计意图：新机型接入从"手绘 SVG"变成"填参数 + 微调坐标"，且自带校验闭环。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

try:
    from . import primitives as P
    from . import motion as M
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import primitives as P
    import motion as M


def build_svg(machine: str, ports: int, chambers: int,
              width: int = 1080, height: int = 840) -> str:
    cx = width / 2
    cy = height / 2

    out = [P.svg_open(width, height), P.defs()]

    # 底板
    out.append(P.baseplate("baseplate", 40, 40, width - 80, height - 80, machine))

    # 塔灯
    out.append(P.signal_tower("TOWER", width - 90, 60))

    # 图签
    out.append(P.title_block("title_block", 60, height - 60,
                             f"{machine} 顶视图", f"ports={ports} chambers={chambers}"))

    # 传输腔（六边形，与 OXE 的 TM 保持一致）
    tm_r = 110
    hex_pts = []
    for i in range(6):
        a = math.radians(60 * i - 30)
        hex_pts.append(f"{cx + tm_r * math.cos(a):.2f},{cy + tm_r * math.sin(a):.2f}")
    out.append(
        '<g id="TM" data-pid="TM">'
        f'<polygon points="{" ".join(hex_pts)}" fill="{P.T("metal.panel")}" '
        f'stroke="{P.T("stroke.default_color")}" stroke-width="{P.T("stroke.default_width")}"/>'
        f'<text x="{cx}" y="{cy + 4}" font-size="12" fill="{P.T("text.inverse")}" '
        f'text-anchor="middle">TM</text>'
        '</g>'
    )

    # 机械臂（三段连杆，hub 在 TM 中心）
    out.append(P.robot_arm("ARM", cx, cy, upper_len=90, fore_len=70, wrist_r=40))

    # Load Port：底部一字排开
    pw = P.T("port.width", 120)
    ph = P.T("port.height", 90)
    gap = 30
    total_w = ports * pw + (ports - 1) * gap
    start_x = cx - total_w / 2
    port_y = height - 80 - ph
    for i in range(ports):
        px = start_x + i * (pw + gap)
        out.append(P.port_box(f"PORT{i + 1}", px, port_y, name=f"PORT{i + 1}"))
        out.append(P.cassette(f"PORT{i + 1}_CST", px + 14, port_y + 12, pw - 28, ph - 34))

    # 工艺腔：围绕 TM 放射状排布
    chamber_r = 62
    ring = tm_r + 120
    for i in range(chambers):
        a = math.radians(-160 + (320 / max(chambers - 1, 1)) * i) if chambers > 1 else math.radians(-90)
        ccx = cx + ring * math.cos(a)
        ccy = cy + ring * math.sin(a)
        out.append(P.chamber(f"CH_{chr(65 + i)}", ccx, ccy, chamber_r,
                             name=f"CH{chr(65 + i)}"))
        # 腔体与 TM 之间的 slit 阀
        mx, my = (ccx + cx) / 2, (ccy + cy) / 2
        out.append(P.slit_valve(f"CH_{chr(65 + i)}_SLIT", mx - 22, my - 4, 44, 8))

    out.append(P.svg_close())
    return "".join(out)


def build_motion(machine: str, ports: int, chambers: int, svg_name: str) -> dict:
    """生成可直接被 motion2d 管线消费的骨架（对齐线上真实格式）"""
    b = M.MotionBuilder(
        machine_type=machine,
        name=f"{machine} 2D Motion",
        src=svg_name,
        deriver=f"{machine.lower()}",
        description=f"脚手架生成：{ports} 个 load port / {chambers} 个工艺腔",
    )
    b.param_defaults(PORT="1", SLOT="1", STATE="idle", LOT_ID="DEMO_LOT01")
    b.part_aliases(ARM="ARM_UPPER")

    green = P.T("state.run")
    red = P.T("state.alarm")

    # 腔体三色状态灯：run / alarm 互斥点亮
    rules = []
    for i in range(chambers):
        ch = f"CH_{chr(65 + i)}"
        rules.append(M.rule(f"{ch}_run", [M.visibility(True)], when="params.STATE == 'run'"))
        rules.append(M.rule(f"{ch}_alarm", [M.visibility(True)], when="params.STATE == 'alarm'"))
        rules.append(M.rule(f"{ch}_unload", [M.visibility(True)], when="params.STATE == 'unload'"))
    b.add("CHAMBER_STATE", rules, description="腔体三色状态灯")

    # 机械臂取放片（三段连杆各转一点，示意）
    b.add("ARM_PICK", [
        M.rule("ARM_UPPER", [M.rotate(-12, duration=350)], when="params.STATE == 'run'", phase=1),
        M.rule("ARM_FORE", [M.rotate(18, duration=350)], when="params.STATE == 'run'", phase=2),
    ], description="机械臂取片")
    b.add("ARM_PLACE", [
        M.rule("ARM_UPPER", [M.rotate(12, duration=350)], when="params.STATE == 'run'", phase=1),
        M.rule("ARM_FORE", [M.rotate(-18, duration=350)], when="params.STATE == 'run'", phase=2),
    ], description="机械臂放片")

    # 开门 / 关门
    for i in range(ports):
        p = i + 1
        b.add(f"DOOR_OPEN_{p}", [
            M.rule(f"PORT{p}_DOOR", [M.offset(x=86 if p == 1 else -86, duration=400)],
                   when=f"params.PORT == '{p}'", phase=1),
        ], description=f"PORT{p} 开门")
        b.add(f"DOOR_CLOSE_{p}", [
            M.rule(f"PORT{p}_DOOR", [M.offset(x=0, duration=400)],
                   when=f"params.PORT == '{p}'", phase=1),
        ], description=f"PORT{p} 关门")

    return b.build()


def main():
    ap = argparse.ArgumentParser(description="生成新机型 SVG + Motion 脚手架")
    ap.add_argument("--machine", required=True, help="机型名，如 NEW-ETCH")
    ap.add_argument("--ports", type=int, default=2, help="load port 数量")
    ap.add_argument("--chambers", type=int, default=3, help="工艺腔数量")
    ap.add_argument("--out", default=None, help="输出路径前缀（默认 models/user/<machine>-topview）")
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=840)
    args = ap.parse_args()

    out_prefix = args.out or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "user", f"{args.machine.lower()}-topview",
    )
    svg_path = out_prefix + ".svg"
    motion_path = out_prefix + ".motion.json"

    svg = build_svg(args.machine, args.ports, args.chambers, args.width, args.height)
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)

    motion = build_motion(args.machine, args.ports, args.chambers,
                          os.path.basename(svg_path))
    with open(motion_path, "w", encoding="utf-8") as f:
        json.dump(motion, f, ensure_ascii=False, indent=2)

    print(f"已生成: {svg_path}")
    print(f"已生成: {motion_path}")
    print("下一步: python -m models.svg_kit.validate "
          f"{svg_path} {motion_path}")


if __name__ == "__main__":
    main()
