-- ============================================================================
-- [已废弃] FabTwin v2.0 升级脚本：添加 animation_config_json 和 source_files_json 字段
-- 说明：新部署使用 init_oracle_db.sql 已包含这两个字段，无需执行此脚本
--       仅对 v2.0 之前已部署的旧环境增量升级时使用
--       Aqua Data Studio 用户请使用 v2.0_upgrade_animation_config_aqua.sql
-- 用途：对现有数据库进行增量升级（不重新初始化）
-- 执行方式（Oracle）：
--   sqlplus fabtwin/password@localhost:1521/ORCLPDB1 @v2.0_upgrade_animation_config.sql
-- 说明：
--   1. 检查字段是否已存在，若存在则跳过
--   2. 新增字段默认值为空JSON对象 {}
--   3. 添加字段注释说明用途
-- ============================================================================

SET DEFINE OFF;
SET SQLBLANKLINES ON;

PROMPT ========================================
PROMPT 开始执行 v2.0 升级脚本...
PROMPT ========================================

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
        EXECUTE IMMEDIATE 'ALTER TABLE machine_model_configs ADD (
            animation_config_json CLOB DEFAULT ''{}''
        )';
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
        EXECUTE IMMEDIATE 'ALTER TABLE machine_model_configs ADD (
            source_files_json CLOB DEFAULT ''{}''
        )';
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
BEGIN
    EXECUTE IMMEDIATE 'COMMENT ON COLUMN machine_model_configs.animation_config_json IS
        ''统一动画配置（v2.0新增）：包含 flows/phases/animations/targets，替代静态 JSON 文件''';
    DBMS_OUTPUT.put_line('[SUCCESS] 已添加注释: ANIMATION_CONFIG_JSON');
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.put_line('[WARN] 添加注释失败: ' || SQLERRM);
END;
/

BEGIN
    EXECUTE IMMEDIATE 'COMMENT ON COLUMN machine_model_configs.source_files_json IS
        ''来源文件信息（v2.0新增）：记录 HTML/SVG/GLB 解析状态和版本''';
    DBMS_OUTPUT.put_line('[SUCCESS] 已添加注释: SOURCE_FILES_JSON');
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.put_line('[WARN] 添加注释失败: ' || SQLERRM);
END;
/

-- ============================================
-- 4. 验证升级结果
-- ============================================
PROMPT ========================================
PROMPT 验证字段是否添加成功...
PROMPT ========================================

SELECT column_name,
       data_type,
       nullable,
       data_default
FROM user_tab_columns
WHERE table_name = 'MACHINE_MODEL_CONFIGS'
AND column_name IN ('ANIMATION_CONFIG_JSON', 'SOURCE_FILES_JSON')
ORDER BY column_name;

PROMPT ========================================
PROMPT 升级完成！
PROMPT 后续步骤：
PROMPT   1. 运行 migrate_animation_config.py 迁移数据
PROMPT   2. 重启后端服务使字段生效
PROMPT ========================================