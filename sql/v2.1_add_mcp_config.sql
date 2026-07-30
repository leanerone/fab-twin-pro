-- ============================================================
-- [已废弃] FabTwin v2.1: AI - N8N MCP Server 配置初始化
-- 日期：2026-07-28
-- 说明：此脚本内容已合并到 create_ai_tables.sql 中（lines 182-193）
--       新部署无需执行此脚本，仅对已部署的旧环境增量升级时使用
-- 执行方式：手动在 Oracle 中执行（Aqua Data Studio）
-- ============================================================

-- 1. MCP 启用开关
MERGE INTO ai_configs t
USING (SELECT 'mcp_n8n_enabled' AS config_key FROM dual) s
ON (t.config_key = s.config_key)
WHEN NOT MATCHED THEN
  INSERT (config_key, config_value, description, updated_at, updated_by)
  VALUES ('mcp_n8n_enabled', 'false', '是否启用 N8N MCP Server', SYSTIMESTAMP, 'system');

-- 2. MCP Server 地址
MERGE INTO ai_configs t
USING (SELECT 'mcp_n8n_url' AS config_key FROM dual) s
ON (t.config_key = s.config_key)
WHEN NOT MATCHED THEN
  INSERT (config_key, config_value, description, updated_at, updated_by)
  VALUES ('mcp_n8n_url', 'http://10.30.116.137/mcp-server/http', 'N8N MCP Server 地址', SYSTIMESTAMP, 'system');

-- 3. MCP Bearer Token（空，需用户在 AI 配置面板录入）
MERGE INTO ai_configs t
USING (SELECT 'mcp_n8n_token' AS config_key FROM dual) s
ON (t.config_key = s.config_key)
WHEN NOT MATCHED THEN
  INSERT (config_key, config_value, description, updated_at, updated_by)
  VALUES ('mcp_n8n_token', '', 'N8N MCP Bearer Token（固定值）', SYSTIMESTAMP, 'system');

-- 4. MCP HTTP 超时
MERGE INTO ai_configs t
USING (SELECT 'mcp_n8n_timeout' AS config_key FROM dual) s
ON (t.config_key = s.config_key)
WHEN NOT MATCHED THEN
  INSERT (config_key, config_value, description, updated_at, updated_by)
  VALUES ('mcp_n8n_timeout', '30', 'N8N MCP HTTP 超时（秒）', SYSTIMESTAMP, 'system');

COMMIT;

-- 验证
SELECT config_key, config_value, description
FROM ai_configs
WHERE config_key LIKE 'mcp_n8n_%'
ORDER BY config_key;
