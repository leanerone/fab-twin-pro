# FabTwin Pro - 半导体工厂数字孪生平台

半导体工厂数字孪生平台，支持机台实时监控、历史数据回放、楼层平面图编辑、OHT天车调度可视化及AI辅助查询。

## 技术栈

### 后端
- Python 3.10+
- FastAPI - Web框架
- SQLAlchemy 2.0 - ORM
- SQLite（Demo）/ Oracle 19c（生产）
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
- ✅ 机台详情 - TEL DRM UNITY精细模型 + 7步工艺动画
- ✅ 历史回放 - 实时/回放双模式 + 6档倍速
- ✅ WebSocket实时推送 - 机台状态/事件实时更新
- ✅ AI助手 - 自然语言查询 + 回放跳转
- ✅ 一键部署 - deploy.bat

## 快速开始

### 环境要求
- Python 3.10+
- Node.js 16+
- Git

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
- 后端API：http://localhost:8001/api
- API文档：http://localhost:8001/docs

### 一键部署

```bash
deploy.bat
```

## 项目结构

```
fab-twin-pro/
├── backend/                    # FastAPI 后端
│   ├── main.py                # 入口
│   ├── config.py              # 配置中心
│   ├── models.py              # 16张表 ORM
│   ├── seed_data.py           # 种子数据
│   ├── requirements.txt       # Python依赖
│   ├── routers/               # API路由
│   │   ├── machines.py
│   │   ├── events.py
│   │   ├── lots.py
│   │   ├── alarms.py
│   │   ├── ai.py
│   │   ├── floors.py
│   │   ├── oht.py
│   │   └── recipes.py
│   └── services/              # 业务服务
│       ├── cache.py           # Redis缓存
│       ├── realtime.py        # WebSocket管理
│       ├── simulator.py       # 工艺模拟器
│       ├── ods.py             # ODS数据中台
│       └── ai_mcp.py          # AI MCP框架
├── frontend/                   # Vue3 前端
│   └── src/
│       ├── views/             # 页面
│       │   ├── Dashboard.vue
│       │   └── MachineDetail.vue
│       ├── components/        # 组件
│       │   ├── FloorView3D.vue
│       │   ├── FloorPlan.vue
│       │   ├── MachineModel3D.vue
│       │   └── ...
│       ├── stores/app.js      # Pinia状态
│       └── api/index.js       # API封装
├── deploy.bat                 # 一键部署
├── start-dev.bat              # 开发启动
└── 项目总结.md                # 详细文档
```

## 数据库

### 表结构
- 4张现有表（Oracle对齐）：DT_EVENT_RAW, DT_EVENT_STD, DT_STATE_SNAPSHOT, DT_ALARM_EVENT
- 12张扩展表：machines, lots, recipes, chamber_snapshots, oht_positions, ai_insights, machine_events, alarms, dashboard_kpi, floors, floor_areas, tracks, vehicles

### 切换到Oracle
修改 `backend/config.py`：
```python
DATABASE_URL = "oracle+oracledb://username:password@host:port/service_name"
```

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

- [项目总结.md](项目总结.md) - 详细项目总结
- [项目计划说明书.md](项目计划说明书.md) - 项目规划
- [GitHub_Copilot_开发方案.md](GitHub_Copilot_开发方案.md) - VS Code Copilot使用指南
- [对接规范文档.md](对接规范文档.md) - 与世庆的协作规范

## 开发规范

### 分支策略
- `main` - 稳定版本
- `develop` - 开发版本
- `feature/*` - 功能分支
- `bugfix/*` - 修复分支

### 代码规范
- Python: PEP8
- JavaScript: ESLint + Prettier
- Vue: Vue官方风格指南

## License

MIT
