#!/usr/bin/env python3
"""
创建 AI_USAGE_LOGS 表（如果不存在）
并添加新字段到已有表
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import engine
from sqlalchemy import text

def create_or_migrate_ai_usage_logs():
    print("=" * 60)
    print("检查并创建/迁移 AI_USAGE_LOGS 表")
    print("=" * 60)
    
    with engine.connect() as conn:
        # 1. 检查表是否存在
        result = conn.execute(text("""
            SELECT COUNT(*) FROM USER_TABLES 
            WHERE TABLE_NAME = 'AI_USAGE_LOGS'
        """))
        table_exists = result.fetchone()[0] > 0
        
        if not table_exists:
            print("\n📋 表不存在，正在创建 AI_USAGE_LOGS 表...")
            
            # 创建表
            create_sql = """
                CREATE TABLE AI_USAGE_LOGS (
                    ID                 NUMBER        NOT NULL,
                    SESSION_ID         VARCHAR2(255),
                    CONFIG_ID          NUMBER,
                    PROVIDER           VARCHAR2(255),
                    PROVIDER_NAME      VARCHAR2(255),
                    MODEL              VARCHAR2(255),
                    PROMPT_TOKENS      NUMBER        DEFAULT 0,
                    COMPLETION_TOKENS  NUMBER        DEFAULT 0,
                    TOTAL_TOKENS       NUMBER        DEFAULT 0,
                    QUESTION_PREVIEW   VARCHAR2(512) DEFAULT '',
                    ANSWER_PREVIEW     CLOB,
                    SUCCESS            NUMBER(1)     DEFAULT 1,
                    ERROR_MSG          CLOB,
                    TOOL_CALLS         CLOB,
                    EXECUTION_LOG      CLOB,
                    CREATED_AT         VARCHAR2(255),
                    CONSTRAINT PK_AI_USAGE_LOGS PRIMARY KEY (ID)
                )
            """
            conn.execute(text(create_sql))
            conn.commit()
            print("  ✅ 表创建成功")
            
            # 创建索引
            indexes = [
                "CREATE INDEX IDX_AI_USAGE_LOGS_SESSION ON AI_USAGE_LOGS (SESSION_ID)",
                "CREATE INDEX IDX_AI_USAGE_LOGS_CONFIG ON AI_USAGE_LOGS (CONFIG_ID)",
                "CREATE INDEX IDX_AI_USAGE_LOGS_PROVIDER ON AI_USAGE_LOGS (PROVIDER)",
                "CREATE INDEX IDX_AI_USAGE_LOGS_CREATED ON AI_USAGE_LOGS (CREATED_AT)",
            ]
            for idx_sql in indexes:
                try:
                    conn.execute(text(idx_sql))
                    conn.commit()
                except Exception as e:
                    print(f"  ⚠️ 索引创建跳过: {e}")
            
            # 创建序列
            try:
                conn.execute(text("""
                    CREATE SEQUENCE SEQ_AI_USAGE_LOGS 
                    START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE
                """))
                conn.commit()
                print("  ✅ 序列创建成功")
            except Exception as e:
                print(f"  ⚠️ 序列创建跳过: {e}")
            
            # 创建触发器
            trigger_sql = """
                CREATE OR REPLACE TRIGGER TRG_AI_USAGE_LOGS_ID
                BEFORE INSERT ON AI_USAGE_LOGS
                FOR EACH ROW
                BEGIN
                    IF :NEW.ID IS NULL THEN
                        SELECT SEQ_AI_USAGE_LOGS.NEXTVAL INTO :NEW.ID FROM DUAL;
                    END IF;
                END;
            """
            try:
                conn.execute(text(trigger_sql))
                conn.commit()
                print("  ✅ 触发器创建成功")
            except Exception as e:
                print(f"  ⚠️ 触发器创建跳过: {e}")
        else:
            print("\n📋 表已存在，检查并添加新字段...")
            
            # 检查现有字段
            result = conn.execute(text("""
                SELECT COLUMN_NAME FROM USER_TAB_COLUMNS 
                WHERE TABLE_NAME = 'AI_USAGE_LOGS'
            """))
            existing_cols = [row[0].upper() for row in result.fetchall()]
            print(f"  现有字段: {existing_cols}")
            
            # 需要添加的新字段
            new_columns = [
                ("PROVIDER_NAME", "NVARCHAR2(255)"),
                ("ANSWER_PREVIEW", "CLOB"),
                ("TOOL_CALLS", "CLOB"),
                ("EXECUTION_LOG", "CLOB"),
            ]
            
            for col_name, col_type in new_columns:
                if col_name in existing_cols:
                    print(f"  ✅ 字段 {col_name} 已存在")
                    continue
                
                alter_sql = f"ALTER TABLE AI_USAGE_LOGS ADD {col_name} {col_type}"
                print(f"  ➕ 添加字段: {col_name} ({col_type})")
                try:
                    conn.execute(text(alter_sql))
                    conn.commit()
                    print(f"     ✅ 成功")
                except Exception as e:
                    print(f"     ❌ 失败: {e}")
        
        # 验证
        print("\n🔍 验证表结构...")
        result = conn.execute(text("""
            SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH 
            FROM USER_TAB_COLUMNS 
            WHERE TABLE_NAME = 'AI_USAGE_LOGS'
            ORDER BY COLUMN_ID
        """))
        print("\n最终字段列表:")
        for row in result.fetchall():
            print(f"  - {row[0]:20s} {row[1]:10s} {row[2]}")
    
    print("\n" + "=" * 60)
    print("迁移完成！")
    print("=" * 60)

if __name__ == "__main__":
    create_or_migrate_ai_usage_logs()
