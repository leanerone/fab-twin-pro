/* ================================================================
   ver2.11.1 增量脚本：DT_EVENT_RAW 复合索引
   生成时间: 2026-10-21
   用途:
     为 DT_EVENT_RAW 建立 (TOOL_ID, RECEIVED_TS_UTC) 复合索引，
     支撑机台状态聚合 / 今日告警 / 今日产量等按「机台+时间范围」
     的高频查询（对应执行开发计划 T1 步骤A）。
   适用环境:
     - 测试环境（DBA 手动执行或直接执行本脚本）
     - 量产环境建议改用 ONLINE 变体（见下方注释）
   回退:
     DROP INDEX IDX_DT_EVENT_RAW_TOOL_RECV;
   ================================================================ */

-- --------------------------------------------
-- 1. 创建索引（测试环境 / 可停窗环境）
-- --------------------------------------------
-- 说明：
--   DT_EVENT_RAW 的 RECEIVED_TS_UTC 在量产库为 TIMESTAMP(6)，
--   本地/部分环境为 VARCHAR2；两种形态均可直接建 B-Tree 索引。
CREATE INDEX IDX_DT_EVENT_RAW_TOOL_RECV
    ON DT_EVENT_RAW (TOOL_ID, RECEIVED_TS_UTC);

-- --------------------------------------------
-- 量产环境推荐写法（需 Oracle Enterprise Edition）：
--   CREATE INDEX IDX_DT_EVENT_RAW_TOOL_RECV
--       ON DT_EVENT_RAW (TOOL_ID, RECEIVED_TS_UTC) ONLINE;
-- ONLINE 建索引期间不锁表，不影响业务写入。
-- --------------------------------------------

-- --------------------------------------------
-- 2. 收集统计信息（让 CBO 立即感知新索引）
-- --------------------------------------------
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'DT_EVENT_RAW');
END;
/

-- --------------------------------------------
-- 3. 验证（执行后应能看到 IDX_DT_EVENT_RAW_TOOL_RECV）
-- --------------------------------------------
-- SELECT INDEX_NAME, INDEX_TYPE, STATUS
-- FROM USER_INDEXES
-- WHERE TABLE_NAME = 'DT_EVENT_RAW';

-- --------------------------------------------
-- 回退语句（如需撤销）：
--   DROP INDEX IDX_DT_EVENT_RAW_TOOL_RECV;
-- --------------------------------------------
