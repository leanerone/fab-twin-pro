# 模块③ AI 助手（ai-assistant）

- **负责人**：朱明钊
- **功能边界**：自然语言问数与对话、AI 配置、语音输入；后端 AI 中间件、providers（local/openai/dify/n8n）、受限 SQL 工具、用量与会话。

## 目录

```
frontend/
  components/ AiAssistant（对话面板）、AIFloatingBall（悬浮球）、AIConfigPanel、VoiceInput
  pages/      AIConfigPage（/ai-config）
```

后端对应：`routers/ai.py`、`services/ai/` 全包
（middleware、providers/、sql、sql_tools、tools、schema、config_store、conversations、usage、mcp_client、mcp_registry）、`services/speech_service.py`；
表 `ai_configs、ai_provider_configs、ai_usage_logs、ai_conversations、ai_insights、machine_dify_configs`。

## 公开接口

- `<AiAssistant>`、`<AIFloatingBall>`（供 App 壳与②详情页挂载）
- `/api/ai/chat`、`/api/ai/chat/stream`（角色由服务端登录态决定，请求体 user_role 已忽略）

## 边界与纪律

- AI 取数必须走受限 SQL 工具（五层围栏 + 物理数据字典反射），数据真实门禁：
  答案 ≡ 直查 Oracle（`tests/ai/test_real_data.py` 21/21）。
- Dify/n8n 的部署与 DSL 资产是⑤张亮负责，本模块只负责代码侧调用。
- `services/ai_middleware.py`、`services/ai_tools.py`、`services/mcp_client.py` 等根文件是
  批次2 拆包的**兼容 shim**（测试 monkeypatch 依赖），勿删。

## 自测

`npm run build`；`pytest tests/ai`（mock 替身 + 真实链路分别验证，二者缺一不算完成）。
