-- ver3：修复平台查询列过宽导致复合索引 ORA-01450。
-- 仅收敛 ORM 已声明为 String(255) 的查询列；DESCRIPTION 等长文本不变。
-- 执行前检查实际字节长度，存在超长数据时中止，不静默截断。
SET DEFINE OFF

DECLARE
  TYPE column_spec IS RECORD (table_name VARCHAR2(30), column_name VARCHAR2(30));
  TYPE column_specs IS TABLE OF column_spec;
  specs column_specs := column_specs(
    column_spec('MACHINE_EVENTS', 'MACHINE_ID'),
    column_spec('MACHINE_EVENTS', 'TIMESTAMP'),
    column_spec('ALARMS', 'MACHINE_ID'),
    column_spec('ALARMS', 'TIMESTAMP'),
    column_spec('OHT_POSITIONS', 'OHT_ID'),
    column_spec('OHT_POSITIONS', 'TIMESTAMP'),
    column_spec('LOTS', 'MACHINE_ID'),
    column_spec('LOTS', 'STATUS')
  );
  max_bytes NUMBER;
BEGIN
  FOR i IN 1 .. specs.COUNT LOOP
    EXECUTE IMMEDIATE 'SELECT NVL(MAX(LENGTHB("' || specs(i).column_name || '")),0) FROM ' || specs(i).table_name
      INTO max_bytes;
    IF max_bytes > 255 THEN
      RAISE_APPLICATION_ERROR(-20001, specs(i).table_name || '.' || specs(i).column_name ||
        ' 存在超过 255 字节的数据，已中止；请先人工清理，禁止静默截断');
    END IF;
  END LOOP;

  FOR i IN 1 .. specs.COUNT LOOP
    EXECUTE IMMEDIATE 'ALTER TABLE ' || specs(i).table_name || ' MODIFY ("' ||
      specs(i).column_name || '" VARCHAR2(255))';
  END LOOP;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX IDX_MACHINE_EVENTS_MID_TS ON MACHINE_EVENTS (MACHINE_ID, "TIMESTAMP")';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE NOT IN (-955, -1408) THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX IDX_ALARMS_MID_TS ON ALARMS (MACHINE_ID, "TIMESTAMP")';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE NOT IN (-955, -1408) THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX IDX_OHT_POS_OID_TS ON OHT_POSITIONS (OHT_ID, "TIMESTAMP")';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE NOT IN (-955, -1408) THEN RAISE; END IF;
END;
/

BEGIN
  EXECUTE IMMEDIATE 'CREATE INDEX IDX_LOTS_MID_STATUS ON LOTS (MACHINE_ID, STATUS)';
EXCEPTION WHEN OTHERS THEN
  IF SQLCODE NOT IN (-955, -1408) THEN RAISE; END IF;
END;
/

COMMIT;
