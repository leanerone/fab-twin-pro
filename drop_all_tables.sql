connect fabtwin/fabtwin@localhost:1521/ORCLPDB;
BEGIN
  FOR rec IN (SELECT table_name FROM user_tables) LOOP
    EXECUTE IMMEDIATE 'DROP TABLE ' || rec.table_name || ' CASCADE CONSTRAINTS PURGE';
  END LOOP;
END;
/
exit;
