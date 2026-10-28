"""Motion JSON 构建器（对齐线上真实格式）

线上格式（对照 models/user/oxe-drm-topview.motion.json 实测）：
{
  "schema_version": "1.1",
  "document": {"name","src","coord"},
  "motions": [ {"step","enabled","when","rules":[
      {"phase","target_part_id","when","actions":[{"type","duration",...}]}
  ]} ],
  "ext": {"machine_type","version","description","deriver",
          "param_defaults","event_aliases","part_aliases","viewBox_fallback"}
}

动作类型（线上实际用到的全部 6 种）：
  snap / visibility / offset / opacity / text / rotate

存在的意义：手写 Motion JSON 最容易出的错是 target_part_id 拼错、或与 SVG 的
data-pid 对不上，运行时表现为动画静默不生效、极难排查。用构建器 + validate.py
可以在生成期就把这类错误拦掉。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

SCHEMA_VERSION = "1.1"

# 线上实测到的全部动作类型
ACTION_TYPES = {"snap", "visibility", "offset", "opacity", "text", "rotate"}


# ── 动作构造 ──────────────────────────────────────────────────────────────
def snap(to_part_id: str, duration: int = 0, visible: bool = None) -> Dict[str, Any]:
    """把部件瞬移到另一个部件的位置（如晶圆吸附到机械臂）"""
    a: Dict[str, Any] = {"type": "snap", "to_part_id": to_part_id, "duration": duration}
    if visible is not None:
        a["visible"] = visible
    return a


def visibility(to: bool, duration: int = 0) -> Dict[str, Any]:
    """显示/隐藏。线上用量最大的动作（1065 次）"""
    return {"type": "visibility", "to": to, "duration": duration}


def offset(x: float = 0.0, y: float = 0.0, duration: int = 400,
           easing: str = None) -> Dict[str, Any]:
    a: Dict[str, Any] = {"type": "offset", "offset_x": x, "offset_y": y, "duration": duration}
    if easing:
        a["easing"] = easing
    return a


def opacity(to: float, duration: int = 300, easing: str = None) -> Dict[str, Any]:
    a: Dict[str, Any] = {"type": "opacity", "to": to, "duration": duration}
    if easing:
        a["easing"] = easing
    return a


def rotate(angle: float, duration: int = 400, easing: str = None) -> Dict[str, Any]:
    a: Dict[str, Any] = {"type": "rotate", "angle": angle, "duration": duration}
    if easing:
        a["easing"] = easing
    return a


def text(content: str, fill: str = None, font_size: int = None,
         stroke_width: float = None, duration: int = 0) -> Dict[str, Any]:
    """改文本部件的内容（如 LOT 标签、状态徽章）"""
    a: Dict[str, Any] = {"type": "text", "content": content, "duration": duration}
    if fill is not None:
        a["fill"] = fill
    if font_size is not None:
        a["fontSize"] = font_size
    if stroke_width is not None:
        a["strokeWidth"] = stroke_width
    return a


# ── 规则 / 步骤 ───────────────────────────────────────────────────────────
def rule(target_part_id: str, actions: List[Dict[str, Any]],
         when: str = "true", phase: int = None) -> Dict[str, Any]:
    """一条规则：when 命中时对 target_part_id 执行 actions

    target_part_id 支持运行时占位符，如 "{POD}" / "{CST}_{PORT}"，
    由 deriver 按 params 展开（validate.py 会跳过这类校验）。
    """
    r: Dict[str, Any] = {"when": when, "target_part_id": target_part_id, "actions": actions}
    if phase is not None:
        r["phase"] = phase
    return r


def step(name: str, rules: List[Dict[str, Any]], when: str = "true",
         enabled: bool = True, description: str = "") -> Dict[str, Any]:
    """一个动画步骤（对应一个事件，如 POD_PLACED / MVIN / DOOR_OPEN）"""
    s: Dict[str, Any] = {"step": name, "enabled": enabled, "when": when, "rules": rules}
    if description:
        s["description"] = description
    return s


class MotionBuilder:
    """链式构建 Motion JSON 文档"""

    def __init__(self, machine_type: str, name: str, src: str,
                 deriver: str = "", version: str = "1.0", description: str = ""):
        self.doc: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "document": {
                "name": name,
                "src": src,
                "coord": {"origin": "top-left", "unit": "px", "y_down": True},
            },
            "motions": [],
            "ext": {
                "machine_type": machine_type,
                "version": version,
                "description": description,
                "deriver": deriver,
                "param_defaults": {},
                "event_aliases": {},
                "part_aliases": {},
                "viewBox_fallback": "0 0 1080 840",
            },
        }

    def param_defaults(self, **kw) -> "MotionBuilder":
        self.doc["ext"]["param_defaults"].update(kw)
        return self

    def part_aliases(self, **kw) -> "MotionBuilder":
        """pid 别名：SVG 改名后无需改所有规则"""
        self.doc["ext"]["part_aliases"].update(kw)
        return self

    def event_aliases(self, **kw) -> "MotionBuilder":
        self.doc["ext"]["event_aliases"].update(kw)
        return self

    def add(self, name: str, rules: List[Dict[str, Any]], when: str = "true",
            enabled: bool = True, description: str = "") -> "MotionBuilder":
        self.doc["motions"].append(step(name, rules, when, enabled, description))
        return self

    def build(self) -> Dict[str, Any]:
        return self.doc
