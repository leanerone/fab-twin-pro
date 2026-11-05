-- ============================================================================
-- v2.21 增量脚本：新增 AI_CHAT_SESSIONS（T3 2026-11-06：AI 聊天会话消息持久化）
-- 背景：此前对话只存后端内存，重启即失忆且内存无界增长。
-- 目标库：Oracle 11g+（XEPDB1 / fabtwin 账号执行）
-- 幂等：重复执行不报错；回退见文件末尾注释
-- ============================================================================
SET DEFINE OFF

-- ---------- 1. 建表 ----------
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE TABLE AI_CHAT_SESSIONS (
      SESSION_ID    VARCHAR2(64) NOT NULL PRIMARY KEY,
      MACHINE_ID    VARCHAR2(64) DEFAULT '',
      MESSAGES      CLOB,
      MESSAGE_COUNT NUMBER(10) DEFAULT 0,
      CREATED_AT    VARCHAR2(255),
      UPDATED_AT    VARCHAR2(255)
    )
  ]';
  DBMS_OUTPUT.PUT_LINE('AI_CHAT_SESSIONS created');
EXCEPTION
  WHEN OTHERS THEN
    IF SQLCODE = -955 THEN
      DBMS_OUTPUT.PUT_LINE('AI_CHAT_SESSIONS already exists, skipped');
    ELSE
      RAISE;
    END IF;
END;
/

-- ---------- 2. 索引：按更新时间做 LRU 淘汰/过期清理 ----------
BEGIN
  EXECUTE IMMEDIATE q'[
    CREATE INDEX IDX_AI_CHAT_SESS_UPDATED
    ON AI_CHAT_SESSIONS (UPDATED_AT)
  ]';
  DBMS_OUTPUT.PUT_LINE('IDX_AI_CHAT_SESS_UPDATED created');
EXCEPTION
  WHEN OTHERS THEN
    IF SQLCODE IN (-955, -1408) THEN
      DBMS_OUTPUT.PUT_LINE('IDX_AI_CHAT_SESS_UPDATED already exists, skipped');
    ELSE
      RAISE;
    END IF;
END;
/

COMMIT;

-- ---------- 验证 ----------
-- SELECT table_name FROM user_tables WHERE table_name = 'AI_CHAT_SESSIONS';
-- SELECT index_name FROM user_indexes WHERE table_name = 'AI_CHAT_SESSIONS';

-- ---------- 回退（如需）----------
-- DROP TABLE AI_CHAT_SESSIONS CASCADE CONSTRAINTS PURGE;
