/* ================================================================
   FabTwin AI 相关表建表脚本（手动执行）
   生成时间: 2026-07-24
   说明:
     本脚本创建 3 张 AI 相关表，供 AI 配置管理功能使用：
       1. AI_CONFIGS          - AI 键值对配置（Dify/N8N等）
       2. AI_PROVIDER_CONFIGS - LLM Provider 多配置管理
       3. AI_USAGE_LOGS       - AI Token 使用量统计
     不在 backend 代码中通过 ORM create_all 创建，
     由 DBA 手动执行本脚本完成建表与初始化。

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
-- 用途: 记录每次 AI 调用的 Token 使用量
-- --------------------------------------------
CREATE TABLE AI_USAGE_LOGS (
    ID                 NUMBER        NOT NULL,
    SESSION_ID         VARCHAR2(255),
    CONFIG_ID          NUMBER,
    PROVIDER           VARCHAR2(255),
    MODEL              VARCHAR2(255),
    PROMPT_TOKENS      NUMBER        DEFAULT 0,
    COMPLETION_TOKENS  NUMBER        DEFAULT 0,
    TOTAL_TOKENS       NUMBER        DEFAULT 0,
    QUESTION_PREVIEW   VARCHAR2(512) DEFAULT '',
    SUCCESS            NUMBER(1)     DEFAULT 1,
    ERROR_MSG          VARCHAR2(512),
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
-- 共创建 3 张表 + 3 个序列 + 3 个触发器
-- 默认配置: 1 条本地规则引擎Provider + 7 条Dify/N8N键值对
-- 后续可通过前端"AI配置管理"面板添加智谱GLM/OpenAI等Provider配置
