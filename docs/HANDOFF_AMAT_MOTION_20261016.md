# AMAT METSPUT 动画开发交接包（2026-10-16 下班版）

> **用途**：回家（或换机器）`git pull` 后照本文档 10 分钟恢复上下文，直接从「ARM_2 正式 SVG」断点继续。
>
> **分支**：`test3`（2026-10-15 起所有开发在 test3，勿再用 test1）
>
> **远程**：https://github.com/leanerone/fab-twin-pro.git

---

## 0. 一句话状态

**P1 晶圆落点偏差 bug 已修复；ARM_2 蛙腿双臂 / ARM_1 JEL 单臂正式 SVG 重画已于 2026-10-17 完成并经浏览器三路径复测全部精确命中（见 §4.5）。2026-10-17 追加：伸缩臂杆实体化 + 晶圆骑盘修复并浏览器实证闭环（见 §4.6，根因=动画配置走 DB 不走文件）。AMAT METSPUT 接入主线全部闭环，无遗留断点。**

---

## 1. 回家后恢复环境

```powershell
git fetch origin
git checkout test3
git pull origin test3
git log --oneline -5   # 应能看到 fix(motion): P1 落点 bug 修复 的提交
```

四件服务（与以往相同）：

| 服务 | 端口 | 启动 |
|---|---|---|
| Oracle | 1521 | 本地库 `fabtwin/fabtwin@localhost:1521/orclpdb`（service_name） |
| backend | 8002 | `cd backend; python main.py` |
| frontend | 5173 | `cd frontend; npm run dev`（依赖未变，无需 npm install） |

动画调试页：浏览器开 `http://localhost:5173/#/model-editor` → 顶部「🔍 动画调试」。

**标准触发流程（每次整页重载后都必须完整走一遍，否则 CHAMBER_PS 拒绝执行）：**

1. combobox 选 `AMAT-METSPUT` → 点「初始化」
2. 确认参数 LOT_ID=N1234 / PORT=1 / SLOT=1 / CHAMBER=目标腔
3. **先点 `BATCH_INFO_FROM_ECUI`**（登记载具映射；映射只存在内存，刷新即失）
4. 再点 `CHAMBER_PS` 触发动画
5. 看「事件日志」与画面落点

坑（都踩过）：
- 改引擎 composables 后 Vite 会**整页 reload**，DOM/内存状态全丢，必须重走上面 4 步。
- CHAMBER_PS 日志出现「未找到载具映射」= 漏了第 3 步。
- 页面里有 **4 个 svg 实例**，只有 1 个可见（宽 720px）。控制台取元素要用
  `Array.from(document.querySelectorAll('#ID')).find(el => el.getBoundingClientRect().width > 0)`。
- 晶圆位置流转登记在 deriver 内存表（waferPosRegistry）：CHAMBER_PS 成功后晶圆登记到目标腔；想重测 cross_arm，先跑一次 `CHAMBER=A`（进 ARM_1 的 A 腔），再跑 `CHAMBER=1`（ARM_2 从 A 腔取片→PVD 1，触发 cross_arm）。刷新页面即重置。

---

## 2. 本次提交内容清单

| 文件 | 变更 | 说明 |
|---|---|---|
| `frontend/src/composables/useMotionPlayback.motion.js` | +25/-8 | **P1 落点 bug 引擎修复**：rotate 默认原点冻结（详见 §3） |
| `models/user/amat_metsput_v1.1.json` | +64 | 新增 `extend_geometry` 实测坐标；CHAMBER_PS p6/p7 增加 R 轴伸缩规则（offset `{ext_dx}/{ext_dy}` / `{ret_dx}/{ret_dy}`） |
| `frontend/src/motionDerivers/amatMetsput.js` | +41 | `computeExtendVec()`：按臂 pivot→腔心几何算出 θ 角与径向伸缩向量并注入模板参数 |
| `frontend/src/components/MotionPreview.vue` | +18 | CHAMBER_PS / WPC 两个注入点加「L轴伸缩」日志 |
| `frontend/src/composables/useExprEval.motion.js` | +8 | offset 动作的字符串模板补丁（`{ext_dx}` 等模板能被求值） |
| `scripts/sync_amat_motion_to_db.py` | 新增 | 一键把 JSON 写入 Oracle `machine_model_configs.animation_config_json`（§5） |
| `model-editor-standalone/src/assets/amat_metsput.svg` | 同步 | 此前停留在阶段0，本次补齐阶段1-3 全部美化（与源文件 MD5 一致） |
| `.gitignore` | +1 | 忽略 `model-editor-standalone/.vite/` |
| `docs/HANDOFF_AMAT_MOTION_20261016.md` | 新增 | 本文档 |

更早、已在 test3 上的三个提交（仅背景，不用动）：
`7a179e1` 阶段1晶圆彩虹质感 → `406dfc7` 阶段2腔室金属化 → `6405cb8` 阶段3光影装饰收尾。

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
| `frontend/src/composables/useMotionPlayback.motion.js` | Motion2D 引擎。重点函数：`applyPreviewAction`（rotate/offset/snap 分派）、`applyPreviewTransform`、`getFrozenCenterOrigin`（本次新增）、`syncFollowerToSnap`（follower 每帧绝对对齐 leader 中心）、`animateFollowersWithLeader`（rAF 循环）、`measureElementMoveAfterTransform`、`frozenOrigins`（播放前预冻结） |
| `frontend/src/motionDerivers/amatMetsput.js` | AMAT 专用 deriver：载具/晶圆位置登记、from/to arm 判定、cross_arm 与 Cross 角、`computeExtendVec()`、commit/reset |
| `frontend/src/components/MotionPreview.vue` | CHAMBER_PS / WPC 模板参数注入点（搜「L轴伸缩」） |
| `frontend/src/composables/useExprEval.motion.js` | `when` 条件与 `{模板}` 求值；offset 字符串模板补丁在此 |
| `models/user/amat_metsput_v1.1.json` | 角度表 `arm_chamber_angles`、parts、CHAMBER_PS 12 条 phase 规则、`extend_geometry` 实测坐标 |

腔室→机械臂映射（角度表原文）：
- ARM_1：A330 / B30 / C265 / D95 / E225 / F135 / LLA190 / LLB160 / Cross0
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
