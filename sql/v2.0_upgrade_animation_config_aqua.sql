/* ============================================================================
   FabTwin v2.0 升级脚本 - Aqua Data Studio 兼容版
   用途：为 MACHINE_MODEL_CONFIGS 表新增 animation_config_json 和 source_files_json 字段
   适用于：对现有数据库进行增量升级（不重新初始化）

   Aqua Data Studio 使用方法：
   1. 连接到 Oracle 数据库（fabtwin 用户）
   2. 打开此文件：File -> Open -> v2.0_upgrade_animation_config_aqua.sql
   3. 执行：Query -> Execute All (或 F5)
   4. 检查执行日志确认无错误

   说明：
   - 已移除所有 SQL*Plus 专用命令（PROMPT/SET 等）
   - 仅使用纯 SQL + PL/SQL 块
   - 兼容 Aqua Data Studio / DBeaver / SQL Developer / Toad
   ============================================================================ */

-- ============================================
-- 1. 新增 ANIMATION_CONFIG_JSON 字段
-- ============================================
DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM user_tab_columns
    WHERE table_name = 'MACHINE_MODEL_CONFIGS'
    AND column_name = 'ANIMATION_CONFIG_JSON';

    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE machine_model_configs ADD (animation_config_json CLOB DEFAULT ''{}'')';
        DBMS_OUTPUT.put_line('[SUCCESS] 已添加字段: ANIMATION_CONFIG_JSON');
    ELSE
        DBMS_OUTPUT.put_line('[SKIP] 字段已存在: ANIMATION_CONFIG_JSON');
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.put_line('[ERROR] 添加字段失败: ANIMATION_CONFIG_JSON - ' || SQLERRM);
END;
/

-- ============================================
-- 2. 新增 SOURCE_FILES_JSON 字段
-- ============================================
DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM user_tab_columns
    WHERE table_name = 'MACHINE_MODEL_CONFIGS'
    AND column_name = 'SOURCE_FILES_JSON';

    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE machine_model_configs ADD (source_files_json CLOB DEFAULT ''{}'')';
        DBMS_OUTPUT.put_line('[SUCCESS] 已添加字段: SOURCE_FILES_JSON');
    ELSE
        DBMS_OUTPUT.put_line('[SKIP] 字段已存在: SOURCE_FILES_JSON');
    END IF;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.put_line('[ERROR] 添加字段失败: SOURCE_FILES_JSON - ' || SQLERRM);
END;
/

-- ============================================
-- 3. 添加字段注释
-- ============================================
COMMENT ON COLUMN machine_model_configs.animation_config_json IS '统一动画配置（v2.0新增）：包含 flows/phases/animations/targets，替代静态 JSON 文件';

COMMENT ON COLUMN machine_model_configs.source_files_json IS '来源文件信息（v2.0新增）：记录 HTML/SVG/GLB 解析状态和版本';

-- ============================================
-- 4. 验证升级结果
-- ============================================
SELECT column_name,
       data_type,
       nullable,
       data_default
FROM user_tab_columns
WHERE table_name = 'MACHINE_MODEL_CONFIGS'
AND column_name IN ('ANIMATION_CONFIG_JSON', 'SOURCE_FILES_JSON')
ORDER BY column_name;
