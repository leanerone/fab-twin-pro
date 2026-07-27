# Dify + n8n 联合开发教学（从测试到生产全流程）

> 适用对象：想从零开始掌握 Dify + n8n 与 FabTwin 集成开发的工程师  
> 学习周期：建议 3-5 天  
> 前置条件：已完成 Dify SOP 和 n8n SOP 中的基础配置

---

## 一、整体架构图

```
┌──────────────────────────────────────────────────────────────┐
│                    FabTwin Pro 前端（Vue3）                    │
│  - AI 悬浮球 / 机台详情 AI Tab / 历史回放 AI                   │
└───────────────┬──────────────────────────────────────────────┘
                │ HTTP /api/ai/chat
                ▼
┌──────────────────────────────────────────────────────────────┐
│              FabTwin AI 中间层（ai_middleware.py）             │
│  - Provider 路由分发                                           │
│  - 本地规则引擎（兜底）                                         │
│  - 6 个 Function Calling 工具                                  │
└──────┬──────────────────────┬────────────────────────────────┘
       │                      │
       │ provider=dify        │ n8n 自动化指令
       ▼                      ▼
┌──────────────┐        ┌──────────────┐
│   Dify AI    │        │     n8n      │
│  - RAG 知识库 │        │  - 工作流编排 │
│  - 工具调用   │        │  - 定时任务   │
│  - 多模型切换 │        │  - 400+ 集成  │
└──────┬───────┘        └──────┬───────┘
       │ 调用 FabTwin API       │ 调用 FabTwin API
       ▼                        ▼
┌──────────────────────────────────────────────────────────────┐
│               FabTwin 后端 API（FastAPI）                       │
│  /api/machines  /api/ai/alarms  /api/lots  /api/events ...    │
└──────────────────────────────────────────────────────────────┘
```

**三种模式的切换**：在 AI 配置面板中切换 Provider：
- `local`：纯本地规则引擎（最快，不依赖外部）
- `zhipu / openai / deepseek / qwen`：直连大模型 + Function Calling
- `dify`：走 Dify 应用（支持 RAG + 工作流 + 更好的可视化配置）

n8n 是**并行的自动化通道**，由关键字触发（如"导出告警报表"），不影响主 Provider 选择。

---

## 二、Day 1：基础搭建与冒烟测试

### 目标

把 Dify 和 n8n 都跑起来，用最简单的调用验证连通性。

### 2.1 环境准备清单

- [ ] Docker Desktop 已安装（Windows/Mac）或 Docker + Docker Compose（Linux）
- [ ] 至少一个可用的大模型 API Key（智谱 / OpenAI / DeepSeek 任选）
- [ ] FabTwin 后端已启动（`http://localhost:8000`）
- [ ] FabTwin 前端已启动（`http://localhost:5173`）
- [ ] 能访问 Oracle 或 SQLite 数据库

### 2.2 快速部署命令

```powershell
# 1. 启动 Dify
cd C:\path\to\dify\docker
docker compose up -d
# 等待 2-3 分钟，访问 http://localhost

# 2. 启动 n8n
docker run -d --name n8n -p 5678:5678 -v C:\n8n_data:/home/node/.n8n n8nio/n8n
# 访问 http://localhost:5678
```

### 2.3 冒烟测试 1：Dify 直连测试

不用 FabTwin，直接测试 Dify 能不能调用大模型：

1. 登录 Dify → 创建空白应用
2. 添加模型供应商（如智谱 AI）
3. 在提示词编排中选 `glm-5.2`
4. 右上角「预览」→ 输入「你好」
5. 能正常回复 → Dify + 模型通了

### 2.4 冒烟测试 2：n8n Webhook 测试

不用 FabTwin，直接测试 n8n Webhook：

1. 新建工作流 → 添加 Webhook 节点
2. Webhook 方法 POST，路径 `test`
3. 激活工作流
4. 复制 Webhook URL
5. 用 curl 测试：

```bash
curl -X POST "http://localhost:5678/webhook/test" `
  -H "Content-Type: application/json" `
  -d '{"name": "test"}'
```

6. 在 n8n 执行记录中能看到请求 → n8n Webhook 通了

### 2.5 冒烟测试 3：FabTwin 调 Dify

在 AI 配置面板中：
1. 启用 Dify，填入 Dify API 地址和 Key
2. Provider 切换为 `dify`
3. 打开 AI 悬浮球，输入「你好」
4. 能收到 Dify 返回的回答 → 端到端通了

### 2.6 冒烟测试 4：FabTwin 调 n8n

在 AI 配置面板中：
1. 启用 n8n，填入 n8n 地址
2. 用 admin 账号登录（n8n 仅 admin 可用）
3. 输入「导出告警报表」
4. 返回带 `[N8N自动化]` 前缀 → n8n 链路通了

---

## 三、Day 2：Dify 工具调用 + RAG 知识库

### 目标

让 Dify 能调用 FabTwin 的 API 查询数据，并能基于知识库回答问题。

### 3.1 配置第一个工具（get_machine_status）

**步骤**：

1. Dify → 你的应用 → 「工具」→「添加工具」
2. 选择「自定义 API」
3. 填写：
   - 工具名：`get_machine_status`
   - 描述：`查询机台实时状态，包括最新事件、运行模式、当前Lot`
4. API 设置：
   - Scheme: `http`
   - Host: `localhost:8000`
   - Path: `/api/machines/{{machine_id}}`
   - Method: `GET`
5. 参数 Schema：
   ```json
   {
     "type": "object",
     "properties": {
       "machine_id": {
         "type": "string",
         "description": "机台ID"
       }
     }
   }
   ```
6. 保存 → 在应用的「工具」中启用这个工具

**验证**：在预览中问「PODOPENER-1 状态怎么样？」，看左侧「工具调用」是否触发。

### 3.2 逐步添加 6 个工具

按以下顺序添加，每个都测试通过后再加下一个：

| 顺序 | 工具 | 难度 | 验证方法 |
|---|---|---|---|
| 1 | get_machine_status | ⭐ | 问机台状态 |
| 2 | get_machine_alarms | ⭐⭐ | 问告警 |
| 3 | get_lot_info | ⭐⭐ | 问 Lot 进度 |
| 4 | get_event_timeline | ⭐⭐ | 问事件时间线 |
| 5 | get_yield_stats | ⭐⭐ | 问产量 |
| 6 | get_recipe_info | ⭐⭐ | 问配方参数 |

### 3.3 优化系统提示词

默认提示词可能不够精准，按以下方向调优：

1. **明确工具使用条件**：什么时候用哪个工具
2. **规定输出格式**：表格、列表、跳转按钮的格式
3. **增加示例**：给 1-2 个完整的问答示例
4. **约束行为**：不知道就说不知道，不要编造

### 3.4 配置 RAG 知识库

**准备文档**：
- 设备操作手册（PDF）
- 工艺规范文档（Word/PDF）
- 故障排查指南
- SOP 文档

**步骤**：
1. Dify → 「知识库」→「创建知识库」
2. 上传文档 → 选择分段方式（自动）
3. 等待索引完成
4. 回到应用 → 「上下文」→ 添加知识库
5. 测试：问一个文档里有的问题，看是否能引用文档回答

**调优技巧**：
- 文档越结构化越好（Markdown > PDF）
- 分段大小建议 500-1000 字符
- 相似度阈值 0.6-0.8 根据实际效果调
- 召回条数 5-10 条

---

## 四、Day 3：n8n 工作流深入开发

### 目标

能独立开发新的自动化工作流，并接入 FabTwin AI。

### 4.1 工作流开发范式

每个自动化工作流都遵循这个标准结构：

```
Webhook 触发 → 解析参数 → 执行业务逻辑 → 返回结果
```

**四节点标准模板**：

| 节点 | 作用 | 输出 |
|---|---|---|
| 1. Webhook | 接收 FabTwin 请求 | `$json.body` 包含所有参数 |
| 2. Set | 提取/设置变量 | 把参数放到独立字段 |
| 3. HTTP/Code/... | 业务逻辑 | 查询数据、生成报表等 |
| 4. Respond to Webhook | 返回给 FabTwin | `answer` + 可选 `data` |

### 4.2 实战练习：开发「设备 OEE 统计」工作流

**需求**：用户问「OEE 怎么样？」，n8n 计算设备综合效率并返回。

**步骤**：

1. **设计接口**：
   - 输入：`machine_id`（可选）
   - 输出：OEE 数值 + 三项分解（可用率/性能率/良率）

2. **创建工作流**：
   - Webhook 节点：路径 `oee_stats`
   - Set 节点：提取 `machine_id`
   - HTTP 节点 1：调用机台状态 API
   - HTTP 节点 2：调用产量 API
   - Code 节点：计算 OEE = 可用率 × 性能率 × 良率
   - Respond 节点：返回格式化回答

3. **修改 FabTwin AI 中间层**：
   在 `_trigger_n8n_workflow` 中增加关键字：
   ```python
   elif "OEE" in question or "效率" in question:
       workflow_type = "oee_stats"
   ```

4. **测试**：
   - 用 curl 直接调 Webhook
   - 在 AI 对话中触发
   - 验证返回格式是否正确

### 4.3 条件分支与错误处理

**IF 节点常见用法**：
- 数据是否为空 → 空数据返回不同提示
- 告警等级 → 严重告警升级处理
- 用户角色 → admin 返回更多数据

**错误处理**：
- 每个 HTTP 节点设置超时（建议 30s）
- 重要节点开启「出错继续」，用 IF 检查状态
- 失败时发送钉钉/邮件通知

### 4.4 定时任务（Cron）

除了 Webhook 触发，还可以用 Cron 节点做定时任务：

**示例：每日 8 点自动生成日报**

1. Cron 节点：每天 08:00 触发
2. HTTP 节点：调用产量和告警 API
3. Code 节点：生成日报内容
4. 邮件/钉钉节点：发送日报
5. 可选：存到数据库或文件

---

## 五、Day 4：Dify + n8n 联动

### 目标

让 Dify 和 n8n 协同工作，Dify 做智能对话，n8n 做流程自动化。

### 5.1 三种联动模式

#### 模式 A：Dify 调用 n8n（推荐）

```
用户问题 → Dify 判断 → 调用 n8n 工具 → n8n 执行业务流程 → 返回结果
```

配置方法：在 Dify 中把 n8n 的 Webhook 注册为一个工具。

#### 模式 B：n8n 调用 Dify

```
定时/事件触发 → n8n 收集数据 → 调 Dify 生成分析报告 → 推送通知
```

配置方法：在 n8n 中用 HTTP 节点调用 Dify 的 `/v1/chat-messages` API。

#### 模式 C：FabTwin 统一调度（当前代码实现的方式）

```
用户问题 → FabTwin AI 中间层 → 分发到 Dify 或 n8n → 返回结果
```

这是当前代码的实现方式，优点是简单，缺点是需要在代码里加规则。

### 5.2 推荐的演进路径

```
Phase 1: 模式 C（当前）          → 快速验证，FabTwin 代码里写死规则
Phase 2: 模式 A + C 混合        → 简单对话走 Dify，自动化指令走 n8n
Phase 3: 模式 A 为主             → Dify 统一入口，n8n 作为工具被 Dify 调用
```

### 5.3 把 n8n 注册为 Dify 工具

让 Dify 能调用 n8n 工作流：

1. Dify → 工具 → 添加自定义 API
2. 配置 n8n Webhook 为工具
3. 参数：`machine_id`、`question`
4. 描述：`触发自动化流程，如导出报表、生成工单等`

这样用户在 Dify 对话中，AI 会自动判断是否需要调用 n8n 工具。

---

## 六、Day 5：生产化与运维

### 6.1 安全加固清单

- [ ] Dify 和 n8n 都启用 HTTPS
- [ ] n8n Webhook 全部带 Secret
- [ ] Dify API Key 定期轮换
- [ ] 数据库账号最小权限
- [ ] 后台访问设置 IP 白名单
- [ ] 操作日志开启审计
- [ ] 敏感数据（API Key）加密存储

### 6.2 监控与告警

**监控指标**：
- Dify 对话量、响应时长、错误率
- n8n 工作流执行次数、失败率
- API 调用成功率、平均耗时
- Token 消耗量

**告警方式**：
- n8n 工作流失败 → 钉钉/邮件通知
- Dify API 调用失败率 > 5% → 告警
- Token 日消耗超阈值 → 告警

### 6.3 备份策略

| 数据 | 备份频率 | 备份方式 |
|---|---|---|
| Dify 应用 DSL | 每次修改后 | 导出 DSL 文件 |
| Dify 知识库 | 每周 | 数据库备份 |
| n8n 工作流 | 每次修改后 | 导出 JSON |
| 对话日志 | 每日 | 数据库备份 |

### 6.4 性能优化

- Dify：开启缓存、向量检索索引优化
- n8n：批量处理、异步执行模式
- API：增加 Redis 缓存层
- 大模型：请求合并、批量调用

---

## 七、常见开发模式速查

### 7.1 新增一个 AI 功能的流程

```
1. 明确需求：用户问什么？返回什么？
2. 判断实现方式：
   - 简单查询 → 本地规则引擎（ai_tools.py 加函数）
   - 需要理解语义 → Function Calling（在 TOOL_DEFINITIONS 加）
   - 需要知识库 → Dify RAG
   - 需要多步流程 → n8n 工作流
3. 开发
4. 测试（curl 直接调 → AI 对话调 → 前端验证）
5. 上线 + 文档更新
```

### 7.2 新增一个自动化流程的流程

```
1. 明确触发条件和输入输出
2. n8n 中开发工作流
3. 用 curl 测试 Webhook
4. 在 ai_middleware.py 加关键字映射
5. 在 AI 配置面板补充说明
6. 更新文档
```

### 7.3 调试技巧

**Dify 调试**：
- Dify 预览界面 → 「调试与预览」→ 看完整上下文
- 看「工具调用」日志，确认参数和返回
- 日志级别调成 debug

**n8n 调试**：
- 工作流编辑时直接「测试执行」
- 每个节点都能看输入输出数据
- 用 Code 节点打印中间变量

**FabTwin 中间层调试**：
- 后端日志看 `[AI]` 开头的日志
- `_debug_ai.py` 可以直接在命令行调 AI
- 浏览器 F12 看 `/api/ai/chat` 响应

---

## 八、下一步可探索方向

### 短期（1-2 周）

- [ ] 把 6 个工具全部在 Dify 中配置完
- [ ] 导入工艺文档到知识库
- [ ] 新增 2-3 个实用的 n8n 工作流
- [ ] n8n 接钉钉/飞书/邮件通知

### 中期（1-2 月）

- [ ] Dify 工作流模式（替代聊天助手模式）
- [ ] 多 Agent 协作（不同 Agent 负责不同机台）
- [ ] n8n 接 MES/RCMS/FDC 系统
- [ ] 智能异常诊断（AI + 历史数据）

### 长期（3-6 月）

- [ ] 完整的 AI 运维助手（问答 + 诊断 + 工单）
- [ ] 预测性维护（基于历史数据建模）
- [ ] 工艺参数优化推荐
- [ ] 全链路可观测性

---

## 九、有用的代码片段

### 9.1 直接测试 Dify API

```python
import requests

DIFY_BASE = "http://localhost/v1"
DIFY_KEY = "app-xxxxxxxx"

resp = requests.post(
    f"{DIFY_BASE}/chat-messages",
    headers={
        "Authorization": f"Bearer {DIFY_KEY}",
        "Content-Type": "application/json"
    },
    json={
        "inputs": {"machine_id": "PODOPENER-1", "user_role": "admin"},
        "query": "这台机台状态怎么样？",
        "response_mode": "blocking",
        "user": "test"
    }
)
print(resp.json())
```

### 9.2 直接测试 n8n Webhook

```python
import requests

N8N_BASE = "http://localhost:5678"
SECRET = "fabtwin_secret_2026"

resp = requests.post(
    f"{N8N_BASE}/webhook/export_alarm_report?secret={SECRET}",
    json={
        "question": "导出告警报表",
        "machine_id": "PODOPENER-1",
        "user_role": "admin",
        "workflow_type": "export_alarm_report"
    }
)
print(resp.json())
```

### 9.3 用 FabTwin 调试脚本

```bash
cd backend
python _debug_ai.py --provider dify --question "PODOPENER-1 状态"
```

---

祝你学习顺利！有问题随时在 FabTwin 的 AI 配置面板里改配置、测效果。
