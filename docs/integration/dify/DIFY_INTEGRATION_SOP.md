# Dify 接入详细 SOP

> 适用版本：Dify 0.6+  
> 对接系统：FabTwin Pro 数字孪生平台  
> 文档版本：v1.0 (2026-07-27)

---

## 一、Dify 是什么？为什么要接入？

Dify 是一款开源的 LLM 应用开发平台，核心价值：

| 能力 | 说明 | 对 FabTwin 的价值 |
|---|---|---|
| **可视化编排** | 拖拽式搭建 AI 工作流 | 非工程师也能配置 AI 对话流程 |
| **RAG 知识库** | 文档/网页/PDF 上传后自动向量化 | 工艺文档、设备手册智能问答 |
| **多模型支持** | 一键切换 OpenAI/智谱/DeepSeek/通义 | 灵活切换模型，降低成本 |
| **工具调用** | 可视化配置 API 工具 | 把 FabTwin 的 API 注册为 Dify 工具 |
| **应用发布** | 一键发布为 WebApp / API / 嵌入 | 快速验证 AI 应用效果 |
| **日志监控** | 对话日志、用户反馈、Token 统计 | 追踪 AI 使用情况 |

---

## 二、Dify 部署方式

### 方案 A：Docker 一键部署（推荐测试用）

```bash
# 克隆 Dify 代码
git clone https://github.com/langgenius/dify.git
cd dify/docker

# 启动（需要 Docker + Docker Compose）
docker compose up -d
```

启动后访问 `http://localhost`，默认账号：`admin@dify.test / dify123456`

### 方案 B：官方 SaaS 版

访问 https://dify.ai 注册账号，免费额度可用于测试。

### 方案 C：内网私有化部署

生产环境建议：
- 独立服务器（4C8G 起步）
- PostgreSQL + Redis 独立部署
- Nginx 反向代理 + HTTPS
- 挂载外部存储（模型 / 知识库文件）

---

## 三、第一步：导入 FabTwin AI 助手模板

模板文件位置：[fabtwin-ai-assistant.dsl.yaml](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/docs/integration/dify/fabtwin-ai-assistant.dsl.yaml)

### 导入步骤

1. **登录 Dify 工作室** → 点击右上角「创建应用」
2. 选择「**从 DSL 导入**」
3. 上传 `fabtwin-ai-assistant.dsl.yaml`
4. 等待导入完成，应用名称为「FabTwin AI Assistant」

### 导入后检查项

- [ ] 左侧「提示词编排」能看到系统提示词
- [ ] 「变量」中有 `machine_id` 和 `user_role` 两个变量
- [ ] 「工具」面板中有 6 个工具（待配置，见下一节）
- [ ] 右上角「预览」能打开聊天窗口

---

## 四、第二步：配置模型供应商

导入模板后，需要先配置可用的大模型：

1. 进入 Dify 后台 → 「设置」→ 「模型供应商」
2. 添加你常用的模型供应商：
   - **智谱 AI**（推荐国内用）：API Key 从 https://open.bigmodel.cn 获取
   - **OpenAI**：官方 API Key
   - **通义千问**：阿里云 DashScope API Key
   - **DeepSeek**：DeepSeek 开放平台 API Key
3. 添加后在「模型」中启用对应的模型（如 `glm-5.2`、`gpt-4o-mini`）

### 在应用中选择模型

1. 打开「FabTwin AI Assistant」应用
2. 左侧「提示词编排」→ 顶部模型选择器
3. 选择刚才添加的模型
4. 调整参数：
   - Temperature：0.3（越低越稳定，适合查询类场景）
   - Max Tokens：2048

---

## 五、第三步：配置 6 个 API 工具

模板中已经定义了 6 个工具，但需要你配置实际的 API 地址（指向 FabTwin 后端）。

### 5.1 工具总览

| 工具名 | 用途 | 对应 FabTwin API |
|---|---|---|
| `get_machine_status` | 查询机台实时状态 | `GET /api/machines/{id}` |
| `get_machine_alarms` | 查询告警记录 | `GET /api/ai/alarms` |
| `get_event_timeline` | 查询事件时间线 | `GET /api/events?machine_id=xxx` |
| `get_yield_stats` | 查询产量统计 | `GET /api/ai/yield-stats` |
| `get_lot_info` | 查询 Lot 信息 | `GET /api/lots?machine_id=xxx` |
| `get_recipe_info` | 查询工艺配方 | `GET /api/recipes?machine_id=xxx` |

### 5.2 配置步骤（以 get_machine_status 为例）

1. 打开「FabTwin AI Assistant」应用 → 「工具」
2. 点击「**添加工具**」→ 选择「**自定义 API**」
3. 填写工具信息：
   - **工具名称**：`get_machine_status`
   - **描述**：`查询机台实时状态，包括最新事件、运行模式、当前Lot。不传machine_id则返回全厂概览。`
4. 配置 API：
   - **请求方式**：`GET`
   - **URL**：`https://your-fabtwin-backend/api/machines/{{machine_id}}`
   - **鉴权方式**：根据你的后端配置（API Key / Bearer Token / 无）
5. 配置参数 Schema：
   ```json
   {
     "type": "object",
     "properties": {
       "machine_id": {
         "type": "string",
         "description": "机台ID，如 PODOPENER-1。不传则查询全厂。"
       }
     },
     "required": []
   }
   ```
6. 点击「保存」

### 5.3 批量配置建议

6 个工具配置方式相同，区别仅在：
- URL 路径
- 请求参数 Schema
- 工具描述

建议按以下顺序配置（从简单到复杂）：
1. `get_machine_status` — 单参数，容易验证
2. `get_machine_alarms` — 两个参数，有默认值
3. `get_lot_info` — 两个可选参数
4. `get_event_timeline` — 返回列表
5. `get_yield_stats` — 统计数据
6. `get_recipe_info` — 配方参数

---

## 六、第四步：配置提示词与变量

### 6.1 系统提示词

模板中已内置提示词，你可以根据实际情况调整。核心要点：

1. **明确工具用途**：告诉 AI 每个工具什么时候用
2. **规定回答格式**：表格 / 列表 / 结构化数据
3. **跳转回放格式**：约定 `JUMP_TIMESTAMP` 和 `JUMP_MACHINE_ID` 标记
4. **行业用语**：半导体行业术语规范

### 6.2 变量说明

模板中定义了 2 个变量：

| 变量名 | 类型 | 默认值 | 用途 |
|---|---|---|---|
| `machine_id` | text | '' | 当前查看的机台 ID，由 FabTwin 前端传入 |
| `user_role` | select | user | 用户角色：user / engineer / admin |

### 6.3 在 FabTwin 中如何传参

FabTwin 后端调用 Dify 时，会通过 `inputs` 字段传递变量：

```python
# ai_middleware.py _call_dify 方法（已实现）
payload = {
    "inputs": {
        "machine_id": machine_id or "",   # 当前机台ID
        "user_role": user_role,            # 用户角色
    },
    "query": question,                     # 用户问题
    "response_mode": "blocking",           # 阻塞模式（等待完整回答）
    "conversation_id": session_id,         # 会话ID，用于多轮对话
    "user": f"fabtwin_{user_role}",        # 用户标识
}
```

---

## 七、第五步：FabTwin 后端配置 Dify

配置好 Dify 应用后，需要在 FabTwin 中填入 Dify 的连接信息。

### 7.1 获取 Dify API Key

1. 在 Dify 中打开「FabTwin AI Assistant」
2. 点击右上角「发布」→ 「API」
3. 复制「API 密钥」（格式：`app-xxxxxx`）
4. 记录「API 地址」（默认 `https://api.dify.ai/v1` 或你的私有化地址）

### 7.2 方法一：在 AI 配置面板中配置（推荐）

1. 打开 FabTwin → 登录 admin 账号
2. 进入「AI 配置管理」页面
3. 找到 Dify 配置区域：
   - **启用 Dify**：打开开关
   - **Dify API 地址**：填入 API 基础地址（如 `http://localhost/v1`）
   - **Dify API Key**：填入刚才复制的 API 密钥
   - **Dify 应用 ID**：可选，用于标识
4. 点击「保存」
5. 在「模型选择」中切换 Provider 为 `dify`

### 7.3 方法二：环境变量配置

```powershell
# Windows PowerShell
$env:DIFY_ENABLED = "True"
$env:DIFY_BASE_URL = "http://localhost/v1"
$env:DIFY_API_KEY = "app-xxxxxxxxxx"
$env:DIFY_APP_ID = "fabtwin-assistant"
```

### 7.4 验证连接

配置完成后，验证方法：

```bash
# 用 curl 测试 Dify API 是否通
curl -X POST "http://localhost/v1/chat-messages" `
  -H "Authorization: Bearer app-xxxxxxxxxx" `
  -H "Content-Type: application/json" `
  -d '{
    "inputs": {"machine_id": "PODOPENER-1", "user_role": "admin"},
    "query": "这台机台现在状态怎么样？",
    "response_mode": "blocking",
    "user": "test_user"
  }'
```

如果返回正常的 `answer` 字段，说明 Dify 配置成功。

---

## 八、第六步：开启对话测试

### 8.1 在 Dify 内部测试

1. 打开「FabTwin AI Assistant」→ 右上角「预览」
2. 输入测试问题：
   - `现在状态怎么样？`
   - `最近有什么告警？`
   - `PODOPENER-1 的 Lot 进度`
   - `产量统计`
3. 观察左侧「工具调用」日志，确认工具是否被正确调用

### 8.2 在 FabTwin 中测试

1. 确保后端已配置 Dify Provider
2. 打开 FabTwin → 点击右下角 AI 悬浮球
3. 输入同样的问题
4. 确认回答来源显示「Dify」

### 8.3 常见测试问题排查

| 现象 | 可能原因 | 解决方法 |
|---|---|---|
| 返回本地规则引擎结果 | Dify 未启用或配置错误 | 检查配置、检查网络连通性 |
| 工具调用失败 | API 地址错误或鉴权失败 | 检查 URL、API Key、后端服务是否启动 |
| AI 不调用工具 | 提示词不够明确 | 调整系统提示词，强调工具使用 |
| 回答格式乱 | 输出格式约束不够 | 在提示词中增加格式要求和示例 |
| 中文乱码 | 字符编码问题 | 确保后端返回 UTF-8 |

---

## 九、进阶：RAG 知识库配置

### 9.1 为什么需要 RAG？

当前 AI 只能查询实时数据，无法回答：
- 设备操作手册问题
- 工艺参数规范
- 故障排查指南
- 历史经验案例

通过 RAG（检索增强生成），可以把文档喂给 AI，让它基于文档回答。

### 9.2 配置步骤

1. 在 Dify 中打开「知识库」→「创建知识库」
2. 上传文档（支持 PDF / DOCX / TXT / Markdown / HTML）：
   - 设备操作手册
   - 工艺规范文档
   - 故障排查指南
   - SOP 文档
3. 选择分段方式（推荐「自动分段」）
4. 等待索引完成
5. 回到「FabTwin AI Assistant」→「提示词编排」→「上下文」
6. 添加上下文，选择刚才创建的知识库
7. 调整检索设置：
   - 检索模式：向量检索 + 关键词检索（混合）
   - 召回条数：5-10 条
   - 相似度阈值：0.7

### 9.3 推荐的知识库结构

```
📁 知识库
 ├── 📄 设备操作手册（PODOPENER）
 ├── 📄 工艺规范文档
 ├── 📄 故障排查指南
 ├── 📄 安全操作规程
 └── 📄 常见问题 FAQ
```

---

## 十、Dify API 完整参考

### 10.1 对话消息（Chat Messages）

```http
POST /v1/chat-messages
Authorization: Bearer {api_key}
Content-Type: application/json

{
  "inputs": {
    "machine_id": "PODOPENER-1",
    "user_role": "admin"
  },
  "query": "这台机台现在状态怎么样？",
  "response_mode": "blocking",
  "conversation_id": "",
  "user": "fabtwin_admin"
}
```

### 10.2 响应结构

```json
{
  "message_id": "xxxx",
  "conversation_id": "xxxx",
  "answer": "PODOPENER-1 当前处于 PACKING 模式...",
  "created_at": 1234567890,
  "token_usage": {
    "prompt_tokens": 500,
    "completion_tokens": 200,
    "total_tokens": 700
  },
  "metadata": {
    "usage": { ... }
  }
}
```

### 10.3 流式响应（Streaming）

如果要实时显示 AI 打字效果，使用 `response_mode: streaming`：

```python
# 流式响应示例（FabTwin 当前用的是 blocking）
response = requests.post(url, json=payload, headers=headers, stream=True)
for line in response.iter_lines():
    if line:
        data = json.loads(line.decode('utf-8').replace('data: ', ''))
        print(data.get('answer', ''), end='')
```

---

## 十一、下一步学习路径

```
入门 → 配置模型 → 导入模板 → 配置工具 → 测试对话
  ↓
进阶 → 添加知识库 → 调整提示词 → 多轮对话优化
  ↓
高级 → 工作流编排 → 多 Agent 协作 → 自定义插件
  ↓
生产 → 权限控制 → 日志审计 → 性能优化 → 监控告警
```

下一份文档：[n8n 接入详细 SOP](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/docs/integration/n8n/N8N_INTEGRATION_SOP.md)
