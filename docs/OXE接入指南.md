# OXE 机台接入平台指南

> **周末开发接续入口文档** · ver2.1.2 → ver2.2
> 更新日期：2026-08-07
> 状态：Step 0 采集阶段（待用户跑 DB 探查脚本）

---

## 一、本周末需要做的事

### 1.1 用户侧（先做）

在能连生产 Oracle 的机器上执行：

```cmd
cd /d "<项目根>\fab-twin-pro\tests\oxe"
run_oxe_db_probe.bat
```

脚本会：
1. 自动调用 `..\..\deploy\env.bat` 读 Oracle 配置（与后端同一份配置）
2. 优先用 `backend\venv\Scripts\python.exe`，没有则用系统 Python
3. Thick 模式自动初始化（与 `backend/database.py` 一致）
4. 采集 6 类信息（全部 SELECT，只读，不改 DB）
5. 生成 `oxe_db_snapshot_*.json`

**前置确认**：`deploy/env.bat` 里的 Oracle 配置是否指向生产环境？如果不是，先改。

**产出物**：`oxe_db_snapshot_*.json` 发给开发后进入 Step 1。

### 1.2 开发侧（拿到 JSON 后做）

按 `docs/开发进度管控.md` 第五章的六步路线图执行：

| 步骤 | 我做什么 | 需要你确认什么 |
|---|---|---|
| **Step 1** | 对照 DB 快照，确认 OXE HTML 的 event_name 和量产 DB 的 event_name 是否一一对应 | 缺失的事件是否需要扩展 `applyEvent()`？ |
| **Step 2** | 确认 FAB_MACHINE 的 machine_id ↔ DT_EVENT_RAW 的 tool_id 映射规则 | 是否需要像 VPO 一样做映射？ |
| **Step 3** | 后端新增 `/api/oxe/history-events` 和 `/api/oxe/latest-event` | 返回格式确认（HTML 期望的字段） |
| **Step 4** | 改 HTML 连平台后端，部署 iframe 集成 | 已确认 1 秒轮询 |
| **Step 5** | 提取 Canvas 引擎为 `OxeCanvasEngine.vue`，统一样式 | 已确认保留独立 HTML 备份 |
| **Step 6** | 建 3 张实时账务表 + AI 分析集成 | 谁写入 DT_EVENT_RAW？答：外部量产系统 |

---

## 二、已确认决策（不再讨论）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 实时画面方案 | 平台内 Canvas + DB 轮询 | 不接收 RV，本就无真实时流；轮询 DB 最新即可 |
| 轮询间隔 | 1 秒 | 用户确认 |
| 阶段1 集成方式 | iframe 嵌入 | 快速上线，过渡可接受 |
| 阶段2 标准化方式 | 提取 `OxeCanvasEngine.vue` | 统一架构，复用平台 KPI/回放/AI |
| 数据源 | 平台后端 + Oracle | 抛弃冗余 RV 网桥 |
| 既有 OXE 模型 | 保留，Tab 切换 | SVG/GLB 强在结构，Canvas 强在动作精度 |
| 独立 HTML 文件 | 保留备份 | 用户确认 |
| AI 分析 | 参考 PODOPENER 实现 | 用户确认 |
| RV 网桥 | ❌ 不再部署，仅留参考 | 平台不接收 RV |
| 外部发布网站 | ❌ 不再部署，仅作 Canvas 参考 | 避免两套系统割裂 |

---

## 三、关键架构对比

### 3.1 现状（不接入的问题）

```
独立 HTML (oxehtml_formatted.html)
  ↓ 调用
RV 网桥 (bridge.py + router.py @7501)
  ↓ 读写
Oracle (DT_EVENT_RAW + DT_EVENT_REALTIMELOT)
  ↑ 写入
外部量产系统（RV 报文）
```

**问题**：
- 平台与 HTML 两套系统割裂
- RV 网桥冗余（平台不接收 RV）
- AI 分析、历史回放无法集成

### 3.2 目标（接入后）

```
外部量产系统 → Oracle (DT_EVENT_RAW)
                    ↓
平台后端 (8002) ← 轮询/查询
  ├── /api/oxe/latest-event   → 1秒轮询 → Canvas 实时画面
  ├── /api/oxe/history-events → 历史回放
  └── /api/ai/...             → AI 分析（参考 PODOPENER）
                    ↓
平台前端 (5173)
  ├── 阶段1: iframe 嵌入 HTML
  └── 阶段2: <OxeCanvasEngine> Vue 组件（统一样式）
```

### 3.3 数据流对比

| 维度 | 现状 | 接入后 |
|---|---|---|
| 实时画面数据源 | RV 网桥 SSE `/events` | 平台 `/api/oxe/latest-event`（轮询） |
| 历史回放数据源 | RV 网桥 `/history-events` | 平台 `/api/oxe/history-events` |
| 状态重建 | RV 网桥 `/latest-event` + `bootstrapFromLatestPODPlaced` | 平台 `/api/oxe/latest-event` + 同一套 bootstrap |
| AI 分析 | ❌ 无 | ✅ 参考 PODOPENER |
| 样式统一 | ❌ 独立 HTML | ✅ 阶段2 后 Vue 组件 |
| 部署 | 两套（平台 + RV 网桥） | 一套（平台） |

---

## 四、文件清单与作用

### 4.1 参考文件（已格式化，不部署）

| 文件 | 作用 | 状态 |
|---|---|---|
| [tests/oxe/bridge.py](file:///tests/oxe/bridge.py) | RV 监听参考 | ✅ 已格式化（382行） |
| [tests/oxe/router.py](file:///tests/oxe/router.py) | HTTP 服务参考 | ✅ 已格式化（362行） |
| [tests/oxe/store.py](file:///tests/oxe/store.py) | Oracle 持久化参考 | ✅ 已格式化（660行） |
| [tests/oxe/DT_EVENT_REALTIMELOT.sql](file:///tests/oxe/DT_EVENT_REALTIMELOT.sql) | 实时账务建表 | ✅ 已格式化 |
| [tests/oxe/DT_RTLOT_EVENT_RULE.sql](file:///tests/oxe/DT_RTLOT_EVENT_RULE.sql) | 事件规则建表 | ✅ 已格式化 |
| [tests/oxe/DT_RTLOT_TOOL_PORT_RULE.sql](file:///tests/oxe/DT_RTLOT_TOOL_PORT_RULE.sql) | 端口规则建表 | ✅ 已格式化 |
| [frontend/dist/oxehtml_formatted.html](file:///frontend/dist/oxehtml_formatted.html) | Canvas 引擎源 | ✅ 已修复结构 |

### 4.2 工具脚本

| 文件 | 作用 |
|---|---|
| [tests/oxe/oxe_db_probe.py](file:///tests/oxe/oxe_db_probe.py) | DB 资料采集（只读） |
| [tests/oxe/run_oxe_db_probe.bat](file:///tests/oxe/run_oxe_db_probe.bat) | 采集启动脚本（调用 env.bat） |

### 4.3 待新建文件（Step 1+）

| 文件 | 作用 | 步骤 |
|---|---|---|
| `backend/routers/oxe.py` | OXE 适配接口 | Step 1 |
| `frontend/src/components/OxeCanvasEngine.vue` | Canvas 引擎 Vue 组件 | Step 4 |

### 4.4 待修改文件（Step 1+）

| 文件 | 修改内容 | 步骤 |
|---|---|---|
| `frontend/dist/oxehtml_formatted.html` | `getApiBaseUrl()` → 8002，SSE → 轮询 | Step 2 |
| `frontend/src/views/MachineDetail.vue` | OXE 机型 iframe 嵌入 / 组件挂载 | Step 3/5 |

---

## 五、HTML 调用的接口与平台对应关系

| HTML 调用 | 平台已有能力 | 差距 | 处理方式 |
|---|---|---|---|
| `GET /history-events?tool_id=xxx` | ✅ `/api/history/{tool_id}` 已实现，支持时间范围/分页/raw_id锚点 | 返回字段格式不同 | Step 1 建 `/api/oxe/history-events` 适配 |
| `GET /latest-event?tool_id=xxx` | ⚠️ 平台有 `/api/history` 但无"最新一条"专用接口 | 需新增 | Step 1 建 `/api/oxe/latest-event` |
| `GET /events`（SSE 实时） | ❌ 平台无 SSE | 但平台不接收 RV，不需要实时推送 | Step 2 改 HTML 为轮询 |
| `GET /bind`（会话绑定） | ✅ 平台有自己的会话机制 | 不需要 | 删除 HTML 的 bind 逻辑 |

---

## 六、DB 新增表设计评估

### 6.1 设计合理性：✅ 合理

| 表 | 作用 | 合理性 | 落地时机 |
|---|---|---|---|
| `DT_EVENT_REALTIMELOT` | 当前 LOT 实时账务 | ✅ 解决"页面打开时恢复当前RUN货状态" | 阶段3 |
| `DT_RTLOT_EVENT_RULE` | 事件动作规则（OPEN/UPDATE/CLEAR/IGNORE） | ✅ 灵活可配置 | 阶段3 |
| `DT_RTLOT_TOOL_PORT_RULE` | 端口管理模式（SINGLE/MULTI） | ✅ 区分不同机台 | 阶段3 |

### 6.2 落地前提

实时账务表的更新由"谁写入 DT_EVENT_RAW"触发。平台不接收 RV，`DT_EVENT_RAW` 由**外部量产系统**直接写入 Oracle。

**触发方式**：平台后端轮询 `DT_EVENT_RAW` 发现新记录时，按规则更新 `DT_EVENT_REALTIMELOT`。会有 1-2 秒延迟（可接受，因为实时画面也是 1 秒轮询）。

### 6.3 SQL 已知问题

3 张 SQL 文件缺少 `CREATE SEQUENCE` 语句（触发器引用了序列）。Step 6 建表时补全。

---

## 七、AI 分析集成方案（Step 6）

参考 PODOPENER 的 AI 实现：

| 功能 | PODOPENER 实现 | OXE 适配 |
|---|---|---|
| AI 入口 | 机台详情页右侧"AI"Tab + 全局悬浮球 | 同上 |
| 数据来源 | 当前事件流 + 历史回放片段 | 同上 |
| 工具调用 | `get_lot_history` / `get_machine_status` / `get_alarm_history` | 同上，新增 OXE 专用工具（如 `get_wafer_flow`） |
| 跳转能力 | `jump_timestamp` + `jump_machine_id` | 同上 |
| Provider 管理 | 多 Provider + Token 统计 | 复用 |

---

## 八、环境对齐检查清单（周末换电脑后）

在另一台电脑打开 TRAE 后，确认以下内容：

- [ ] `git pull origin test1` 拉到最新（commit `d8be2a1`）
- [ ] `deploy/env.bat` 的 Oracle 配置正确
- [ ] `backend/venv` 已创建且装了 `oracledb`
- [ ] `frontend/node_modules` 已安装
- [ ] 本文档和 `docs/开发进度管控.md` 第五章内容一致

---

## 九、联系点

- **DB 探查脚本问题**：看 `tests/oxe/oxe_db_probe.py` 顶部注释
- **架构决策问题**：看本文档第二章
- **路线图问题**：看 `docs/开发进度管控.md` 第五章
- **HTML 代码问题**：看 [frontend/dist/oxehtml_formatted.html](file:///frontend/dist/oxehtml_formatted.html)
