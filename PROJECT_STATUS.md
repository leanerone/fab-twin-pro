# FabTwin Pro 项目进度文档

> 更新日期：2026-09-11
> 当前版本：ver2.10.21
> 分支：test1（开发与测试都走这个分支）

---

## 〇、当前状态速览（2026-09-11）

### 本地起服务（四件）

| 服务 | 端口 | 启动方式 |
|---|---|---|
| Oracle | 1521 | 本地库 `fabtwin / fabtwin @ localhost:1521/orclpdb` |
| db_proxy | 8001 | `cd services\db_proxy` → 先设 `$env:ORACLE_DSN_TYPE="service_name"` → `python main.py` |
| backend | 8002 | `cd backend` → `python main.py` |
| frontend | 5173 | `cd frontend` → `npm run dev` |

**坑**：本地连的是 PDB（orclpdb），db_proxy 默认 `ORACLE_DSN_TYPE=sid`，**不设成 `service_name` 会连不上**。backend 的 config 已经默认 `service_name`，不用管。

### 本地测试脚本

```powershell
# 平台数据工具（fab_query / fab_admin）：只测 proxy 层，先排除 n8n 干扰
python tests\test_n8n_f1_f10.py --layer proxy --proxy http://localhost:8001 --machine OXE-51 --lot V394K

# 完整两层（n8n + db_proxy）
python tests\test_n8n_f1_f10.py --merged --proxy http://10.30.5.216:8001 --json-out tests\n8n_result.json

# MES/SPC 那 5 个 MCP 工具
$env:MCP_URL="http://10.30.116.137/mcp-server/http"; $env:MCP_TOKEN="<token>"
python tests\test_mcp_connection.py

# Dify 应用连通性
python tests\test_dify_integration.py --base-url http://<Dify>:8088/v1 --api-key app-xxxx
```

### 数据库数据不在仓库里

`.gitignore` 把 `tests/prod_export_*/`、`tests/db_backups/`、`tests/AI_CONFIGS*` 都排除了（含真实账号与 API Key，**故意不提交**）。换机器后要重建测试数据，用仓库里的脚本：

```powershell
# 生成"今天"的完整演示数据（PODOPENER-1 / OXE-1 / OXE-51 三台机台的完整动画流程）
python tests\generate_today_demo.py

# 补一个历史日期（--history-only 只写 DT_EVENT_RAW，不污染实时画面表）
python tests\generate_today_demo.py --date 2026-09-09 --raw-base 6000000 --history-only

# OXE-1 的告警演示数据（SPC异常/机台异常/SMIF异常等）
python tests\generate_oxe_alarms.py --date 2026-09-11
```

### ver2.10.17 ~ ver2.10.21 解决的问题

| 版本 | 问题 | 根因 |
|---|---|---|
| 2.10.17 | 量产查不到历史日期（只有当天能查） | 量产 `DT_EVENT_RAW` 时间列是 `TIMESTAMP(6)`、本地是 `VARCHAR2`，代码里的 `LIKE '2026-09-09%'` 打在 TIMESTAMP 上恒不匹配且不报错；再被「取最新 N 条」的兜底掩盖成「只有当天有数据」 |
| 2.10.18 | AI 助手 alarm / lot / run 数量全查不到 | ① 同上（db_proxy 四处 `event_ts_utc >= :since`）② `(:mid = '' OR ...)` 在 Oracle 里空串=NULL 恒不成立 ③ 批次完成口径只认 `LotEnd`，实际机台报的是 `POD_REMOVED`/`MOC` ④ 告警清单漏 `ALARM_REPORT` ⑤ F9 绑定名用了保留字 `:desc` |
| 2.10.19 | F8 43.7s、F7 60s 超时、F9 主键冲突 | ① 上一版用 `NVL()` 包住列做过滤，索引失效 ② F7 无行数上限也无时间窗口 ③ `alarms.ID` 在 Oracle 11g 没有自增机制 |
| 2.10.20 | — | Dify 助手融合 MES/SPC/EAP日志/文档解析，工具 2 → 10 个，意图 10 → 18 类 |
| 2.10.21 | F7 仍 60s 超时 | 排序写成 `ORDER BY raw_id ASC`，升序让 Oracle 无法提前停止（stopkey 失效）；改 `DESC` |

### 遗留待办（回家优先处理）

| # | 事项 | 阻塞点 | 下一步 |
|---|---|---|---|
| 1 | **量产 n8n 整层不通** | `10.30.116.151:5678` 全部 21s 超时 | `curl -v http://10.30.116.151:5678/healthz` 确认服务/防火墙；不通则 Dify 侧 fab_query/fab_admin/MES 全都调不动 |
| 2 | **量产 `DT_EVENT_RAW` 缺索引** | F5 14s / F8 43s / F7 可能仍超时 | 让 DBA 执行 `CREATE INDEX IDX_DT_EVENT_RAW_TOOL_RECV ON DT_EVENT_RAW (TOOL_ID, RECEIVED_TS_UTC);` —— 这是慢查询的根本解 |
| 3 | F7 的 stopkey 是否真生效 | 本机是小库，优化器怎么选都快，**验证不了** | 部署后重测；若仍超时，加 `/*+ INDEX(DT_EVENT_RAW) */` hint 或 raw_id 二分锚点 |
| 4 | F3 / F8 告警统计被低估 | ROWNUM 上限是「过滤后截断再统计」 | 依赖 #2；有索引后提高上限。现状：同条件同机台 F3 报 243 条、F8 报 591 条 |
| 5 | MES 工具「admin 也用不了」 | Dify 工作区成员角色 ≠ prompt 里的 `user_role` 变量 | Dify 预览面板把「用户角色」选成 admin；再确认 MCP 是否真调通 |
| 6 | Dify MCP provider 凭据 | 导出的 YAML 不含 endpoint / token | 目标 Dify 里建同名 provider `liang_n8n_MCPTrigger_TestEnv` |
| 7 | OXE 机台 tool_id 映射 | `history.py` 缺 OXE 前缀匹配（`ai_tools.py` 有） | 需要确认 `OXE-61` ↔ `OXE-T61` / `OXE-T61A` 的准确对应规则，不能直接用 `OXE` 前缀（会误伤所有 OXE 机台） |

---

## 一、版本更新记录

### ver2（2026-07-19）

#### 核心修复

| 修复项 | 说明 |
|--------|------|
| 时间戳格式统一 | 所有时间格式统一为东八区本地时间（无Z后缀），解决历史回放时间不一致问题 |
| 历史回放修复 | 时间轴显示与实际数据时间匹配，日期切换正常 |
| 自动播放修复 | 点击事件/Lot/时间轴不再自动播放，播放/暂停按钮功能恢复 |
| 实时模式修复 | 切换实时模式后停止播放历史内容，正确对接WinForm实时事件 |
| 日期输入框同步 | 修复多个日期选择器不同步问题 |
| 3D视图事件匹配 | 修复回放模式下只有POD_PLACED和POD_REMOVED能触发动画的问题，现在所有14个事件都能正确匹配动画阶段 |

#### 新增功能

| 功能 | 说明 |
|------|------|
| DB轮询服务 | db_poller.py，每秒轮询DB新事件并通过WebSocket推送 |
| WinForm模拟器 | winform_simulator.py，tkinter GUI，支持完整PACKING/UNPACKING流程 |
| 事件-阶段映射 | 2D/3D视图均实现完整的14个事件到动画阶段的映射 |
| 事件ID动态生成 | WinForm从数据库读取最大ID作为初始值，解决ORA-00001唯一约束冲突 |

### ver1（2026-07-18）

- PODOPENER-1 机台接入完成
- DT_EVENT_RAW_CUR 表创建
- 7天历史数据生成（10920条事件）
- 历史回放UNKNOWN修复
- 3D视图流程按钮移除
- 前端事件动作映射初始化
- 双模式实时驱动架构搭建

---

## 二、整体进度评估

### 2.1 功能模块完成度

| 模块 | 进度 | 状态 | 说明 |
|------|------|------|------|
| 主页看板 | 85% | ✅ 可用 | KPI卡片、机台列表、楼层切换、告警统计 |
| 机台详情页 | 90% | ✅ 可用 | 多视图切换、事件/告警/Lot/AI面板 |
| PODOPENER 2D视图 | 90% | ✅ 可用 | 14个事件全部匹配动画阶段 |
| PODOPENER 3D视图 | 90% | ✅ 可用 | 14个事件全部匹配动画阶段 |
| TEL DRM 3D模型 | 85% | ✅ 可用 | 7步工艺动画、状态灯 |
| OXE 等角2.5D视图 | 80% | ✅ 可用 | 机械臂动画、Wafer流转 |
| 历史回放系统 | 85% | ✅ 可用 | 时间轴、分类统计、跳转回放、6档倍速 |
| 实时推送系统 | 90% | ✅ 可用 | WebSocket + DB轮询 + 模拟器双模式 |
| WinForm模拟器 | 95% | ✅ 可用 | 完整流程、报警模拟、事件ID动态生成 |
| 2D平面图编辑器 | 80% | ✅ 可用 | 5种工具、拖拽编辑、JSON导入导出 |
| 楼层3D视图 | 80% | ✅ 可用 | 机台/区域/轨迹/天车3D可视化 |
| AI助手 | 70% | ⚠️ 待增强 | 规则引擎可用，MCP/Dify待接入 |
| 模型编辑器 | 60% | ⚠️ 待完善 | 基础框架可用，配置化需完善 |
| 用户权限 | 0% | 📋 待开发 | 登录页有，权限体系未实现 |

### 2.2 PODOPENER 专项进度

| 任务 | 进度 | 说明 |
|------|------|------|
| 机台ID重命名(VPO-01→PODOPENER-1) | ✅ 100% | 前端UI全部更新 |
| DT_EVENT_RAW_CUR表 | ✅ 100% | Oracle已创建，ORM模型已定义 |
| 历史回放UNKNOWN修复 | ✅ 100% | history.py新增事件分类 |
| 时间戳格式统一 | ✅ 100% | 东八区本地时间，无Z后缀 |
| 3D视图事件-阶段映射 | ✅ 100% | 14个事件全部匹配动画阶段 |
| 2D视图事件-阶段映射 | ✅ 100% | 14个事件全部匹配动画阶段 |
| 模拟器PODOPENER流程 | ✅ 100% | 14+6完整事件，写入DB |
| DB轮询服务 | ✅ 100% | db_poller.py，每秒轮询+WS推送 |
| 7天历史数据 | ✅ 100% | 10000+条事件，含报警 |
| WinForm模拟器 | ✅ 100% | tkinter GUI，单步/自动/报警 |
| 前端事件动作映射 | ✅ 100% | useEventActionMapping.js |
| 播放控制修复 | ✅ 100% | 点击事件不自动播放，暂停/播放正常 |
| 实时模式对接 | ✅ 95% | WinForm→DB→轮询→WS→前端 |
| 2D/3D动画驱动联动 | ⚠️ 90% | 事件已映射，需完整端到端测试 |

### 2.3 数据库现状

- **数据库**: Oracle 19c (PDB: ORCLPDB)
- **用户**: fabtwin
- **机台数据**: 38台机台，PODOPENER-1已就绪
- **历史数据**: PODOPENER-1共10920条事件（7天）
- **当前状态表**: DT_EVENT_RAW_CUR 已创建并投入使用
- **表总数**: 19张（5张Oracle对齐 + 14张扩展）

---

## 三、PODOPENER 业务流程

### 3.1 穿入流程（PACKING）- 14个事件

| 序号 | 事件名 | 说明 | 典型间隔 | 对应动画阶段 |
|------|--------|------|----------|-------------|
| 1 | POD_PLACED | POD放置到位 | 0s | ATTACH_POD_PLACE |
| 2 | COMPLETED_PORT_LOCK | 端口锁定完成 | 3-4s | POD_LOCK |
| 3 | READ_BATTERY | 读取电池状态 | 1s | READ_TAG |
| 4 | READ_TAG | 读取RFID标签 | 1-2s | READ_TAG |
| 5 | BATCH_INFO_FROM_ECUI | 获取批次信息 | 1s | BATCH_START |
| 6 | OPEN_POD | 打开POD盖 | 10s | ATTACH_POD_UP |
| 7 | REACH_STAGE | 机械臂到达平台 | 3s | ATTACH_POD_REACH_STAGE |
| 8 | UI_CONFIRM | 操作员确认 | 变化大 | UI_CONFIRM |
| 9 | CLOSE_POD | 关闭POD盖 | 10s | ATTACH_POD_DOWN |
| 10 | ACK_UI_DOUBLECHECK | 二次确认 | 变化大 | UI_DOUBLECHECK |
| 11 | REACH_POS | 机械臂到位 | 3s | ATTACH_POD_REACH_POS |
| 12 | WRITE_TAG | 写入RFID标签 | 3s | WRITE_TAG |
| 13 | COMPLETED_PORT_UNLOCK | 端口解锁完成 | 3-4s | POD_UNLOCK |
| 14 | POD_REMOVED | POD移走 | 变化大 | ATTACH_POD_REMOVE |

### 3.2 脱出流程（UNPACKING）- 6个事件

| 序号 | 事件名 | 说明 | 典型间隔 |
|------|--------|------|----------|
| 1 | UI_CONFIRM | 操作员确认 | 0s |
| 2 | CLOSE_POD | 关闭POD盖 | 10s |
| 3 | REACH_POS | 机械臂到位 | 3s |
| 4 | WRITE_TAG | 写入RFID标签 | 3s |
| 5 | COMPLETED_PORT_UNLOCK | 端口解锁完成 | 5s |
| 6 | POD_REMOVED | POD移走 | 变化大 |

### 3.3 报警事件

| alarm_id | 说明 | 严重程度 |
|----------|------|----------|
| 0201 | 电池电压异常 | warn |
| 9003 | 测试机时间快到了 | info |
| 9004 | 超过测试限Run批数 | warn |
| 0411 | POD/Cassette清洗到期 | info |
| 20011 | DirtyBit不匹配 | warn |

---

## 四、双模式实时驱动架构

### 4.1 模式一：内部模拟器（Demo用）

```
simulator.py 定时器
    ↓ 每2秒生成事件
写入 DT_EVENT_RAW + DT_EVENT_RAW_CUR
    ↓
db_poller.py 每秒轮询
    ↓
WebSocket 广播到前端
    ↓
前端动画驱动 (useEventActionMapping)
```

配置开关（config.py）：
```python
SIMULATION_ENABLED = True
SIMULATION_INTERVAL_MS = 2000
```

### 4.2 模式二：外部DB写入（生产/WinForm用）

```
WinForm模拟器 / EAP系统
    ↓ 直接写入DB
DT_EVENT_RAW + DT_EVENT_RAW_CUR
    ↓
db_poller.py 每秒轮询
    ↓
WebSocket 广播到前端
    ↓
前端动画驱动
```

配置开关（config.py）：
```python
DB_POLLER_ENABLED = True
DB_POLLER_INTERVAL_MS = 1000
```

---

## 五、运行方式

### 5.1 启动后端
```powershell
cd n:\AI\fab-twin-pro-ver1\backend
.\venv\Scripts\python.exe main.py
```
- 后端地址: http://localhost:8002
- API文档: http://localhost:8002/docs

### 5.2 启动前端
```powershell
cd n:\AI\fab-twin-pro-ver1\frontend
npm run dev
```
- 前端地址: http://localhost:5173

### 5.3 启动WinForm模拟器
```powershell
cd n:\AI\fab-twin-pro-ver1
python winform_simulator.py
```

### 5.4 重新生成历史数据
```powershell
cd n:\AI\fab-twin-pro-ver1\backend
.\venv\Scripts\python.exe gen_podopener_history.py
```

---

## 六、API接口清单

### 6.1 机台接口
| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/machines` | 获取机台列表 |
| GET | `/api/machines/{machine_id}` | 获取机台详情 |
| GET | `/api/machines/stats` | 获取机台统计KPI |

### 6.2 历史回放接口
| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/history/{tool_id}` | 获取历史事件时间轴 |
| GET | `/api/history/{tool_id}/timeline` | 获取时间轴摘要（按小时聚合） |
| GET | `/api/history/{tool_id}/alarms` | 获取告警历史 |

### 6.3 WebSocket接口
| 路径 | 描述 |
|------|------|
| `/ws/realtime` | 实时数据推送（DB轮询+模拟器） |

### 6.4 其他接口
| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/lots` | 批次列表 |
| GET | `/api/alarms` | 告警统计 |
| GET | `/api/floors` | 楼层列表 |
| GET | `/api/oht/positions` | 天车位置 |
| GET | `/api/recipes` | 工艺配方 |
| POST | `/api/ai/query` | AI自然语言查询 |
| POST | `/api/rvmessages` | RV消息接收 |

---

## 七、后续开发优化方向

### Phase 1：功能完善与测试验证（近期）

#### 7.1.1 端到端测试验证
- **优先级**: 🔴 高
- **内容**:
  - PODOPENER完整流程端到端测试（WinForm→DB→轮询→WS→2D/3D动画）
  - WebSocket连接稳定性优化（解决持续重连问题）
  - 14个事件动画阶段逐一验证
  - 报警事件联动测试（报警闪烁、状态变色）
- **目标**: 确保所有14个动作在2D/3D视图下都能正确触发动画

#### 7.1.2 历史回放优化
- **优先级**: 🟡 中
- **内容**:
  - 大数据量分页优化
  - 时间轴虚拟滚动
  - 回放进度条拖拽体验优化
  - 事件详情面板增强

#### 7.1.3 前端构建验证
- **优先级**: 🟡 中
- **内容**:
  - 验证 `npm run build` 正常
  - 生产环境打包测试
  - 修复可能的构建错误

### Phase 2：配置化与多机型扩展（1-2周）

#### 7.2.1 ModelEditor升级
- **优先级**: 🔴 高
- **内容**:
  - 可视化动作编排UI（事件→动作拖拽配置）
  - 部件列表、属性面板
  - 配置版本管理（导入/导出/对比）
- **目标**: 新机台型号接入无需改代码，纯配置完成

#### 7.2.2 多机型配置化接入
- **优先级**: 🟡 中
- **内容**:
  - PODOPENER配置化接入验证
  - OXE机台配置化改造
  - TEL DRM UNITY配置化改造

#### 7.2.3 二三维联动优化
- **优先级**: 🟡 中
- **内容**:
  - 点击2D设备自动跳转3D视角
  - 状态同步（选中/高亮）
  - 设备信息面板统一

### Phase 3：真实数据接入与AI增强（2-4周）

#### 7.3.1 EAP真实数据对接
- **优先级**: 🔴 高
- **内容**:
  - TIBRV→Redis/MQTT桥接
  - 真实RV报文接入测试
  - 关闭模拟器，验证真实数据
- **目标**: 生产环境可用

#### 7.3.2 AI能力升级
- **优先级**: 🟡 中
- **内容**:
  - Dify本地部署 + RAG知识库
  - n8n工作流编排（Oracle/MES/RCMS/FDC）
  - AI查询Lot History + 回放跳转
  - 智能异常诊断
- **目标**: AI可查询Lot历史、告警分析

#### 7.3.3 用户权限管理
- **优先级**: 🟡 中
- **内容**:
  - 登录/角色/权限体系
  - 操作审计日志

### Phase 4：生产级优化（持续）

#### 7.4.1 性能优化
- **优先级**: 🟡 中
- **内容**:
  - 3D模型LOD（多层次细节）
  - API分页优化
  - 前端虚拟滚动
  - DB轮询优化（索引/批量）
  - 闲置设备降频渲染
  - Redis缓存启用

#### 7.4.2 部署优化
- **优先级**: 🟢 低
- **内容**:
  - 一键部署方案完善
  - 数据库初始化脚本
  - Docker容器化部署
  - 性能监控与告警
  - 备份与恢复方案

#### 7.4.3 高级功能（远期）
- **优先级**: 🟢 低
- **内容**:
  - 多机台扩展验证(1000+)
  - 历史数据归档策略
  - 告警通知（邮件/钉钉/企业微信）
  - 数字孪生仿真
  - AR巡检
  - 良率预测

---

## 八、已知问题与风险

### 8.1 已知问题

| 问题 | 影响 | 状态 | 解决方案 |
|------|------|------|----------|
| WebSocket持续重连 | 实时事件推送不稳定 | ⚠️ 待修复 | 检查后端WS服务状态、Vite proxy配置 |
| 3D模型为代码生成 | 模型不够精细 | 📋 待优化 | 替换为Blender导出的GLB |
| WinForm使用tkinter | 不够专业 | 📋 待优化 | 可用C#重写WinForm版本 |
| 配置化程度不足 | 新机台需改代码 | 📋 待完善 | ModelEditor升级后解决 |

### 8.2 风险评估

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| Oracle连接稳定性 | 中 | 后端服务中断 | 连接池+重试机制 |
| DB轮询性能 | 低 | 大量数据查询影响响应 | 增量查询、索引优化 |
| 历史数据量增长 | 中 | 历史回放变慢 | 数据分区、归档策略 |
| EAP真实数据接入不确定 | 中 | 生产环境受限 | 模拟器+WinForm双兜底 |
| 前端动画与事件联动不顺畅 | 低 | 演示效果打折扣 | 优先保证PODOPENER动画流畅 |

### 8.3 待确认事项

| 事项 | 说明 |
|------|------|
| RV消息的具体格式和字段 | 生产环境接入时需确认 |
| 告警等级的完整分类规则 | 目前只有5种常见告警 |
| 历史数据的保留策略 | 保留周期和归档策略 |
| WebSocket重连的根本原因 | 需排查后端WS服务或网络配置 |

---

## 九、参考文档

- [README.md](README.md) - 项目说明
- [docs/项目总结.md](docs/项目总结.md) - 详细项目总结
- [docs/项目统一架构规划.md](docs/项目统一架构规划.md) - 架构设计与规范
- [docs/项目计划说明书.md](docs/项目计划说明书.md) - 项目计划与里程碑
- [docs/3D模型集成指南.md](docs/3D模型集成指南.md) - 3D模型接入规范
- [docs/对接规范文档.md](docs/对接规范文档.md) - 与世庆的协作规范
- [docs/PODOPENER.docx](docs/PODOPENER.docx) - PODOPENER机台业务流程
- [docs/alarmnew.docx](docs/alarmnew.docx) - 告警事件说明

---

*文档维护：每次功能迭代后更新此文档*
