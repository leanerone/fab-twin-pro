# 任务 2 工作计划：模型编辑器公共库开发 + 三张参考图新机台建模

> 负责人：ZCode（AI-A）｜ 分支：`feature/model-kit`（基线 `8a74590`）｜ 工作副本：`E:\AI\fab\fab-twin-pro`
> 任务 1（AI 链路）：另一 AI（AI-B）｜ 分支：`feature/ai-chain`（worktree：`C:\Users\Administrator\WorkBuddy\Worktrees\fab-twin-pro-main\test3-5f23dcb7`）
> 编写日期：2026-10-30（v2 修订：M2 改为「三张参考图 → 三个新机台建模」）｜ 总工时预估：**22~27 小时（约 3 个工作日）**

---

## 一、目标与验收口径

**目标**：
1. 把 `models/svg_kit` 从骨架收口为可支撑"看图建模"的公共库（validate 接入编辑器、primitives 补齐、tokens 收敛）
2. **以用户上传的三张机台参考图为蓝本，用公共库构建三个新机台的 motion2d 模型（SVG 资产 + Motion JSON + deriver）并端到端跑通**：
   - `LAM2300`（docs/assets/machine-references/LAM2300.jpg）：Lam 2300 平台俯视布局——ATM 大气端（3×Load Port + Aligner + 2×Buffer + Control Rack）+ 中央 VTM + PM1~4×4 腔 + 2×Airlock
   - `Centris Sym3`（Centris-Sym3-Etch-Chamber-Manual.jpg）：AMAT Centris Sym3——6×方形刻蚀腔（顶面螺栓阵列）+ 中央静电卡盘腔 + EFEM 柜体 + 3×气体泵模块，等角风格
   - `TEL Synapse`（SPT.jpg）：TEL 200mm fpD——Transport Module 居中 + 6×PM 环绕 + User Interface，等角线稿风格
3. 现有三机台（PODOPENER/OXE/AMAT）做 validate 基线跑分留档（不重画，作为公共库改造的回归对照）

**总验收口径（合版前必须全绿）**：
1. 三个新机台各自的 SVG×Motion 经 `python -m models.svg_kit.validate` **0 error**
2. 三个新机台 debug 注入全事件链端到端通过（注入→DB→轮询→WS→deriver→动画），零警告
3. 事件驱动**复用现有标准事件词表**（POD_PLACED/LOCK/MAPPING/WAFERLOADED/WAFERUNLOADED/PE/ALARM…，即 OXE 27 步同款）+ 新写一个 `generic_cluster` 泛型 deriver——新机型不发明新事件名，现有 DB 数据/调试流程/AI 链路天然可驱动
4. 模型编辑器内可见 validate 结果并完成部件高亮走查
5. `npm run build` 通过；三台新机台各留截图基线；变更记录更新

## 二、里程碑分解

### M0 对齐收尾（0.5h，✅ 已完成）
- [x] 三方基线对齐 `8a74590`；本地 test3 引用修复
- [x] WS 重复投递修复（`realtime.py` 广播汇聚点 raw_id 去重，验收脚本通过）— 提交 `528acee`
- [x] vite 双栈监听修复；8002 单进程确认

### M1 svg_kit 公共库收口（4~5h）

| # | 条目 | 产出 | 工时 |
|---|---|---|---|
| 1.1 | **validate 接入编辑器**：把 validate 规则移植为前端模块 `frontend/src/utils/svgMotionValidate.js`（与 Python CLI 同一规则集），MotionPreview/ModelEditor 挂校验面板 + 部件 id 双向高亮 | 前端校验面板 | 2h |
| 1.2 | **primitives 补件（面向三张参考图）**：等角投影件（iso_box/iso_cylinder——Sym3 与 Synapse 需要）、方形腔体+顶面螺栓阵列、airlock、buffer station、aligner、气体泵模块、control rack | primitives.py 扩充 | 1.5h |
| 1.3 | **tokens 收敛**：三份存量 SVG 的 defs 改引统一 token（回归对照：validate + 截图对比不劣化） | tokens.json 扩充 | 1h |
| 1.4 | **validate 规则强化**：part_id 命名规范、`data-motion-base-visibility` 与首条规则一致性、offset 累积路径复核 | validate.py | 0.5h |

**M1 验收**：scaffold 样例 0 error；三份存量资产 validate 基线报告留档（作为 M3 改造的回归对照）。

### M2 三张参考图 → 三个新机台建模（12~15h，每台 4~5h）

> **2026-10-30 续：三台全部落地并全链验证。** Sym3/Synapse 按本计划「§风险：单台超 6h 先降级俯视并留档」执行——结构（6 腔/泵模块/ESC/螺栓）齐备，等角 iso 件留 M3。详见 `docs/交接说明_2026-10-30_续.md`。

**通用设计决策（三台共用）**：
- 事件词表复用 OXE 27 步标准集；新写 `generic_cluster` deriver（从 `oxe.js` 泛化：端口/腔体归一 + 占位符 id 产出，去掉 OXE 专用映射）
- 视图风格跟随参考图：LAM2300=俯视平面图；Centris Sym3=等角；TEL Synapse=等角
- 每台的动画语义按参考图可辨识的机构定义：load port 门/POD、VTM/Transport Module 机械臂取放、PM 加工状态、airlock/buffer 流转

| # | 机台 | 建模内容 | 工时 |
|---|---|---|---|
| 2.1 | **LAM2300**（俯视） | ATM 区：3×Load Port（门+POD+CST 25槽）+ Aligner + 2×Buffer + Control Rack；ATM/VTM 双机械臂 + airlock 联通；PM1~4 放射。事件映射：POD 放置→ATM 臂→airlock→VTM 臂→PM 加工→回程，全链 27 步词表 | 5h |
| 2.2 | **Centris Sym3**（等角） | 6×方形刻蚀腔（顶面螺栓阵列，开关盖动画）+ 中央卡盘腔（晶圆吸附发光）+ EFEM 柜体 + 3×气体泵（状态灯）。iso_box/iso_cylinder primitives 首次实战 | 4.5h |
| 2.3 | **TEL Synapse**（等角） | Transport Module 居中双臂 + 6×PM 环绕（等角布局）+ UI 站；6 腔轮转加工编排 | 3.5h |
| 2.4 | 三台接线与验收 | MACHINE_MODEL_CONFIGS 建模（scaffold 产出 source_files 槽位登记）+ 演示机台绑定 + debug 全链注入验收 + 截图基线（docs/assets/baseline/） | 2h |

**M2 验收**：三台新机台在 5173 页面可见、可切换；27 步词表注入全通过零警告；validate 0 error；截图基线入库。

### M3 编辑器集成与 SOP（3~4h）

| # | 条目 | 产出 | 工时 |
|---|---|---|---|
| 3.1 | ModelEditor 闭环补齐：上传/生成 → validate 面板 → 部件高亮走查 → MotionBuilder 编排 → 入库 | 编辑器功能 | 2h |
| 3.2 | `docs/新机台建模SOP_v1.md`：**以三张参考图的实建过程为蓝本**（看图→scaffold→primitives 建模→validate→编辑器走查→接线→验收），记录每台实耗 | SOP 文档 | 1.5h |
| 3.3 | 独立工具（oxe_editor.html 等）标记历史参考，SOP 指向平台编辑器 | — | 0.5h |

### M4 回归与合版准备（2h）

- [ ] 三台新机台 + 三台存量机台全量回归（存量做 validate/截图对照）
- [ ] `npm run build` + preview 冒烟
- [ ] 变更记录 ver2.15 + PROJECT_STATUS 速览
- [ ] `feature/model-kit` 推远端 + 《合版说明》（文件清单 + merge-tree 预检）

## 三、与任务 1（AI-B）的对齐机制

### 3.1 分支与拓扑（已核实的事实）
- AI-B 的会话目录是 `fab-twin-pro-main` 的 **linked worktree**（共享 refs）；我的仓库是独立克隆。**双方各自在自己目录开发，互不去对方目录操作**（同分支不能两边同时 checkout）
- 合版：`feature/model-kit` → `test3`，`feature/ai-chain` → `test3`，**合并顺序由用户拍板**；后合的一方负责解决冲突

### 3.2 文件边界（冲突域声明，合版预检以此为准）

| 区域 | 归属 | 说明 |
|---|---|---|
| `frontend/src/**`、`models/**`、`model-editor-standalone/**`、`docs/assets/baseline/**` | **AI-A（我）** | 含 useWebSocket.js / stores/app.js（WS 去重已由我修完） |
| `backend/services/ai_*`、`backend/routers/ai.py`、`dify/**`、`services/db_proxy/**`、`deploy/`（AI 相关） | **AI-B** | |
| `backend/main.py`、`backend/config.py`、`requirements.txt` | **缓冲区（默认 AI-B，改动先知会）** | 我方任务 2 期间不动；若新机台接线需要动（如演示机台 seed），改 `seed_*.py` 旁路，不动 main.py |
| `backend/services/realtime.py` | **共享敏感区**：我已提交去重修复（`528acee`），AI-B 若需改动先拉我的分支或知会 |
| `backend/services/db_poller.py` / `routers/rvmessages.py` | AI-B；我方只读不改 |

### 3.3 环境隔离表

| 资源 | AI-A（任务 2） | AI-B（任务 1） |
|---|---|---|
| 前端 | 5173（我的副本，双栈已修） | 5174（自己副本，proxy 指向 8003） |
| 后端 | 8002（已在跑；AI-B 重启共享后端前知会） | 8003（`API_PORT` 环境变量化由 AI-B 实施） |
| db_proxy | 不依赖 | 8001（自起） |
| Oracle schema | `fabtwin`（现用） | 建议 `fabtwin_dev2`（未建；共用 `fabtwin` 则遵守 3.4） |

### 3.4 测试数据隔离约定（共用 schema 期间的降级方案）
- debug 注入按**机台号分工**：AI-A 的存量验收用 `OXE-03` / `PODOPENER-1` / `AMAT-T1`；**三台新机台的注入用各自演示机台号（LAM-01 / SYM3-01 / SYNAPSE-01，任务 2 新建，天然隔离）**；AI-B 的 AI 链路联调造数用 `OXE-51` 等演示机台且 AI 查询约定查**历史日期**
- `MACHINE_MODEL_CONFIGS` 写入分工：AI-A 写三个存量 + 三个新 model_id；AI-B 不写机型配置

### 3.5 同步节奏与简报格式
- **节奏**：每完成一个里程碑互发一次对齐简报；**共享文件改动**（realtime.py / main.py / config.py）发生时**即时**知会，不等里程碑
- **简报模板**（双方统一）：
  ```
  【里程碑】M1 完成/进行中
  【提交】feature/xxx @ <短hash>（新增 N 提交）
  【改动文件】涉及共享区的列出：文件 + 行为（新增/修改/未动）
  【影响对方】有无：…（端口/服务重启/共享文件/DB 数据）
  【需要对方】有无：…（验收/拍板/告知）
  ```
- **冲突预警**：预计要动缓冲区文件提前声明；合并前 `git merge-tree $(git merge-base HEAD test3) HEAD test3` 预检并在简报列出冲突清单

### 3.6 合版流程（SOP）
1. 双方 feature 分支推远端，出具《合版说明》（改动文件清单 + 自验记录 + 截图基线路径）
2. 用户拍板合并顺序；先合者直接 ff/merge，**后合者负责解冲突**（冲突域按 3.2 归属表取舍）
3. 合并后 test3 联合冒烟：build + 三机台动画抽查 + AI 链路连通性（`test_dify_integration.py`）
4. 合版后双方 `git fetch` + `git branch -f test3 origin/test3` 对齐引用

## 四、风险与预案

| 风险 | 概率 | 预案 |
|---|---|---|
| 等角投影（Sym3/Synapse）部件几何复杂，primitives 首战超时 | 中 | iso 件先做"简化多面体"版保结构正确，细节渐变留 M3 打磨；单台超 6h 先降级为俯视风格并留档说明 |
| 新机台无真实事件流，语义靠推断 | 中 | 复用标准 27 步词表 + generic deriver（不发明新事件名）；动画语义按参考图可辨识机构映射 |
| AI-B 改 realtime.py 与我去重修复分叉 | 中 | 3.2 已声明；合版以功能等价为准（去重语义保留） |
| OXE Motion JSON（1.5 万行）validate 报错量大 | 中 | 源头在 `build_oxe_motion.py` 修，不手改 JSON |
| 新机台演示机台号与现有 seed 冲突 | 低 | 新 model_id/machine_id 用独立前缀（LAM/SYM3/SYNAPSE），seed 幂等先删后插 |

## 五、状态跟踪（每里程碑更新此表）

| 里程碑 | 状态 | 实际工时 | 提交 |
|---|---|---|---|
| M0 对齐收尾 | ✅ 完成 | 0.5h | `528acee` |
| M1 svg_kit 收口 | ⬜ 未开始 | — | — |
| M2 三张参考图建模（LAM2300/Sym3/Synapse） | ✅ 完成（LAM2300 俯视；Sym3/Synapse 按风险预案俯视降级，等角升级留 M3） | — | c282491+ |
| M3 编辑器集成与 SOP | ⬜ 未开始 | — | — |
| M4 回归与合版准备 | ⬜ 未开始 | — | — |
