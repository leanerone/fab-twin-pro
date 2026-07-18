# FabTwin 项目进度文档 - PODOPENER-1 改造

## 📅 更新日期
2026-07-18

---

## 一、已完成工作总结

### 1.1 功能开发完成清单

| 功能 | 状态 | 完成日期 | 说明 |
|------|------|----------|------|
| VPO-01 名称残留修复 | ✅ 已完成 | 2026-07-18 | 前端所有VPO引用替换为PODOPENER |
| DT_EVENT_RAW_CUR 表创建 | ✅ 已完成 | 2026-07-18 | Oracle数据库中创建当前状态表 |
| 历史回放 UNKNOWN 修复 | ✅ 已完成 | 2026-07-18 | 事件名称正确显示，分类完整 |
| DB轮询服务 | ✅ 已完成 | 2026-07-18 | 每秒轮询DB，WebSocket实时推送 |
| PODOPENER 7天历史数据 | ✅ 已完成 | 2026-07-18 | 10920条事件，含随机告警 |
| WinForm 模拟器 | ✅ 已完成 | 2026-07-18 | tkinter实现，支持单步/自动/报警 |
| VPO3D 去除流程按钮 | ✅ 已完成 | 2026-07-18 | 移除POD穿入/脱出/开始循环按钮 |
| 前端事件动作映射 | ✅ 已完成 | 2026-07-18 | useEventActionMapping.js扩展 |
| 项目总结文档 | ✅ 已完成 | 2026-07-18 | 项目总结.md |
| 架构规划文档 | ✅ 已完成 | 2026-07-18 | 项目统一架构规划.md |
| 功能测试验证 | ✅ 已完成 | 2026-07-18 | 90%通过率（9/10项） |

### 1.2 功能测试结果

```
测试通过率: 9/10 (90%)

✅ PASS - 健康检查
✅ PASS - 机台列表API (38台机台)
✅ PASS - PODOPENER-1机台详情
✅ PASS - 历史事件查询 (10920条)
✅ PASS - 单日时间轴
✅ PASS - 告警历史
✅ PASS - 楼层列表 (4层)
✅ PASS - 机台型号配置 (3种)
✅ PASS - 批次列表 (1505批)
```

### 1.3 数据库现状

- **数据库**: Oracle 19c (PDB: ORCLPDB)
- **用户**: fabtwin
- **机台数据**: 38台机台，PODOPENER-1已就绪
- **历史数据**: PODOPENER-1共10920条事件（7天）
- **当前状态表**: DT_EVENT_RAW_CUR 已创建并投入使用

---

## 二、PODOPENER 业务流程

### 2.1 穿入流程（PACKING）- 14个事件

| 序号 | 事件名 | 中文说明 | 典型间隔 |
|------|--------|----------|----------|
| 1 | POD_PLACED | POD放置到位 | 0s |
| 2 | COMPLETED_PORT_LOCK | 端口锁定完成 | 3-4s |
| 3 | READ_BATTERY | 读取电池状态 | 1s |
| 4 | READ_TAG | 读取RFID标签 | 1-2s |
| 5 | BATCH_INFO_FROM_ECUI | 获取批次信息 | 1s |
| 6 | OPEN_POD | 打开POD盖 | 10s |
| 7 | REACH_STAGE | 机械臂到达平台 | 3s |
| 8 | UI_CONFIRM | 操作员确认 | 变化大 |
| 9 | CLOSE_POD | 关闭POD盖 | 10s |
| 10 | ACK_UI_DOUBLECHECK | 二次确认 | 变化大 |
| 11 | REACH_POS | 机械臂到位 | 3s |
| 12 | WRITE_TAG | 写入RFID标签 | 3s |
| 13 | COMPLETED_PORT_UNLOCK | 端口解锁完成 | 3-4s |
| 14 | POD_REMOVED | POD移走 | 变化大 |

**总时长**: 约40-60秒（不含人工操作）

### 2.2 脱出流程（UNPACKING）- 6个事件

| 序号 | 事件名 | 中文说明 | 典型间隔 |
|------|--------|----------|----------|
| 1 | UI_CONFIRM | 操作员确认 | 0s |
| 2 | CLOSE_POD | 关闭POD盖 | 10s |
| 3 | REACH_POS | 机械臂到位 | 3s |
| 4 | WRITE_TAG | 写入RFID标签 | 3s |
| 5 | COMPLETED_PORT_UNLOCK | 端口解锁完成 | 5s |
| 6 | POD_REMOVED | POD移走 | 变化大 |

**总时长**: 约20-30秒（不含人工操作）

### 2.3 常见报警

| alarm_id | 说明 | 严重程度 |
|----------|------|----------|
| 0201 | 电池电压异常 | warn |
| 9003 | 测试机时间快到了 | info |
| 9004 | 超过测试限Run批数 | warn |
| 0411 | POD/Cassette清洗到期 | info |
| 20011 | DirtyBit不匹配 | warn |

---

## 三、双模式实时驱动架构

### 3.1 模式一：内部模拟器（Demo用）

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

**配置开关** (config.py):
```python
SIMULATION_ENABLED = True
SIMULATION_INTERVAL_MS = 2000
```

### 3.2 模式二：外部DB写入（生产/WinForm用）

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

**配置开关** (config.py):
```python
DB_POLLER_ENABLED = True
DB_POLLER_INTERVAL_MS = 1000
```

---

## 四、项目文件结构

```
fab-twin-pro-ver1/
├── backend/
│   ├── main.py                 # FastAPI入口
│   ├── config.py               # 配置文件
│   ├── models.py               # 数据库模型（含DT_EVENT_RAW_CUR）
│   ├── database.py             # 数据库连接
│   ├── seed_data.py            # 初始化数据
│   ├── gen_podopener_history.py # 生成7天历史数据
│   ├── winform_simulator.py    # WinForm模拟器（tkinter）
│   ├── full_test.py            # 完整功能测试脚本
│   ├── routers/
│   │   ├── machines.py         # 机台API
│   │   ├── history.py          # 历史回放API
│   │   └── ...
│   └── services/
│       ├── simulator.py        # 内部模拟器
│       ├── db_poller.py        # DB轮询服务（新增）
│       └── realtime.py         # WebSocket管理
├── frontend/
│   └── src/
│       ├── composables/
│       │   └── useEventActionMapping.js  # 事件动作映射
│       ├── views/
│       │   ├── MachineDetail.vue
│       │   └── ...
│       └── ...
├── 项目总结.md
├── 项目统一架构规划.md
└── PROJECT_STATUS.md (本文件)
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
cd n:\AI\fab-twin-pro-ver1\backend
.\venv\Scripts\python.exe winform_simulator.py
```

### 5.4 重新生成历史数据
```powershell
cd n:\AI\fab-twin-pro-ver1\backend
.\venv\Scripts\python.exe gen_podopener_history.py
```

### 5.5 运行功能测试
```powershell
cd n:\AI\fab-twin-pro-ver1\backend
.\venv\Scripts\python.exe full_test.py
```

---

## 六、下一步计划

### 6.1 短期任务（近期）

#### 任务1：历史回放功能完善
- **优先级**: 高
- **内容**:
  - 日期选择器优化
  - 回放速度控制 (0.5x - 16x)
  - 时间轴进度条拖动
  - Lot号快速跳转
  - 事件详情面板优化

#### 任务2：二三维联动优化
- **优先级**: 中
- **内容**:
  - 点击2D设备自动跳转3D视角
  - 状态同步（选中/高亮）
  - 设备信息面板统一

#### 任务3：前端构建验证
- **优先级**: 中
- **内容**:
  - 验证 `npm run build` 正常
  - 生产环境打包测试
  - 修复可能的构建错误

### 6.2 中期任务（下月）

#### 任务4：AI助手集成
- **内容**: Dify对话管理，自然语言查询Lot号
- **目标**: 支持Material Lot号查询，直接跳转到回放时间

#### 任务5：动作码映射表配置界面
- **内容**: 前端可视化配置事件→动作的映射关系
- **目标**: 支持新增设备快速配置，无需改代码

#### 任务6：TIBRV数据接入（真实数据）
- **内容**: 通过Redis/MQTT桥接接入真实RV消息
- **目标**: 生产环境可用

### 6.3 长期任务（后续）

#### 任务7：AI异常检测
- **内容**: 集成AI进行数据查询和异常检测
- **包括**: Dify对话管理、RAG知识库、N8N自动化工作流

#### 任务8：性能优化
- **内容**: 数据库索引优化、前端防抖节流、闲置设备降频渲染

#### 任务9：部署优化
- **内容**: 一键部署方案，完善deploy.bat，数据库初始化脚本

---

## 七、API接口清单

### 7.1 机台接口
| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/machines` | 获取机台列表 |
| GET | `/api/machines/{machine_id}` | 获取机台详情 |
| GET | `/api/machines/stats` | 获取机台统计KPI |

### 7.2 历史回放接口
| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/history/{tool_id}` | 获取历史事件时间轴 |
| GET | `/api/history/{tool_id}/timeline` | 获取时间轴摘要（按小时聚合） |
| GET | `/api/history/{tool_id}/alarms` | 获取告警历史 |

### 7.3 WebSocket接口
| 路径 | 描述 |
|------|------|
| `/ws/realtime` | 实时数据推送（DB轮询+模拟器） |

### 7.4 状态接口
| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |

---

## 八、风险与注意事项

### 8.1 已知风险
| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Oracle连接稳定性 | 后端服务中断 | 连接池+重试机制 |
| DB轮询性能 | 大量数据查询影响响应 | 增量查询、索引优化 |
| 历史数据量增长 | 历史回放变慢 | 数据分区、归档策略 |

### 8.2 待确认事项
| 事项 | 说明 |
|------|------|
| RV消息的具体格式和字段 | 生产环境接入时需确认 |
| 告警等级的完整分类规则 | 目前只有5种常见告警 |
| 历史数据的保留策略 | 保留周期和归档策略 |

---

## 九、参考文档

- `项目总结.md` - 项目功能详细总结
- `项目统一架构规划.md` - 架构设计与规范
- `PODOPENER.docx` - PODOPENER机台业务流程
- `alarmnew.docx` - 告警事件说明
- `项目.txt` - 项目技术规范和需求

---

*文档维护：每次功能迭代后更新此文档*
