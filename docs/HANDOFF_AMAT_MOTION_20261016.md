# AMAT METSPUT 动画开发交接包（2026-10-16 下班版）

> **用途**：回家（或换机器）`git pull` 后照本文档 10 分钟恢复上下文，直接从「ARM_2 正式 SVG」断点继续。
>
> **分支**：`test3`（2026-10-15 起所有开发在 test3，勿再用 test1）
>
> **远程**：https://github.com/leanerone/fab-twin-pro.git

---

## 0. 一句话状态

**2026-10-18 全部闭环**：①三处 `amat_metsput.svg` MD5 全同并加备份；②机台详情页晶圆送腔心 23px 偏差已修（`useMotionPlayback.js measureSvg` 归一 viewBox user 坐标系），E/CH_1 双轮连播 0px；③编辑器调试台臂杆 ARM1_Link 不联动已修（`MotionPreview.vue` 补 pickup_link/drop_link + link_ext/ret 4 参数），trace 实测 scale(1,2.14)/scale(1,3.30) 联动、两路径晶圆居中 0/0.76px。**AMAT METSPUT 接入主线全部闭环，无遗留断点。**

---

## 1. 换地方开发恢复环境（2026-10-18 更新）

```powershell
git fetch origin
git checkout test3
git pull origin test3
git log --oneline -8   # 顶部应有 fix(motion): 详情页腔心 23px 偏差 + 编辑器臂杆联动 的提交
```

四件服务（与以往相同）：

| 服务 | 端口 | 启动 |
|---|---|---|
| Oracle | 1521 | 本地库 `fabtwin/fabtwin@localhost:1521/orclpdb`（service_name） |
| backend | 8002 | `cd backend; python main.py` |
| frontend | 5173 | `cd frontend; npm run dev`（依赖未变，无需 npm install） |

**两个调试入口**：
- 机台详情页：`http://localhost:5173/#/machine/AMAT-T1` → 顶部「播放完整流程」
- 模型编辑器（动画调试台）：`http://localhost:5173/#/model-editor` → 顶部「🔍 动画调试」

**标准触发流程（每次整页重载后都必须完整走一遍，否则 CHAMBER_PS 拒绝执行）：**

1. combobox 选 `AMAT-METSPUT` → 点「初始化」
2. 确认参数 LOT_ID=N1234 / PORT=1 / SLOT=1 / CHAMBER=目标腔
3. **先点 `BATCH_INFO_FROM_ECUI`**（登记载具映射；映射只存在内存，刷新即失）
4. 再点 `CHAMBER_PS` 触发动画
5. 看「事件日志」与画面落点

**新地方首次同步**：如果 DB 是空的或旧的，跑一次：
```powershell
cd backend
python seed_amat_metsput.py        # 或 python ..\scripts\sync_amat_motion_to_db.py
```

坑（都踩过）：
- 改引擎 composables 后 Vite 会**整页 reload**，DOM/内存状态全丢，必须重走上面 4 步。
- CHAMBER_PS 日志出现「未找到载具映射」= 漏了第 3 步。
- **页面里有 3 个 svg 实例，只有 1 个可见**（宽 720px，`.svg-container` 下）。控制台取元素要用：
  ```js
  const s2 = [...document.querySelectorAll('svg')].filter(s => s.getBoundingClientRect().width > 0)[0];
  s2.querySelector('#ID')
  ```
  `document.getElementById` 会拿到隐藏副本（§4.9 ④）。
- **hidden-tab 渲染冻结**：`visibilityState=hidden` 时带 `transition: transform 900ms` 的写入不推进（§4.8 伪象），自动化测试时先把 tab 置前。
- 晶圆位置流转登记在 deriver 内存表（waferPosRegistry）：CHAMBER_PS 成功后晶圆登记到目标腔；想重测 cross_arm，先跑一次 `CHAMBER=A`（进 ARM_1 的 A 腔），再跑 `CHAMBER=1`（ARM_2 从 A 腔取片→PVD 1，触发 cross_arm）。刷新页面即重置。

---

## 2. 本次提交内容清单

**2026-10-18 本轮（最新提交）**：

| 文件 | 变更 | 说明 |
|---|---|---|
| `frontend/src/composables/useMotionPlayback.js` | +26/-8 | **详情页 23px 偏差引擎修复**：`measureSvg` 归一 viewBox(user) 坐标系（§4.9 ②） |
| `frontend/src/components/MotionPreview.vue` | +14 | **编辑器臂杆联动修复**：补 `armLinkPart` + `fillExtend` link 4 参数 + `pickup_link/drop_link`（§4.9 ③） |
| `frontend/src/components/MachineMotion2D.vue` | +8 | `debugPlayFlow` 开播前 `resetView()` 保证跨流程幂等；序列补 WPC SLOT2 |
| `backend/demo_amat_motion.py` | +2 | demo 序列补 `WAFER_PROCESS_COMPLETE SLOT=2` |
| `models/user/amat_metsput_v1.1.json` | +1/-1 | 角度表 `ARM_1.LLA` 190→198（夹手朝向） |
| `model-editor-standalone/src/assets/amat_metsput.svg.bak-20261018` | 新增 | SVG 备份 |
| `docs/HANDOFF_AMAT_MOTION_20261016.md` | +§4.8/§4.9 | 本文档 |

**2026-10-16/17 前轮（已在 test3）**：

| 文件 | 变更 | 说明 |
|---|---|---|
| `frontend/src/composables/useMotionPlayback.motion.js` | +25/-8 | **P1 落点 bug 引擎修复**：rotate 默认原点冻结（详见 §3） |
| `models/user/amat_metsput_v1.1.json` | +64 | 新增 `extend_geometry` 实测坐标；CHAMBER_PS p6/p7 增加 R 轴伸缩规则（offset `{ext_dx}/{ext_dy}` / `{ret_dx}/{ret_dy}`） |
| `frontend/src/motionDerivers/amatMetsput.js` | +41 | `computeExtendVec()`：按臂 pivot→腔心几何算出 θ 角与径向伸缩向量并注入模板参数 |
| `frontend/src/composables/useExprEval.motion.js` | +8 | offset 动作的字符串模板补丁（`{ext_dx}` 等模板能被求值） |
| `scripts/sync_amat_motion_to_db.py` | 新增 | 一键把 JSON 写入 Oracle `machine_model_configs.animation_config_json`（§5） |
| `model-editor-standalone/src/assets/amat_metsput.svg` | 同步 | 与源文件 MD5 一致 |
| `.gitignore` | +1 | 忽略 `model-editor-standalone/.vite/` |

更早、已在 test3 上的三个提交（仅背景，不用动）：
`7a179e1` 阶段1晶圆彩虹质感 → `406dfc7` 阶段2腔室金属化 → `6405cb8` 阶段3光影装饰收尾 → `5fb1fd8` 伸缩臂杆实体化 → `01ed11d` 锚圆锁定臂组旋转中心 + 阶段4金属化。

---

## 3. P1 落点 bug 档案（已修复，留档防回归）

### 3.1 现象
ARM_1 放片结束后，晶圆相对目标腔中心确定性偏差约 **(+20, -5)px**（合 20.6px），每条路径都复现。

### 3.2 根因（定量定案）
引擎 rotate 动作默认原点用 CSS `transform-box: fill-box; transform-origin: center`，
**旋转原点 = 元素实时 bbox 中心**。p6 阶段 chuck（Wafer_Chuck1）沿 R 轴伸出时，父组 ARM_1 的 bbox 被撑大、bbox 中心随子部件位置漂移；于是 ARM_1 的旋转绕着一个「移动的原点」发生，径向轨迹被污染。

证据链：
- MutationObserver 时间线证明引擎 follow 逻辑全程正确（wafer 每帧被精确对齐 chuck 实时中心）——问题在 chuck 自身渲染轨迹。
- 浏览器实测：chuck 伸出后 ARM_1 的 bbox 原点漂移 (0, -39.27) ≡ **T/2**（T=(-4.16,-78.54) 为伸缩量）。
- 理论误差 `(I − R(θ))·T/2 ≈ 20.3px`，与实测 20.6px 吻合。

### 3.3 修复手法（引擎最小改动，4 处）
rotate 默认 center pivot 时，把原点**冻结为动作应用那一刻的 bbox 中心**，改用
`transform-box: view-box` + 绝对 px origin（不再随 bbox 漂移）；无 viewBox 的 svg 退化为 (0,0) 基准。

- 新增 helper `getFrozenCenterOrigin(el)`
- `applyPreviewTransform`：transformBox 取 `state.originBox || 'fill-box'`
- `applyPreviewAction` rotate 分支：useCenter 时冻结原点写 `state.origin/originBox`
- `ensurePreviewState` / `readPreviewStateFromEl`：贯穿 `originBox` 字段（连播 reset=false 种子路径也要带）

修复后 ARM_1 实际 style：
`transform-box: view-box; transform-origin: 363.58px 506.365px; transform: rotate(330deg)`。

### 3.4 浏览器验证结果（2026-10-16）

| 路径 | 机械臂 | θ / ext | 落点偏差（wafer−腔心） |
|---|---|---|---|
| CHAMBER=**A**（LLB 载具→A 腔） | ARM_1 | θ=330, ext=(-4.16, 78.54) | **(0, 0)** ✅ |
| CHAMBER=**E**（LLA→E 腔） | ARM_1 | θ=225, ext=(3.19, 141.02) | **(0, 0)** ✅ |
| CHAMBER=**1**（A 腔→PVD 1，**cross_arm 交接 ARM_2**，phase 3/4 首次触发） | ARM_1→ARM_2 | ARM_1 Cross=0 / ARM_2 Cross=180→250 | **(-0.7, -2)px** ✅（≈精确命中，取整误差级） |

遗留小点（不阻塞）：显式 pivot 路径（action.pivot 非 0）仍是 fill-box + px origin，理论上有同类漂移隐患；本模型未使用显式 pivot，本次按最小改动未动。以后有机型用到再统一。

---

## 4. 断点：ARM_2 / ARM_1 正式 SVG 重画（回家从这里干）

### 4.1 硬红线（违反必坏动画，来自历次教训）

1. **动画引用的元素 id 一个都不能改、不能删**。
2. 不能用空 translate 覆盖元素，否则会清掉 SVG 原生静态 `transform` 属性导致整体偏移；动态/静态变换必须 matrix 合并。
3. 组件不要做全深色主题（深色部件压深背景，看不清）。
4. 每次改完 **SVG 三副本必须同步**：
   - `models/user/amat_metsput.svg`（源文件，入库）
   - `backend/uploads/models/amat_metsput.svg`（运行时上传目录，**gitignore 不入库**，手工拷贝）
   - `model-editor-standalone/src/assets/amat_metsput.svg`（入库；本次已追到阶段3，以后别再漏）

### 4.2 ARM_2 目标：蛙腿（frog-leg）菱形四连杆双臂

现状（源 SVG 中 `<g id="ARM_2">`，约 L256-272，按 id 定位勿认行号）：

| id | 现状 | 重画处置 |
|---|---|---|
| `ARM_2`（g） | 整组，transform=identity | **保留 id**，θ 旋转仍作用在整组 |
| `svg_36` | 中央 hub 圆（cx360 cy278 r28） | **保留 id**，A 驱动铰贴 hub |
| `Wafer_Chuck2` | 上叉吸附圆（359,213.5 r34.5） | **保留 id 与中心**，blade 桨叶化；它是动画 drop_part，R 轴全量 offset 作用对象 |
| `svg_38` | 下叉圆（360.5,341.5 r33.5） | **保留 id**（双臂下层，180° 背向）；本期是否做伸缩动画见下方决策点 |
| `svg_39/40/41` | 旧装饰连杠 path | 可删/可替换（不在动画引用里），删前全局 grep 确认 |
| `g.arm-deco` | 金属装饰（pointer-events=none） | 随新结构重画即可 |

几何蓝本（PureShowWidget 概念图 `arm2_frogleg_diamond_v4` 的参数，已与用户确认）：
- 菱形四连杆：A=驱动铰（贴 hub）、B/C=肘铰、D=末端铰（固连 Blade）；L1=L2，
  缩回=真菱形（α≈35°），伸出=压扁近平行杆（α≈8°）；概念图 L=34、hub(184,205)，
  正式 SVG 按 720x900 画布等比放大到当前 hub(360,278)、上叉心(359,213.5) 的实际尺度。
- 运动学约束：Y(D)≡0 纯径向伸缩、晶圆不自转；双臂上下两层 Z 向错开、180° 背向、共 hub。

动画方案（引擎零改动，沿用已验证机制）：
- **θ 轴**：整条 `ARM_2` 组 rotate（现有 phase 3/5 规则不动）。
- **R 轴**：blade 组做全量 offset，两个肘铰组各做半量 offset（菱形中点速度=末端一半）。
- JSON 新增模板参数 `{ext_hx}/{ext_hy}`（半量 = ext 向量/2），注入两处：
  - `frontend/src/motionDerivers/amatMetsput.js` 的 `computeExtendVec()` 返回值里加 hx/hy；
  - `frontend/src/components/MotionPreview.vue` CHAMBER_PS 注入点（约 L350-360，参照现有 ext_dx 注入写法）。
  - 新增的肘铰 `<g>` 需要**新 id**（例如 `svg_arm2_up_elb`/`elw`，命名后全局保持一致），并在 CHAMBER_PS p6/p7 各加 2 条 offset 规则（半量、反向半量）。
- **开工前决策点（先跟用户确认再画下层）**：本期下层叉 `svg_38` 只做静态视觉跟随，还是也配一套半量连杆动画（当前 JSON 的 drop_part 只有 Wafer_Chuck2 一个吸附点）。

### 4.3 ARM_1（ARM_2 验证通过后再做）
目标 = JEL 式单臂两段伸缩结构。保留 id：`ARM_1`、`Wafer_Chuck1`（现中心 364.36,463.6）、
`svg_48`（底座）、`svg_51/52/53`（若删除先 grep 确认无动画引用）。
动画机制与 ARM_2 R 轴同一套（全量/半量 offset），引擎不需要再改。

### 4.4 每阶段完成标准
1. 三副本同步；2. 模型调试页按 §3.4 三路径复测落点；3. 机台详情页回放复测（历史曾出过回放矩阵覆盖静态 transform 的问题，现已修，留意回归）；4. 再提交。

### 4.5 完成记录（2026-10-17）

**实施方案（与 §4.2/4.3 原计划的偏差说明）**：最终采用「视觉升级、动画零改动」路线——新结构全部落在原 `ARM_1`/`ARM_2` 组内，动画引用的 9 个 id 原样保留，新增细节（轮毂塔法兰/螺栓、blade 吸附环/真空孔阵列、关节罩、基座塔内环等）放在 `g.arm-deco[pointer-events=none]` 内静态跟随旋转组。§4.2 规划的「肘铰半量 offset + 新 id + JSON 加规则」未实施，作为可选增强留待后续（当前 R 轴全量 offset 只作用 blade，视觉已可接受）。

**新增关键约束（从代码挖掘，比本文档先前记录更细）**：
- 动画引擎 `transform-origin` 恒为 `fill-box center`（useMotionPlayback.js）→ **SVG 组的渲染包围盒中心必须 == extend_geometry 中的 pivot 坐标**，差 1px 旋转就会甩尾。
- CSS 渐变/滤镜引用 id `svg_36/38/39/48/51` 必须保留。
- 运行时通过 bbox 中心校验：ARM_2 (360.02,277.00)、ARM_1 (363.58,506.36)、Wafer_Chuck1 (364.36,463.60)、Wafer_Chuck2 (359.00,213.50)。

**验证结果（浏览器动画调试页，标准触发流程）**：
| 检查项 | 结果 |
|---|---|
| DOM 中 13 个关键 id | 全部存在，ARM_2 含 7 子元素 / ARM_1 含 6 子元素 |
| 可见副本 bbox 中心 | ARM_2=(360.00,277.00) Δ0.02；ARM_1=(363.58,506.36) Δ0.00，均 == pivot |
| CHAMBER=A | ARM_1 旋转 matrix == 330° 精确，零平移分量 |
| CHAMBER=E | ARM_1 == 225° 精确 |
| CHAMBER=A（回程） | ARM_1 == 330° 精确 |
| CHAMBER=1（cross_arm） | ARM_1==0°（Cross 位）+ ARM_2==250°（腔1），双臂交接正常 |
| 三副本同步 | user/uploads/model-editor 三份均 56379 bytes |

**遗留观察项**：调试页 DOM 中有 3-4 个 svg 实例，只有 1 个可见，`document.getElementById` 可能命中隐藏副本导致 getBBox 全 0；校验时用 `querySelectorAll` 过滤可见副本（§1 坑清单已记录取法）。

### 4.6 伸缩臂杆 + 晶圆骑盘修复（2026-10-17，本轮提交）

**用户反馈**：①画面看不到实体机械手臂；②晶圆不在吸附盘上、空中飞。

**根因（重要教训）**：`/api/models/{model_id}` 的动画配置**从 Oracle `MACHINE_MODEL_CONFIGS.animation_config_json` 直读，不读文件**。此前只改了 JSON 文件没写库，页面跑的仍是旧配置——改 JSON 后必须按 §5 同步 DB 才生效（SVG 相反，拷文件即生效）。

**修复内容**：
- SVG 三副本：`ARM1_Link`/`ARM2_Link` 伸缩杆 rect（桁架杆，物理连接轮毂与 chuck）。
- 引擎双链路（useMotionPlayback.js / .motion.js + 两侧 useExprEval）：新增 scaleY/scale_y 模板通道。
- deriver amatMetsput.js：`computeExtendVec` 输出 `link_sy=(lbase+e)/lbase`、`link_oy=e/2`，`fillExtendParams` 注入 `link_ext_sy/oy`、`link_ret_sy/oy`。
- JSON：`ext.extend_geometry.arms[].link_lbase`（ARM_1=61.4）+ CHAMBER_PS 8 条平行杆规则。

**浏览器实证**：杆 transform 实测 `scale(1, 2.15~3.30)` 随目标腔几何变化；晶圆中心与 chuck 中心距离轮询 d=0（LLA1 去程/回程、LLA2 回程均精确骑盘）。证据图：`N:\AI\amat_arm2_extend_evidence.png`、`N:\AI\amat_wafer_ride_evidence.png`（本机，未入库）。

### 4.7 锚圆锁定旋转中心 + 整体金属化（2026-10-18，本轮提交）

**用户反馈**：①杆伸出时组旋转中心偏移；②要求整体 SVG 金属化；③全流程回归测试。

**锚圆方案（旋转中心修复）**：引擎 `transform-origin` 恒为 `fill-box center`，而 ARM 组 fill-box = 子元素几何并集——杆 scale 伸出 / chuck offset 伸出会改变组 bbox，导致旋转中心漂移（实测 12.4px）。修复 = 在 `ARM_1`/`ARM_2` 组内各加一个 **r=240、圆心=pivot** 的锚圆（`ARM1_Anchor`/`ARM2_Anchor`），把组 bbox 撑成恒定大圆，伸缩/旋转全程 pivot 不变。

**锚圆关键坑（务必遵守）**：引擎 `resetMotionState()`（useMotionPlayback.js L377-391）复位时对容器内**所有带 id 元素** `removeAttribute('visibility')`——只写 `visibility="hidden"` 会被剥掉，锚圆渲染成 r=240 黑色巨圆盖住机台。正确写法三件套：
```xml
<circle ... visibility="hidden" data-motion-base-visibility="hidden" fill="none" pointer-events="none"/>
```
`data-motion-base-visibility="hidden"` 让引擎复位后恢复隐藏（L394-400）；`fill="none"` 双保险（getBBox/fill-box 与 fill 无关，几何照常参与计算；即使 visibility 再失效也不渲染）。

**整体金属化（阶段4，纯 SVG 内 `<defs><style>` CSS 覆盖，引擎零改动）**：LLA/LLB 装载锁→chSteel + 描边；腔室底座椭圆（svg_11/17/23/29）→pedestalMetal（径向）；8 阀盖→valveMetal；SMIF 顶/底面板→panelMetal（深色阳极氧化）；SMIF 前窗→glassDark；BOARD→boardMetal；CASSETTE→cassetteMetal。至此晶圆/腔室/臂/SMIF/转盘/装载锁/阀盖/底座全部金属渐变，无扁平色块。

**验证结果（机台页 `#/machine/AMAT-T1` 实测）**：
| 检查项 | 结果 |
|---|---|
| 锚圆 hidden 持久化 | 复位后 computed visibility=hidden、fill=none，无黑圆回归 |
| ARM_2 杆伸出组中心 | retracted/extended/restored 均 (360,277)，drift=[0,0] |
| 阶段4 全部 CSS | LLA→chSteel、底座→pedestalMetal、阀盖→valveMetal、SMIF→panelMetal/glassDark、BOARD→boardMetal、CASSETTE→cassetteMetal 全部生效 |
| 全流程 7 事件回归 | 采样 334 tick/100s：双臂漂移 0px、无晶圆飞行、LLA1 精确归位、杆/chuck 结束态全 identity |

**遗留**：`svg_1` 外框 rect 内曾混入乱码文本（不渲染，本轮已清理）；LLA2 归位差 310.7 为 demo 序列设计（SLOT2 无 COMPLETE 事件），非缺陷。

### 4.8 腔心送达回归 + "页面不同步"三层根因实锤（2026-10-18）

**用户反馈**：①动画调试台 SVG 与机台详情不同步；②晶圆送不到 chamber 中心；③run 完送回 CASSETTE 夹手歪。

**修复**：`amat_metsput_v1.1.json` 角度表 `ARM_1.LLA` 190→**198**（夹手朝向修正）；跨流程运行时残留前轮已修（debugPlayFlow 开播前 resetView + 流程补 WPC SLOT2 snap）。

**"改了没生效"根因实锤（不是 HTTP 缓存）**：API 响应无 Cache-Control/ETag/Last-Modified（8002 直连与 5173 代理均验）、无 Service Worker、页面内 default/no-store 两种 fetch 均返回新值——三重证据排除缓存。真因 = **页面生命周期陈旧**：长寿命 tab 在 seed/改文件前已加载，hash 路由 SPA 下同 URL `browser_navigate` = 无操作，组件不重挂载（`loadAssets` 仅挂载时拉一次）。修复 = `location.reload()` 真刷新。

**回归（reload 后连播两遍 + 150ms 中心采样，1812 样本）**：
| 检查项 | 结果 |
|---|---|
| LLA=198 生效 | 两遍首条 ARM_1 写入均 `rotate(198deg)` |
| 跨流程幂等 | 两遍旋转序列逐条一致（198→225→198→0(Cross)→…→198） |
| 晶圆送腔心 | LLA1 驻留 E=(230.82,633.5) 3s；LLA2 驻留 CH_1=(179,340) 3s（均精确） |
| 归位 | 两片终点均 home=(326.75,613.25)；骑叉中间位与几何推算全吻合 |
| 落腔写入数值 | LLA1 (-95.94,20.25)、LLA2 (-147.73,-273.23)，精确指向腔心 |

**自动化测试伪象（勿误判为 bug）**：hidden tab（`visibilityState=hidden`）下 Chrome 冻结渲染时钟——**带 `transition: transform 900ms` 的 transform 写入完全不推进**（探针实锤：写 translate(80,0) 后 1s 采样仍在起始值），`transition: none` 的写入（轨道逐帧、duration:0 snap）立即生效。故自动化采样中"落腔/伸缩不体现、snap 体现"是环境伪象；真实可见浏览器 transition 正常。`browser_tabs activate` 不能解除（窗口本身不可见）。

**调试台 SVG 不可能与主舞台漂移**：`MachineMotion2D.vue` L363 全组件仅一处 `v-html="svgMarkup"`，调试面板与主舞台共用同一实例；源头 = DB 快照 `view_2d.model_source` → `/uploads/models/amat_metsput.svg`，fetch `no-store`。

**"为什么总是不同步"三层论（给用户的最终解释）**：
1. **文件 → DB 快照**：`models/user/*.json|svg` 改动必须跑同步脚本（`scripts/sync_amat_motion_to_db.py` 或 `backend/seed_amat_metsput.py`，均幂等），否则 DB 快照漂移；
2. **页面生命周期**：已打开的页面不会随 DB/文件更新自动刷新（本轮 198 即此因）——改完须刷新页面；
3. **运行时状态残留**：deriver 登记表/状态缓存跨流程残留（前轮已修，本轮回归验证幂等 ✓）。

### 4.9 详情页腔心 23px 偏差根因 + 编辑器臂杆不联动根因（2026-10-18 下班版）

**用户反馈**：模型编辑器/机台详情/standalone 三处 SVG 一致前提下，机台详情晶圆送不到 chamber 中心，且与动画调试台行为不一致。

**① 三处 SVG 同步实锤（用户任务1）**
- 三处 `amat_metsput.svg` MD5 全同 `B54EF4A90AD79F8862EDC1F6EAC297FC`：
  - `models/user/amat_metsput.svg`（源）
  - `backend/uploads/models/amat_metsput.svg`（DB 快照运行时拉这份）
  - `model-editor-standalone/src/assets/amat_metsput.svg`
- 备份：`model-editor-standalone/src/assets/amat_metsput.svg.bak-20261018`

**② 机台详情腔心偏差 23px 根因（用户任务2 修复）**
- **根因**：`useMotionPlayback.js` 旧 `measureSvg` 用 `el.getCTM()`，含 viewBox→viewport 的渲染缩放 s≈1.197。deriver 注入的位移（ext_dx/dy）是 viewBox user 单位；`applyState` 用含 1/s 的 inv 换算时把位移二次缩放，导致 chuck 少伸 ~16%、晶圆偏离腔心 ~23px。
- **修复**：`measureSvg` 归一到 **viewBox(user) 坐标系**——用 `M = svg.getScreenCTM().inverse()`（screen→user）把元素/父链 CTM 归一；`getScreenCTM` 不可用时回退 `getCTM`。
- **代码**：`useMotionPlayback.js` L74-125 `measureSvg`、`userCtmOf`。
- **回归**：详情页 `#/machine/AMAT-T1` 两轮连播，E 腔/CH_1 均 0px 误差，晶圆精确送达腔心。

**③ 编辑器调试台臂杆不联动根因（用户任务3 修复）**
- **现象**：`#/model-editor` 动画调试 Tab 下，CHAMBER_PS 时 chuck 已伸出但 `ARM1_Link`（伸缩臂杆）纹丝不动；日志 `target` 字面显示 `{drop_link}`。
- **根因**：JSON `CHAMBER_PS`/`WAFER_PROCESS_COMPLETE` 规则含 target `{pickup_link}`/`{drop_link}`（各 4 处）和 `offset_x:0, offset_y:"{pk_link_ext_oy}", scale_y:"{pk_link_ext_sy}"` 系参数；但 `MotionPreview.vue` 旧版**从不填** `pickup_link`/`drop_link` 目标 id 和 `link_ext_sy/oy`、`link_ret_sy/oy` 这 4 个参数。模板原样输出→`target` 字面 `"{drop_link}"`→找不到元素→臂杆不动。
- **修复**（`MotionPreview.vue` 4 处）：
  - L101-104 新增 `armLinkPart(armId)` → `ARM{n}_Link`
  - L264-272 `fillExtend` 末尾追加 `link_ext_sy/link_ext_oy/link_ret_sy/link_ret_oy`（公式与 deriver `fillExtendParams` 完全对齐：`link_sy=(lbase+e)/lbase`，`link_ext_oy=+e/2`，`link_ret_sy=1`，`link_ret_oy=-e/2`）
  - L332-333 CHAMBER_PS 块填 `params.pickup_link = armLinkPart(fromArm)`、`params.drop_link = armLinkPart(toArm)`
  - L429-430 WAFER_PROCESS_COMPLETE 块同填
- **引擎侧已支持 `scale_y`**：`useMotionPlayback.motion.js` `applyPreviewAction` L493-498 收到 `scale_y` 即 `state.scale = scale(x,y); origin='center'; originBox='fill-box'`；`applyPreviewTransform` L215-217 输出 scale。所以编辑器只需填参数即可，无需改引擎。
- **回归（修复后 trace）**：
  - pickup 侧 chuck translate(1.22,-70.28)、link translate(0,-35.15) scale(1,2.1448)（e≈70.3）
  - drop 侧 chuck translate(3.19,-141.02)、link translate(0,-70.53) scale(1,3.2973)（e=141.02）
  - 臂杆已联动伸缩，日志 target 全部解析为 `ARM1_Link`
  - 两条路径晶圆居中：CH_E dist 0、CH_1 dist 0.76px

**④ 调试陷阱（勿再踩）**
- **页面上有 3 份 SVG 副本**（`svgCount:3`）：idx0=模型列表面板（隐藏 w=0）、idx1=record-svg-section（隐藏）、**idx2=动画调试预览（可见 720×900，`.svg-container < .svg-area < preview-body < motion-preview < debug-panel`）**。`document.getElementById('ARM_1')` 返回**文档序第一个=隐藏副本**——上一会话"零位移"全部探针都打在了隐藏副本上。
- **正确探针**：先按可见性过滤再 querySelector：
  ```js
  const s2 = [...document.querySelectorAll('svg')].filter(s=>{const r=s.getBoundingClientRect(); return r.width>0})[0];
  s2.querySelector('#ARM_1')
  ```
- **hidden-tab 渲染冻结**（§4.8 已记）：`visibilityState=hidden` 时带 `transition: transform 900ms` 的写入不推进，`transition: none` 的写入立即生效。自动化采样时若怀疑"动画不动"，先看 `document.visibilityState` 和 `el.getAnimations().playState`。
- **浏览器 MCP 工具链变更**：旧 `mcp_trae-remote-official_browser_browser` 已下线；现用 browseruse skill + `integrated_code_mode.Exec`。Exec 顶层禁止 `return`（用 `text(value)` 输出）；`browser_snapshot` 等返回 `{content:[{text}]}`，须先取 `.content[0].text` 再做字符串处理；`browser_evaluate` 的 script 禁止 IIFE、用顶层 `return`。

**⑤ 本轮 demo 序列补全**
- `backend/demo_amat_motion.py` 序列补 `WAFER_PROCESS_COMPLETE SLOT=2`（跨臂回 LLA），避免 SLOT2 晶圆位置残留污染下一轮。
- `frontend/src/components/MachineMotion2D.vue` `debugPlayFlow` 开播前 `resetView()` + 跳过历史事件，保证跨流程幂等。

---

## 5. DB 导入资料（量产/本地库都要用）

**要入库的东西只有一个**：`models/user/amat_metsput_v1.1.json` 的完整内容 →
表 `MACHINE_MODEL_CONFIGS` 的 `ANIMATION_CONFIG_JSON` 列（CLOB/Text）。
表定义见 `backend/models.py` 的 `MachineModelConfig`（主键 `model_id`，另有 `version`、`updated_at`）。
SVG 不入库，走文件/上传 API。

### 路径 A：脚本一键同步（推荐，本地库）

```powershell
cd backend
python ..\scripts\sync_amat_motion_to_db.py
```

脚本逻辑：复用 `backend/database.py` 的 engine → LIKE '%METSPUT%' 找记录（多条取 version 最大）
→ 用文件内容整体 UPDATE → 打印新 CLOB 长度。找不到记录会终止，不会乱插。
注意脚本依赖 backend 的 Oracle 连接配置（service_name=orclpdb）。

### 路径 B：手工 SQL（用户偏好；量产库或没 Python 环境时）

```sql
-- ① 确认目标记录（model_id 以查询结果为准，可能是 AMAT-METSPUT）
SELECT model_id, model_name, version, LENGTH(animation_config_json) AS len
FROM machine_model_configs
WHERE UPPER(model_id) LIKE '%METSPUT%' OR UPPER(model_name) LIKE '%METSPUT%';

-- ② 更新前备份：把查出来的整段 JSON 粘存为文件（如 amat_metsput_v1.0.backup.json）
SELECT animation_config_json FROM machine_model_configs WHERE model_id = 'AMAT-METSPUT';

-- ③ 更新（SQL Developer 里用绑定变量 :cfg，把 amat_metsput_v1.1.json 全文粘进去）
UPDATE machine_model_configs
SET animation_config_json = :cfg,
    version = '1.1',
    updated_at = SYSTIMESTAMP
WHERE model_id = 'AMAT-METSPUT';
COMMIT;

-- ④ 回滚：对 :cfg 绑定第②步备份的旧 JSON，重复一次 UPDATE + COMMIT 即可
```

校验：更新后 len 应与本地文件字节数同量级；前端模型编辑器重新选机型初始化，
事件日志应出现「R轴伸缩: ARM_1 CH_x θ=… ext=(…)」即新配置生效。

### SVG 部署
- 量产/本地后端：拷贝 `models/user/amat_metsput.svg` → `backend/uploads/models/amat_metsput.svg`
  （或走后台模型管理的上传 API，等价）。
- standalone 模型编辑器：更新 `model-editor-standalone/src/assets/amat_metsput.svg` 后随其构建发布。
- 前端无需为 SVG/JSON 改动重新 npm build（运行时加载）；只有改了 `frontend/src` 才需要发布前端。

---

## 6. 关键代码地图

| 文件 | 看什么 |
|---|---|
| `frontend/src/composables/useMotionPlayback.js` | **详情页**引擎入口。本次修复重点：`measureSvg` L74-125（viewBox user 归一）、`userCtmOf` |
| `frontend/src/composables/useMotionPlayback.motion.js` | **编辑器**Motion2D 引擎。重点函数：`applyPreviewAction`（rotate/offset/scale_y/snap 分派）、`applyPreviewTransform`、`getFrozenCenterOrigin`、`syncFollowerToSnap`、`animateFollowersWithLeader`（rAF）、`measureElementMoveAfterTransform`、`frozenOrigins` |
| `frontend/src/motionDerivers/amatMetsput.js` | AMAT 专用 deriver：载具/晶圆位置登记、from/to arm 判定、cross_arm 与 Cross 角、`computeExtendVec()`、`fillExtendParams`（link_ext_sy/oy 等 4 参数填法样板）、commit/reset |
| `frontend/src/components/MotionPreview.vue` | CHAMBER_PS / WPC 模板参数注入点（搜「L轴伸缩」「armLinkPart」「fillExtend」） |
| `frontend/src/components/MachineMotion2D.vue` | 详情页调试 Tab，`debugPlayFlow` 完整流程编排、`resetView` 跨流程复位 |
| `frontend/src/composables/useExprEval.motion.js` | `when` 条件与 `{模板}` 求值；offset 字符串模板补丁在此 |
| `models/user/amat_metsput_v1.1.json` | 角度表 `arm_chamber_angles`、parts、CHAMBER_PS 12 条 phase 规则、`extend_geometry` 实测坐标 |

腔室→机械臂映射（角度表原文）：
- ARM_1：A330 / B30 / C265 / D95 / E225 / F135 / LLA198 / LLB160 / Cross0
- ARM_2：1=250 / 2=290 / 3=70 / 4=110 / A210 / B140 / Cross180
- cross_arm 条件：from_arm ≠ to_arm（例如晶圆先送 A（ARM_1），再送 1（ARM_2））。

---

## 7. 后续推荐执行顺序（2026-10-17 更新：ARM SVG 断点已闭环）

1. ~~画 ARM_2 / ARM_1 正式 SVG~~ ✅ 已完成（§4.5）。
2. **M2 — AMAT-T1 RV 事件数据**：本地库造 AMAT-T1 的实时事件流（参照 `backend/seed_oxe_test_data.py` 的 OXE-01 模式），让机台详情页「实时模式」也能看 AMAT 动画回放。
3. **M3 — 量产导入 SOP 沉淀**：把 §5 扩成正式 SOP（含三副本同步、bbox 中心校验、三路径复测检查单）。
4. **M4 — 机型库扩展流水线**：以 AMAT-METSPUT 为模板，固化「SVG 绘制约束 → 动画 JSON → deriver → 调试页验证」的新机型接入流程。
5. 量产库按 §5 路径 B 导入 JSON、拷贝 SVG（随下次上线）。
6. 可选增强：ARM_2 肘铰半量 offset 动画（§4.5 偏差说明）、下层叉 `svg_38` 吸附点动画。
