-- =====================================================
-- v2.6 机台外部跳转链接（iframe 嵌入）字段升级
-- 适用：Oracle 10g/11g/12c+/19c+
-- 表：machines
-- 新增字段：
--   external_url       VARCHAR2(500)  外部跳转网站 URL
--   use_external_url   NUMBER(1)      是否使用跳转网站：0=原路线，1=跳转网站
-- 注意：本脚本只加列，不改 DT 量产数据；可重复执行（容错）
-- =====================================================

-- 安全模式：先判断列是否存在（USER_TAB_COLUMNS），不存在才加
BEGIN
  -- external_url
  BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE machines ADD external_url VARCHAR2(500) DEFAULT ''''';
  EXCEPTION
    WHEN OTHERS THEN
      IF SQLERRM LIKE '%ORA-01430%' OR SQLERRM LIKE '%already exists%' THEN NULL;
      ELSE RAISE;
      END IF;
  END;

  -- use_external_url
  BEGIN
    EXECUTE IMMEDIATE 'ALTER TABLE machines ADD use_external_url NUMBER(1) DEFAULT 0';
  EXCEPTION
    WHEN OTHERS THEN
      IF SQLERRM LIKE '%ORA-01430%' OR SQLERRM LIKE '%already exists%' THEN NULL;
      ELSE RAISE;
      END IF;
  END;
END;
/

-- 校验
COMMENT ON COLUMN machines.external_url IS '外部跳转网站 URL（iframe 嵌入），空=不跳转';
COMMENT ON COLUMN machines.use_external_url IS '是否使用外部跳转网站：0=原路线(机台详情)，1=跳转网站(iframe)';

-- 查询确认
SELECT id, external_url, use_external_url FROM machines WHERE ROWNUM <= 5;
