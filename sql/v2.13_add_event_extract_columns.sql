/* ================================================================
   ver2.13 增量脚本：DT_EVENT_RAW 物化列 + 索引 + 提取触发器
   生成时间: 2026-10-26
   背景（测试报告雷区A/B，docs/TEST31_数据读写测试报告_20261026.md）:
     - 雷区A: payload_json 是 CLOB，全仓 14 处 LIKE '%lot%' / '%alarm_code%'
       查询在千万级表上全表扫描（lot 命中 645s，404 也要 703s）。
     - 雷区B: 缺 (TOOL_ID, RAW_ID) 复合索引，实时模式查询 490s。
   本脚本内容:
     1. DT_EVENT_RAW 增加 3 个物化列: LOT_ID / EVENT_NAME / ALARM_CODE
     2. 建立 3 个索引（雷区B 复合索引 + 2 个稀疏物化列索引）
     3. BEFORE INSERT 触发器：从 payload_json 用 REGEXP_SUBSTR 提取三列
        —— 兜底 WinForm 等直写 SQL、不经过后端 ORM listener 的写入路径
   配套应用侧改动（已随 ver2.13 代码发布）:
     - 后端 models.py before_insert listener 自动填列（ORM 写入路径）
     - 存量历史行由 tests/backfill_event_columns.py 回填（先跑本脚本 1/2，
       再跑回填，最后启用触发器或直接全量执行）
     - 14 处 LIKE 查询已改为物化列等值过滤
   兼容: Oracle 11g/12c/19c（REGEXP_SUBSTR 支持 CLOB 与 subexpr 参数）
   回退: 见文件末尾
   ================================================================ */

-- --------------------------------------------
-- 1. 增加物化列（幂等：已存在则跳过）
-- --------------------------------------------
BEGIN
    FOR c IN (
        SELECT 'LOT_ID'     AS col, 'VARCHAR2(64)'  AS dtype FROM DUAL UNION ALL
        SELECT 'EVENT_NAME' AS col, 'VARCHAR2(128)' FROM DUAL UNION ALL
        SELECT 'ALARM_CODE' AS col, 'VARCHAR2(64)'  FROM DUAL
    ) LOOP
        DECLARE
            v_cnt NUMBER;
        BEGIN
            SELECT COUNT(*) INTO v_cnt FROM USER_TAB_COLUMNS
            WHERE TABLE_NAME = 'DT_EVENT_RAW' AND COLUMN_NAME = c.col;
            IF v_cnt = 0 THEN
                EXECUTE IMMEDIATE 'ALTER TABLE DT_EVENT_RAW ADD (' || c.col || ' ' || c.dtype || ')';
            END IF;
        END;
    END LOOP;
END;
/

-- --------------------------------------------
-- 2. 创建索引（幂等：已存在则跳过）
-- --------------------------------------------
-- IDX_DT_EVENT_RAW_TOOL_RAW : 雷区B。tool_id=? AND raw_id<? ORDER BY raw_id DESC
--   变 INDEX RANGE SCAN DESCENDING。
-- IDX_DT_EVENT_RAW_LOT / IDX_DT_EVENT_RAW_ALARM : 雷区A 物化列索引。
--   Oracle 不索引全 NULL 行 → 天然稀疏索引，只覆盖有 lot/告警的行。
-- 注意: 千万级表上 CREATE INDEX 需要数分钟，建议低峰执行；
--       量产 Enterprise Edition 可在语句末尾加 ONLINE 不锁表。
BEGIN
    FOR i IN (
        SELECT 'IDX_DT_EVENT_RAW_TOOL_RAW' AS idx, '(TOOL_ID, RAW_ID)' AS cols FROM DUAL UNION ALL
        SELECT 'IDX_DT_EVENT_RAW_LOT'      AS idx, '(LOT_ID)'          AS cols FROM DUAL UNION ALL
        SELECT 'IDX_DT_EVENT_RAW_ALARM'    AS idx, '(ALARM_CODE)'      AS cols FROM DUAL
    ) LOOP
        DECLARE
            v_cnt NUMBER;
        BEGIN
            SELECT COUNT(*) INTO v_cnt FROM USER_INDEXES WHERE INDEX_NAME = i.idx;
            IF v_cnt = 0 THEN
                EXECUTE IMMEDIATE 'CREATE INDEX ' || i.idx || ' ON DT_EVENT_RAW ' || i.cols;
            END IF;
        END;
    END LOOP;
END;
/

-- --------------------------------------------
-- 3. 提取触发器（直写 SQL 路径的兜底填列）
-- --------------------------------------------
-- 逻辑与后端 models.py extract_payload_fields() 一致：
--   从 payload_json 中提取 "lot_id" / "event_name" / "alarm_code" 的字符串值；
--   JSON null（无引号）不匹配 → 列保持 NULL；
--   值为 ''/'NULL'/'null' 字符串（灌库脏数据）→ 归一为 NULL（与后端 _norm 一致）；
--   超长截断到列宽。
-- 仅在对应列为 NULL 时填充，不覆盖应用已填好的值（与后端 listener 幂等共存）。
-- VFEI 信封结构（{"msg_type":"VFEI","data":{...}}）无需特殊处理：
--   正则在整条 payload 内搜索键名，嵌套层级的键一样命中。
CREATE OR REPLACE TRIGGER TRG_DT_EVENT_RAW_EXTRACT
BEFORE INSERT ON DT_EVENT_RAW
FOR EACH ROW
DECLARE
    v_lot   VARCHAR2(64);
    v_evt   VARCHAR2(128);
    v_alarm VARCHAR2(64);
BEGIN
    IF :NEW.LOT_ID IS NULL THEN
        v_lot := SUBSTR(
            REGEXP_SUBSTR(:NEW.PAYLOAD_JSON, '"lot_id"[ ]*:[ ]*"([^"]+)"', 1, 1, NULL, 1),
            1, 64);
        :NEW.LOT_ID := CASE WHEN v_lot IS NULL OR UPPER(v_lot) = 'NULL' THEN NULL ELSE v_lot END;
    END IF;
    IF :NEW.EVENT_NAME IS NULL THEN
        v_evt := SUBSTR(
            REGEXP_SUBSTR(:NEW.PAYLOAD_JSON, '"event_name"[ ]*:[ ]*"([^"]+)"', 1, 1, NULL, 1),
            1, 128);
        :NEW.EVENT_NAME := CASE WHEN v_evt IS NULL OR UPPER(v_evt) = 'NULL' THEN NULL ELSE v_evt END;
    END IF;
    IF :NEW.ALARM_CODE IS NULL THEN
        v_alarm := SUBSTR(
            REGEXP_SUBSTR(:NEW.PAYLOAD_JSON, '"alarm_code"[ ]*:[ ]*"([^"]+)"', 1, 1, NULL, 1),
            1, 64);
        :NEW.ALARM_CODE := CASE WHEN v_alarm IS NULL OR UPPER(v_alarm) = 'NULL' THEN NULL ELSE v_alarm END;
    END IF;
END;
/

-- --------------------------------------------
-- 4. 收集统计信息（让 CBO 立即感知新索引/新列）
-- --------------------------------------------
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'DT_EVENT_RAW');
END;
/

-- --------------------------------------------
-- 5. 验证（去掉注释执行）
-- --------------------------------------------
-- 列与索引应全部存在：
-- SELECT COLUMN_NAME, DATA_TYPE FROM USER_TAB_COLUMNS
-- WHERE TABLE_NAME = 'DT_EVENT_RAW'
--   AND COLUMN_NAME IN ('LOT_ID', 'EVENT_NAME', 'ALARM_CODE');
--
-- SELECT INDEX_NAME, STATUS FROM USER_INDEXES
-- WHERE TABLE_NAME = 'DT_EVENT_RAW'
--   AND INDEX_NAME IN ('IDX_DT_EVENT_RAW_TOOL_RAW', 'IDX_DT_EVENT_RAW_LOT', 'IDX_DT_EVENT_RAW_ALARM');
--
-- SELECT TRIGGER_NAME, STATUS FROM USER_TRIGGERS
-- WHERE TRIGGER_NAME = 'TRG_DT_EVENT_RAW_EXTRACT';
--
-- 回填进度验证（回填脚本跑完后 LOT_ID 非 NULL 行数应 > 0）：
-- SELECT COUNT(*) AS total,
--        COUNT(LOT_ID) AS has_lot,
--        COUNT(ALARM_CODE) AS has_alarm
-- FROM DT_EVENT_RAW;

-- --------------------------------------------
-- 回退语句（如需撤销，按顺序执行）：
--   DROP TRIGGER TRG_DT_EVENT_RAW_EXTRACT;
--   DROP INDEX IDX_DT_EVENT_RAW_TOOL_RAW;
--   DROP INDEX IDX_DT_EVENT_RAW_LOT;
--   DROP INDEX IDX_DT_EVENT_RAW_ALARM;
--   ALTER TABLE DT_EVENT_RAW DROP (LOT_ID, EVENT_NAME, ALARM_CODE);
-- --------------------------------------------
