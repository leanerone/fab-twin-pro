# FabTwin + Dify + n8n 部署执行 SOP（手把手版）

> **你不需要懂 Dify/n8n 原理，照着下面每一步做就行。**
> 每步都写了：去哪个页面 → 点什么按钮 → 填什么值 → 怎么确认成功。
>
> 前置条件：Dify 和 n8n 已部署能访问网页。
> - Dify 地址示例：http://10.30.116.68
> - n8n 地址示例：http://10.30.116.151:5678

---

## 总览（6 大步）

| 步骤 | 在哪做 | 做什么 | 耗时参考 |
|---|---|---|---|
| 第 1 步 | n8n | 导入 10 个工作流 + 绑定 Oracle 凭据 + 激活 | 20 分钟 |
| 第 2 步 | Dify | 导入应用模板 .yml | 2 分钟 |
| 第 3 步 | Dify | 配置 OpenAPI 工具（接通 n8n） | 10 分钟 |
| 第 4 步 | Dify | 测试对话（验证 AI 能调工具） | 5 分钟 |
| 第 5 步 | FabTwin 后端 | 配置 .env（Dify 地址 + API Key） | 3 分钟 |
| 第 6 步 | FabTwin 网页 | 端到端测试（发问题→拿答案） | 5 分钟 |

---

## 第 1 步：在 n8n 导入 10 个工作流

### 1.1 导入工作流

1. 打开 n8n 网页 → 左上角点 **Workflows**
2. 点右上角 **Import from File** 按钮
3. 选择文件：`docs/integration/n8n/F1_get_machine_status.json`
4. 导入成功后会看到 5 个节点用线连起来
5. 重复上述操作，依次导入 F2 ~ F10 共 10 个文件

**确认成功**：左侧 Workflows 列表能看到 10 个工作流名称（F1~F10）

### 1.2 绑定 Oracle 凭据

每个工作流里有一个 **Query Oracle** 节点，需要绑定你的 Oracle 数据库连接：

1. 打开刚导入的 **F1_get_machine_status** 工作流
2. 双击画布上的 **Query Oracle** 节点
3. 在右侧参数面板，找到 **Credential** 下拉框
4. 如果已有 Oracle 凭据 → 直接选它
5. 如果没有 → 点下拉框旁边的 **Create New** → 填入：
   - **Name**：FabTwin Oracle
   - **Host**：你的 Oracle 服务器 IP（如 10.30.116.150）
   - **Port**：1521
   - **Service / SID**：你的 Oracle SID
   - **User**：你的 Oracle 用户名
   - **Password**：你的 Oracle 密码
   - 点 **Save**
6. 回到画布，对 F2~F10 重复此操作（所有 10 个工作流都要绑定）

**确认成功**：Query Oracle 节点上不再有红色感叹号

### 1.3 激活工作流

1. 在每个工作流页面，右上角有个 **Active** 开关
2. 打开它（变绿色）
3. 10 个工作流都要激活

**确认成功**：左下角 Active 标签变为绿色

---

## 第 2 步：在 Dify 导入应用模板

1. 打开 Dify 网页 → 登录
2. 左上角点头像 → **Create App** → 或首页点 **创建空白应用**
3. 不需要选模板，直接看右上角 → 有一个 **Import** 按钮（或 "导入 DSL"）
4. 选择文件：`docs/integration/dify/fabtwin-ai-assistant.dsl.yml`
5. 点 **导入**
6. 导入后自动跳转到应用编排页面

**确认成功**：
- 应用名称显示 "FabTwin AI Assistant"
- 编排页面能看到 **pre_prompt** 里有大段中文系统提示词
- 左下角 **Variables** 能看到 `machine_id` 和 `user_role` 两个变量

> 如果要导入 OXE 专属版：同样操作，选 `fabtwin-ai-assistant-OXE.dsl.yml`

---

## 第 3 步：在 Dify 配置 OpenAPI 工具（接通 n8n）

这一步是让 Dify 知道"有 10 个工具可以调用"，每个工具指向 n8n 的一个 Webhook。

### 3.1 上传 OpenAPI 规范

1. 在应用编排页面，找到 **Tools** 区域（或左侧菜单 **工具**）
2. 点 **Add Tool** → 选 **Custom Tool**（自定义工具）
3. 填写：
   - **Name**：FabTwin n8n Tools
   - **Schema**：把 `docs/integration/dify/fabtwin-tools-openapi.yaml` 的内容完整粘贴进去
4. **重要**：OpenAPI 里的 `servers.url` 是 `{{n8n_base_url}}/webhook`，这是占位符。你需要改成你的真实 n8n 地址，例如：`http://10.30.116.151:5678/webhook`
5. 点 **Save**

### 3.2 在应用里启用这 10 个工具

1. 回到应用编排页面
2. 在 **Tools** 区域，应该能看到刚创建的 "FabTwin n8n Tools"
3. 展开它，勾选全部 10 个工具（get_machine_status / get_lot_info / ... / list_capabilities）
4. 确保每个工具的 **Enabled** 开关都是打开的

**确认成功**：工具列表显示 10 个工具，全部 enabled

### 3.3 设置 n8n Webhook Secret（可选但推荐）

如果 n8n 工作流里配了 Webhook Secret：

1. 在 Dify 应用的变量配置里，找到 n8n_secret 变量
2. 填入和 n8n Webhook 节点里相同的 secret 值
3. 如果没配 secret，跳过此步

---

## 第 4 步：在 Dify 测试对话

1. 在应用编排页面，点右上角 **Preview**（预览）或 **调试**
2. 在对话框输入：`你能帮我干什么`
3. 应该看到 AI 调用 list_capabilities 工具，返回 10 类功能清单
4. 再输入：`今天产量`（注意：先设置变量 machine_id = OXE-1）
5. 应该看到 AI 调用 get_yield_stats 工具，返回产量数据表格

**如果报错**：
- "Tool not found" → 检查第 3 步工具是否全部启用
- "Connection refused" → 检查 n8n 地址是否正确、n8n 是否在运行
- "401 Unauthorized" → 检查 n8n Webhook Secret 是否匹配

**确认成功**：AI 能正确回答问题，回答里没有 SQL 代码

---

## 第 5 步：配置 FabTwin 后端

### 5.1 获取 Dify API Key

1. 在 Dify 应用页面，点 **Publish**（发布）→ 选 **API Access** 或 **访问 API**
2. 复制 **API Key**（格式：app-xxxxxxxx）
3. 记下 Dify 的 API 地址（格式：http://10.30.116.68/v1）

### 5.2 编辑 FabTwin 后端配置

打开 FabTwin 后端的 `.env` 文件（通常在 `backend/.env`），修改：

```env
# 关闭本地规则兜底（纯 Dify 模式）
ENABLE_LOCAL_RULE_FALLBACK=false

# Dify 全局配置
DIFY_BASE_URL=http://10.30.116.68
DIFY_API_KEY=app-你刚才复制的key

# OXE 机台专属 Dify（如果导入了 OXE 版本）
MACHINE_DIFY_CONFIGS_OXE_DIFY_ENDPOINT=http://10.30.116.68
MACHINE_DIFY_CONFIGS_OXE_DIFY_API_KEY=app-OXE专属应用的key
```

保存后重启后端：
```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**确认成功**：后端日志无报错，能正常启动

---

## 第 6 步：FabTwin 网页端到端测试

### 6.1 浮动球（全局对话）

1. 打开 FabTwin 网页首页
2. 点右下角浮动球（AI 助手）
3. 输入：`今天产量`（不带机台名）
4. **预期**：AI 回复"请告诉我您想查询的机台 ID（例如 OXE-1），我才能查精确数据。"（因为 C5 产量查询机台必填）

### 6.2 机台详情页（带机台上下文）

1. 在网页上进入 **OXE-1 机台详情页**
2. 在侧栏 AI 助手输入：`今天产量`（仍然不带机台名）
3. **预期**：AI 直接返回 OXE-1 的产量表格 + 跳转按钮，不需要你再说 OXE-1

### 6.3 报警查询（全厂）

1. 在浮动球输入：`最近 7 天有什么报警`
2. **预期**：AI 返回全厂报警统计表格（因为 C3 报警可全厂查询，机台可空）

### 6.4 跳转按钮测试

1. 在 OXE-1 详情页输入：`最近有什么报警`
2. **预期**：AI 返回报警列表，回答末尾有跳转信息，前端渲染出"去机台回放"按钮
3. 点按钮 → 跳转到 3D 回放页面，时间定位到报警发生时刻

### 6.5 管理员权限测试

1. 普通用户输入：`导出报警报表`
2. **预期**：AI 回复"该功能需管理员权限，请联系您的管理员。"
3. 管理员用户输入同样问题
4. **预期**：AI 调用 export_alarm_report 工具，返回下载链接

---

## 故障排查速查表

| 现象 | 原因 | 解决 |
|---|---|---|
| Dify 导入 .yml 报错 | 格式不匹配 | 确认 Dify 版本 0.6.0+，检查 .yml 里 dependencies.value 无引号 |
| n8n 导入 JSON 报错 | 格式不匹配 | 确认 n8n 版本 1.20+，检查 JSON 里有 pinData/active/settings/meta 字段 |
| Dify 调工具报 404 | n8n 工作流未激活 | 在 n8n 里打开 Active 开关 |
| Dify 调工具报 401 | Webhook Secret 不匹配 | 检查 Dify 工具配置和 n8n Webhook 节点的 secret 值 |
| Dify 调工具超时 | Oracle 凭据错误或网络不通 | 在 n8n 里单独执行 Query Oracle 节点测试 |
| 回答里有 SQL 代码 | Dify prompt 未生效 | 检查 pre_prompt 是否包含完整系统提示词 |
| 回答没有表格 | table_data 为 null | 检查 n8n Format 节点是否正确输出 table_data |
| 回答没有跳转按钮 | jump_timestamp 为 null | 检查 n8n Format 节点是否设置了 jump_timestamp |
| 后端报 Dify 连接失败 | DIFY_BASE_URL 错误 | 检查 .env 里 DIFY_BASE_URL 是否能 ping 通 |
| 机台详情页 AI 不带机台 | 后端未注入 machine_id | 检查后端 _get_machine_metadata 方法是否正确查到 model |

---

## 文件清单

| 文件 | 用途 | 位置 |
|---|---|---|
| F1~F10 共 10 个 .json | n8n 工作流模板 | `docs/integration/n8n/` |
| fabtwin-ai-assistant.dsl.yml | Dify 应用模板（全局） | `docs/integration/dify/` |
| fabtwin-ai-assistant-OXE.dsl.yml | Dify 应用模板（OXE 专属） | `docs/integration/dify/` |
| fabtwin-tools-openapi.yaml | Dify 工具 OpenAPI 定义 | `docs/integration/dify/` |
| dify_n8n_format_reference.md | Dify/n8n 真实格式参考 | `docs/integration/` |
