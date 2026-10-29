# 任务 2 工作计划：模型编辑器公共库开发 + 三机台建模定稿

> 负责人：ZCode（AI-A）｜ 分支：`feature/model-kit`（基线 `8a74590`）｜ 工作副本：`E:\AI\fab\fab-twin-pro`
> 任务 1（AI 链路）：另一 AI（AI-B）｜ 分支：`feature/ai-chain`（worktree：`C:\Users\Administrator\WorkBuddy\Worktrees\fab-twin-pro-main\test3-5f23dcb7`）
> 编写日期：2026-10-30 ｜ 总工时预估：**16~19 小时（约 2 个工作日）**

---

## 一、目标与验收口径

**目标**：把 `models/svg_kit` 从骨架收口为三个机台真实可用的公共库；以公共库 + 模型编辑器为唯一建模通道，完成 PODOPENER-2200 / OXE DRM / AMAT METSPUT 三机台的 2D 建模定稿。

**总验收口径（合版前必须全绿）**：
1. `python -m models.svg_kit.validate` 对三机台 SVG×Motion 全量校验 **0 error**（warning 允许留档说明）
2. 三机台 debug 注入全事件链端到端通过（注入→DB→轮询→WS→deriver→动画），零警告
3. 模型编辑器内可见校验结果（部件高亮走查可用），不再需要独立 HTML 工具
4. `npm run build` 通过；三机台各留一份截图基线
5. 变更记录 + 本计划的状态列更新完毕

## 二、里程碑分解

### M0 对齐收尾（0.5h，✅ 已完成）
- [x] 三方基线对齐 `8a74590`；本地 test3 引用修复
- [x] WS 重复投递修复（`realtime.py` 广播汇聚点 raw_id 去重，验收脚本通过）— 提交 `528acee`
- [x] vite 双栈监听修复；8002 单进程确认
- [ ] AI-B 侧 db_proxy(8001) 起动确认（其自测项，不阻塞我）

### M1 svg_kit 公共库收口（4~5h）

| # | 条目 | 产出 | 工时 |
|---|---|---|---|
| 1.1 | **validate 接入编辑器**：MotionPreview/ModelEditor 挂"校验"面板（调 python CLI 太绕，改为把 validate 移植成同规则的前端模块 `frontend/src/utils/svgMotionValidate.js`，双端共用同一规则集），部件 id 双向高亮联动 | 前端校验面板 + 单测 | 2h |
| 1.2 | **primitives 补件**：PODOPENER 风格件（机柜钣金/升降载台/锁扣对/观察窗/控制箱）、AMAT 风格件（楔形腔/彩虹晶圆/金属槽条）从三份 SVG 抽取进公共库 | primitives.py 扩充 | 1.5h |
| 1.3 | **tokens 收敛**：三机台 SVG 的 defs（渐变/滤镜/pattern）改引统一 token 生成，消除三份重复定义 | tokens.json 扩充 + 三 SVG defs 瘦身 | 1h |
| 1.4 | **validate 规则强化**：新增规则——part_id 命名规范（小写下划线/禁保留字）、`data-motion-base-visibility` 与首条规则一致性、offset 累积路径复核（防"跳起点→动画到终点"漏写 phase 1） | validate.py 规则 + 用例 | 0.5h |

**M1 验收**：scaffold 生成的新机台样例经 validate 0 error；三机台资产跑 validate 出具第一份基线报告（error 清零或留档）。

### M2 三机台建模定稿（6~8h，每台 2~2.5h）

| 机台 | 走查范围 | 工时 |
|---|---|---|
| PODOPENER-2200 | 14 事件 motions 逐条走查（穿入/脱出分支、锁扣双态、晶舟时序）；svg_kit 重构 defs；ModelEditor 高亮走查全部 part_id；debug 全链注入验收（PACKING+UNPACKING 各一轮）+ 截图基线 | 2.5h |
| OXE DRM | 资产由 `gen_oxe_svg.py`/`build_oxe_motion.py` 生成——生成器接 tokens/primitives 收敛（不改 14989 行 JSON 手工面）；26 步逐条 validate；端到端注入验收（取放片 13 相编排 + 双 PORT + mapping）+ 截图基线 | 2.5h |
| AMAT METSPUT | svg_kit 重构 defs（该资产已被 26af040 精修过，做收敛而非重画）；motions 6 步 + deriver 双臂语义走查；端到端注入验收 + 截图基线 | 2h |

**M2 验收**：三机台"validate 0 error + 端到端零警告 + 截图基线入库（docs/assets/baseline/）"。

### M3 编辑器集成与 SOP（3~4h）

| # | 条目 | 产出 | 工时 |
|---|---|---|---|
| 3.1 | ModelEditor 建模页串起完整闭环：上传/生成 → validate 面板 → 部件高亮走查 → Motion 编排（MotionBuilder）→ 一键入库（seed 等价 API） | 编辑器功能补齐 | 2h |
| 3.2 | `docs/新机台建模SOP_v1.md`：以第四台假想机型走一遍 scaffold→validate→编辑器→入库 全流程，记录耗时作为"零代码接入"的实证 | SOP 文档 | 1.5h |
| 3.3 | 回归确认：归档的独立工具（oxe_editor.html 等）标记为历史参考，SOP 指向平台编辑器 | — | 0.5h |

### M4 回归与合版准备（2h）

- [ ] 三机台全事件回归（沿用 M2 截图基线对比）
- [ ] `npm run build` + vite preview 冒烟
- [ ] 变更记录 ver2.15 草稿 + PROJECT_STATUS 速览更新
- [ ] `feature/model-kit` 推远端，出具《合版说明》（改动文件清单 + 冲突预检：`git merge-tree` 对 test3 试合并）

## 三、与任务 1（AI-B）的对齐机制

### 3.1 分支与拓扑（已核实的事实）
- AI-B 的会话目录是 `fab-twin-pro-main` 的 **linked worktree**（共享 refs）；我的仓库是独立克隆。**双方各自在自己目录开发，互不去对方目录操作**（同分支不能两边同时 checkout）
- 合版：`feature/model-kit` → `test3`，`feature/ai-chain` → `test3`，**合并顺序由用户拍板**；后合的一方负责解决冲突

### 3.2 文件边界（冲突域声明，合版预检以此为准）

| 区域 | 归属 | 说明 |
|---|---|---|
| `frontend/src/**`、`models/**`、`model-editor-standalone/**` | **AI-A（我）** | 含 useWebSocket.js / stores/app.js（WS 去重已由我修完，AI-B 无需再动） |
| `backend/services/ai_*`、`backend/routers/ai.py`、`dify/**`、`services/db_proxy/**`、`deploy/`（AI 相关） | **AI-B** | |
| `backend/main.py`、`backend/config.py`、`requirements.txt` | **缓冲区（默认 AI-B，改动先知会）** | 我方承诺任务 2 期间不动 main.py / requirements.txt；config.py 只读 |
| `backend/services/realtime.py` | **共享敏感区**：我已提交去重修复（`528acee`），AI-B 若需改动 **先拉我的分支或知会**，避免同文件分叉 |
| `backend/services/db_poller.py` / `routers/rvmessages.py` | AI-B（8a74590 已含其 P0 改造）；我方只读不改 |

### 3.3 环境隔离表

| 资源 | AI-A（任务 2） | AI-B（任务 1） |
|---|---|---|
| 前端 | 5173（我的副本，host 双栈已修） | 5174（自己副本，proxy 指向 8003） |
| 后端 | 8002（已在跑，**AI-B 改共享后端代码需重启前知会**） | 8003（`API_PORT=8003` 需 config 环境变量化——已建议，AI-B 实施） |
| db_proxy | 不依赖 | 8001（自起） |
| Oracle schema | `fabtwin`（现用） | 建议切 `fabtwin_dev2`（未建；若 AI-B 直接共用 `fabtwin`，则遵守 3.4） |
| WS 验收 | 我的动画链路依赖 raw_event 单次投递（`528acee` 保证） | AI 链路若监听 WS，同样受益 |

### 3.4 测试数据隔离约定（共用 schema 期间的降级方案）
- debug 注入事件按**机台号分工**：AI-A 用 `OXE-03` / `PODOPENER-1` / `AMAT-T1`；AI-B 的 AI 链路联调若需造数，用 `OXE-51` 等演示机台，且 AI 查询测试约定查**历史日期**（非当日），避开我注入的当日事件
- 双方不动对方的 seed 脚本；`MACHINE_MODEL_CONFIGS` 行我只写 `PODOPENER-2200` / `TEL-DRM-UNIT` / `AMAT-METSPUT` 三个 model_id

### 3.5 同步节奏与简报格式
- **节奏**：每完成一个里程碑互发一次对齐简报（不设固定钟点）；**共享文件改动**（realtime.py / main.py / config.py）发生时**即时**知会，不等里程碑
- **简报模板**（双方统一）：
  ```
  【里程碑】M1 完成/进行中
  【提交】feature/xxx @ <短hash>（新增 N 提交）
  【改动文件】涉及共享区的列出：文件 + 行为（新增/修改/未动）
  【影响对方】有无：…（端口/服务重启/共享文件/DB 数据）
  【需要对方】有无：…（验收/拍板/告知）
  ```
- **冲突预警**：任一方预计要动缓冲区文件，提前一条消息声明；合并前用 `git merge-tree $(git merge-base HEAD test3) HEAD test3` 预检冲突文件清单并在简报中列出

### 3.6 合版流程（SOP）
1. 双方 feature 分支推远端，出具《合版说明》（改动文件清单 + 自验记录 + 截图基线路径）
2. 用户拍板合并顺序；先合者直接 ff/merge，**后合者负责解冲突**（冲突域按 3.2 归属表判断取舍）
3. 合并后 test3 上跑联合冒烟：build + 三机台动画抽查 + AI 链路连通性（`test_dify_integration.py`）
4. 合版后双方 `git fetch` + 本地 test3 引用对齐（`git branch -f test3 origin/test3`，防旧引用再漂移）

## 四、风险与预案

| 风险 | 概率 | 预案 |
|---|---|---|
| AI-B 改 realtime.py 与我去重修复分叉 | 中 | 3.2 已声明；我的提交粒度小，合版以功能等价为准（去重语义保留即可） |
| OXE Motion JSON（1.5 万行）validate 报错量大 | 中 | 生成器 `build_oxe_motion.py` 是源头——规则改动回生成器修，不手改 JSON |
| 编辑器校验面板改 MotionPreview 触碰 AI-B 也关注的文件 | 低 | MotionPreview 在我的边界内（已声明）；AI-B 的改动集中在 ai 域 |
| 共用 schema 下 AI 链路测试读到我的当日注入事件 | 中 | 3.4 机台/日期分工；AI-B 建好 dev2 schema 后自动归零 |
| 工期交叉（双方都今晚出大提交） | 低 | 合版顺序用户拍板；我方 M4 的 merge-tree 预检把冲突清单提前暴露 |

## 五、状态跟踪（每里程碑更新此表）

| 里程碑 | 状态 | 实际工时 | 提交 |
|---|---|---|---|
| M0 对齐收尾 | ✅ 完成 | 0.5h | `528acee` |
| M1 svg_kit 收口 | ⬜ 未开始 | — | — |
| M2 三机台建模定稿 | ⬜ 未开始 | — | — |
| M3 编辑器集成与 SOP | ⬜ 未开始 | — | — |
| M4 回归与合版准备 | ⬜ 未开始 | — | — |
