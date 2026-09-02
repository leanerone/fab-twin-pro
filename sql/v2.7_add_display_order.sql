-- ======================================================================
-- FabTwin Pro v2.7→v2.9 D 批 升级脚本：补 display_order 列（用于图层置顶/置底）
--
-- 适用库：Oracle (emuuser schema / APCDB) / SQLite 本地测试库
-- 生效范围：MACHINES / FLOOR_AREAS 两张表各新增 1 列。
--
-- 说明：
--   * 本脚本幂等，重复执行不会报错。
--   * 启动时 backend/database.py 的 _ensure_missing_columns() 也会自动
--     执行等价的 ALTER，所以一般无需手动跑本脚本；这里为 DBA/部署同学
--     提供一份"手动方式"作为兜底或变更记录。
--   * 若 Oracle 账户执行 USER_TAB_COLUMNS 看不到自己的表，请确认当前
--     用户就是表所属 schema；否则改用 ALL_TAB_COLUMNS + OWNER 条件。
-- ======================================================================

-- ========== Oracle 段（在 emuuser 下执行即可）==========
DECLARE
    v_cnt NUMBER;
BEGIN
    -- 1) MACHINES.display_order
    SELECT COUNT(*) INTO v_cnt FROM USER_TAB_COLUMNS
     WHERE TABLE_NAME = 'MACHINES' AND COLUMN_NAME = 'DISPLAY_ORDER';
    IF v_cnt = 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE MACHINES ADD (DISPLAY_ORDER NUMBER(10) DEFAULT 0)';
        DBMS_OUTPUT.PUT_LINE('[OK] MACHINES.DISPLAY_ORDER added (DEFAULT 0)');
    ELSE
        DBMS_OUTPUT.PUT_LINE('[SKIP] MACHINES.DISPLAY_ORDER already exists');
    END IF;

    -- 2) FLOOR_AREAS.display_order
    SELECT COUNT(*) INTO v_cnt FROM USER_TAB_COLUMNS
     WHERE TABLE_NAME = 'FLOOR_AREAS' AND COLUMN_NAME = 'DISPLAY_ORDER';
    IF v_cnt = 0 THEN
        EXECUTE IMMEDIATE 'ALTER TABLE FLOOR_AREAS ADD (DISPLAY_ORDER NUMBER(10) DEFAULT 0)';
        DBMS_OUTPUT.PUT_LINE('[OK] FLOOR_AREAS.DISPLAY_ORDER added (DEFAULT 0)');
    ELSE
        DBMS_OUTPUT.PUT_LINE('[SKIP] FLOOR_AREAS.DISPLAY_ORDER already exists');
    END IF;
END;
/

COMMIT;
-- ===== Oracle 段 END ====================================================

-- ========== SQLite 段（本地 tests/local.db 等，用 sqlite3 或 tests/init_local_db.py 附带）==========
-- SQLite 不支持 IF NOT EXISTS 直接写在 ALTER ADD COLUMN 里，所以用匿名块等价写法：
-- 直接先试 PRAGMA 判断后再执行。sqlite3 CLI 支持 .read 时可逐句：
-- .param init
-- PRAGMA table_info('machines');
-- 下列 2 条仅当上面没返回 display_order 行时才需执行：
--   ALTER TABLE machines ADD COLUMN display_order INTEGER DEFAULT 0;
--   ALTER TABLE floor_areas ADD COLUMN display_order INTEGER DEFAULT 0;
--
-- 上面 2 句直接重复执行 SQLite 会返回"duplicate column name"错误，
-- 生产化建议用 Python（tests/init_local_db.py 已在 init_db() 后走自动补齐）。
-- ===== SQLite 段 END ====================================================
