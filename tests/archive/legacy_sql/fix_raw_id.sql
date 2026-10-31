-- 给 dt_event_raw_cur 加 raw_id 列（F1 查询需要）
CONN fabtwin/fabtwin@//localhost:1521/orclpdb

ALTER TABLE dt_event_raw_cur ADD (raw_id NUMBER);
UPDATE dt_event_raw_cur SET raw_id = ROWNUM;
COMMIT;

SELECT tool_id, raw_id, event_ts_utc FROM dt_event_raw_cur ORDER BY tool_id;
EXIT;
