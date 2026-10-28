"""SVG / Motion JSON 一致性校验

把「动画静默不生效」这类运行时难查的问题提前到构建期发现。

检查项：
1. SVG 是否 XML 合法
2. data-pid 是否唯一（重复会让引擎只改到第一个）
3. Motion JSON 结构是否符合通用规范
4. Motion 里引用的 target_part_id 是否在 SVG 中存在（**最容易出错的一项**）
5. SVG 里定义了但 Motion 从未引用的 pid（仅提示，可能是静态部件）
"""
from __future__ import annotations

import json
import re
import sys
from typing import Dict, List, Tuple

import xml.etree.ElementTree as ET

try:
    from . import primitives as P
    from .motion import ACTION_TYPES
except ImportError:  # 允许直接 python models/svg_kit/validate.py 运行
    import primitives as P
    from motion import ACTION_TYPES


_PID_RE = re.compile(r'data-pid="([^"]+)"')
_ID_RE = re.compile(r'\sid="([^"]+)"')
# 运行时占位符：{POD} / {CST}_{PORT} / {home}，由 deriver 按 params 展开，
# 构建期无法解析，不做存在性校验。
_PLACEHOLDER_RE = re.compile(r"\{[^}]+\}")


def extract_ids(svg_text: str) -> List[str]:
    """SVG 中所有 id（引擎按 id 定位目标，故这是合法 target 的全集）"""
    return _ID_RE.findall(svg_text)


def extract_parts(svg_text: str) -> List[str]:
    """可检视部件：带 data-pid 的元素，取其 id 作为键"""
    parts = []
    for m in re.finditer(r"<[a-zA-Z]+\b[^>]*?\bdata-pid=\"([^\"]+)\"[^>]*>", svg_text):
        tag = m.group(0)
        idm = _ID_RE.search(tag)
        parts.append(idm.group(1) if idm else m.group(1))
    return parts


def extract_pids(svg_text: str) -> List[str]:
    """按出现顺序提取所有 data-pid"""
    return _PID_RE.findall(svg_text)


def check_svg(svg_text: str) -> Tuple[List[str], List[str]]:
    """返回 (errors, warnings)"""
    errors: List[str] = []
    warnings: List[str] = []

    try:
        ET.fromstring(svg_text)
    except ET.ParseError as e:
        errors.append(f"SVG 不是合法 XML: {e}")
        return errors, warnings

    parts = extract_parts(svg_text)
    if not parts:
        errors.append("SVG 中没有任何带 data-pid 的部件，模型编辑器将看不到可检视部件")
        return errors, warnings

    ids = extract_ids(svg_text)
    seen: Dict[str, int] = {}
    for p in ids:
        seen[p] = seen.get(p, 0) + 1
    dup = [p for p, c in seen.items() if c > 1]
    if dup:
        errors.append(f"id 重复（引擎只会驱动第一个）: {dup[:10]}")

    # 带 data-pid 却没有 id 的部件：编辑器里显示为空白项，且动画无法定位
    no_id = [m.group(1) for m in re.finditer(r"<[a-zA-Z]+\b[^>]*?\bdata-pid=\"([^\"]+)\"[^>]*>", svg_text)
             if not _ID_RE.search(m.group(0))]
    if no_id:
        errors.append(
            f"以下部件只有 data-pid 没有 id，动画会静默不生效（引擎按 id 定位）: {no_id[:10]}"
        )

    return errors, warnings


def check_motion(motion: dict) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    for key in ("schema_version", "document", "motions"):
        if key not in motion:
            errors.append(f"Motion JSON 缺少顶层字段: {key}")
    if "motions" not in motion:
        return errors, warnings

    for mi, m in enumerate(motion.get("motions", [])):
        if not isinstance(m, dict):
            errors.append(f"motions[{mi}] 不是对象")
            continue
        # 线上字段名是 step（兼容旧式的 name）
        sname = m.get("step") or m.get("name")
        if not sname:
            errors.append(f"motions[{mi}] 缺少 step")
        if "rules" not in m:
            errors.append(f"motions[{mi}]({sname}) 缺少 rules")
            continue
        for ri, r in enumerate(m.get("rules", [])):
            if not isinstance(r, dict):
                errors.append(f"motions[{mi}].rules[{ri}] 不是对象")
                continue
            if "target_part_id" not in r:
                errors.append(f"{sname}.rules[{ri}] 缺少 target_part_id")
            if "actions" not in r:
                errors.append(f"{sname}.rules[{ri}] 缺少 actions")
            elif not r["actions"]:
                warnings.append(
                    f"{sname}.rules[{ri}] 的 actions 为空（命中后无视觉效果，确认是否为占位）"
                )
            for ai, a in enumerate(r.get("actions", []) or []):
                at = (a or {}).get("type")
                if at is not None and at not in ACTION_TYPES:
                    warnings.append(
                        f"{sname}.rules[{ri}].actions[{ai}] 类型 '{at}' 不在已知集合中 {sorted(ACTION_TYPES)}"
                    )
    return errors, warnings


def cross_check(svg_text: str, motion: dict) -> Tuple[List[str], List[str]]:
    """交叉校验：Motion 引用的部件必须在 SVG 里存在"""
    errors: List[str] = []
    warnings: List[str] = []

    # 引擎按 id 定位，合法目标 = 全部 id ∪ 别名
    svg_pids = set(extract_ids(svg_text))
    aliases = (motion.get("ext", {}) or {}).get("part_aliases", {}) or {}
    valid = svg_pids | set(aliases.keys())

    referenced = set()
    placeholder_refs = set()
    for m in motion.get("motions", []):
        sname = m.get("step") or m.get("name")
        for r in m.get("rules", []):
            t = r.get("target_part_id")
            if not t:
                continue
            referenced.add(t)
            if _PLACEHOLDER_RE.search(t):
                placeholder_refs.add(t)
                continue  # 运行时展开，跳过存在性校验
            if t not in valid:
                errors.append(
                    f"Motion 引用了不存在的部件: step={sname} target_part_id={t}"
                )

    if placeholder_refs:
        warnings.append(
            f"{len(placeholder_refs)} 个 target_part_id 含运行时占位符，已跳过存在性校验"
            f"（需 deriver 侧保证展开后存在）: {sorted(placeholder_refs)[:8]}"
        )

    # 只对"可检视部件"统计未引用，避免把渐变/滤镜等绘制资源 id 也算进来
    unused = sorted(set(extract_parts(svg_text)) - referenced)
    if unused:
        warnings.append(
            f"{len(unused)} 个可检视部件未被任何 Motion 引用（可能是静态部件，确认是否有遗漏）: "
            f"{unused[:12]}{' ...' if len(unused) > 12 else ''}"
        )
    return errors, warnings


def validate(svg_path: str, motion_path: str) -> int:
    with open(svg_path, "r", encoding="utf-8") as f:
        svg_text = f.read()
    with open(motion_path, "r", encoding="utf-8") as f:
        motion = json.load(f)

    errors: List[str] = []
    warnings: List[str] = []
    for fn in (lambda: check_svg(svg_text),
               lambda: check_motion(motion),
               lambda: cross_check(svg_text, motion)):
        e, w = fn()
        errors.extend(e)
        warnings.extend(w)

    name = svg_path.split("\\")[-1].split("/")[-1]
    print(f"=== 校验 {name} ===")
    print(f"  id 总数     : {len(set(extract_ids(svg_text)))}")
    print(f"  可检视部件  : {len(set(extract_parts(svg_text)))}")
    print(f"  motion 步骤 : {len(motion.get('motions', []))}")
    for w in warnings:
        print(f"  [WARN]  {w}")
    if errors:
        for e in errors:
            print(f"  [ERROR] {e}")
        print(f"  结果: 失败（{len(errors)} 项错误）")
        return 1
    print("  结果: 通过")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("用法: python validate.py <机台.svg> <机台.motion.json>")
        sys.exit(2)
    sys.exit(validate(sys.argv[1], sys.argv[2]))
