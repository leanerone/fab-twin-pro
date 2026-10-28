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
        f'font-family="{ff}" width="{width}" height="{height}" '
        f'style="width: {width}px; height: {height}px;">\n'
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
</defs>
"""


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
