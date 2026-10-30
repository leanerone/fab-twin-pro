# SVG 公共库（svg-kit）编写指南

> 建立日期：2026-10-29　|　版本：1.2
> 目标：**后续新建机型的 SVG 有公共库可以编写**，不再从零手绘、不再踩重复的坑。
> 当前边界：俯视与等角公共部件已可用于新机型；LAM2300、Centris Sym3、TEL Synapse 已完成布局模板，存量 PODOPENER 外观仍按原资产保留。

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

### 第 4 步：编辑器校验、上传与调试

SVG 同步到 `backend/uploads/models/`。在模型编辑器的「动画配置」Tab 点击「校验」，
前端会把当前内存中的 SVG 与 Motion 草稿提交到 `POST /api/uploads/models/validate-draft`；
结果面板分别列出 errors 与 warnings，保存前会再次校验，存在 errors 或校验请求失败时阻止保存。

随后在「动画调试」Tab 点选部件、单步触发事件验证；部件清单与 SVG 支持双向高亮，
`ext.part_aliases` 的静态别名也会解析到实际部件。动画调试不放到机台详情页。

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

### 俯视 cluster 与等角部件
| 函数 | 产出子部件 pid | 说明 |
|---|---|---|
| `top_process_chamber(pid, cx, cy, w, h, angle, name)` | `{pid}_run/_alarm/_unload` | 带正面 slit 的俯视工艺腔，`angle` 用于朝向传输区 |
| `top_airlock(pid, cx, cy, w, h, angle, name)` | `{pid}_DOOR` | 双门真空 Airlock |
| `vacuum_channel(pid, x1, y1, x2, y2, width)` | — | 封闭真空/大气通道；先画通道，再画腔体覆盖端部 |
| `aligner(pid, cx, cy, r)` | `ALIGNER_WAFER`（调用方约定） | 对准器及晶圆挂点 |
| `buffer_station(pid, cx, cy, r)` | — | Buffer 工位 |
| `control_rack(pid, x, y, w, h)` | — | 大气端控制柜 |
| `iso_box(pid, cx, cy, w, d, h, ...)` | — | 等角长方体；`cx/cy` 为底面中心，顶面中心为 `(cx, cy-h)` |
| `iso_cylinder(pid, cx, cy, rx, ry, h, ...)` | — | 等角圆柱；`cx/cy` 为底部椭圆中心 |
| `iso_process_chamber(pid, ...)` | `{pid}_run/_alarm/_unload` | 蓝色金属工艺腔、superellipse 圆角孔阵顶盖、铜色底座 |
| `iso_cabinet_chamber(pid, ...)` | `{pid}_run/_alarm/_unload` | 高柜控制/排气结构与圆形前腔 |
| `iso_load_port(pid, ...)` | `{pid}_DOOR` | 等角 Load Port 外壳与门 |
| `pump_module(pid, cx, cy, scale)` | — | 金色泵头与银色基座 |

等角金属色使用 `tokens.json` 的 `iso.*`；`defs()` 同时提供 `isoSilverBody`、`isoBlueBody`、
`isoCopperBody`、`isoGoldBody` 与 `isoShadow`。Sym3/Synapse 为保留既有 DB `document.src`，
文件名仍沿用 `*-topview.svg`，但实际图形为等角视图。

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
- `models/user/*.svg` 与 `backend/uploads/models/` 的运行时副本必须同步；提交前复核哈希。`backend/uploads/` 默认被忽略，新增规范运行时文件要逐文件 `git add -f`，不要强制添加整个上传目录
- 动画开发只在「模型编辑器 → 动画调试」进行，机台详情仅用于最终演示

---

## 八、机型参考图与下一轮接续

参考原图已随仓库保存，不依赖聊天附件：

- [LAM2300](assets/machine-references/LAM2300.jpg)
- [SPT](assets/machine-references/SPT.jpg)
- [Centris Sym3 Etch Chamber Manual](assets/machine-references/Centris-Sym3-Etch-Chamber-Manual.jpg)

### 三台参考图的实现分工

- `models/build_lam2300.py`：3×Load Port、Aligner、2×Buffer、Control Rack、双斜置 Airlock、中央 VTM 与 PM1~4；PM 正面朝向传输区，ATM→Airlock→VTM→PM 使用封闭通道。
- `models/build_sym3.py`：6×蓝色等角工艺腔、圆角矩形孔阵顶盖、铜色中央框板、银色 EFEM、3×金/银泵组。
- `models/build_synapse.py`：6×高柜式 PM、中央圆形 Transport Module、前侧 EFEM 与独立 UI 站。

三台共享 `cluster_motion.py` 的 26 步标准事件和现有 deriver，不另造事件名或部件 ID。
新增通用结构时回收到 `primitives.py`；机型脚本只维护布局、通道、专属外观与动作参数。
完整操作流程见《新机台建模SOP_v1》。
