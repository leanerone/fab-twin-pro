-- ============================================================================
-- [已废弃] FabTwin v2.0 数据库迁移：新增 animation_config_json 和 source_files_json 字段
-- 说明：新部署使用 init_oracle_db.sql 已包含这两个字段，无需执行此脚本
--       仅对 v2.0 之前已部署的旧环境增量升级时使用
-- 执行方式：
--   Oracle: sqlplus user/pass@db @v2.0_add_animation_config.sql
--   SQLite: 不需要执行，SQLAlchemy 会自动创建新字段
-- ============================================================================

-- 说明：
-- 此迁移为 machine_model_configs 表新增两个字段：
-- 1. animation_config_json: 存储统一动画配置（flows/animations/targets）
--    - 替代原 configs/machine-animations/*.json 静态文件
--    - 支持运行时修改，无需重新构建前端
-- 2. source_files_json: 存储来源文件路径及解析状态
--    - 记录 HTML/SVG/GLB 文件的解析结果
--    - 用于版本追溯和增量更新

-- ============================================================================
-- Oracle 版本
-- ============================================================================

-- 检查字段是否已存在（Oracle 不支持 IF NOT EXISTS）
-- 如果字段已存在会报错，可以忽略继续执行

-- 新增 animation_config_json 字段
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
        DBMS_OUTPUT.put_line('Added column: animation_config_json');
    ELSE
        DBMS_OUTPUT.put_line('Column already exists: animation_config_json');
    END IF;
END;
/

-- 新增 source_files_json 字段
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
        DBMS_OUTPUT.put_line('Added column: source_files_json');
    ELSE
        DBMS_OUTPUT.put_line('Column already exists: source_files_json');
    END IF;
END;
/

-- 添加字段注释
COMMENT ON COLUMN machine_model_configs.animation_config_json IS
'统一动画配置（v2.0新增）：包含 flows/phases/animations/targets，替代静态 JSON 文件';

COMMENT ON COLUMN machine_model_configs.source_files_json IS
'来源文件信息（v2.0新增）：记录 HTML/SVG/GLB 解析状态和版本';

-- ============================================================================
-- SQLite 版本（如果使用 SQLite，执行以下语句）
-- ============================================================================

-- SQLite 版本（取消注释执行）
-- ALTER TABLE machine_model_configs ADD COLUMN animation_config_json TEXT DEFAULT '{}';
-- ALTER TABLE machine_model_configs ADD COLUMN source_files_json TEXT DEFAULT '{}';

-- ============================================================================
-- 数据迁移：将 PODOPENER-2200 的动画配置写入 DB
-- ============================================================================

-- 注意：Oracle CLOB 更新需要在 Python 中执行，因为内容较长
-- 请使用后端的 migrate_animation_config.py 脚本完成迁移

-- 验证迁移结果：
-- SELECT model_id,
--        DBMS_LOB.SUBSTR(animation_config_json, 100, 1) as config_preview,
--        LENGTH(animation_config_json) as config_length
-- FROM machine_model_configs
-- WHERE model_id = 'PODOPENER-2200';

-- ============================================================================
-- 完成提示
-- ============================================================================

PROMPT Migration v2.0 completed successfully!
PROMPT New columns added: animation_config_json, source_files_json
PROMPT Please run migrate_animation_config.py to populate initial data.