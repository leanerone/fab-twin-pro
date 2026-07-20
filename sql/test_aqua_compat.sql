/* Aqua Data Studio 兼容性测试脚本
   执行此脚本验证 Aqua SQL 是否能正确解析
*/
-- 测试1: 简单查询
SELECT 'TEST_BASIC' AS test_name, 1 AS value FROM DUAL;

-- 测试2: PL/SQL 块（模拟 TRIGGER 创建）
BEGIN
    NULL;
END;
/

-- 测试3: CREATE SEQUENCE（如不存在则创建）
CREATE SEQUENCE TEST_AQUA_SEQ START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE;

-- 测试4: 删除测试序列
DROP SEQUENCE TEST_AQUA_SEQ;

-- 测试完成
SELECT 'TEST_COMPLETE' AS result FROM DUAL;
