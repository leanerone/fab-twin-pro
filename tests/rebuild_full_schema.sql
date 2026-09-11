-- 按后端 ORM 完整 schema 重建测试表
CONN fabtwin/fabtwin@//localhost:1521/orclpdb

DROP TABLE dt_event_raw_cur;
DROP TABLE dt_event_raw;

-- dt_event_raw 完整 schema（匹配 ORM）
CREATE TABLE dt_event_raw (
    raw_id            VARCHAR2(255) PRIMARY KEY,
    tool_id           VARCHAR2(255) NOT NULL,
    source_system     VARCHAR2(255) NOT NULL,
    source_message_id VARCHAR2(255) NOT NULL,
    received_ts_utc   VARCHAR2(255),
    event_ts_utc      VARCHAR2(255),
    payload_json      CLOB,
    parse_status      VARCHAR2(255) DEFAULT 'NEW',
    error_message     VARCHAR2(255)
);
CREATE INDEX idx_dt_event_raw_tool ON dt_event_raw(tool_id);
CREATE INDEX idx_dt_event_raw_recv ON dt_event_raw(received_ts_utc);

-- dt_event_raw_cur 完整 schema
CREATE TABLE dt_event_raw_cur (
    tool_id           VARCHAR2(255) PRIMARY KEY,
    raw_id            VARCHAR2(255),
    source_system     VARCHAR2(255) NOT NULL,
    source_message_id VARCHAR2(255) NOT NULL,
    received_ts_utc   VARCHAR2(255),
    event_ts_utc      VARCHAR2(255),
    payload_json      CLOB,
    parse_status      VARCHAR2(255) DEFAULT 'NEW',
    error_message     VARCHAR2(255)
);
CREATE INDEX idx_dt_event_raw_cur_recv ON dt_event_raw_cur(received_ts_utc);

-- 今天 (2026-09-10)
INSERT INTO dt_event_raw VALUES ('R001', 'OXE-1',  'TIBRV', 'M001', '2026-09-10 14:30:01', '2026-09-10 14:30:00', '{"event_name":"LotStart","lot_id":"L20260910-01","recipe":"RECIPE_A","machine_state":"Running","operator":"张三"}', 'PARSED', NULL);
INSERT INTO dt_event_raw VALUES ('R002', 'OXE-1',  'TIBRV', 'M002', '2026-09-10 15:00:01', '2026-09-10 15:00:00', '{"event_name":"WaferLoaded","lot_id":"L20260910-01","recipe":"RECIPE_A","machine_state":"Running"}', 'PARSED', NULL);
INSERT INTO dt_event_raw VALUES ('R003', 'OXE-1',  'TIBRV', 'M003', '2026-09-10 15:30:01', '2026-09-10 15:30:00', '{"event_name":"LotEnd","lot_id":"L20260910-01","recipe":"RECIPE_A","machine_state":"Idle","qty":25,"product":"WAFER_X"}', 'PARSED', NULL);
INSERT INTO dt_event_raw VALUES ('R004', 'OXE-51', 'TIBRV', 'M004', '2026-09-10 15:14:48', '2026-09-10 15:14:47', '{"event_name":"WAFERLOADED","lot_id":"L20260910-02","machine_state":"Running"}', 'PARSED', NULL);
INSERT INTO dt_event_raw VALUES ('R005', 'OXE-51', 'TIBRV', 'M005', '2026-09-10 14:00:01', '2026-09-10 14:00:00', '{"event_name":"EC_ALARM_REPORT","alarm_id":"A001","alarm_text":"温度超限","machine_state":"Alarm"}', 'PARSED', NULL);
INSERT INTO dt_event_raw VALUES ('R006', 'OXE-3',  'TIBRV', 'M006', '2026-09-10 09:00:01', '2026-09-10 09:00:00', '{"event_name":"Start","lot_id":"L20260910-03","machine_state":"Running"}', 'PARSED', NULL);
INSERT INTO dt_event_raw VALUES ('R007', 'OXE-3',  'TIBRV', 'M007', '2026-09-10 12:00:01', '2026-09-10 12:00:00', '{"event_name":"LotEnd","lot_id":"L20260910-03","qty":30,"product":"WAFER_Y","machine_state":"Idle"}', 'PARSED', NULL);
-- 昨天
INSERT INTO dt_event_raw VALUES ('R008', 'OXE-1',  'TIBRV', 'M008', '2026-09-09 10:00:01', '2026-09-09 10:00:00', '{"event_name":"LotStart","lot_id":"L20260909-01","machine_state":"Running"}', 'PARSED', NULL);
INSERT INTO dt_event_raw VALUES ('R009', 'OXE-1',  'TIBRV', 'M009', '2026-09-09 16:00:01', '2026-09-09 16:00:00', '{"event_name":"LotEnd","lot_id":"L20260909-01","qty":20,"product":"WAFER_X","machine_state":"Idle"}', 'PARSED', NULL);
INSERT INTO dt_event_raw VALUES ('R010', 'OXE-51', 'TIBRV', 'M010', '2026-09-09 11:00:01', '2026-09-09 11:00:00', '{"event_name":"Start","lot_id":"L20260909-02","machine_state":"Running"}', 'PARSED', NULL);
INSERT INTO dt_event_raw VALUES ('R011', 'OXE-3',  'TIBRV', 'M011', '2026-09-09 08:00:01', '2026-09-09 08:00:00', '{"event_name":"EC_ALARM_REPORT","alarm_id":"A002","alarm_text":"气压低","machine_state":"Alarm"}', 'PARSED', NULL);
-- 前天
INSERT INTO dt_event_raw VALUES ('R012', 'OXE-1',  'TIBRV', 'M012', '2026-09-08 09:00:01', '2026-09-08 09:00:00', '{"event_name":"Start","lot_id":"L20260908-01","machine_state":"Running"}', 'PARSED', NULL);
INSERT INTO dt_event_raw VALUES ('R013', 'OXE-1',  'TIBRV', 'M013', '2026-09-08 17:00:01', '2026-09-08 17:00:00', '{"event_name":"LotEnd","lot_id":"L20260908-01","qty":15,"product":"WAFER_X","machine_state":"Idle"}', 'PARSED', NULL);

-- cur 表（每台最新）
INSERT INTO dt_event_raw_cur VALUES ('OXE-1',  'R003', 'TIBRV', 'M003', '2026-09-10 15:30:01', '2026-09-10 15:30:00', '{"event_name":"LotEnd","lot_id":"L20260910-01","recipe":"RECIPE_A","machine_state":"Idle","qty":25,"product":"WAFER_X"}', 'PARSED', NULL);
INSERT INTO dt_event_raw_cur VALUES ('OXE-51', 'R004', 'TIBRV', 'M004', '2026-09-10 15:14:48', '2026-09-10 15:14:47', '{"event_name":"WAFERLOADED","lot_id":"L20260910-02","machine_state":"Running"}', 'PARSED', NULL);
INSERT INTO dt_event_raw_cur VALUES ('OXE-3',  'R007', 'TIBRV', 'M007', '2026-09-10 12:00:01', '2026-09-10 12:00:00', '{"event_name":"LotEnd","lot_id":"L20260910-03","qty":30,"product":"WAFER_Y","machine_state":"Idle"}', 'PARSED', NULL);

COMMIT;

-- 验证
SELECT SUBSTR(event_ts_utc, 1, 10) AS day, COUNT(*) AS cnt FROM dt_event_raw GROUP BY SUBSTR(event_ts_utc, 1, 10) ORDER BY day DESC;
SELECT '---cur---' FROM dual;
SELECT tool_id, raw_id, event_ts_utc FROM dt_event_raw_cur ORDER BY tool_id;

EXIT;
