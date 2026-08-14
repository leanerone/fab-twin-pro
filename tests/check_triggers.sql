SELECT trigger_name, status FROM user_triggers WHERE trigger_name LIKE 'TRG_%';
SELECT '---' FROM dual;
SELECT trigger_name, trigger_body FROM user_triggers WHERE trigger_name LIKE 'TRG_AI%' AND status='INVALID';
EXIT
