# n8n 接入详细 SOP

> 适用版本：n8n 1.20+  
> 对接系统：FabTwin Pro 数字孪生平台  
> 文档版本：v1.0 (2026-07-27)

---

## 一、n8n 是什么？为什么要接入？

n8n 是一款开源的工作流自动化平台，核心价值：

| 能力 | 说明 | 对 FabTwin 的价值 |
|---|---|---|
| **可视化工作流** | 拖拽式节点编排 | 无需编码即可配置自动化流程 |
| **Webhook 触发** | HTTP 请求触发工作流 | FabTwin AI 对话中触发自动化 |
| **400+ 集成** | 邮件/钉钉/飞书/Oracle/Excel... | 打通 MES/RCMS/FDC/邮件等系统 |
| **条件分支** | IF/Switch/循环节点 | 复杂业务逻辑可视化编排 |
| **错误重试** | 失败自动重试 + 告警 | 生产环境可靠运行 |
| **定时触发** | Cron 定时任务 | 日报/周报自动生成推送 |

### FabTwin 与 n8n 的关系

```
用户问AI："导出PODOPENER-1今天的告警报表"
      │
      ▼
FabTwin AI 中间层（ai_middleware.py）
      │  识别为 n8n 自动化指令
      ▼
n8n Webhook → 工作流执行 → 调用 FabTwin API → 生成报表 → 返回结果
      │
      ▼
AI 把结果返回给用户
```

---

## 二、n8n 部署方式

### 方案 A：Docker 一键部署（推荐）

```bash
# 创建数据目录
mkdir -p ~/.n8n

# 启动 n8n
docker run -it --rm \
  --name n8n \
  -p 5678:5678 \
  -v ~/.n8n:/home/node/.n8n \
  n8nio/n8n
```

启动后访问 `http://localhost:5678`，首次进入设置账号密码。

### 方案 B：npm 安装

```bash
npm install n8n -g
n8n start
```

### 方案 C：n8n Cloud 官方云服务

访问 https://n8n.io/cloud，注册后直接使用（免费额度有限）。

---

## 三、第一步：导入工作流模板

模板文件位置：

| 序号 | 文件名 | 用途 | Webhook 路径 |
|---|---|---|---|
| 1 | [01_export_alarm_report.json](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/docs/integration/n8n/01_export_alarm_report.json) | 导出告警报表 | `/webhook/export_alarm_report` |
| 2 | [02_generate_work_order.json](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/docs/integration/n8n/02_generate_work_order.json) | 生成故障工单 | `/webhook/generate_work_order` |
| 3 | [03_export_machine_data.json](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/docs/integration/n8n/03_export_machine_data.json) | 批量导出设备数据 | `/webhook/export_machine_data` |
| 4 | [04_push_daily_report.json](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/docs/integration/n8n/04_push_daily_report.json) | 产线日报自动推送 | `/webhook/push_daily_report` |
| 5 | [05_general_query.json](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/docs/integration/n8n/05_general_query.json) | 通用查询（转发给 AI） | `/webhook/general_query` |

### 导入步骤（每个工作流都一样）

1. 登录 n8n → 左上角「工作流」→「新建工作流」
2. 点击右上角「⋯」菜单 → 「从文件导入」
3. 选择对应的 JSON 文件
4. 导入后点击「保存」，给工作流命名
5. **重要**：点击 Webhook 节点 → 复制「Webhook URL」备用

### 导入后检查项

- [ ] 工作流画布上节点连接正确
- [ ] 左上角「测试执行」可以点击
- [ ] Webhook 节点显示「正在监听」（需先激活）

---

## 四、第二步：配置 Webhook 安全

生产环境必须给 Webhook 加上密钥，防止未授权调用。

### 4.1 设置 Webhook Secret

方法一：在每个 Webhook 节点中设置

1. 点击 Webhook 节点
2. 「认证」→ 选择「Header Auth」或「Query Auth」
3. 设置密钥（如 `fabtwin_secret_2026`）

方法二：n8n 全局 Webhook 密钥（推荐）

在 n8n 环境变量中设置：

```bash
N8N_WEBHOOK_SECRET=fabtwin_secret_2026
```

这样所有 Webhook 都需要 `?secret=xxx` 才能访问。

### 4.2 在 FabTwin 中配置 n8n

#### 方法一：AI 配置面板（推荐）

1. 登录 FabTwin admin 账号
2. 进入「AI 配置管理」
3. 找到 N8N 配置区域：
   - **启用 N8N**：打开开关
   - **N8N 服务地址**：填入你的 n8n 地址（如 `http://localhost:5678`）
   - **N8N Webhook 密钥**：填入刚才设置的 secret
4. 点击「保存」

#### 方法二：环境变量

```powershell
$env:N8N_ENABLED = "True"
$env:N8N_BASE_URL = "http://localhost:5678"
$env:N8N_WEBHOOK_SECRET = "fabtwin_secret_2026"
```

---

## 五、第三步：配置 FabTwin API 连接

工作流模板中所有 HTTP 请求节点的 URL 都用了占位符 `https://your-fabtwin-backend`，需要改成你实际的后端地址。

### 5.1 修改步骤（以导出告警报表为例）

1. 打开「导出告警报表」工作流
2. 双击「调用告警 API」HTTP 节点
3. 把 URL 中的 `https://your-fabtwin-backend` 改成实际地址：
   - 本地开发：`http://localhost:8000`
   - 服务器部署：`https://your-domain.com`
4. 根据需要配置认证（如果后端需要 API Key）
5. 点击「保存」

### 5.2 需要修改的节点清单

| 工作流 | 节点名称 | 默认 API 路径 |
|---|---|---|
| 导出告警报表 | 调用告警 API | `/api/ai/alarms` |
| 生成故障工单 | 获取最新告警 | `/api/ai/alarms` |
| 批量导出设备数据 | 获取机台列表 | `/api/machines` |
| | 获取告警数据 | `/api/ai/alarms` |
| | 获取 Lot 数据 | `/api/ai/lot-info` |
| 产线日报推送 | 获取产量统计 | `/api/ai/yield-stats` |
| | 获取告警汇总 | `/api/ai/alarms` |
| 通用查询 | 调用 FabTwin AI | `/api/ai/chat` |

### 5.3 验证 API 连通性

在每个 HTTP 节点中：
1. 点击「测试执行」
2. 看是否返回 200 和正确的数据
3. 如果报错，检查：
   - URL 是否正确
   - 后端服务是否启动
   - 网络是否通
   - 认证信息是否正确

---

## 六、第四步：激活工作流并测试

### 6.1 激活工作流

1. 打开工作流
2. 右上角「非活动」切换为「活动」
3. Webhook 节点变为「正在监听」状态

### 6.2 使用 curl 测试

```bash
# 测试导出告警报表
curl -X POST "http://localhost:5678/webhook/export_alarm_report?secret=fabtwin_secret_2026" `
  -H "Content-Type: application/json" `
  -d '{
    "question": "导出PODOPENER-1的告警报表",
    "machine_id": "PODOPENER-1",
    "user_role": "admin",
    "workflow_type": "export_alarm_report"
  }'
```

预期返回：

```json
{
  "answer": "告警报表已生成，共 15 条告警记录...",
  "data": [...],
  "workflow": "export_alarm_report",
  "status": "success"
}
```

### 6.3 在 FabTwin AI 中测试

1. 确保 n8n 已配置并启用
2. 登录 admin 账号（n8n 自动化仅 admin 可用）
3. 打开 AI 对话框
4. 输入触发指令：
   - `导出PODOPENER-1的告警报表`
   - `生成故障工单`
   - `导出设备数据`
   - `推送日报`
5. 观察 AI 返回是否带 `[N8N自动化]` 前缀

### 6.4 n8n 执行日志查看

1. 打开 n8n 工作流
2. 左侧「执行」标签
3. 可以看到每次执行的：
   - 触发时间
   - 执行状态（成功/失败）
   - 每个节点的输入输出
   - 错误信息（如果失败）

---

## 七、工作流触发规则详解

FabTwin AI 中间层通过**关键字匹配**来判断是否调用 n8n，规则定义在 `ai_middleware.py` 的 `_is_n8n_command` 和 `_trigger_n8n_workflow` 中。

### 7.1 关键字映射表

| 触发关键字 | 工作流类型 | Webhook 路径 | 示例 |
|---|---|---|---|
| 导出 + 告警/报警 | `export_alarm_report` | `/webhook/export_alarm_report` | "导出PODOPENER-1的告警报表" |
| 工单 / 故障 | `generate_work_order` | `/webhook/generate_work_order` | "给这台机生成故障工单" |
| 导出 + 数据 | `export_machine_data` | `/webhook/export_machine_data` | "批量导出设备数据" |
| 报表 + 推送 | `push_daily_report` | `/webhook/push_daily_report` | "推送今天的产线日报" |
| 其他（默认） | `general_query` | `/webhook/general_query` | 无法识别的指令 |

### 7.2 请求参数结构

FabTwin 发给 n8n 的请求体格式：

```json
{
  "question": "用户原始问题",
  "machine_id": "PODOPENER-1",
  "user_role": "admin",
  "workflow_type": "export_alarm_report",
  "timestamp": "2026-07-27T10:30:00.000Z"
}
```

### 7.3 返回参数结构

n8n 需要返回给 FabTwin 的格式：

```json
{
  "answer": "AI显示给用户的文本",
  "sql": "可选，查询SQL",
  "data": [
    // 可选，表格数据（数组）
  ],
  "jump_timestamp": "可选，跳转回放时间戳",
  "jump_machine_id": "可选，跳转回放机台ID"
}
```

---

## 八、进阶：自定义工作流开发

### 8.1 工作流开发步骤

1. **明确需求**：这个自动化要做什么？输入输出是什么？
2. **设计节点**：画出节点流程图
3. **选择触发方式**：Webhook / 定时 / 手动
4. **添加处理节点**：HTTP 请求 / 数据处理 / 条件分支
5. **配置返回**：用「Respond to Webhook」节点返回结果
6. **测试验证**：用 curl 或 AI 对话测试
7. **上线激活**：切换为「活动」状态

### 8.2 常用节点速查

| 节点 | 用途 | 场景 |
|---|---|---|
| Webhook | HTTP 触发工作流 | AI 对话触发自动化 |
| Cron | 定时触发 | 日报/周报自动生成 |
| HTTP Request | 调用外部 API | 调用 FabTwin API |
| Set | 设置变量 | 解析请求参数 |
| IF | 条件判断 | 有告警才开工单 |
| Code (JavaScript) | 自定义逻辑 | 复杂数据处理 |
| Spreadsheet File | 生成 CSV/Excel | 导出报表 |
| Send Email | 发送邮件 | 告警通知、日报推送 |
| Slack / 钉钉 / 飞书 | 消息推送 | 即时通知 |
| MySQL / PostgreSQL | 数据库操作 | 直接查生产库 |

### 8.3 新增工作流后如何接入 AI

如果你新增了一个工作流（比如"设备保养提醒"），需要做两件事：

1. **n8n 侧**：创建工作流，Webhook 路径设为 `maintenance_reminder`
2. **FabTwin 侧**：修改 `ai_middleware.py`，在 `_trigger_n8n_workflow` 中增加关键字匹配：

```python
# 在识别工作流类型的 if-elif 链中添加
elif "保养" in question or "维护" in question:
    workflow_type = "maintenance_reminder"
```

3. 在 AI 配置面板的 n8n 说明中补充支持的流程列表

---

## 九、生产环境部署建议

### 9.1 安全加固

| 措施 | 说明 |
|---|---|
| Webhook Secret | 所有 Webhook 必须带密钥 |
| HTTPS | 生产环境必须启用 HTTPS |
| 网络隔离 | n8n 部署在内网，不暴露公网 |
| 访问控制 | n8n 后台设置强密码，启用 2FA |
| 权限最小化 | 数据库账号只给 SELECT 权限 |

### 9.2 高可用

```
              ┌── n8n 主节点 ──┐
负载均衡 ─────┤                ├──── PostgreSQL（主从）
              └── n8n 备节点 ──┘
```

- 使用 PostgreSQL 替换 SQLite 作为元数据库
- 多节点部署共享队列
- 定时备份工作流定义

### 9.3 监控告警

- n8n 执行失败自动发邮件/钉钉通知
- 监控工作流执行时长
- 监控 Webhook 调用频率
- 日志收集到 ELK / Loki

---

## 十、常见问题排查

| 问题 | 原因 | 解决方法 |
|---|---|---|
| AI 返回「N8N 自动化服务未配置」 | n8n 未启用或地址错误 | 检查 AI 配置面板的 n8n 设置 |
| AI 返回「需要管理员权限」 | 当前用户不是 admin | n8n 自动化仅 admin 可调用，这是安全设计 |
| n8n 工作流执行失败 | HTTP 节点请求错误 | 查看执行日志，检查 URL 和参数 |
| 工作流激活了但收不到请求 | Webhook URL 不对或网络不通 | 用 curl 直接测试 Webhook URL |
| 返回的数据 AI 显示不正常 | 返回格式不符合约定 | 确保返回 `answer` 字段，表格数据放 `data` |
| 工作流执行很慢 | 某个节点耗时太长 | 检查是哪个节点慢，优化 API 或增加超时时间 |

---

## 十一、学习资源

- **n8n 官方文档**：https://docs.n8n.io
- **n8n 模板库**：https://n8n.io/workflows
- **n8n 社区论坛**：https://community.n8n.io
- **B站教程**：搜索「n8n 教程」有大量中文资源

---

下一份文档：[Dify + n8n 联合开发教学](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/docs/integration/DIFY_N8N_ADVANCED_GUIDE.md)
