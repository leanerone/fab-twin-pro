-- ================================================================
-- DB清理脚本：保留 PODOPENER-1，清理其他机台数据
-- 生成时间: 2026-07-20
-- 说明: 请先检查后执行，执行前建议备份
-- ================================================================

SET DEFINE OFF;

-- ============================================
-- 步骤0: 修复 DT_STATE_SNAPSHOT 中 VPO-01 残留（改名为 PODOPENER-1）
-- ============================================
UPDATE DT_STATE_SNAPSHOT SET TOOL_ID = 'PODOPENER-1' WHERE TOOL_ID = 'VPO-01';
-- 预期影响: 10 行

-- ============================================
-- 步骤1: DT表清理（量产数据，只清理非PODOPENER-1）
-- ============================================

-- DT_EVENT_RAW: 清理 1850 条，保留 713 条
DELETE FROM DT_EVENT_RAW WHERE TOOL_ID != 'PODOPENER-1';

-- DT_EVENT_STD: 清理 1850 条，保留 713 条
DELETE FROM DT_EVENT_STD WHERE TOOL_ID != 'PODOPENER-1';

-- DT_ALARM_EVENT: 清理 308 条，保留 462 条
DELETE FROM DT_ALARM_EVENT WHERE TOOL_ID != 'PODOPENER-1';

-- DT_STATE_SNAPSHOT: 清理 370 条，保留 10 条（步骤0修复后）
DELETE FROM DT_STATE_SNAPSHOT WHERE TOOL_ID != 'PODOPENER-1';

-- DT_EVENT_RAW_CUR: 清理 0 条（当前无数据）
DELETE FROM DT_EVENT_RAW_CUR WHERE TOOL_ID != 'PODOPENER-1';

-- ============================================
-- 步骤2: 平台表清理（模拟数据，只清理非PODOPENER-1）
-- ============================================

-- MACHINE_EVENTS: 清理 276390 条，保留 9249 条
DELETE FROM MACHINE_EVENTS WHERE MACHINE_ID != 'PODOPENER-1';

-- ALARMS: 清理 431 条，保留 15 条
DELETE FROM ALARMS WHERE MACHINE_ID != 'PODOPENER-1';

-- LOTS: 清理 1435 条，保留 36 条
DELETE FROM LOTS WHERE MACHINE_ID != 'PODOPENER-1';

-- CHAMBER_SNAPSHOTS: 清理 4440 条，保留 120 条
DELETE FROM CHAMBER_SNAPSHOTS WHERE MACHINE_ID != 'PODOPENER-1';

-- ============================================
-- 步骤3: 确认保留数据
-- ============================================
-- MACHINES表: 保留所有38台机台定义（floor布局需要）
-- MACHINE_MODEL_CONFIGS: 保留所有3个模型配置
-- EVENT_ACTION_MAPPINGS: 保留所有3条映射
-- MACHINE_TOOL_MAPPINGS: 保留所有1条映射

COMMIT;

-- ============================================
-- 验证查询（执行后运行）
-- ============================================
-- SELECT 'DT_EVENT_RAW' AS T, COUNT(*) FROM DT_EVENT_RAW
-- UNION ALL SELECT 'DT_EVENT_STD', COUNT(*) FROM DT_EVENT_STD
-- UNION ALL SELECT 'DT_ALARM_EVENT', COUNT(*) FROM DT_ALARM_EVENT
-- UNION ALL SELECT 'DT_STATE_SNAPSHOT', COUNT(*) FROM DT_STATE_SNAPSHOT
-- UNION ALL SELECT 'MACHINE_EVENTS', COUNT(*) FROM MACHINE_EVENTS
-- UNION ALL SELECT 'ALARMS', COUNT(*) FROM ALARMS
-- UNION ALL SELECT 'LOTS', COUNT(*) FROM LOTS
-- UNION ALL SELECT 'CHAMBER_SNAPSHOTS', COUNT(*) FROM CHAMBER_SNAPSHOTS;
