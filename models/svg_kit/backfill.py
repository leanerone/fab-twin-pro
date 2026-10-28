"""给存量 SVG 回填 data-pid 标记

背景：模型编辑器的部件清单只取带 data-pid 的元素（MotionPreview.vue:589），
引擎则按 id 定位（useMotionPlayback.js:222）。存量机型里 OXE 两类都齐，
但 PODOPENER / AMAT 只有 id、没有 data-pid，导致编辑器部件清单为空、部件无法点选。

本工具给"非绘制资源"的带 id 元素补上 data-pid="<id>"，使其进入可检视部件清单。
幂等：已有 data-pid 的元素不动；默认写回前生成 .bak。

用法：
    python -m models.svg_kit.backfill models/user/podopener-2200.svg
    python -m models.svg_kit.backfill models/user/*.svg --no-backup
"""
from __future__ import annotations

import argparse
import re
import sys

# 这些标签属于绘制资源（渐变/图案/滤镜/裁剪/标记），不是可视部件
RESOURCE_TAGS = {
    "linearGradient", "radialGradient", "pattern", "filter",
    "clipPath", "mask", "marker", "symbol", "style", "defs",
}


def _tag_name(tag: str) -> str:
    m = re.match(r"<\s*([a-zA-Z][\w:-]*)", tag)
    return m.group(1) if m else ""


def backfill(svg_text: str) -> tuple[str, int]:
    """返回 (新文本, 新增数量)"""
    added = 0

    def repl(m: re.Match) -> str:
        nonlocal added
        tag = m.group(0)
        if "data-pid=" in tag:
            return tag
        if _tag_name(tag) in RESOURCE_TAGS:
            return tag
        idm = re.search(r'\sid="([^"]+)"', tag)
        if not idm:
            return tag
        pid = idm.group(1)
        # 插到 id 之后，保持属性顺序可读
        insert_at = idm.end()
        added += 1
        return f'{tag[:insert_at]} data-pid="{pid}"{tag[insert_at:]}'

    # 只匹配带 id 且自闭合或非自闭合的开始标签（不跨标签）
    new_text = re.sub(r"<[a-zA-Z][\w:-]*(?:\s[^<>]*?)?\sid=\"[^\"]+\"[^<>]*>", repl, svg_text)
    return new_text, added


def main():
    ap = argparse.ArgumentParser(description="回填 SVG 的 data-pid 标记")
    ap.add_argument("files", nargs="+", help="SVG 文件路径")
    ap.add_argument("--no-backup", action="store_true", help="不生成 .bak 备份")
    args = ap.parse_args()

    exit_code = 0
    for path in args.files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                original = f.read()
        except OSError as e:
            print(f"[ERROR] 读取失败 {path}: {e}")
            exit_code = 1
            continue

        new_text, added = backfill(original)
        if added == 0:
            print(f"跳过 {path}（已全部带 data-pid，无需改动）")
            continue

        if not args.no_backup:
            with open(path + ".bak", "w", encoding="utf-8") as f:
                f.write(original)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_text)
        print(f"已回填 {path}: 新增 {added} 个 data-pid"
              + ("" if args.no_backup else f"，原文件备份为 {path}.bak"))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
