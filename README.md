# FabTwin Pro - 半导体工厂数字孪生平台

半导体工厂数字孪生平台，支持机台实时监控、历史数据回放、楼层平面图编辑、OHT天车调度可视化及AI辅助查询。

**当前版本**：ver2（2026-07-19）

## 技术栈

### 后端
- Python 3.10+
- FastAPI - Web框架
- SQLAlchemy 2.0 - ORM
- Oracle 19c（生产）/ SQLite（Demo）
- Redis（可选，缓存）
- WebSocket - 实时推送

### 前端
- Vue 3.4 + Vite 5
- Pinia - 状态管理
- Vue Router 4 - 路由
- Three.js 0.160 - 3D可视化
- Element Plus - UI组件库

## 功能特性

- ✅ 主页看板 - 7个KPI卡片 + 楼层选择 + 机台列表
- ✅ 楼层3D视图 - 机台/区域/轨迹/天车 3D可视化
- ✅ 2D平面图编辑器 - 拖拽标注机台/区域/轨迹/天车
- ✅ 机台详情 - 多机型精细模型 + 工艺动画
- ✅ PODOPENER 完整业务流程 - 14步穿入 + 6步脱出 + 报警事件
- ✅ 历史回放 - 实时/回放双模式 + 6档倍速 + 时间轴拖拽
- ✅ WebSocket实时推送 - DB轮询 + 模拟器双模式驱动
- ✅ 事件-阶段映射 - 14个事件全部匹配2D/3D动画阶段
- ✅ WinForm模拟器 - tkinter GUI，按钮控制流程事件写入DB
- ✅ AI助手 - 自然语言查询 + 回放跳转
- ✅ 一键部署 - deploy.bat

## 快速开始

### 环境要求
- Python 3.10+
- Node.js 16+
- Git
- Oracle客户端（生产环境）

### 开发模式

```bash
# 方式一：使用启动脚本（Windows）
start-dev.bat

# 方式二：手动启动
# 后端
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py

# 前端（新终端）
cd frontend
npm install
npm run dev
```

### 访问地址
- 前端：http://localhost:5173
- 后端API：http://localhost:8002/api
- API文档：http://localhost:8002/docs
- WebSocket：ws://localhost:8002/ws/realtime

### WinForm 模拟器

```bash
# 在项目根目录运行
python winform_simulator.py
```

功能：
- 单步执行穿入/脱出流程每个事件
- 自动执行完整流程（每步间隔1.5秒）
- 5种报警模拟
- 实时事件日志

### 一键部署

```bash
deploy.bat
```

## 项目结构

```
fab-twin-pro-ver1/
├── backend/                    # FastAPI 后端
│   ├── main.py                # 入口（路由注册+WS+启动）
│   ├── config.py              # 配置中心（DB/Redis/AI/ODS/模拟器/轮询）
│   ├── models.py              # 19张表 ORM 模型
│   ├── schemas.py             # Pydantic 模型
│   ├── database.py            # 数据库连接
│   ├── seed_data.py           # 种子数据生成
│   ├── gen_podopener_history.py # 生成PODOPENER 7天历史数据
│   ├── create_cur_table.py    # 创建DT_EVENT_RAW_CUR表
│   ├── import_sql.py          # SQL导入工具
│   ├── rvsimulator.py         # RV消息模拟器
│   ├── requirements.txt       # Python依赖
│   ├── routers/               # 12个API路由模块
│   │   ├── machines.py        # 机台+KPI统计
│   │   ├── history.py         # 历史数据回放API
│   │   ├── events.py          # 事件+趋势时间轴
│   │   ├── lots.py            # 批次查询
│   │   ├── alarms.py          # 告警统计
│   │   ├── ai.py              # AI自然语言查询
│   │   ├── floors.py          # 楼层/区域/轨迹/天车CRUD
│   │   ├── oht.py             # 天车位置
│   │   ├── recipes.py         # 工艺配方
│   │   ├── models.py          # 机台型号配置CRUD
│   │   ├── auth.py            # 认证
│   │   └── rvmessages.py      # RV消息接收API
│   └── services/              # 业务服务层
│       ├── cache.py           # Redis缓存（含内存回退）
│       ├── realtime.py        # WebSocket连接管理
│       ├── simulator.py       # 工艺模拟器+PODOPENER流程模拟器
│       ├── db_poller.py       # DB事件轮询服务（外部写入驱动）
│       ├── ods.py             # ODS数据中台
│       └── ai_mcp.py          # AI MCP调用框架
├── frontend/                   # Vue3 前端
│   └── src/
│       ├── views/             # 4个页面
│       │   ├── Dashboard.vue      # 主页看板
│       │   ├── MachineDetail.vue # 机台详情
│       │   ├── ModelEditor.vue   # 模型编辑器
│       │   └── Login.vue         # 登录页
│       ├── components/        # 18个组件
│       │   ├── FloorView3D.vue       # 楼层3D视图
│       │   ├── FloorPlan.vue         # 2D平面图编辑器
│       │   ├── MachineModel3D.vue    # TEL DRM UNITY精细模型
│       │   ├── MachineModel2D.vue    # 2D原理图
│       │   ├── MachineIsoView.vue    # OXE等角2.5D视图
│       │   ├── MachineVpoView.vue    # PODOPENER 2D视图
│       │   ├── MachineVpo3DView.vue  # PODOPENER 3D视图
│       │   ├── HistoryReplay.vue     # 历史回放时间轴
│       │   ├── PlaybackBar.vue       # 播放控制条
│       │   ├── KpiCards.vue          # KPI卡片
│       │   ├── AiAssistant.vue       # AI助手
│       │   ├── EventList.vue         # 事件列表
│       │   ├── AlarmStats.vue        # 告警统计
│       │   └── ...
│       ├── composables/       # 5个组合式函数
│       │   ├── useThree.js            # Three.js封装
│       │   ├── useIsoProjection.js    # 等角投影
│       │   ├── useWebSocket.js        # WebSocket管理
│       │   ├── useEventActionMapping.js # 事件动作映射
│       │   └── useAuth.js             # 认证
│       ├── stores/            # 3个Pinia状态管理
│       │   ├── app.js         # 全局状态
│       │   ├── model.js       # 机台型号配置
│       │   └── auth.js        # 认证状态
│       └── api/index.js       # API统一封装
├── docs/                       # 归档文档
│   ├── 项目总结.md            # 详细项目总结
│   ├── 项目统一架构规划.md     # 架构设计与规范
│   ├── 项目计划说明书.md       # 项目计划与里程碑
│   ├── 3D模型集成指南.md       # 3D模型接入规范
│   ├── GitHub_Copilot_开发方案.md # VS Code Copilot使用指南
│   ├── 对接规范文档.md         # 与世庆的协作规范
│   ├── PODOPENER.docx         # PODOPENER业务参考
│   ├── alarmnew.docx          # 报警事件说明
│   ├── VPO_2D.docx            # VPO 2D设计文档
│   ├── alarm.docx             # 告警参考文档
│   ├── OXE_2D.html            # OXE 2D原型
│   ├── VPO2D.html             # VPO 2D原型
│   ├── VPO_3D.HTML            # VPO 3D原型
│   └── 项目.txt               # 项目技术规范
├── scripts/                    # 工具脚本
│   └── extract_vpo_model.py   # VPO模型提取工具
├── sql/                        # SQL脚本
│   └── init_oracle_db.sql     # Oracle初始化脚本
├── winform_simulator.py       # WinForm(tkinter)模拟器
├── PROJECT_STATUS.md          # 项目进度文档
├── deploy.bat                 # 一键部署
├── start-dev.bat              # 开发启动
├── init_db.bat                # 数据库初始化
├── create_user.bat            # 创建数据库用户
└── create_user.sql            # 创建用户SQL
```

## 数据库

### 表结构（19张表）

**5张Oracle对齐表**：
| 表名 | 说明 |
|------|------|
| `dt_event_raw` | 原始事件表（RV报文，TIBRV来源） |
| `dt_event_raw_cur` | 当前状态表（每台机台最新RV消息） |
| `dt_event_std` | 标准化事件表 |
| `dt_state_snapshot` | 状态快照表 |
| `dt_alarm_event` | 告警事件表 |

**14张扩展表**：
machines, machine_events, lots, recipes, chamber_snapshots, oht_positions, ai_insights, alarms, dashboard_kpi, floors, floor_areas, tracks, vehicles, machine_model_configs, event_action_mappings

### 切换到Oracle

修改 `backend/config.py`：
```python
DATABASE_URL = "oracle+oracledb://username:password@host:port/service_name"
```

## PODOPENER 业务流程

### 穿入流程（PACKING）- 14个事件

| 序号 | 事件名 | 说明 | 对应动画阶段 |
|------|--------|------|-------------|
| 1 | POD_PLACED | POD放置到位 | 空POD放置 |
| 2 | COMPLETED_PORT_LOCK | 端口锁定完成 | POD锁定 |
| 3 | READ_BATTERY | 读取电池状态 | 扫描标签 |
| 4 | READ_TAG | 读取RFID标签 | 扫描标签 |
| 5 | BATCH_INFO_FROM_ECUI | 获取批次信息 | 批次开始 |
| 6 | OPEN_POD | 打开POD盖 | POD上升 |
| 7 | REACH_STAGE | 机械臂到达平台 | POD到达平台 |
| 8 | UI_CONFIRM | 操作员确认 | UI确认 |
| 9 | CLOSE_POD | 关闭POD盖 | POD下降 |
| 10 | ACK_UI_DOUBLECHECK | 二次确认 | UI二次确认 |
| 11 | REACH_POS | 机械臂到位 | POD到位 |
| 12 | WRITE_TAG | 写入RFID标签 | 写入标签 |
| 13 | COMPLETED_PORT_UNLOCK | 端口解锁完成 | POD解锁 |
| 14 | POD_REMOVED | POD移走 | 满POD移走 |

### 脱出流程（UNPACKING）- 6个事件

| 序号 | 事件名 | 说明 |
|------|--------|------|
| 1 | UI_CONFIRM | 操作员确认 |
| 2 | CLOSE_POD | 关闭POD盖 |
| 3 | REACH_POS | 机械臂到位 |
| 4 | WRITE_TAG | 写入RFID标签 |
| 5 | COMPLETED_PORT_UNLOCK | 端口解锁完成 |
| 6 | POD_REMOVED | POD移走 |

## 双模式实时驱动架构

### 模式一：内部模拟器（Demo用）

```
simulator.py 定时器 → 写入DT_EVENT_RAW → db_poller轮询 → WebSocket → 前端动画
```

配置开关（config.py）：
```python
SIMULATION_ENABLED = True
SIMULATION_INTERVAL_MS = 2000
```

### 模式二：外部DB写入（生产/WinForm用）

```
WinForm模拟器/EAP系统 → 写入DT_EVENT_RAW → db_poller轮询 → WebSocket → 前端动画
```

配置开关（config.py）：
```python
DB_POLLER_ENABLED = True
DB_POLLER_INTERVAL_MS = 1000
```

## 机台型号配置

| 型号ID | 型号名称 | 工艺类型 | 视图模式 | 机台实例 |
|--------|---------|---------|---------|---------|
| VPO-2200 | PODOPENER 开盖机 | PODOPENER | vpo/vpo3d | PODOPENER-1 |
| TEL-DRM-UNIT | TEL DRM UNITY 刻蚀机 | ETCH | isometric | T01, T09, T11, T15 |
| GENERIC-ETCH | 通用刻蚀机 | ETCH | threejs | 其他ETCH机台 |

## 楼层说明

| 楼层 | 名称 | 机台数 |
|------|------|--------|
| 1F | 测试与分选区 | ~10台 |
| 2F | 电梯与通道(办公区) | ~5台 |
| 3F | 主生产楼层 | ~15台 |
| 4F | 刻蚀区扩展 | ~12台 |

## AI功能

### 当前实现（本地规则引擎）
- Lot号查询 + 回放跳转
- 机台状态查询
- 告警统计分析
- 温度趋势分析
- 产量统计
- 异常检测

### 扩展方案（Dify + n8n）
1. 部署 Dify - 对话管理 + RAG知识库
2. 部署 n8n - 工具编排（Oracle/MES/RCMS/FDC）
3. 配置 `backend/config.py` 中 AI MCP 参数

## 文档

- [PROJECT_STATUS.md](PROJECT_STATUS.md) - 项目进度与后续开发计划
- [docs/项目总结.md](docs/项目总结.md) - 详细项目总结
- [docs/项目统一架构规划.md](docs/项目统一架构规划.md) - 架构设计与规范
- [docs/项目计划说明书.md](docs/项目计划说明书.md) - 项目计划与里程碑
- [docs/3D模型集成指南.md](docs/3D模型集成指南.md) - 3D模型接入规范
- [docs/对接规范文档.md](docs/对接规范文档.md) - 与世庆的协作规范

## 开发规范

### 分支策略
- `main` - 稳定版本
- `ver1` / `ver2` - 版本迭代
- `feature/*` - 功能分支
- `bugfix/*` - 修复分支

### 代码规范
- Python: PEP8
- JavaScript: ESLint + Prettier
- Vue: Vue官方风格指南

## License

MIT
