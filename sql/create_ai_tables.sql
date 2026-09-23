/* ================================================================
   FabTwin AI 相关表建表脚本（手动执行）
   生成时间: 2026-07-24
   更新: 2026-09-23 (v2.9.x) 增加 MACHINE_DIFY_CONFIGS 种子数据；改 idempotent
   说明:
     本脚本创建 4 张 AI 相关表，供 AI 配置管理功能使用：
       1. AI_CONFIGS            - AI 键值对配置（Dify/N8N等）
       2. AI_PROVIDER_CONFIGS   - LLM Provider 多配置管理
       3. AI_USAGE_LOGS         - AI Token 使用量统计
       4. MACHINE_DIFY_CONFIGS  - 机台专属 Dify 应用配置（v2.9.1）
     AI_CONFIGS / AI_PROVIDER_CONFIGS / AI_USAGE_LOGS 不在 backend 代码中通过
     ORM create_all 创建，由 DBA 手动执行本脚本完成建表与初始化。
     MACHINE_DIFY_CONFIGS 会被 backend ORM create_all 自动建（Identity 列版本），
     本脚本对其做了幂等兼容：表已存在则跳过，仅刷新 trigger/sequence/seed。

   执行方式:
     sqlplus fabtwin/<pwd>@<TNS> @create_ai_tables.sql
     或在 Aqua Data Studio / DBeaver 中整段执行
   ================================================================ */

SET DEFINE OFF;
SET SQLBLANKLINES ON;

-- ============================================
-- 1. 清理旧表（如存在）
-- ============================================
DROP TABLE AI_USAGE_LOGS CASCADE CONSTRAINTS PURGE;
DROP TABLE AI_PROVIDER_CONFIGS CASCADE CONSTRAINTS PURGE;
DROP TABLE AI_CONFIGS CASCADE CONSTRAINTS PURGE;

-- ============================================
-- 2. 建表
-- ============================================

-- --------------------------------------------
-- 表: AI_CONFIGS
-- 用途: 存储 Dify/N8N 等键值对配置，重启后从DB加载
-- --------------------------------------------
CREATE TABLE AI_CONFIGS (
    ID           NUMBER        NOT NULL,
    CONFIG_KEY   VARCHAR2(255) NOT NULL,
    CONFIG_VALUE CLOB          DEFAULT '',
    DESCRIPTION  VARCHAR2(255) DEFAULT '',
    UPDATED_AT   VARCHAR2(255),
    UPDATED_BY   VARCHAR2(255) DEFAULT 'system',
    CONSTRAINT PK_AI_CONFIGS PRIMARY KEY (ID),
    CONSTRAINT UK_AI_CONFIGS_KEY UNIQUE (CONFIG_KEY)
);

CREATE INDEX IDX_AI_CONFIGS_KEY ON AI_CONFIGS (CONFIG_KEY);

-- --------------------------------------------
-- 表: AI_PROVIDER_CONFIGS
-- 用途: 多 LLM 配置管理（智谱GLM/OpenAI/DeepSeek/Qwen/Custom/Local）
-- --------------------------------------------
CREATE TABLE AI_PROVIDER_CONFIGS (
    ID           NUMBER        NOT NULL,
    NAME         VARCHAR2(255) NOT NULL,
    PROVIDER     VARCHAR2(255) NOT NULL,
    BASE_URL     VARCHAR2(512) DEFAULT '',
    API_KEY      VARCHAR2(512) DEFAULT '',
    MODEL        VARCHAR2(255) DEFAULT '',
    TEMPERATURE  FLOAT         DEFAULT 0.7,
    MAX_TOKENS   NUMBER        DEFAULT 2048,
    IS_ENABLED   NUMBER(1)     DEFAULT 1,
    IS_DEFAULT   NUMBER(1)     DEFAULT 0,
    SORT_ORDER   NUMBER        DEFAULT 0,
    DESCRIPTION  VARCHAR2(512) DEFAULT '',
    CREATED_AT   VARCHAR2(255),
    UPDATED_AT   VARCHAR2(255),
    CONSTRAINT PK_AI_PROVIDER_CONFIGS PRIMARY KEY (ID)
);

CREATE INDEX IDX_AI_PROVIDER_CONFIGS_PROVIDER ON AI_PROVIDER_CONFIGS (PROVIDER);

-- --------------------------------------------
-- 表: AI_USAGE_LOGS
-- 用途: 记录每次 AI 调用的 Token 使用量、工具调用和执行详情
-- --------------------------------------------
CREATE TABLE AI_USAGE_LOGS (
    ID                 NUMBER        NOT NULL,
    SESSION_ID         VARCHAR2(255),
    CONFIG_ID          NUMBER,
    PROVIDER           VARCHAR2(255),
    PROVIDER_NAME      VARCHAR2(255),
    MODEL              VARCHAR2(255),
    PROMPT_TOKENS      NUMBER        DEFAULT 0,
    COMPLETION_TOKENS  NUMBER        DEFAULT 0,
    TOTAL_TOKENS       NUMBER        DEFAULT 0,
    QUESTION_PREVIEW   VARCHAR2(512) DEFAULT '',
    ANSWER_PREVIEW     CLOB,
    SUCCESS            NUMBER(1)     DEFAULT 1,
    ERROR_MSG          CLOB,
    TOOL_CALLS         CLOB,
    EXECUTION_LOG      CLOB,
    CREATED_AT         VARCHAR2(255),
    CONSTRAINT PK_AI_USAGE_LOGS PRIMARY KEY (ID)
);

CREATE INDEX IDX_AI_USAGE_LOGS_SESSION ON AI_USAGE_LOGS (SESSION_ID);
CREATE INDEX IDX_AI_USAGE_LOGS_CONFIG  ON AI_USAGE_LOGS (CONFIG_ID);
CREATE INDEX IDX_AI_USAGE_LOGS_PROVIDER ON AI_USAGE_LOGS (PROVIDER);
CREATE INDEX IDX_AI_USAGE_LOGS_CREATED ON AI_USAGE_LOGS (CREATED_AT);

-- ============================================
-- 3. 序列与触发器（模拟 IDENTITY 自增主键）
-- ============================================

-- AI_CONFIGS 自增ID
CREATE SEQUENCE SEQ_AI_CONFIGS START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE;

CREATE OR REPLACE TRIGGER TRG_AI_CONFIGS_ID
BEFORE INSERT ON AI_CONFIGS
FOR EACH ROW
BEGIN
    IF :NEW.ID IS NULL THEN
        SELECT SEQ_AI_CONFIGS.NEXTVAL INTO :NEW.ID FROM DUAL;
    END IF;
END;
/

-- AI_PROVIDER_CONFIGS 自增ID
CREATE SEQUENCE SEQ_AI_PROVIDER_CONFIGS START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE;

CREATE OR REPLACE TRIGGER TRG_AI_PROVIDER_CONFIGS_ID
BEFORE INSERT ON AI_PROVIDER_CONFIGS
FOR EACH ROW
BEGIN
    IF :NEW.ID IS NULL THEN
        SELECT SEQ_AI_PROVIDER_CONFIGS.NEXTVAL INTO :NEW.ID FROM DUAL;
    END IF;
END;
/

-- AI_USAGE_LOGS 自增ID
CREATE SEQUENCE SEQ_AI_USAGE_LOGS START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE;

CREATE OR REPLACE TRIGGER TRG_AI_USAGE_LOGS_ID
BEFORE INSERT ON AI_USAGE_LOGS
FOR EACH ROW
BEGIN
    IF :NEW.ID IS NULL THEN
        SELECT SEQ_AI_USAGE_LOGS.NEXTVAL INTO :NEW.ID FROM DUAL;
    END IF;
END;
/

-- ============================================
-- 4. 初始化数据
-- ============================================

-- --------------------------------------------
-- 4.1 AI_PROVIDER_CONFIGS 默认配置
--     仅内置"本地规则引擎"作为默认配置（无需API Key，开箱可用）
--     其他Provider（智谱/OpenAI/DeepSeek/Qwen）请在管理面板中添加
-- --------------------------------------------
INSERT INTO AI_PROVIDER_CONFIGS
    (NAME, PROVIDER, BASE_URL, API_KEY, MODEL, TEMPERATURE, MAX_TOKENS,
     IS_ENABLED, IS_DEFAULT, SORT_ORDER, DESCRIPTION, CREATED_AT, UPDATED_AT)
VALUES
    ('本地规则引擎', 'local', '', '', '', 0.7, 2048,
     1, 1, 0, '默认配置：基于关键字匹配的本地规则引擎，无需外部API',
     TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
     TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'));

-- --------------------------------------------
-- 4.2 AI_CONFIGS 默认键值对（Dify/N8N 默认禁用）
--     应用首次启动时若 DB 中无对应键，会用环境变量覆盖写入
-- --------------------------------------------
INSERT INTO AI_CONFIGS (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION, UPDATED_AT, UPDATED_BY) VALUES
    ('dify_enabled', 'false', '是否启用Dify', TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), 'system');
INSERT INTO AI_CONFIGS (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION, UPDATED_AT, UPDATED_BY) VALUES
    ('dify_base_url', '', 'Dify API地址', TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), 'system');
INSERT INTO AI_CONFIGS (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION, UPDATED_AT, UPDATED_BY) VALUES
    ('dify_api_key', '', 'Dify API密钥', TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), 'system');
INSERT INTO AI_CONFIGS (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION, UPDATED_AT, UPDATED_BY) VALUES
    ('dify_app_id', '', 'Dify应用ID', TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), 'system');
INSERT INTO AI_CONFIGS (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION, UPDATED_AT, UPDATED_BY) VALUES
    ('n8n_enabled', 'false', '是否启用N8N', TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), 'system');
INSERT INTO AI_CONFIGS (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION, UPDATED_AT, UPDATED_BY) VALUES
    ('n8n_base_url', '', 'N8N服务地址', TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), 'system');
INSERT INTO AI_CONFIGS (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION, UPDATED_AT, UPDATED_BY) VALUES
    ('n8n_webhook_secret', '', 'N8N Webhook密钥', TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), 'system');

-- v2.1: N8N MCP Server 配置（MCP 协议调用 N8N 工作流）
INSERT INTO AI_CONFIGS (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION, UPDATED_AT, UPDATED_BY) VALUES
    ('mcp_n8n_enabled', 'false', '是否启用 N8N MCP Server', TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), 'system');
INSERT INTO AI_CONFIGS (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION, UPDATED_AT, UPDATED_BY) VALUES
    ('mcp_n8n_url', 'http://10.30.116.137/mcp-server/http', 'N8N MCP Server 地址', TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), 'system');
INSERT INTO AI_CONFIGS (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION, UPDATED_AT, UPDATED_BY) VALUES
    ('mcp_n8n_token', '', 'N8N MCP Bearer Token（固定值）', TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), 'system');
INSERT INTO AI_CONFIGS (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION, UPDATED_AT, UPDATED_BY) VALUES
    ('mcp_n8n_timeout', '30', 'N8N MCP HTTP 超时（秒）', TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), 'system');

-- v2.1: Provider 显示名称配置
INSERT INTO AI_CONFIGS (CONFIG_KEY, CONFIG_VALUE, DESCRIPTION, UPDATED_AT, UPDATED_BY) VALUES
    ('provider_name', '本地规则引擎', 'Provider显示名称（如智谱GLM、OpenAI官方）', TO_CHAR(SYSTIMESTAMP AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), 'admin');

COMMIT;

-- ============================================
-- 5. 验证查询（可选执行）
-- ============================================
-- SELECT ID, NAME, PROVIDER, MODEL, IS_ENABLED, IS_DEFAULT FROM AI_PROVIDER_CONFIGS;
-- SELECT ID, CONFIG_KEY, CONFIG_VALUE, DESCRIPTION FROM AI_CONFIGS;
-- SELECT COUNT(*) FROM AI_USAGE_LOGS;

-- ============================================
-- 完成说明
-- ============================================
-- 共创建 4 张表 + 4 个序列 + 4 个触发器（v2.9.1 新增 MACHINE_DIFY_CONFIGS）
-- 默认配置: 1 条本地规则引擎Provider + 7 条Dify/N8N键值对 + 4 条MCP配置键值对 + 1 条Provider名称配置（v2.1）
--            + 3 条 MACHINE_DIFY_CONFIGS 默认配置（v2.9.x：OXE / VPO / PODOPENER）
-- 后续可通过前端"AI配置管理"面板添加智谱GLM/OpenAI等Provider配置
-- 幂等性: MACHINE_DIFY_CONFIGS 已存在（ORM Identity 列版本）则跳过 CREATE，仅刷新 trigger/sequence/seed

-- ============================================
-- v2.9.1 (2026-09-03): 机台专属 Dify 配置表
-- 每个机型可绑定独立的 Dify App，机台详情页 AI 自动路由
-- v2.9.x (2026-09-23): 改为幂等建表，兼容 backend/database.py init_db()
--   自动 create_all 已建过 Identity 列版本的情况。
--   检测 USER_TABLES 已存在则跳过 CREATE TABLE，仅刷新 trigger/sequence。
-- ============================================

DECLARE
    e_table_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_table_exists, -955);
BEGIN
    EXECUTE IMMEDIATE q'[
        CREATE TABLE MACHINE_DIFY_CONFIGS (
            ID            NUMBER        NOT NULL,
            CONFIG_NAME   VARCHAR2(100) NOT NULL,
            MODEL_ID      VARCHAR2(255) NOT NULL,
            DIFY_BASE_URL VARCHAR2(500) DEFAULT '',
            DIFY_API_KEY  VARCHAR2(200) DEFAULT '',
            IS_ACTIVE     NUMBER(1)     DEFAULT 1,
            CREATED_AT    VARCHAR2(255),
            UPDATED_AT    VARCHAR2(255),
            CONSTRAINT PK_MACHINE_DIFY_CONFIGS PRIMARY KEY (ID)
        )
    ]';
    EXECUTE IMMEDIATE 'CREATE INDEX IDX_MACHINE_DIFY_MODEL ON MACHINE_DIFY_CONFIGS (MODEL_ID)';
    DBMS_OUTPUT.PUT_LINE('[v2.9.1] MACHINE_DIFY_CONFIGS 表+索引创建成功');
EXCEPTION
    WHEN e_table_exists THEN
        DBMS_OUTPUT.PUT_LINE('[v2.9.1] MACHINE_DIFY_CONFIGS 表已存在（可能由 backend ORM create_all 建过），跳过 CREATE，跳过重建 trigger/sequence');
    WHEN OTHERS THEN
        RAISE;
END;
/

-- 序列 + 触发器总是 OR REPLACE，保证老 SQL/手工 INSERT 走老接口可用
-- 注：若表是 ORM Identity 列版本，trigger 检测 :NEW.ID IS NULL 时不触发赋值，不会冲突
DECLARE
    e_seq_exists EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_seq_exists, -955);
BEGIN
    EXECUTE IMMEDIATE 'CREATE SEQUENCE SEQ_MACHINE_DIFY_CONFIGS START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE';
    DBMS_OUTPUT.PUT_LINE('[v2.9.1] SEQ_MACHINE_DIFY_CONFIGS 创建成功');
EXCEPTION
    WHEN e_seq_exists THEN
        DBMS_OUTPUT.PUT_LINE('[v2.9.1] SEQ_MACHINE_DIFY_CONFIGS 已存在，跳过');
END;
/

CREATE OR REPLACE TRIGGER TRG_MACHINE_DIFY_CONFIGS_ID
BEFORE INSERT ON MACHINE_DIFY_CONFIGS
FOR EACH ROW
WHEN (NEW.ID IS NULL)
BEGIN
    SELECT SEQ_MACHINE_DIFY_CONFIGS.NEXTVAL INTO :NEW.ID FROM DUAL;
END;
/

-- ============================================
-- v2.9.x (2026-09-23): 默认 Dify 配置种子数据
-- 按 MODEL_ID 去重，仅当表中无对应机型配置时插入示例
-- ============================================
MERGE INTO MACHINE_DIFY_CONFIGS tgt
USING (
    SELECT 1 AS ID, 'OXE 默认 Dify 应用' AS CONFIG_NAME, 'OXE' AS MODEL_ID,
           'http://localhost/v1' AS DIFY_BASE_URL, '' AS DIFY_API_KEY, 1 AS IS_ACTIVE,
           '2026-09-23T00:00:00' AS CREATED_AT, '2026-09-23T00:00:00' AS UPDATED_AT FROM DUAL
    UNION ALL
    SELECT 2, 'VPO 默认 Dify 应用', 'VPO', 'http://localhost/v1', '', 1,
           '2026-09-23T00:00:00', '2026-09-23T00:00:00' FROM DUAL
    UNION ALL
    SELECT 3, 'PODOPENER 默认 Dify 应用', 'PODOPENER', 'http://localhost/v1', '', 1,
           '2026-09-23T00:00:00', '2026-09-23T00:00:00' FROM DUAL
) src
ON (tgt.MODEL_ID = src.MODEL_ID)
WHEN NOT MATCHED THEN
    INSERT (ID, CONFIG_NAME, MODEL_ID, DIFY_BASE_URL, DIFY_API_KEY, IS_ACTIVE, CREATED_AT, UPDATED_AT)
    VALUES (src.ID, src.CONFIG_NAME, src.MODEL_ID, src.DIFY_BASE_URL, src.DIFY_API_KEY,
            src.IS_ACTIVE, src.CREATED_AT, src.UPDATED_AT);

COMMIT;
