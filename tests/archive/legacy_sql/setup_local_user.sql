-- 在 orclpdb 创建 fabtwin 用户并建测试表
-- 用法: sqlplus -S -L "/ as sysdba" @setup_local_user.sql

ALTER SESSION SET CONTAINER = orclpdb;

-- 删除旧用户（如存在）
BEGIN
  EXECUTE IMMEDIATE 'DROP USER fabtwin CASCADE';
EXCEPTION
  WHEN OTHERS THEN NULL;
END;
/

-- 创建用户
CREATE USER fabtwin IDENTIFIED BY fabtwin
  DEFAULT TABLESPACE users
  TEMPORARY TABLESPACE temp
  QUOTA UNLIMITED ON users;

GRANT CREATE SESSION, CREATE TABLE, CREATE SEQUENCE TO fabtwin;
GRANT UNLIMITED TABLESPACE TO fabtwin;

-- 切换到 fabtwin 建表
CONN fabtwin/fabtwin@//localhost:1521/orclpdb

-- 建表
CREATE TABLE dt_event_raw (
    tool_id         VARCHAR2(50),
    event_ts_utc    VARCHAR2(30),
    received_ts_utc VARCHAR2(30),
    payload_json    CLOB
);

CREATE TABLE dt_event_raw_cur (
    tool_id         VARCHAR2(50),
    event_ts_utc    VARCHAR2(30),
    received_ts_utc VARCHAR2(30),
    payload_json    CLOB
);

-- 今天 (2026-09-10)
INSERT INTO dt_event_raw VALUES ('OXE-1',  '2026-09-10 14:30:00', '2026-09-10 14:30:01', '{"event_name":"LotStart","lot_id":"L20260910-01","recipe":"RECIPE_A","machine_state":"Running","operator":"张三"}');
INSERT INTO dt_event_raw VALUES ('OXE-1',  '2026-09-10 15:00:00', '2026-09-10 15:00:01', '{"event_name":"WaferLoaded","lot_id":"L20260910-01","recipe":"RECIPE_A","machine_state":"Running"}');
INSERT INTO dt_event_raw VALUES ('OXE-1',  '2026-09-10 15:30:00', '2026-09-10 15:30:01', '{"event_name":"LotEnd","lot_id":"L20260910-01","recipe":"RECIPE_A","machine_state":"Idle","qty":25,"product":"WAFER_X"}');
INSERT INTO dt_event_raw VALUES ('OXE-51', '2026-09-10 15:14:47', '2026-09-10 15:14:48', '{"event_name":"WAFERLOADED","lot_id":"L20260910-02","machine_state":"Running"}');
INSERT INTO dt_event_raw VALUES ('OXE-51', '2026-09-10 14:00:00', '2026-09-10 14:00:01', '{"event_name":"EC_ALARM_REPORT","alarm_id":"A001","alarm_text":"温度超限","machine_state":"Alarm"}');
INSERT INTO dt_event_raw VALUES ('OXE-3',  '2026-09-10 09:00:00', '2026-09-10 09:00:01', '{"event_name":"Start","lot_id":"L20260910-03","machine_state":"Running"}');
INSERT INTO dt_event_raw VALUES ('OXE-3',  '2026-09-10 12:00:00', '2026-09-10 12:00:01', '{"event_name":"LotEnd","lot_id":"L20260910-03","qty":30,"product":"WAFER_Y","machine_state":"Idle"}');

-- 昨天 (2026-09-09)
INSERT INTO dt_event_raw VALUES ('OXE-1',  '2026-09-09 10:00:00', '2026-09-09 10:00:01', '{"event_name":"LotStart","lot_id":"L20260909-01","machine_state":"Running"}');
INSERT INTO dt_event_raw VALUES ('OXE-1',  '2026-09-09 16:00:00', '2026-09-09 16:00:01', '{"event_name":"LotEnd","lot_id":"L20260909-01","qty":20,"product":"WAFER_X","machine_state":"Idle"}');
INSERT INTO dt_event_raw VALUES ('OXE-51', '2026-09-09 11:00:00', '2026-09-09 11:00:01', '{"event_name":"Start","lot_id":"L20260909-02","machine_state":"Running"}');
INSERT INTO dt_event_raw VALUES ('OXE-3',  '2026-09-09 08:00:00', '2026-09-09 08:00:01', '{"event_name":"EC_ALARM_REPORT","alarm_id":"A002","alarm_text":"气压低","machine_state":"Alarm"}');

-- 前天 (2026-09-08)
INSERT INTO dt_event_raw VALUES ('OXE-1',  '2026-09-08 09:00:00', '2026-09-08 09:00:01', '{"event_name":"Start","lot_id":"L20260908-01","machine_state":"Running"}');
INSERT INTO dt_event_raw VALUES ('OXE-1',  '2026-09-08 17:00:00', '2026-09-08 17:00:01', '{"event_name":"LotEnd","lot_id":"L20260908-01","qty":15,"product":"WAFER_X","machine_state":"Idle"}');

-- cur 表
INSERT INTO dt_event_raw_cur VALUES ('OXE-1',  '2026-09-10 15:30:00', '2026-09-10 15:30:01', '{"event_name":"LotEnd","lot_id":"L20260910-01","recipe":"RECIPE_A","machine_state":"Idle","qty":25,"product":"WAFER_X"}');
INSERT INTO dt_event_raw_cur VALUES ('OXE-51', '2026-09-10 15:14:47', '2026-09-10 15:14:48', '{"event_name":"WAFERLOADED","lot_id":"L20260910-02","machine_state":"Running"}');
INSERT INTO dt_event_raw_cur VALUES ('OXE-3',  '2026-09-10 12:00:00', '2026-09-10 12:00:01', '{"event_name":"LotEnd","lot_id":"L20260910-03","qty":30,"product":"WAFER_Y","machine_state":"Idle"}');

COMMIT;

-- 验证
SELECT SUBSTR(event_ts_utc, 1, 10) AS day, COUNT(*) AS cnt FROM dt_event_raw GROUP BY SUBSTR(event_ts_utc, 1, 10) ORDER BY day DESC;
SELECT '---cur---' FROM dual;
SELECT tool_id, event_ts_utc FROM dt_event_raw_cur ORDER BY tool_id;

EXIT;
