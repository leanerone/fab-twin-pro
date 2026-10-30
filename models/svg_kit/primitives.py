"""FabTwin SVG 公共部件库（Python 侧，构建期使用）

用途：让新机型的 2D 视图 SVG 通过"公共部件 + 布局参数"拼装，而不是每次从零手绘。
与 `tokens.json` 配套——色值/线宽/尺寸一律走令牌，保证与存量机型视觉一致。

约定（与 motion2d 管线强相关，不要改）：
- 每个可动部件必须带 `data-pid`，Motion JSON 的 target 靠它定位
- pid 用大写下划线命名（PORT1_SLIT / ARM_UPPER / WAFER_P1_S3）
- 子部件 pid 用父 pid 作前缀，便于 deriver 做前缀匹配

用法示例见 docs/SVG公共库编写指南.md 与 models/svg_kit/scaffold.py
"""
from __future__ import annotations

import json
import math
import os
from xml.sax.saxutils import escape

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOKENS_CACHE = None


def load_tokens() -> dict:
    """加载设计令牌（进程内缓存）"""
    global _TOKENS_CACHE
    if _TOKENS_CACHE is None:
        with open(os.path.join(_HERE, "tokens.json"), "r", encoding="utf-8") as f:
            _TOKENS_CACHE = json.load(f)
    return _TOKENS_CACHE


def T(path: str, default=None):
    """按点路径取令牌，如 T('metal.light') / T('state.run')"""
    node = load_tokens()
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


# ── 基础工具 ──────────────────────────────────────────────────────────────
def esc(text) -> str:
    """XML 转义，防止含 & < > 的文本炸坏 SVG"""
    return escape(str(text), {'"': "&quot;", "'": "&apos;"})


def pid_attr(pid: str) -> str:
    """部件标识：必须同时输出 id 与 data-pid。

    2026-10-29 对齐线上真实约定（重要）：
    - `id`    —— 引擎按它定位：useMotionPlayback.js:222 用 querySelector('#<id>')
    - `data-pid` —— 标记"这是可检视部件"：MotionPreview.vue:589 只把带 data-pid 的
      元素列进部件清单，取的是它们的 id

    只写 data-pid 不写 id 的部件，动画会静默不生效（引擎找不到目标）。
    """
    return f' id="{esc(pid)}" data-pid="{esc(pid)}"' if pid else ""


def svg_open(width: int = 1080, height: int = 840, viewbox: str = None) -> str:
    vb = viewbox or f"0 0 {width} {height}"
    ff = T("canvas.font_family", "Arial, sans-serif")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" '
        f'font-family="{ff}" width="{width}" height="{height}">\n'
    )


def svg_close() -> str:
    return "</svg>\n"


def defs() -> str:
    """标准 defs：彩虹晶圆渐变 + die 网格 + 晶圆阴影 + 金属边渐变。

    所有机型共用同一套 id；重复引入不会冲突（后定义的被忽略）。
    """
    wf = T("wafer", {})
    gid = wf.get("gradient_id", "rainbowGrad")
    pidp = wf.get("pattern_id", "waferPattern")
    shade = wf.get("shade_id", "waferShade")
    stops = "".join(
        f'<stop offset="{o}" stop-color="{c}"/>' for o, c in wf.get("stops", [])
    )
    return f"""<defs>
  <style>
    .shape {{ fill: #fff; stroke: {T('stroke.default_color')}; stroke-width: {T('stroke.default_width')}; stroke-linecap: round; stroke-linejoin: round; }}
  </style>
  <linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="1">{stops}</linearGradient>
  <pattern id="dieGrid" width="0.05" height="0.05" patternUnits="objectBoundingBox">
   <path d="M0.05,0 L0.05,0.05 M0,0.05 L0.05,0.05" fill="none" stroke="rgba(20,25,40,0.32)" stroke-width="0.008"/>
  </pattern>
  <pattern id="{pidp}" width="1" height="1" patternUnits="objectBoundingBox" patternContentUnits="objectBoundingBox">
   <rect width="1" height="1" fill="url(#{gid})"/><rect width="1" height="1" fill="url(#dieGrid)"/>
  </pattern>
  <radialGradient id="{shade}" cx="0.38" cy="0.32" r="0.78">
   <stop offset="0" stop-color="#ffffff" stop-opacity="0.4"/><stop offset="0.45" stop-color="#dde8f6" stop-opacity="0.1"/>
   <stop offset="0.8" stop-color="#8395b8" stop-opacity="0.16"/><stop offset="1" stop-color="#16233a" stop-opacity="0.5"/>
  </radialGradient>
  <linearGradient id="edgeMetal" x1="0" y1="0" x2="1" y2="1">
   <stop offset="0" stop-color="{T('metal.edge_light')}"/><stop offset="0.35" stop-color="{T('metal.mid')}"/>
   <stop offset="0.6" stop-color="{T('metal.edge_light')}"/><stop offset="1" stop-color="{T('metal.edge_dark')}"/>
  </linearGradient>
  <linearGradient id="isoSilverBody" x1="0" y1="0" x2="1" y2="0">
   <stop offset="0" stop-color="#6f7d90"/><stop offset="0.22" stop-color="#e8eef5"/>
   <stop offset="0.48" stop-color="#9eabbc"/><stop offset="0.72" stop-color="#f4f7fb"/><stop offset="1" stop-color="#657388"/>
  </linearGradient>
  <linearGradient id="isoBlueBody" x1="0" y1="0" x2="1" y2="0">
   <stop offset="0" stop-color="#043c63"/><stop offset="0.2" stop-color="#18a9d7"/>
   <stop offset="0.42" stop-color="#07567f"/><stop offset="0.66" stop-color="#48d4f2"/><stop offset="1" stop-color="#043653"/>
  </linearGradient>
  <linearGradient id="isoCopperBody" x1="0" y1="0" x2="1" y2="0">
   <stop offset="0" stop-color="#633416"/><stop offset="0.28" stop-color="#e0a05b"/>
   <stop offset="0.52" stop-color="#8c4c21"/><stop offset="0.76" stop-color="#f0bd7e"/><stop offset="1" stop-color="#633416"/>
  </linearGradient>
  <linearGradient id="isoGoldBody" x1="0" y1="0" x2="1" y2="0">
   <stop offset="0" stop-color="#69450c"/><stop offset="0.3" stop-color="#f0bd4e"/>
   <stop offset="0.55" stop-color="#9a6411"/><stop offset="0.8" stop-color="#ffe18a"/><stop offset="1" stop-color="#69450c"/>
  </linearGradient>
  <filter id="isoShadow" x="-30%" y="-30%" width="160%" height="180%">
   <feGaussianBlur stdDeviation="7"/>
  </filter>
</defs>
"""


def _legacy_node(node: dict, level: int = 2) -> str:
    """按 tokens.json 中的节点描述渲染存量 defs 资源。"""
    indent = " " * level
    attrs = dict(node.get("attrs", {}))
    if "id" in node:
        attrs = {"id": node["id"], **attrs}
    attr_text = "".join(f' {key}="{esc(value)}"' for key, value in attrs.items())
    tag = node["tag"]
    children = [
        {"tag": "stop", "attrs": stop} for stop in node.get("stops", [])
    ] + list(node.get("children", []))
    if not children:
        return f"{indent}<{tag}{attr_text}/>"
    lines = [f"{indent}<{tag}{attr_text}>"]
    lines.extend(_legacy_node(child, level + 2) for child in children)
    lines.append(f"{indent}</{tag}>")
    return "\n".join(lines)


def legacy_defs(profile_name: str, style: str = None) -> str:
    """渲染 OXE/AMAT/PODOPENER 的存量 defs，不影响标准 defs()。"""
    profiles = T("legacy_defs", {})
    profile = profiles[profile_name]
    base = profiles.get(profile.get("extends"), {})
    resources = list(base.get("resources", profile.get("resources", [])))
    for anchor, additions in profile.get("insert_after", {}).items():
        index = next(
            (i for i, resource in enumerate(resources) if resource.get("id") == anchor),
            None,
        )
        if index is None:
            raise ValueError(f"legacy defs 缺少插入锚点: {anchor}")
        resources[index + 1:index + 1] = additions

    style_text = style if style is not None else profile.get("style", base.get("style"))
    lines = ["<defs>"]
    if style_text is not None:
        lines.append(f"  <style>{style_text}</style>")
    lines.extend(_legacy_node(resource) for resource in resources)
    lines.append("</defs>")
    return "\n".join(lines)


def group(pid: str, children: str, transform: str = None, extra: str = "") -> str:
    """可动组：motion 的 transform 由引擎写在这里，故必须独立成组"""
    tf = f' transform="{transform}"' if transform else ""
    ex = f" {extra}" if extra else ""
    return f'<g{pid_attr(pid)}{tf}{ex}>\n{children}\n</g>\n'


def rect(pid, x, y, w, h, fill=None, rx=0, stroke=None, sw=None, extra="") -> str:
    fill = fill or T("metal.light")
    stroke = stroke if stroke is not None else T("stroke.default_color")
    sw = sw if sw is not None else T("stroke.default_width")
    ex = f" {extra}" if extra else ""
    return (
        f'<rect{pid_attr(pid)} x="{x}" y="{y}" width="{w}" height="{h}" '
        f'rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{ex}/>'
    )


def circle(pid, cx, cy, r, fill=None, stroke=None, sw=None, extra="") -> str:
    fill = fill or T("metal.light")
    stroke = stroke if stroke is not None else T("stroke.default_color")
    sw = sw if sw is not None else T("stroke.default_width")
    ex = f" {extra}" if extra else ""
    return (
        f'<circle{pid_attr(pid)} cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="{sw}"{ex}/>'
    )


def label(pid, x, y, text, size=None, anchor="middle", fill=None, weight="500") -> str:
    size = size if size is not None else T("text.label_size", 11)
    fill = fill or T("text.primary")
    return (
        f'<text{pid_attr(pid)} x="{x}" y="{y}" font-size="{size}" fill="{fill}" '
        f'text-anchor="{anchor}" font-weight="{weight}">{esc(text)}</text>'
    )


# ── 复合部件 ──────────────────────────────────────────────────────────────
def bolt_circle(cx, cy, r, count=8, bolt_r=2.6, start_deg=0, fill=None) -> str:
    """法兰螺栓圈：机台上几乎所有圆形腔体都有，单独抽出来避免每处重写三角函数"""
    fill = fill or T("metal.bolt")
    out = []
    for i in range(count):
        a = math.radians(start_deg + 360.0 * i / count)
        bx = cx + r * math.cos(a)
        by = cy + r * math.sin(a)
        out.append(
            f'<circle cx="{bx:.2f}" cy="{by:.2f}" r="{bolt_r}" fill="{fill}" '
            f'stroke="{T("stroke.default_color")}" stroke-width="{T("stroke.thin_width")}"/>'
        )
    return "\n".join(out)


def chamber(pid, cx, cy, r, name="", state_pid_suffix=True, bolts=8, bolt_r=None):
    """圆形工艺腔（ICP/刻蚀 cluster 的标准件）

    产出：腔体本体 + 螺栓法兰圈 + 腔名标签 + 三色状态灯（_run/_alarm/_unload）
    """
    bolt_r = bolt_r or r * 0.82
    parts = [
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{T("metal.panel")}" '
        f'stroke="{T("stroke.default_color")}" stroke-width="{T("stroke.default_width")}"/>',
        f'<circle cx="{cx}" cy="{cy}" r="{r * 0.72:.2f}" fill="{T("metal.dark")}" '
        f'stroke="{T("stroke.default_color")}" stroke-width="{T("stroke.thin_width")}"/>',
        bolt_circle(cx, cy, bolt_r, bolts),
    ]
    if name:
        parts.append(label(None, cx, cy + r + 14, name, size=T("text.label_size")))

    lamps = ""
    if state_pid_suffix:
        lx = cx - 26
        ly = cy - r - 16
        lamps = "".join(
            f'<circle id="{pid}_{s}" data-pid="{pid}_{s}" cx="{lx + i * 18}" cy="{ly}" r="5" '
            f'fill="{c}" stroke="{T("stroke.default_color")}" stroke-width="1"/>'
            for i, (s, c) in enumerate(
                [("run", T("state.run")), ("alarm", T("state.alarm")), ("unload", T("state.unload"))]
            )
        )
        parts.append(lamps)
    return group(pid, "\n".join(parts))


def signal_tower(pid, x, y, width=None, lamp_h=None, lamps=("run", "alarm", "idle")) -> str:
    """三色塔灯：机台右上角的标准状态指示"""
    width = width or T("tower.width", 22)
    lamp_h = lamp_h or T("tower.lamp_height", 16)
    color_map = {
        "run": T("tower.lamp_run"), "alarm": T("tower.lamp_alarm"),
        "idle": T("tower.lamp_idle"), "off": T("tower.lamp_off"),
    }
    body = [
        rect(None, x, y, width, lamp_h * len(lamps) + 6, fill=T("tower.body"), rx=3),
    ]
    for i, s in enumerate(lamps):
        ly = y + 4 + i * lamp_h
        body.append(
            f'<rect id="{pid}_{s}" data-pid="{pid}_{s}" x="{x + 3}" y="{ly}" width="{width - 6}" '
            f'height="{lamp_h - 4}" rx="2" fill="{color_map.get(s, color_map["off"])}" '
            f'stroke="{T("stroke.default_color")}" stroke-width="1"/>'
        )
    return group(pid, "\n".join(body))


def wafer(pid, cx, cy, r) -> str:
    """彩虹晶圆：die 网格 + 彩虹渐变 + 径向阴影三层叠"""
    return (
        f'<g{pid_attr(pid)}>'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#{T("wafer.pattern_id")})"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#{T("wafer.shade_id")})"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{T("stroke.default_color")}" '
        f'stroke-width="{T("stroke.thin_width")}"/>'
        f'</g>'
    )


def cassette(pid, x, y, w, h, slots=None, slot_state=None, pitch=None):
    """晶舟/FOUP：25 槽片条，槽位 pid 为 {pid}_S{1..25}

    slot_state: 可选 dict {slot_no: 'empty'|'waiting'|'processing'|'done'}
    """
    slots = slots or T("cassette.default_slots", 25)
    pitch = pitch or T("cassette.slot_pitch", 1.75)
    state_color = {
        "empty": T("slot.empty"), "waiting": T("slot.waiting"),
        "processing": T("slot.processing"), "done": T("slot.done"),
    }
    parts = [
        rect(None, x, y, w, h, fill=T("cassette.shell_fill"), rx=4),
        rect(None, x + 4, y + 4, w - 8, h - 8, fill=T("cassette.body_fill"), rx=3),
    ]
    top = y + 10
    for i in range(slots):
        sy = top + i * pitch * 2
        st = (slot_state or {}).get(i + 1, "empty")
        parts.append(
            f'<rect id="{pid}_S{i + 1}" data-pid="{pid}_S{i + 1}" x="{x + 8}" y="{sy:.2f}" '
            f'width="{w - 16}" height="{pitch:.2f}" fill="{state_color.get(st, state_color["empty"])}" '
            f'stroke="none"/>'
        )
    return group(pid, "\n".join(parts))


def port_box(pid, x, y, w=None, h=None, name="", with_door=True, with_slit=True):
    """Load Port：卡匣承载台 + 门板 + slit 阀

    子部件 pid：{pid}_DOOR、{pid}_SLIT、{pid}_CST
    """
    w = w or T("port.width", 120)
    h = h or T("port.height", 90)
    parts = [
        rect(None, x, y, w, h, fill=T("port.body_fill"), rx=5),
        rect(f"{pid}_WINDOW", x + 10, y + 10, w - 20, h - 34, fill=T("port.inner_fill"), rx=3),
    ]
    if name:
        parts.append(label(None, x + w / 2, y + h - 8, name, size=T("text.hint_size")))
    if with_door:
        parts.append(
            rect(f"{pid}_DOOR", x + 12, y + h - 26, w - 24, 8, fill=T("port.door_fill"), rx=2)
        )
    if with_slit:
        parts.append(
            rect(f"{pid}_SLIT", x + 6, y - 7, w - 12, 7, fill=T("metal.mid"), rx=2,
                 sw=T("stroke.thin_width"))
        )
    return group(pid, "\n".join(parts))


def slit_valve(pid, x, y, w, h=8) -> str:
    """独立的 slit 阀压条（腔体与传输腔之间）"""
    return group(pid, rect(None, x, y, w, h, fill=T("metal.mid"), rx=2,
                           sw=T("stroke.thin_width")))


def robot_arm(pid, hub_x, hub_y, upper_len=90, fore_len=70, wrist_r=40):
    """三段连杆机械臂：肩 / 肘 / 腕

    子部件 pid：{pid}_UPPER、{pid}_FORE、{pid}_WRIST
    deriver 按这三层做 IK，动画符合连杆原理（不是整臂平移）
    """
    upper = (
        f'<line x1="0" y1="0" x2="{upper_len}" y2="0" stroke="{T("metal.mid")}" '
        f'stroke-width="11" stroke-linecap="round"/>'
        f'<circle cx="0" cy="0" r="8" fill="{T("metal.dark")}" stroke="{T("stroke.default_color")}" '
        f'stroke-width="{T("stroke.thin_width")}"/>'
    )
    fore = (
        f'<line x1="0" y1="0" x2="{fore_len}" y2="0" stroke="{T("metal.light")}" '
        f'stroke-width="9" stroke-linecap="round"/>'
        f'<circle cx="0" cy="0" r="6" fill="{T("metal.dark")}" stroke="{T("stroke.default_color")}" '
        f'stroke-width="{T("stroke.thin_width")}"/>'
    )
    wrist = (
        f'<circle cx="0" cy="0" r="{wrist_r * 0.35:.1f}" fill="{T("metal.dark")}" '
        f'stroke="{T("stroke.default_color")}" stroke-width="{T("stroke.thin_width")}"/>'
        f'<path d="M {-wrist_r * 0.7:.1f} -6 L {wrist_r * 0.7:.1f} -6 L {wrist_r * 0.7:.1f} 6 '
        f'L {-wrist_r * 0.7:.1f} 6 Z" fill="{T("metal.light")}" stroke="{T("stroke.default_color")}" '
        f'stroke-width="{T("stroke.thin_width")}"/>'
    )
    inner = (
        group(f"{pid}_UPPER", upper, transform=f"translate({hub_x},{hub_y})")
        + group(f"{pid}_FORE", fore, transform=f"translate({hub_x + upper_len},{hub_y})")
        + group(f"{pid}_WRIST", wrist, transform=f"translate({hub_x + upper_len + fore_len},{hub_y})")
    )
    return group(pid, inner)


def baseplate(pid, x, y, w, h, label_text=None) -> str:
    """机台底板/台面"""
    parts = [rect(None, x, y, w, h, fill=T("metal.light"), rx=6)]
    if label_text:
        parts.append(label(None, x + w / 2, y + h - 10, label_text,
                           size=T("text.hint_size"), fill=T("text.secondary")))
    return group(pid, "\n".join(parts))


def title_block(pid, x, y, title, subtitle="") -> str:
    """图签：右下角机型 + 图号"""
    parts = [label(None, x, y, title, size=T("text.title_size"), anchor="start")]
    if subtitle:
        parts.append(label(None, x, y + 16, subtitle, size=T("text.hint_size"),
                           anchor="start", fill=T("text.secondary")))
    return group(pid, "\n".join(parts))


# ── 等角与 cluster 公共部件 ───────────────────────────────────────────────
def _pts(points):
    return " ".join(f"{x:.2f},{y:.2f}" for x, y in points)


def _poly(points, fill, stroke=None, sw=None, extra=""):
    stroke = stroke if stroke is not None else T("iso.edge")
    sw = sw if sw is not None else T("stroke.thin_width")
    ex = f" {extra}" if extra else ""
    return f'<polygon points="{_pts(points)}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{ex}/>'


def iso_box(pid, cx, cy, w, d, h, top=None, left=None, right=None, extra=""):
    """等角柜体；cx/cy 为底面中心，顶面中心为 (cx, cy-h)。"""
    ty = cy - h
    p_top = (cx, ty - d / 2)
    p_right = (cx + w / 2, ty)
    p_bottom = (cx, ty + d / 2)
    p_left = (cx - w / 2, ty)
    parts = [
        _poly([p_left, p_bottom, (p_bottom[0], p_bottom[1] + h), (p_left[0], p_left[1] + h)],
              left or "url(#isoSilverBody)"),
        _poly([p_bottom, p_right, (p_right[0], p_right[1] + h), (p_bottom[0], p_bottom[1] + h)],
              right or T("iso.right")),
        _poly([p_top, p_right, p_bottom, p_left], top or T("iso.top")),
    ]
    body = "\n".join(parts)
    return group(pid, body, extra=extra) if pid else body


def iso_cylinder(pid, cx, cy, rx, ry, h, top=None, body=None, extra=""):
    """等角圆柱/泵体；cx/cy 为底部椭圆中心。"""
    ty = cy - h
    body_fill = body or "url(#isoSilverBody)"
    top_fill = top or T("iso.top")
    d = (
        f"M {cx-rx:.2f} {ty:.2f} L {cx-rx:.2f} {cy:.2f} "
        f"A {rx:.2f} {ry:.2f} 0 0 0 {cx+rx:.2f} {cy:.2f} "
        f"L {cx+rx:.2f} {ty:.2f} Z"
    )
    parts = [
        f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{T("metal.deep")}" opacity="0.18"/>',
        f'<path d="{d}" fill="{body_fill}" stroke="{T("iso.edge")}" stroke-width="{T("stroke.thin_width")}"/>',
        f'<ellipse cx="{cx}" cy="{ty}" rx="{rx}" ry="{ry}" fill="{top_fill}" stroke="{T("iso.edge")}" stroke-width="{T("stroke.thin_width")}"{(" " + extra) if extra else ""}/>',
        f'<path d="M {cx-rx*.72:.2f} {ty+4:.2f} L {cx-rx*.72:.2f} {cy-3:.2f}" fill="none" stroke="#ffffff" stroke-opacity="0.38" stroke-width="2"/>',
    ]
    content = "\n".join(parts)
    return group(pid, content) if pid else content


def _rounded_top(cx, cy, rx, ry):
    """等角 superellipse 顶盖，四角圆弧、四边平直，贴近 Sym3 圆角矩形。"""
    points = []
    for i in range(40):
        a = 2 * math.pi * i / 40
        ca, sa = math.cos(a), math.sin(a)
        x = rx * math.copysign(abs(ca) ** 0.5, ca)
        y = ry * math.copysign(abs(sa) ** 0.5, sa)
        points.append((cx + x, cy + y))
    return "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in points) + " Z"


def _state_lamps(pid, cx, cy):
    return "\n".join(
        f'<circle id="{pid}_{s}" data-pid="{pid}_{s}" cx="{cx + i * 17 - 17:.2f}" cy="{cy:.2f}" r="4.6" '
        f'fill="{c}" stroke="{T("iso.edge")}" stroke-width="1"/>'
        for i, (s, c) in enumerate((("run", T("state.run")), ("alarm", T("state.alarm")), ("unload", T("state.unload"))))
    )


def iso_process_chamber(pid, cx, cy, w=150, d=92, h=150, name="", perforated=True):
    """Sym3 类蓝色圆角工艺腔：金属身、圆角顶盖、孔阵与状态灯。"""
    rx, ry, ty = w / 2, d / 2, cy - h
    parts = [iso_cylinder(None, cx, cy + 5, rx * 0.82, ry * 0.76, 20,
                          top=T("iso.copper_top"), body="url(#isoCopperBody)")]
    body_d = (
        f"M {cx-rx:.2f} {ty:.2f} L {cx-rx:.2f} {cy:.2f} "
        f"C {cx-rx:.2f} {cy+ry*.72:.2f} {cx-rx*.72:.2f} {cy+ry:.2f} {cx:.2f} {cy+ry:.2f} "
        f"C {cx+rx*.72:.2f} {cy+ry:.2f} {cx+rx:.2f} {cy+ry*.72:.2f} {cx+rx:.2f} {cy:.2f} "
        f"L {cx+rx:.2f} {ty:.2f} Z"
    )
    parts.append(f'<path d="{body_d}" fill="url(#isoBlueBody)" stroke="{T("iso.edge")}" stroke-width="1.4"/>')
    parts.append(f'<path d="{_rounded_top(cx, ty, rx, ry)}" fill="{T("iso.blue_top")}" stroke="{T("iso.edge")}" stroke-width="1.5"/>')
    parts.append(f'<path d="M {cx-rx:.2f} {ty+25:.2f} C {cx:.2f} {ty+ry+25:.2f} {cx+rx:.2f} {ty+25:.2f} {cx+rx:.2f} {ty+25:.2f}" fill="none" stroke="#8ee8ff" stroke-opacity="0.65" stroke-width="2"/>')
    if perforated:
        for ix in range(-3, 4):
            for iy in range(-2, 3):
                dx, dy = ix * 15, iy * 12
                if (dx / (rx * 0.72)) ** 2 + (dy / (ry * 0.72)) ** 2 <= 1:
                    parts.append(f'<circle cx="{cx+dx}" cy="{ty+dy}" r="3.2" fill="{T("metal.deep")}" stroke="#8ee8ff" stroke-width="0.6"/>')
    parts.append(label(None, cx, cy - 32, name or pid, size=11, fill=T("text.inverse"), weight="700"))
    parts.append(_state_lamps(pid, cx, ty - ry - 12))
    return group(pid, "\n".join(parts))


def iso_cabinet_chamber(pid, cx, cy, w=116, d=82, h=180, name=""):
    """SPT 类高柜工艺模块：后部控制/排气柜 + 前侧圆形工艺腔。"""
    ty = cy - h
    parts = [iso_box(None, cx, cy, w, d, h)]
    for i in range(-3, 4):
        parts.append(f'<line x1="{cx-w*.26+i*5:.2f}" y1="{ty-8:.2f}" x2="{cx+w*.12+i*5:.2f}" y2="{ty+12:.2f}" stroke="{T("metal.dark")}" stroke-width="2" opacity="0.75"/>')
    parts.append(iso_cylinder(None, cx + w * 0.18, ty - d * 0.15, 10, 6, 24,
                              top=T("metal.light"), body="url(#isoSilverBody)"))
    parts.append(f'<path d="M {cx-w/2+8:.2f} {ty+18:.2f} L {cx-w/2+8:.2f} {cy-12:.2f} M {cx+w/2-8:.2f} {ty+18:.2f} L {cx+w/2-8:.2f} {cy-12:.2f}" fill="none" stroke="{T("metal.dark")}" stroke-width="1.2"/>')
    parts.append(iso_cylinder(None, cx, cy + 23, w * 0.39, d * 0.34, 65,
                              top=T("metal.light"), body="url(#isoSilverBody)"))
    parts.append(f'<ellipse cx="{cx}" cy="{cy-42}" rx="{w*.25}" ry="{d*.19}" fill="{T("metal.dark")}" stroke="{T("metal.bolt")}" stroke-width="3"/>')
    parts.append(label(None, cx, cy - 70, name or pid, size=10, fill=T("text.primary"), weight="700"))
    parts.append(_state_lamps(pid, cx, ty - d / 2 - 12))
    return group(pid, "\n".join(parts))


def iso_load_port(pid, cx, cy, w=105, d=70, h=105, name=""):
    parts = [iso_box(None, cx, cy, w, d, h)]
    ty = cy - h
    parts.append(rect(f"{pid}_DOOR", cx - w * 0.31, ty + 26, w * 0.62, 14,
                      fill=T("port.door_fill"), rx=2, sw=1))
    parts.append(rect(f"{pid}_SLIT", cx - w * 0.34, cy - 18, w * 0.68, 8,
                      fill=T("metal.dark"), rx=2, sw=1))
    parts.append(label(None, cx, ty - d / 2 - 10, name or pid, size=9, weight="700"))
    return group(pid, "\n".join(parts))


def pump_module(pid, cx, cy, scale=1.0):
    """前侧真空泵：银色基座 + 金色多级泵头。"""
    parts = [
        iso_cylinder(None, cx, cy, 27 * scale, 15 * scale, 68 * scale),
        iso_cylinder(None, cx, cy - 55 * scale, 32 * scale, 18 * scale, 53 * scale,
                     top=T("iso.gold_top"), body="url(#isoGoldBody)"),
        f'<ellipse cx="{cx}" cy="{cy-108*scale}" rx="{20*scale}" ry="{11*scale}" fill="none" stroke="{T("iso.gold_right")}" stroke-width="{4*scale}"/>',
        f'<ellipse cx="{cx}" cy="{cy-108*scale}" rx="{8*scale}" ry="{5*scale}" fill="{T("metal.dark")}"/>',
    ]
    return group(pid, "\n".join(parts))


def vacuum_channel(pid, x1, y1, x2, y2, width=24):
    """两腔之间的封闭通道，先画通道再画腔体可避免裸露断口。"""
    length = math.hypot(x2 - x1, y2 - y1)
    angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
    parts = [
        rect(None, 0, -width / 2, length, width, fill=T("metal.mid"), rx=3),
        rect(None, 5, -width * 0.25, max(0, length - 10), width * 0.5,
             fill=T("metal.dark"), rx=2, sw=1),
        rect(None, 3, -width * 0.65, 8, width * 1.3, fill=T("metal.light"), rx=2, sw=1),
        rect(None, max(0, length - 11), -width * 0.65, 8, width * 1.3, fill=T("metal.light"), rx=2, sw=1),
    ]
    return group(pid, "\n".join(parts), transform=f"translate({x1:.2f},{y1:.2f}) rotate({angle:.2f})")


def top_process_chamber(pid, cx, cy, w=122, h=132, angle=0, name=""):
    """LAM 类顶视矩形 PM，正面 slit 朝向本地 -Y，再按 angle 旋转。"""
    x, y = cx - w / 2, cy - h / 2
    parts = [
        rect(None, x, y, w, h, fill="url(#edgeMetal)", rx=5),
        rect(None, x + 10, y + 12, w - 20, h - 25, fill=T("metal.light"), rx=3, sw=1.2),
        rect(f"{pid}_SLIT", cx - 28, y - 5, 56, 9, fill=T("metal.dark"), rx=2, sw=1),
    ]
    for bx in (x + 12, x + w - 12):
        for by in (y + 16, y + h - 16):
            parts.append(circle(None, bx, by, 3, fill=T("metal.bolt"), sw=0.8))
    parts.append(label(None, cx, cy + 5, name or pid, size=12, weight="700"))
    parts.append(_state_lamps(pid, cx, y - 14))
    return group(pid, "\n".join(parts), transform=f"rotate({angle:.2f} {cx:.2f} {cy:.2f})")


def top_airlock(pid, cx, cy, w=100, h=112, angle=0, name=""):
    x, y = cx - w / 2, cy - h / 2
    parts = [
        rect(None, x, y, w, h, fill="url(#edgeMetal)", rx=5),
        rect(f"{pid}_DOOR", x + 10, y + 10, w - 20, h - 20, fill=T("port.inner_fill"), rx=4),
        rect(None, x + 19, y + 18, w - 38, h - 36, fill=T("metal.mid"), rx=3, sw=1),
        label(None, cx, cy + 4, name or pid, size=10, fill=T("text.inverse"), weight="700"),
    ]
    return group(pid, "\n".join(parts), transform=f"rotate({angle:.2f} {cx:.2f} {cy:.2f})")


def aligner(pid, cx, cy, r=42):
    parts = [
        circle(None, cx, cy, r, fill=T("metal.panel")),
        circle(None, cx, cy, r * 0.64, fill=T("metal.dark"), sw=1),
        bolt_circle(cx, cy, r * 0.86, 8),
        wafer(f"{pid}_WAFER", cx, cy, r * 0.34),
    ]
    return group(pid, "\n".join(parts))


def buffer_station(pid, cx, cy, r=38):
    parts = [circle(None, cx, cy, r, fill=T("metal.panel")),
             circle(None, cx, cy, r * 0.7, fill=T("metal.dark"), sw=1),
             label(None, cx, cy + 4, "BUF", size=10, fill=T("text.inverse"))]
    return group(pid, "\n".join(parts))


def control_rack(pid, x, y, w, h):
    parts = [rect(None, x, y, w, h, fill=T("metal.panel"), rx=6)]
    for i in range(4):
        parts.append(rect(None, x + 12, y + 14 + i * (h - 28) / 4, w - 24, (h - 42) / 4,
                          fill=T("metal.dark"), rx=2, sw=1))
    parts.append(label(None, x + w / 2, y + h - 9, "CONTROL RACK", size=9, fill=T("text.inverse")))
    return group(pid, "\n".join(parts))
