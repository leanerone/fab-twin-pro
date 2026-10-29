# SVG 公共库（svg-kit）编写指南

> 建立日期：2026-10-29　|　版本：1.1
> 目标：**后续新建机型的 SVG 有公共库可以编写**，不再从零手绘、不再踩重复的坑。
> 当前边界：初版公共部件已可用；PODOPENER 新外观尚未全部回收，LAM2300/SPT/Sym3 仍需补布局模板。

---

## 一、为什么需要它

ver2.14/2.15 把 PODOPENER、OXE、AMAT 三个机型迁到 motion2d 统一管线后，"加一个新机型"的成本
收敛成了「SVG 资产 + Motion JSON + deriver」三件套。但实际做的时候仍有三类重复劳动：

1. **视觉不一致**：每台机型的金属色、状态灯色、线宽都是手写的，新旧机型放一起看得出差别
2. **部件重写**：法兰螺栓圈、三色塔灯、25 槽晶舟、三段机械臂——每个机型都重写一遍三角函数
3. **错误难查**：Motion JSON 里 `target_part_id` 拼错，运行时表现为"动画静默不生效"，极难定位

svg-kit 就是针对这三点建的。

---

## 二、库的位置与组成

```
models/svg_kit/
├── tokens.json      设计令牌（Python / JS / HTML 编辑器共用同一份色板与尺寸）
├── primitives.py    公共部件生成器（腔体/塔灯/晶舟/晶圆/门/机械臂/LoadPort...）
├── motion.py        Motion JSON 构建器（对齐线上真实格式）
├── validate.py      SVG × Motion 交叉校验
├── backfill.py      给存量 SVG 回填 data-pid
└── scaffold.py      新机型脚手架 CLI
```

---

## 三、最重要的一条约定：id 与 data-pid 必须同时存在

这是本次建库时通过校验器发现、并已确认到源码的硬约定：

| 属性 | 作用 | 证据 |
|---|---|---|
| `id` | **引擎按它定位部件**，动画的 target | `useMotionPlayback.js:222` 用 `querySelector('#<id>')` |
| `data-pid` | 标记"这是可检视部件"，决定它是否出现在模型编辑器部件清单 | `MotionPreview.vue:589` 只取带 `data-pid` 的元素，再读它们的 `id` |

**只写 `data-pid` 不写 `id` → 动画静默不生效。**
**只写 `id` 不写 `data-pid` → 模型编辑器里看不到这个部件、无法点选。**

`primitives.py` 的 `pid_attr()` 已经保证两个一起输出，用公共部件就不会踩这个坑。

### 存量机型的实际状态（2026-10-29 校验结果）

| 机型 | id 总数 | 可检视部件 | 状态 |
|---|---|---|---|
| OXE (oxe-drm-topview) | 353 | 50 | 正常 |
| PODOPENER (podopener-2200) | 53 | **0 → 32 → 35** | 已回填并按 GLB 重绘，保留动画挂点 |
| AMAT (amat_metsput) | 261 | **0 → 237** | 已用 backfill 修复 |

> PODOPENER / AMAT 原先完全没有 `data-pid`，模型编辑器部件清单是空的——这正是
> ver2.15 反馈的"部件不能点选查看"在另两个机型上的残留。已用 `backfill.py` 修复；
> PODOPENER 后续重绘后的最终数量为 53 IDs / 35 可检视部件。

### 根 SVG 尺寸约定

- 必须同时保留 `viewBox` 与根节点 `width` / `height`，否则调试预览可能得到 `0×0` 画布。
- **禁止在根节点写固定 `style="width:...px;height:...px"`**，它会覆盖预览 CSS 的等比缩放并产生 viewport 留白；`primitives.svg_open()` 已遵守此约定。
- 部件内部尺寸仍使用 SVG 用户坐标；响应式显示交给预览容器，不要把屏幕像素尺寸写进部件参数。

---

## 四、写新机型的标准流程

### 第 1 步：生成脚手架

```powershell
python -m models.svg_kit.scaffold --machine NEW-ETCH --ports 2 --chambers 3
```

产出 `models/user/new-etch-topview.svg` 与 `.motion.json`，已包含：
底板、三色塔灯、图签、六边形传输腔 TM、三段连杆机械臂、N 个 Load Port（含 25 槽晶舟）、
N 个放射状工艺腔（含三色状态灯 + slit 阀）。

### 第 2 步：按真机布局微调坐标

脚手架给的是合理默认布局，按实际机台照片/图纸调整坐标即可。
所有部件都从 `primitives.py` 来，色值走 `tokens.json`，**不要手写颜色**。

### 第 3 步：校验

```powershell
python -m models.svg_kit.validate models/user/new-etch-topview.svg models/user/new-etch-topview.motion.json
```

校验项：
- SVG 是否为合法 XML
- `id` 是否重复（引擎只会驱动第一个）
- 是否有"只有 data-pid 没有 id"的部件（动画会静默失效）
- Motion JSON 结构是否符合规范、动作类型是否已知
- **Motion 引用的 `target_part_id` 是否在 SVG 中存在**（最容易出错的一项）
- 含 `{POD}` 这类运行时占位符的引用会跳过存在性校验，但会提示需 deriver 侧保证

### 第 4 步：上传与调试

SVG 同步到 `backend/uploads/models/`，在模型编辑器的「动画调试」Tab 里点选部件、
单步触发事件验证。

---

## 五、公共部件清单（primitives.py）

### 基础
| 函数 | 说明 |
|---|---|
| `svg_open(w, h, viewbox)` / `svg_close()` | 画布 |
| `defs()` | 彩虹晶圆渐变 + die 网格 + 金属边渐变（所有机型共用同一套 id） |
| `group(pid, children, transform)` | 可动组（motion 的 transform 写在组上） |
| `rect/circle/label(pid, ...)` | 基础图元（自动带 id + data-pid） |

### 复合部件
| 函数 | 产出子部件 pid | 说明 |
|---|---|---|
| `chamber(pid, cx, cy, r, name)` | `{pid}_run/_alarm/_unload` | 圆形工艺腔 + 螺栓法兰圈 + 三色状态灯 |
| `signal_tower(pid, x, y)` | `{pid}_run/_alarm/_idle` | 三色塔灯 |
| `cassette(pid, x, y, w, h, slots=25)` | `{pid}_S1..S25` | 晶舟 25 槽片条 |
| `wafer(pid, cx, cy, r)` | — | 彩虹晶圆（渐变 + die 网格 + 径向阴影三层） |
| `port_box(pid, x, y, name)` | `{pid}_DOOR/_SLIT/_WINDOW` | Load Port 承载台 + 门板 + slit 阀 |
| `slit_valve(pid, x, y, w)` | — | 独立 slit 阀压条 |
| `robot_arm(pid, hub_x, hub_y)` | `{pid}_UPPER/_FORE/_WRIST` | 三段连杆机械臂（肩/肘/腕，供 IK 使用） |
| `bolt_circle(cx, cy, r, n)` | — | 法兰螺栓圈 |
| `baseplate(pid, ...)` / `title_block(pid, ...)` | — | 底板 / 图签 |

---

## 六、Motion JSON 构建器（motion.py）

线上真实格式（对照 `oxe-drm-topview.motion.json` 实测）：

```json
{
  "schema_version": "1.1",
  "document": {"name","src","coord"},
  "motions": [
    {"step":"POD_PLACED","enabled":true,"when":"true","rules":[
      {"phase":1,"target_part_id":"{POD}","when":"params.pod_shell == '1'",
       "actions":[{"type":"snap","to_part_id":"{home}","duration":0,"visible":true}]}
    ]}
  ],
  "ext": {"machine_type","version","description","deriver",
          "param_defaults","event_aliases","part_aliases","viewBox_fallback"}
}
```

**动作类型共 6 种**（线上实际用到的全部）：`snap` / `visibility` / `offset` / `opacity` / `text` / `rotate`

```python
from models.svg_kit import motion as M

b = M.MotionBuilder(machine_type="NEW-ETCH", name="NEW-ETCH 2D Motion",
                    src="new-etch-topview.svg", deriver="newetch")
b.param_defaults(PORT="1", SLOT="1", STATE="idle")
b.add("DOOR_OPEN", [
    M.rule("PORT1_DOOR", [M.offset(x=86, duration=400)], when="params.PORT == '1'", phase=1),
])
json.dump(b.build(), f, ensure_ascii=False, indent=2)
```

---

## 七、维护约定

- **色值/线宽/尺寸一律走 `tokens.json`**，不要在机型脚本里硬编码颜色
- 新增通用部件时，同时补 `primitives.py` 与本文件的部件清单表
- 改完任何 SVG 或 Motion JSON，跑一次 `validate.py` 再提交
- `tokens.json` 是 Python / JS / HTML 编辑器共用的唯一真源，改色板只改这一处
- `models/user/*.svg` 与 `backend/uploads/models/` 的运行时副本必须同步；提交前复核哈希
- 动画开发只在「模型编辑器 → 动画调试」进行，机台详情仅用于最终演示

---

## 八、机型参考图与下一轮接续

参考原图已随仓库保存，不依赖聊天附件：

- [LAM2300](assets/machine-references/LAM2300.jpg)
- [SPT](assets/machine-references/SPT.jpg)
- [Centris Sym3 Etch Chamber Manual](assets/machine-references/Centris-Sym3-Etch-Chamber-Manual.jpg)

### 推荐开发顺序

1. **先回收 PODOPENER 通用件**：把 POD 外壳、载台、钣金机架、精密导轨、观察窗、控制盒整理为 `primitives.py` 参数化函数；动画 ID 由调用方传入，不在公共函数里绑定机型事件。
2. **再拆参考图**：分别记录 LAM2300/SPT/Sym3 的腔体、传输区、Load Port、机械臂和专属外形，能复用的只传布局与尺寸参数，确属机型专属的结构才单独绘制。
3. **新增布局模板**：优先扩展 `scaffold.py` 或增加机型布局脚本，不另建一套与 `svg_kit` 不兼容的库。
4. **最后接 Motion/Deriver**：沿用 Motion JSON v1.1 和现有 deriver 注册机制；在动画调试页逐步验收，不在机台详情新增调试入口。
5. **每次交付前**：跑 SVG × Motion 校验、前端构建和后端语法检查，并更新《变更更改版记录》。

> 新机型不是绝对零绘制：公共库负责基础部件、材质和通用结构；机型仍保留布局、通道、少量专属外观及动作调教。
