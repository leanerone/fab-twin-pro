# FabTwin Pro - 半导体工厂数字孪生平台

半导体工厂数字孪生平台，支持机台实时监控、历史数据回放、楼层平面图编辑、OHT天车调度可视化、AI辅助查询、语音识别及统一动画配置管理。

**当前版本**：ver2（2026-07-19）

## 技术栈

### 后端
- Python 3.10+
- FastAPI - Web框架
- SQLAlchemy 2.0 - ORM
- Oracle 19c（生产）/ SQLite（Demo）
- Redis（可选，缓存）
- WebSocket - 实时推送
- faster-whisper - 本地语音识别（CPU/int8离线）
- imageio-ffmpeg - 音频解码

### 前端
- Vue 3.4 + Vite 5
- Pinia - 状态管理
- Vue Router 4 - 路由
- Three.js 0.160 - 3D可视化
- 原生HTML/CSS - UI组件（替代Element Plus）

## 功能特性

- ✅ 主页看板 - 7个KPI卡片 + 楼层选择 + 机台列表
- ✅ 楼层3D视图 - 机台/区域/轨迹/天车 3D可视化
- ✅ 2D平面图编辑器 - 拖拽标注机台/区域/轨迹/天车
- ✅ 机台详情 - 多机型精细模型 + 工艺动画
- ✅ PODOPENER 完整业务流程 - 14步穿入 + 6步脱出 + 报警事件
- ✅ 历史回放 - 实时/回放双模式 + 6档倍速 + 时间轴拖拽
- ✅ WebSocket实时推送 - DB轮询 + 模拟器双模式驱动
- ✅ 统一动画配置层 - podopener.json + useAnimationConfig.js，2D/3D视图共用配置消除偏差
- ✅ 模型编辑器 - 动画配置可视化编辑 + 手动调试触发 + JSON导出 + 开发SOP
- ✅ AI中间适配层 - 规则引擎 + Dify/n8n扩展 + 上下文感知
- ✅ AI配置面板 - 参数热编辑 + 系统Prompt自定义 + 温度/Token调节
- ✅ AI悬浮球 - 全局快速AI对话入口
- ✅ 语音识别 - 本地faster-whisper离线识别，MediaRecorder录音，无需联网
- ✅ 语音播报 - 机台状态/报警语音播报
- ✅ WinForm模拟器 - tkinter GUI，按钮控制流程事件写入DB
- ✅ 一键部署 - deploy.bat

## 快速开始

### 环境要求
- Python 3.10+
- Node.js 16+
- Git
- Oracle客户端（生产环境）
- ffmpeg（语音识别需要，通过pip install imageio-ffmpeg自动安装）

### 安装依赖

```bash
# 后端
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 前端
cd frontend
npm install
```

### 开发模式

```bash
# 方式一：使用启动脚本（Windows）
start-dev.bat

# 方式二：手动启动
# 后端
cd backend
venv\Scripts\activate
python main.py

# 前端（新终端）
cd frontend
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
│   │   ├── ai.py              # AI自然语言查询+语音识别
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
│       ├── ai_mcp.py          # AI MCP调用框架
│       ├── ai_middleware.py   # AI中间适配层（规则引擎+Dify+n8n）
│       └── speech_service.py  # 本地Whisper语音识别服务
├── frontend/                   # Vue3 前端
│   └── src/
│       ├── views/             # 4个页面
│       │   ├── Dashboard.vue      # 主页看板
│       │   ├── MachineDetail.vue # 机台详情
│       │   ├── ModelEditor.vue   # 模型编辑器（配置+调试+指南）
│       │   └── Login.vue         # 登录页
│       ├── components/        # 组件
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
│       │   ├── AiAssistant.vue       # AI助手面板
│       │   ├── AIConfigPanel.vue     # AI配置面板（参数热编辑）
│       │   ├── AIFloatingBall.vue    # AI全局悬浮球
│       │   ├── VoiceInput.vue        # 语音输入组件
│       │   ├── EventAnimationDebugger.vue # 动画调试面板
│       │   ├── EventList.vue         # 事件列表
│       │   ├── AlarmStats.vue        # 告警统计
│       │   └── ...
│       ├── composables/       # 组合式函数
│       │   ├── useThree.js            # Three.js封装
│       │   ├── useIsoProjection.js    # 等角投影
│       │   ├── useWebSocket.js        # WebSocket管理
│       │   ├── useEventActionMapping.js # 事件动作映射
│       │   ├── useAnimationConfig.js  # 统一动画配置加载器
│       │   └── useAuth.js             # 认证
│       ├── configs/             # 配置文件
│       │   └── machine-animations/  # 机台动画配置
│       │       ├── podopener.json    # VPO事件-阶段-动画映射
│       │       └── _schema.json     # 配置Schema校验
│       ├── stores/            # Pinia状态管理
│       │   ├── app.js         # 全局状态
│       │   ├── model.js       # 机台型号配置
│       │   └── auth.js        # 认证状态（支持*通配符权限）
│       └── api/index.js       # API统一封装
├── docs/                       # 归档文档
│   ├── 系统架构说明书.md       # 系统架构详细说明
│   ├── 开发进度管控.md         # 开发里程碑与进度
│   ├── 变更改版记录.md         # 版本变更记录
│   ├── 新机台开发SOP.md       # 新机台开发标准流程
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

## 统一动画配置架构

### 四层架构

```
设备模型描述层 → 统一映射配置层 → 动画动作原语层 → 可视化调试层
   (JSON)          (podopener.json)    (translate/rotate)   (模型编辑器)
```

### 配置文件结构（podopener.json）

```json
{
  "machine_type": "podopener",
  "version": "2.0",
  "flows": {
    "PACKING": {
      "phases": [{ "key": "POD_PLACE", "label": "空POD放置", "duration_ms": 2000 }],
      "event_to_phase": { "POD_PLACED": { "phase": "POD_PLACE", "anim": "pod.enter" } }
    }
  },
  "animations": {
    "pod.enter": { "action": "translate", "target": "pod", "axis": "x", "from": -120, "to": 0, "duration_ms": 2000 }
  },
  "targets": {
    "pod": { "view_2d": "pod2dLayer", "view_3d": "podShell", "desc": "POD外壳" }
  }
}
```

### 模型编辑器工作流

1. **模型管理** - 查看机台型号、创建新型号
2. **动画配置** - 可视化编辑阶段/事件映射/动画原语/部件目标（4个子Tab）
3. **动画调试** - 手动触发事件、阶段跳转、时间轴可视化
4. **导出上线** - 导出JSON覆盖到configs目录，2D/3D视图自动加载

## AI功能

### AI中间适配层

```
用户输入 → ai_middleware.py → 规则引擎(本地) / Dify(云端) / n8n(编排)
                              ↓
                         上下文感知（当前机台/状态/事件）
```

- 本地规则引擎：Lot查询、机台状态、告警统计、温度趋势、产量统计、异常检测
- Dify扩展：对话管理 + RAG知识库
- n8n扩展：工具编排（Oracle/MES/RCMS/FDC）

### AI配置面板

- 系统Prompt自定义
- 温度/最大Token/Top-P 调节
- AI模式切换（规则引擎/Dify/n8n）
- 语音播报开关

### 语音识别

- 前端：MediaRecorder API 录音 → webm/opus 格式上传
- 后端：faster-whisper (CPU/int8) + imageio-ffmpeg 解码
- 完全离线，国内网络可用
- 模型：`openai/whisper-small`（通过 hf-mirror.com 镜像下载）

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

## 文档

- [系统架构说明书](docs/系统架构说明书.md) - 系统架构详细说明
- [开发进度管控](docs/开发进度管控.md) - 开发里程碑与进度
- [变更更改版记录](docs/变更更改版记录.md) - 版本变更记录
- [新机台开发SOP](docs/新机台开发SOP.md) - 新机台开发标准流程
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
