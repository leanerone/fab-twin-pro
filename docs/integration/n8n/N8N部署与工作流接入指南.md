# n8n 本地部署与工作流接入完整指南
> 文档版本: v1.0 (2026-08-28)
> 代码基线: FabTwin Pro ver2.7.1+
> 适用环境: Windows Server 2022 / Win11 Pro / Ubuntu 22.04
> n8n 版本: 1.20+ (latest)
> 前置条件: Docker Desktop / Docker Engine ≥ 24

---

## 一、部署总览

```
┌────────────────────────────────────────────┐
│           n8n 服务器 (可复用 Dify 机器)     │
│  ┌──────────────┐  ┌────────────────────┐  │
│  │ n8n (5678)   │  │ PostgreSQL 15:5434│  │
│  │ Web UI + API │←│ (n8n 业务持久化)    │  │
│  └──────┬───────┘  └────────────────────┘  │
│         │  Webhook 回调                     │
│         │  /webhook/export_alarm_report     │
│         │  /webhook/generate_work_order     │
│         │  /webhook/export_machine_data     │
│         │  /webhook/push_daily_report       │
│         │  /webhook/general_query           │
└─────────┼──────────────────────────────────┘
          │ HTTP Webhook 触发
┌─────────┴──────────────────────────────────┐
│                 FabTwin Pro 平台              │
│   后端 ai_middleware._trigger_n8n_workflow() │
│   前端 AIConfigPanel [Dify/N8N] Tab          │
│   本地规则引擎：管理员问"导出告警报表"→触发 │
└─────────────────────────────────────────────┘
```

**资源需求**（可与 Dify 共服务器）

| 规模 | CPU | 内存 | 磁盘 | 用途 |
|---|---|---|---|---|
| 开发测试 | 1 核 | 1 GB | 10 GB | 5 工作流 + 低频触发 |
| 小量产  | 2 核 | 2 GB | 50 GB | 5 工作流 + 定时 Cron + 10 并发 |
| 中量产  | 4 核 | 4 GB | 100 GB | 多工作流 + 高频触发 + 外部系统集成 |

---

## 二、一键部署 n8n (Windows / Linux)

### 2.1 执行安装
Windows PowerShell（管理员）：
```powershell
cd <项目目录>\fab-twin-pro\deploy
powershell -ExecutionPolicy Bypass -File .\deploy_n8n.ps1 -Action install -HostPort 5678 -PgPort 5434
```

Linux (bash)：
```bash
# 创建数据目录
mkdir -p /opt/n8n/{db,n8n}
# docker-compose.yaml 使用 deploy_n8n.ps1 中生成的模板（手动拷贝或用 docker run）
docker run -d --name n8n --restart always \
  -p 5678:5678 \
  -e DB_TYPE=postgresdb \
  -e DB_POSTGRESDB_HOST=postgres \
  -e DB_POSTGRESDB_PORT=5432 \
  -e DB_POSTGRESDB_DATABASE=n8n \
  -e DB_POSTGRESDB_USER=admin \
  -e DB_POSTGRESDB_PASSWORD='FabTwin#2026!N8n' \
  -e N8N_BASIC_AUTH_ACTIVE=true \
  -e N8N_BASIC_AUTH_USER=admin \
  -e N8N_BASIC_AUTH_PASSWORD='FabTwin#2026!N8n' \
  -e GENERIC_TIMEZONE=Asia/Shanghai \
  -v /opt/n8n/n8n:/home/node/.n8n \
  n8nio/n8n:latest
```

### 2.2 导入工作流模板
```powershell
powershell -ExecutionPolicy Bypass -File .\deploy_n8n.ps1 -Action import
```
脚本会自动读取 `docs/integration/n8n/*.json` 5 个模板并导入 n8n。

也可手动导入：
1. 访问 `http://<服务器IP>:5678`
2. 登录（admin / FabTwin#2026!N8n）
3. 左侧菜单 → Workflows → Import from File
4. 依次上传 5 个 JSON 文件

### 2.3 常用管理命令
| 操作 | PowerShell |
|---|---|
| 状态 | `.\deploy_n8n.ps1 status` |
| 日志 | `.\deploy_n8n.ps1 logs` |
| 重启 | `.\deploy_n8n.ps1 restart` |
| 导入工作流 | `.\deploy_n8n.ps1 import` |
| 卸载（含卷） | `.\deploy_n8n.ps1 uninstall` |

---

## 三、5 个工作流模板

| 序号 | 文件名 | Webhook 路径 | 功能 |
|---|---|---|---|
| 1 | `01_export_alarm_report.json` | `/webhook/export_alarm_report` | 导出告警报表（调用 FabTwin `/api/ai/alarms`，返回 data 列表） |
| 2 | `02_generate_work_order.json` | `/webhook/generate_work_order` | 生成故障工单（调用外部 MES/RCMS API 或生成工单记录） |
| 3 | `03_export_machine_data.json` | `/webhook/export_machine_data` | 批量导出设备数据（调用 FabTwin `/api/events`，返回事件列表） |
| 4 | `04_push_daily_report.json` | `/webhook/push_daily_report` | 产线日报推送（聚合数据 → 发送邮件/钉钉/飞书） |
| 5 | `05_general_query.json` | `/webhook/general_query` | 通用查询（转发给 AI 或直接查 DB） |

### 导入后需配置的参数
每个工作流模板中都有 `your-fabtwin-backend` 占位符，导入后需替换为真实地址：

1. 进入工作流编辑器 → 找到 HTTP Request 节点
2. 将 URL 中的 `https://your-fabtwin-backend` 替换为：
   - 开发：`http://localhost:8002`
   - 测试：`http://10.30.116.137:8002`
   - 量产：`https://fabtwin.xxfab.com/api`
3. 若 FabTwin 启用了认证 → HTTP Request 节点 → Authentication → 添加 Header
   `Authorization: Bearer <token>`（通过 `/api/auth/login` 获取）
4. 对于日报推送（04）：配置邮件/钉钉节点的凭据
5. 点击右上角 **Active** 开关激活工作流

---

## 四、FabTwin 平台对接 n8n

### 4.1 在 FabTwin AI 配置面板填写
1. 登录 FabTwin（管理员）→ AI 配置管理 → **Dify/N8N** Tab
2. 填写 n8n 区域：
   - ✅ 启用 N8N
   - N8N 服务地址：`http://10.30.116.137:5678`
   - N8N Webhook 密钥：（留空，或在 n8n Webhook 节点中设置了密钥时填入）
3. 点击「**测试连接**」，预期提示：
   - `N8N 连接成功，工作流数：5，已激活 Webhook：5/5`
4. 保存。

### 4.2 端到端验证（与 FabTwin AI 联动）
以管理员登录 FabTwin 后：
1. 打开 AI 助手悬浮球或机台详情页 AI 面板
2. 发送以下问题（验证 3 种 n8n 工作流触发）：
   ```
   (1) "导出OXE-01今天的告警报表"
       ⇒ 触发 export_alarm_report 工作流
       ⇒ 回答：🤖 [N8N自动化] 已导出告警报表，共 N 条报警记录。
       ⇒ table_data 展示报警列表

   (2) "给OXE-01生成故障工单"
       ⇒ 触发 generate_work_order 工作流
       ⇒ 回答：🤖 [N8N自动化] 故障工单已生成，工单号：WO-xxxx

   (3) "推送今天的产线日报"
       ⇒ 触发 push_daily_report 工作流
       ⇒ 回答：🤖 [N8N自动化] 产线日报已推送到钉钉群
   ```
3. 在「AI 配置管理 → 使用日志」Tab 中：
   - 确认 n8n 调用记录的 tool_calls 中有 `n8n_{workflow_type}` 字段
   - 详情抽屉 → 工具调用链：能看到 `execution_id` / `duration_ms` / `rows_count`

### 4.3 后端直连测试（脚本）
```powershell
cd tests
python test_n8n_integration.py `
  --base-url http://10.30.116.137:5678 `
  --user admin --password "FabTwin#2026!N8n" `
  --fabtwin-url http://localhost:8002 `
  --fabtwin-user admin --fabtwin-password admin123
```

---

## 五、常见故障排查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| n8n Web UI 无法访问 | 容器未启动 / 端口被占 | `deploy_n8n.ps1 status`；检查 5678 端口 |
| 测试连接成功但 Webhook 0/5 | 工作流未导入或未 Active | `deploy_n8n.ps1 import`；在 n8n UI 中确认 Active 开关 |
| AI 对话不触发 n8n | 用户非管理员 / n8n 未启用 / 关键词不匹配 | 确认 user_role=admin；确认 n8n_enabled=True；关键词需包含"导出+报警"或"工单"或"推送+报表" |
| Webhook 404 | 工作流路径与后端不匹配 | 后端使用 `/webhook/{workflow_type}`，n8n 中 Webhook 节点 path 必须一致 |
| Webhook 401 | Webhook Secret 不匹配 | 后端 n8n_webhook_secret 与 n8n Webhook 节点的 secret 一致 |
| PostgreSQL 连接失败 | 容器网络隔离 | 确保 n8n 容器和 postgres 在同一 docker network |
| 工作流中 HTTP Request 返回 401 | FabTwin API 需要认证 | HTTP Request 节点配置 `Authorization: Bearer <token>` |
| n8n 日志报 "Could not find credential" | 凭据未配置 | 在 n8n → Credentials 中配置 FabTwin API 凭据并绑定到节点 |

---

## 六、量产部署 Checklist

- [ ] 服务器 Docker 可用
- [ ] `deploy_n8n.ps1 install` 成功，2 个容器 Up
- [ ] n8n Web UI 可访问，账号密码可登录
- [ ] `deploy_n8n.ps1 import` 导入 5 个工作流成功
- [ ] 工作流中 `your-fabtwin-backend` 已替换为真实地址
- [ ] 5 个工作流全部 Active（开关打开）
- [ ] 日报推送（04）的邮件/钉钉凭据已配置
- [ ] FabTwin AIConfigPanel 填写 n8n URL，测试连接返回 5/5 Webhook
- [ ] AI 对话 3 个 n8n 触发问题全部通过
- [ ] 使用日志中 n8n 调用记录的 tool_calls 正确显示

---

## 七、参考文件清单

| 文件名 | 位置 | 用途 |
|---|---|---|
| deploy_n8n.ps1 | `deploy/deploy_n8n.ps1` | n8n 一键部署 + 工作流导入脚本 |
| 01~05_*.json | `docs/integration/n8n/` | 5 个工作流模板 |
| N8N_INTEGRATION_SOP.md | `docs/integration/n8n/` | 图文版操作 SOP |
| test_n8n_integration.py | `tests/test_n8n_integration.py` | 10 TC 端到端测试脚本 |

---

> 文档维护：FabTwin Pro 项目组。配置变更请同步更新本文档与改版记录。
