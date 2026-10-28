"""FabTwin SVG 公共库（svg-kit）

目标：让后续新机型的 2D SVG 有公共库可以编写，而不是每次从零手绘。

组成：
- tokens.json   设计令牌（Python / JS / HTML 编辑器共用同一份色板与尺寸）
- primitives.py 公共部件生成器（腔体/塔灯/晶舟/晶圆/门/机械臂/LoadPort ...）
- motion.py     Motion JSON 构建器（避免手写 target_part_id 拼错）
- validate.py   SVG × Motion 交叉校验（把"动画静默不生效"提前到构建期发现）
- scaffold.py   新机型脚手架 CLI（填参数即产出可校验的 SVG + Motion）

快速开始：
    python -m models.svg_kit.scaffold --machine NEW-ETCH --ports 2 --chambers 3
    python -m models.svg_kit.validate models/user/new-etch-topview.svg \
                                      models/user/new-etch-topview.motion.json

详细编写指南见 docs/SVG公共库编写指南.md
"""
from . import primitives  # noqa: F401
from . import motion  # noqa: F401

__all__ = ["primitives", "motion"]
__version__ = "1.0"
