# 模块③ AI 助手（ai-assistant）

- **负责人**：朱明钊
- **功能边界**：自然语言问数与对话、AI 配置、语音输入；后端 AI 中间件、providers（local/openai/dify/n8n）、受限 SQL 工具、用量与会话。

## 目录

```
frontend/
  components/ AiAssistant（对话面板）、AIFloatingBall（悬浮球）、AIConfigPanel、VoiceInput
  pages/      AIConfigPage（/ai-config）
```

后端对应（当前真实目录）：`backend/modules/ai_assistant/routes/ai.py`、
`backend/modules/ai_assistant/services/` 全包
（middleware、providers/、sql、sql_tools、tools、schema、config_store、conversations、usage、mcp_client、mcp_registry、speech_service）。
Dify/n8n 平台 Provider 仍在 `backend/modules/ai_assistant/services/providers/`，归朱明钊；`backend/integrations/dify_n8n/` 是张亮的集成资产，不替代平台 Provider。
表 `ai_configs、ai_provider_configs、ai_usage_logs、ai_conversations、ai_insights、machine_dify_configs`。

## 公开接口

- `<AiAssistant>`、`<AIFloatingBall>`（供 App 壳与②详情页挂载）
- `/api/ai/chat`、`/api/ai/chat/stream`（角色由服务端登录态决定，请求体 user_role 已忽略）

## 边界与纪律

- AI 取数必须走受限 SQL 工具（五层围栏 + 物理数据字典反射），数据真实门禁：
  答案 ≡ 直查 Oracle（`tests/ai/test_real_data.py` 21/21）。
- Dify/n8n 的部署与 DSL 资产是⑤张亮负责，本模块只负责代码侧调用。
- 旧 AI 中间件、Schema、SQL、工具与 MCP 的 7 个**兼容 shim 已移除**；直接导入 `backend/modules/ai_assistant/services/` 的真实模块，不要恢复旧 shim。

## 自测

`npm run build`；`pytest tests/ai`（mock 替身 + 真实链路分别验证，二者缺一不算完成）。
