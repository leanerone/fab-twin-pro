# Dify / n8n 可导入资产（2026-11-03 从真实运行实例导出）

> 本目录文件**全部从本机真实运行实例导出并做过导入回环验证**（导入→验证节点数→清理）。
> 旧的 `fabtwin-ai-assistant.dsl.yml`（0.10.3 agent-chat，依赖 azure_openai/markitdown 插件）
> 保留仅作历史参考；**新环境请用本目录文件**。

## 一、Dify（适配 1.17.x）

| 文件 | 说明 |
|---|---|
| `dify/fabtwin-chat-1.17.dsl.yml` | 「FabTwin 对话测试」chat 应用（当前模型：OpenAI 兼容 → mock-model） |

**导入步骤**：
1. Dify 控制台 → 工作室 → 导入 DSL 文件（选本 yml）
2. ⚠️ DSL 只带模型**绑定关系**不带凭据——导入后需配模型：
   - 控制台右上头像 → 设置 → 模型供应商 → 安装 `OpenAI-API-compatible` 插件
   - 填模型凭据（`api_key`/`endpoint_url`/`context_size`），或直接配真实厂商（智谱/OpenAI…）的 Key
3. 应用详情 → API 访问 → 生成/复制 API Key（`app-xxx`）
4. 配置 FabTwin 后端：
   ```
   PUT /api/ai/config  {"provider":"dify","dify_enabled":true,"dify_base_url":"<Dify地址>/v1","dify_api_key":"app-xxx"}
   ```
5. 验证：`python tests/test_dify_integration.py --base-url <Dify地址>/v1 --api-key app-xxx`
   （TC01 `/v1/info` 通过即 Key 有效；TC03 起需配好模型供应商）

> 凭据样本见 `E:\AI\fab-ai-services\dify_credentials.json`（不入库）。
> 已知差异：1.17.x 登录/管理 API 的三个坑——密码字段 Base64 编码传输、
> token 在 Cookie 不在响应体、管理请求需带 `X-CSRF-Token`（值为登录下发的 csrf_token cookie）。

## 二、n8n（适配 2.x，docker/npm 通用）

| 文件 | 说明 |
|---|---|
| `n8n/fabtwin-general-query.workflow.json` | 通用查询 webhook（回显问题+executionId） |
| `n8n/fabtwin-export-alarm-report.workflow.json` | 报警报表导出（webhook → 反查 FabTwin `/api/alarms` → 聚合回传） |

**导入步骤**：
1. n8n 界面 → Workflows → Import from File（或 `POST /rest/workflows` 用该 JSON）
2. ⚠️ 报警工作流里 HTTP 节点的 `Authorization` 头是占位符
   `Bearer REPLACE_WITH_FABTWIN_ADMIN_TOKEN`——**导入后必须替换**为
   FabTwin 管理员 token（`POST /api/auth/login-password` 获取），并按部署形态改主机名：
   | n8n 形态 | 工作流内 FabTwin 地址 |
   |---|---|
   | docker 容器 | `http://host.docker.internal:8002` |
   | npm/宿主机 | `http://127.0.0.1:8002`（Node 20 会把 localhost 解析成 ::1，勿用） |
3. 激活工作流 → 后端配置 `PUT /api/ai/config {"n8n_enabled":true,"n8n_base_url":"http://localhost:5678"}`
4. 验证：`cd tests/ai/n8n_local && bash ai_real_test.sh` —— **要求 7/7**
5. 一键重建（本机 docker 实例）：`python backend/n8n_docker_setup.py`

> 已知坑（实测踩过，README 详见 tests/ai/n8n_local/）：
> ① webhook 表达式必须 `{{ }}` 双花括号（单花括号成字面量，查询空转）
> ② HTTP Request 节点把 JSON **数组**响应拆成多 item，下游 Code 节点必须 `$input.all()` 聚合
> ③ docker 内访问宿主机后端用 `host.docker.internal`，npm 版用 `127.0.0.1`
> 本目录两份工作流 JSON 已内置 ①② 的正确写法。
