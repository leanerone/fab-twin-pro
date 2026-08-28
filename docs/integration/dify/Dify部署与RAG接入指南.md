# Dify 本地部署与 RAG 接入完整指南
> 文档版本: v1.0 (2026-08-28)  
> 代码基线: FabTwin Pro ver2.7.0+  
> 适用环境: Windows Server 2022 / Win11 Pro / Ubuntu 22.04  
> Dify 版本: 0.10.3 LTS（推荐）  
> 前置条件: Docker Desktop / Docker Engine ≥ 24，Docker Compose v2

---

## 一、部署总览

```
┌────────────────────────────────────────────────────────────┐
│                   Dify 服务器 (独立机器推荐)                 │
│  ┌─────────┐  ┌────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Nginx   │→ │ Web UI │  │ API(5001)│  │ Worker(异步) │  │
│  │:8088    │  └────────┘  └──────────┘  └──────────────┘  │
│  └────┬────┘       │             │              │          │
│       │   静态资源  │    ┌────────▼───────────────▼────┐   │
│       └─────────────┘    │ PostgreSQL 15  :5433       │   │
│                          │ Redis 6        :6380       │   │
│                          │ Weaviate 1.25  (向量库)    │   │
│                          └────────────────────────────┘   │
└────────────────────────────────────────────────────────────┘
         ▲                         ▲ 知识库写入 / 查询
         │ 对话 API (/v1/*)        │
┌────────┴─────────────────────────┴──────────────────────────┐
│                     FabTwin Pro 平台                         │
│   后端 ai_middleware._call_dify() ──► Bearer Token 鉴权     │
│   前端 AIConfigPanel [Dify/N8N] Tab 填 BaseURL / Key / ID   │
└─────────────────────────────────────────────────────────────┘
```

**资源需求**

| 规模 | CPU | 内存 | 磁盘 | 用途 |
|---|---|---|---|---|
| 开发测试 | 4 核 | 8 GB | 50 GB SSD | RAG ≤ 1000 文档，单机 |
| 小量产  | 8 核 | 16 GB | 200 GB SSD | RAG ≤ 10k 文档，≤ 20 并发 |
| 中量产  | 16 核 | 32 GB | 500 GB SSD | RAG ≤ 50k 文档，≤ 100 并发 |

---

## 二、一键部署 Dify (Windows / Linux 通用)

### 2.1 准备
1. 确认 Docker 已就绪：
   ```bash
   docker --version
   docker compose version
   docker info
   ```
2. 将 FabTwin Pro 项目中的 `deploy/deploy_dify.ps1` 拷贝到目标服务器任意目录，
   或直接在项目目录下执行。

### 2.2 执行安装
Windows PowerShell（管理员）：
```powershell
cd <项目目录>\fab-twin-pro\deploy
powershell -ExecutionPolicy Bypass -File .\deploy_dify.ps1 -Action install -HostPort 8088 -PgPort 5433 -RedisPort 6380
```

Linux (bash)：
> 推荐直接用官方 compose：
```bash
git clone --depth 1 --branch 0.10.3 https://github.com/langgenius/dify.git
cd dify/docker
cp .env.example .env
# 修改 .env 中 EXPOSE_NGINX_PORT=8088、DB_PORT=5433 等端口
docker compose up -d
```

### 2.3 安装后验证
```powershell
# 查看状态
powershell -ExecutionPolicy Bypass -File .\deploy_dify.ps1 -Action status
# 应看到 web/api/worker/db/redis/weaviate/sandbox 共 7 个容器状态 Up

# 浏览器访问
Start-Process "http://localhost:8088"
```

首次访问会提示**设置管理员账号**：
- 邮箱：`admin@fabtwin.local`（建议，避免与 SaaS 混淆）
- 密码：`FabTwin#2026!Dify`（强度合规）

### 2.4 常用管理命令
| 操作 | PowerShell | Linux |
|---|---|---|
| 状态 | `.\deploy_dify.ps1 status` | `docker compose ps` |
| 日志 | `.\deploy_dify.ps1 logs` | `docker compose logs -f --tail=100` |
| 重启 | `.\deploy_dify.ps1 restart` | `docker compose restart` |
| 停止 | `.\deploy_dify.ps1 stop` | `docker compose stop` |
| 卸载（含卷！注意备份） | `.\deploy_dify.ps1 uninstall` | `docker compose down -v` |

### 2.5 数据备份（建议每日）
```powershell
# PostgreSQL 备份（Dify 业务核心）
$ts = Get-Date -Format yyyyMMdd_HHmmss
docker exec docker-db-1 pg_dump -U postgres dify > "dify-db-$ts.sql"

# 知识库向量库备份（Weaviate 采用文件卷直接复制）
robocopy <VolumeRoot>\weaviate <BackupDir>\weaviate-$ts /E /COPY:DAT

# 上传文件与日志
robocopy <VolumeRoot>\app\storage <BackupDir>\storage-$ts /E /COPY:DAT
```

---

## 三、Dify 配置四步走

### 3.1 Step 1: 配置模型供应商
路径：Dify 后台 → 设置（左下角齿轮）→ 模型供应商

**国内标配组合（推荐）：**
| 类型 | 供应商 | 模型名 | 获取 Key |
|---|---|---|---|
| 对话 LLM | 智谱 AI | `glm-5.2` (或 `glm-4-plus`) | https://open.bigmodel.cn/ |
| Embedding | 智谱 AI | `embedding-3` | 同上，开通 Embedding 包 |
| Rerank   | 智谱 AI | `rerank-2` (可选，提升 RAG 精度) | 同上 |

**海外标配：**
| 类型 | 供应商 | 模型名 |
|---|---|---|
| 对话 LLM | OpenAI | `gpt-4o-mini` / `gpt-4o` |
| Embedding | OpenAI | `text-embedding-3-small` |
| Rerank   | Jina / Voyage | `jina-reranker-v2-base-multilingual` |

**验证：** 配置完 → 每个供应商点击「连接测试」按钮，绿灯 OK。

### 3.2 Step 2: 导入 FabTwin AI Assistant DSL 模板
模板路径：[docs/integration/dify/fabtwin-ai-assistant.dsl.yaml](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/docs/integration/dify/fabtwin-ai-assistant.dsl.yaml)

> ⚠️ **2026-08-28 根据您实际导入截图再次修正：mode=chat（Basic Chatbot），不是 agent-chat。**
> Agent 模式 (`mode: agent-chat`) 的 Dify 应用需要把提示词写到 `agent_mode.prompt`、工具以 Function Calling 格式写到 `model_config.tools[]`，而且会生成左上角的 AGENT 标签；之前用 agent-chat + chat_prompt_config 的组合在您的 Dify 版本里被校验器直接清空了全部提示词和变量（提示词框里是 0 字符、"变量"栏变成了外部工具标签）。本次 DSL：
> 1. 改为 `mode: chat`（和您截图左侧"编排"是普通聊天布局、不是 Agent 布局匹配）
> 2. 删除了 Chat 应用不支持的字段：`dependencies / agent_mode / annotation_reply / external_data_tools`
> 3. 提示词 `prompt_template`（老版）+ `chat_prompt_config.prompt`（新版）双写
> 4. 对话变量 `variables`（老版）+ `conversation_variables`（新版）双写
> 5. 工具**不写在 DSL 里**——Chat 模式 Dify 不支持 DSL 声明 external_data_tools，请在 Step 3 用 UI 手动从 OpenAPI/API 扩展导入 6 个 FabTwin 工具
> 6. 模型4字段（completion_params/mode/name/provider）与您导出的模板 100% 一致

1. 回到 Dify「工作室」首页 → 应用列表页面 → 某个应用卡右上角「···」菜单 → 「从 DSL 导入」。
2. 选择 `fabtwin-ai-assistant.dsl.yaml`。
3. **导入后必做的一步：切换模型供应商**（默认占位符是 Azure OpenAI，按您实际环境改）：
   - 进入应用 → 右上角「设置」→「模型和供应商」→「模型」Tab
   - **如果您的环境是官方 OpenAI**：供应商选 `OpenAI`，模型选 `gpt-4o-mini` 或 `gpt-5.3-codex`
   - **如果是 Azure OpenAI**：供应商选 `Azure OpenAI`（请先在全局「系统设置→模型供应商」配置 Azure Resource Name / API Key / Deployment ID）
   - **如果是国内供应商（通义/智谱/DeepSeek）**：先在全局供应商添加，再在这里选中
   - 保存后点击「连接测试」，绿灯即可
4. 导入后再确认（以下 4 项必须全部看到，说明 Chat 模式解析成功）：
   - [ ] 提示词编辑器里**有文字**（不是空的 0 字符），开头是「你是 FabTwin Pro 半导体产线数字孪生平台的 AI 助手」
   - [ ] 变量区域（不是 REQUIRED 标签样式！普通聊天变量卡片样式）有 `machine_id`（文本输入）+ `user_role`（下拉）
   - [ ] 开场白（调试与预览面板上方）显示「👋 你好！我是 FabTwin Pro 数字孪生 AI 助手……」
   - [ ] 左上角标题下**没有 AGENT 标签**（如果看到 AGENT 标签说明又走了 Agent 分支，请删掉这个应用用新的 DSL 重新导入）
   - [ ] 「设置 → 编排 → 知识库」里 `retriever_resource` 已开启（用于在 FabTwin 前端展示知识库引用来源）

### 3.3 Step 3: 配置 FabTwin API 工具（6 个）
**重要**：Chat 模式 Dify 不支持在 DSL 里写 `external_data_tools`（上一轮写入导致变量栏变成工具的 REQUIRED 标签，就是这个字段被错误解析了）。6 个 FabTwin 工具必须在 Dify UI「工具 → 添加工具」里手动接入，步骤：

1. **方式 A（推荐，批量）**：先通过 OpenAPI schema 一次性导入：
   - FabTwin 后端地址 + `/openapi.json` 导出（或在浏览器打开 `http://10.30.116.137:8002/openapi.json` 另存为 JSON）
   - 进入 Dify「工作室 → 工具 → 添加工具 → OpenAPI/Swagger」→ 选择刚刚的 JSON / 直接填 URL
   - 勾选 get_machine_status / get_machine_alarms / get_event_timeline / get_yield_stats / get_lot_info / get_recipe_info 共 6 个接口
   - 鉴权方式选 **API Key**，Key 名 `Authorization`，值 `Bearer <FABTWIN_ADMIN_TOKEN>`
     - 获取 Token：`POST {fabtwin}/api/auth/login` Body: `{ "username": "admin", "password": "admin123" }`
   - 导入成功后，回到「FabTwin AI Assistant」应用 → 编排 → 工具 → 「+ 添加」→ 选中刚导入的 6 个 → 确认
2. **方式 B（逐个）**：每个工具单独"添加工具 → API 扩展"，填入：
   - API Base URL：实际 FabTwin 后端地址（开发 `http://localhost:8002` / 测试 `http://10.30.116.137:8002` / 量产走 Nginx 反代 `https://fabtwin.xxfab.com/api`）
   - 路径 & 参数与提示词里写的一致（machine_id 可选、limit 默认 20 等）
3. 逐个工具 → 「测试」→ 成功后保存。

### 3.4 Step 4: 创建 RAG 知识库并绑定应用
知识库种子文档路径：
[docs/integration/dify/knowledgebase/OXE_Etcher_SOP_v1.0.md](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/docs/integration/dify/knowledgebase/OXE_Etcher_SOP_v1.0.md)

1. Dify 顶部菜单 →「知识库」→「创建知识库」。
2. 名称：`OXE-Etcher-SOP`，权限：仅工作室成员。
3. 选择「上传文档」→ 把 `OXE_Etcher_SOP_v1.0.md` 拖入。
4. 索引方式：**高质量（推荐）** → Embedding 模型选 `embedding-3` / `text-embedding-3-small`。
5. 分段设置：
   - 分段最大长度：`500` tokens
   - 分段重叠长度：`50` tokens
   - 分段标识符：默认（空行 + 标题）
6. 点击「保存并处理」→ 等待文档处理完（通常 1~2 分钟）。
7. **验证检索**：知识库 →「测试检索」→ 输入提问：
   - 例：`OXE Chamber 颗粒偏高怎么排查？`
   - 应能命中 §6 FAQ Q1 的片段（Score ≥ 0.8）。
8. **绑定应用**：回到「FabTwin AI Assistant」→「编排」→「知识库」→ 关联 `OXE-Etcher-SOP`。
   - 召回策略：语义搜索（默认）
   - Rerank：如已开通开启 `rerank-2`，TopN=6
   - 召回数量：`6` 段

---

## 四、FabTwin 平台对接 Dify

### 4.1 获取 Dify 应用的 API Key
1. Dify →「FabTwin AI Assistant」应用 → 左上角「访问 API」（发布 / API 按钮）。
2. 创建一个新的 API Key，名称写 `fabtwin-backend`。**复制保存**（只显示一次）。
3. 页面顶部会显示 API 地址：`https://<你的dify>/v1` 或 `http://x.x.x.x:8088/v1`。

### 4.2 在 FabTwin AI 配置面板填写
1. 登录 FabTwin（管理员）→「用户管理」旁边的「AI 配置管理」。
2. 切换 Tab 到 **Dify/N8N**。
3. 填写：
   - ✅ 启用 Dify
   - Dify 服务地址：`http://10.30.116.137:8088/v1`（以实际为准，末尾不要 /chat-messages）
   - Dify API 密钥：刚才复制的 Key（`app-xxxx...`）
   - Dify 应用 ID：（可选，留空即可，Dify API Key 已绑定单应用）
4. 点击「**测试连接**」，预期提示：
   - `Dify 连接成功，应用：FabTwin AI Assistant，知识库数：1`
5. 保存。

### 4.3 设置 AI Provider 为 Dify 模式
在「模型配置」Tab 或顶部 Provider 下拉中：
- 切换 Provider 为：**Dify** 或 **Hybrid 混合**（Dify 失败回退本地规则）
- Hybrid 模式适合生产（避免 Dify 服务短暂故障导致 AI 完全不可用）。

### 4.4 端到端验证（与 FabTwin 联动）
以管理员登录 FabTwin 后：
1. 进入任一台 OXE 机台详情页。
2. 点击右上角 AI 助手悬浮球 → 打开对话框。
3. 发送以下三个问题（验证 3 条不同链路）：
   ```
   (1) RAG 知识问答：「OXE 做 PM-A 周期是多少？CQ 验证哪些项目？」
       ⇒ 回答中应引用 SOP §3 的 PM 表格；消息下方显示 2~6 条 RAG 引用来源。

   (2) 工具调用：「查询 OXE-01 当前 Chamber 状态」
       ⇒ 调用 get_machine_status 工具并返回 JSON 化的 Chamber 实时色。

   (3) 跳转联动：「查 OXE-01 最近 24h 的报警并跳到最近一条 E201」
       ⇒ 返回报警列表，每条带「跳转到该时间戳」按钮（FabTwin 回放自动 seek）。
   ```
4. 在「AI 配置管理 → 使用日志」Tab 中：
   - 确认 Dify provider 记录的 token 用量 > 0（prompt_tokens / completion_tokens 均有值）。
   - 详情抽屉 → 工具调用链：能看到 `dify_chat` + `rag_docs_count` 字段。

### 4.5 后端直连测试（脚本）
在 FabTwin 后端服务器执行：
```powershell
cd tests
python test_dify_integration.py `
  --base-url http://10.30.116.137:8088/v1 `
  --api-key app-xxxxxxxxxxxxxxxxxx
```
见 §6 测试脚本。

---

## 五、常见故障排查

| 现象 | 可能原因 | 处理 |
|---|---|---|
| Dify 面板保存后测试连接失败：`HTTP 401` | API Key 错误 | 重新生成 API Key 并粘贴；注意不要带前后空格 |
| 测试连接成功，但 AI 回答是本地规则 | 未启用 Dify 开关 / Provider 未切到 Dify | 在 Dify/N8N Tab 打勾启用；切换 Provider 为 Dify/Hybrid |
| RAG 回答无引用（sources 只有 dify 项） | 知识库未关联应用 | §3.4 第 8 步：进入应用编排 → 知识库 → 关联 |
| RAG 回答命中率低 | Embedding 模型不匹配 / 分段过大 / 无 Rerank | 尝试 500 段 + Rerank；换质量更高的 Embedding 模型 |
| Dify chat-messages 返回 504 / 超时 | Worker 容器死或 Redis 压力大 | `docker compose logs worker`；扩容 Worker 为 2 副本 |
| FabTwin AI 日志中 `rag_docs_count=0` | Dify 返回字段名为 docs 而不是 retriever_resources | 已在 ver2.7.0 ai_middleware 兼容，升级后端代码即可 |
| Weaviate 容器反复重启 | 内存不足或已有损坏的 shm | 加大内存；删除 volumes/weaviate 后重建 |
| PostgreSQL 15 权限错误 | 挂载卷是 root 所有（Linux） | `chown -R 999:999 volumes/db` |

---

## 六、量产部署 Checklist（上线必打勾）

- [ ] 服务器：CPU ≥ 8核、内存 ≥ 16 GB、SSD ≥ 200GB
- [ ] Docker ≥ 24，Compose v2 可用
- [ ] 部署命令：`deploy_dify.ps1 install` 成功，7 个容器全部 `Up (healthy)`
- [ ] 管理员账号创建成功，2FA 已启用
- [ ] 模型供应商配置完毕：对话 LLM + Embedding 均通过连接测试
- [ ] DSL 模板导入成功（变量 `machine_id` / `user_role`，6 个 API 工具）
- [ ] 6 个 FabTwin API 工具 Base URL 已修改为真实后端地址，并逐个测试通过
- [ ] RAG 知识库创建，SOP 文档导入，测试检索 Top3 命中正确
- [ ] 知识库绑定到应用
- [ ] 生成 API Key，并写入 FabTwin AIConfigPanel；保存 + 测试连接 OK
- [ ] Provider 切到 Hybrid，FabTwin 前台 AI 助手 3 个问题（RAG / 工具 / 跳转）全部通过
- [ ] AI 使用日志中 Dify 调用的 token 用量与 RAG 引用字段正确显示
- [ ] 备份脚本（§2.5）已配置到 Windows 任务计划 / cron 每日执行

---

## 七、参考文件清单

| 文件名 | 位置 | 用途 |
|---|---|---|
| deploy_dify.ps1 | `deploy/deploy_dify.ps1` | Dify 一键部署脚本 |
| fabtwin-ai-assistant.dsl.yaml | `docs/integration/dify/` | Dify 应用 DSL 模板 |
| OXE_Etcher_SOP_v1.0.md | `docs/integration/dify/knowledgebase/` | RAG 知识库种子文档 |
| test_dify_integration.py | `tests/` | 端到端测试脚本（本任务 2.7） |
| create_ai_tables.sql | `sql/create_ai_tables.sql` | AI_CONFIGS 等表建表脚本（首次部署必执行） |
| DIFY_INTEGRATION_SOP.md | `docs/integration/dify/` | 图文版操作 SOP |

---

> 文档维护：FabTwin Pro 项目组。任何配置变更请同步更新本文档与 ver2.7.x 改版记录。
