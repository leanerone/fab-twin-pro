#!/usr/bin/env python3
"""
完整诊断脚本：检查 AI_USAGE_LOGS 表及相关对象的状态
请运行后将完整输出发给我做判断
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import engine
from sqlalchemy import text

def diagnose():
    print("=" * 80)
    print("AI_USAGE_LOGS 完整诊断报告")
    print("=" * 80)
    print(f"工作目录: {os.getcwd()}")
    print()

    with engine.connect() as conn:
        # 1. 当前数据库用户
        print("【1】当前数据库用户")
        result = conn.execute(text("SELECT USER FROM DUAL"))
        db_user = result.fetchone()[0]
        print(f"  当前用户: {db_user}")
        print()

        # 2. 当前用户下所有表
        print("【2】当前用户下所有表（USER_TABLES）")
        result = conn.execute(text("SELECT TABLE_NAME FROM USER_TABLES ORDER BY TABLE_NAME"))
        tables = [row[0] for row in result.fetchall()]
        print(f"  共 {len(tables)} 个表:")
        for t in tables:
            marker = " <-- AI相关" if "AI" in t.upper() else ""
            print(f"    - {t}{marker}")
        print()

        # 3. 检查 AI_USAGE_LOGS 表（各种方式）
        print("【3】AI_USAGE_LOGS 表存在性检查")
        checks = [
            ("USER_TABLES", "SELECT COUNT(*) FROM USER_TABLES WHERE TABLE_NAME = 'AI_USAGE_LOGS'"),
            ("ALL_TABLES (当前用户)", "SELECT COUNT(*) FROM ALL_TABLES WHERE OWNER = USER AND TABLE_NAME = 'AI_USAGE_LOGS'"),
            ("ALL_TABLES (全库)", "SELECT OWNER, TABLE_NAME FROM ALL_TABLES WHERE TABLE_NAME = 'AI_USAGE_LOGS'"),
            ("TAB (用户视图)", "SELECT COUNT(*) FROM TAB WHERE TNAME = 'AI_USAGE_LOGS'"),
        ]
        for name, sql in checks:
            try:
                result = conn.execute(text(sql))
                rows = result.fetchall()
                if len(rows) == 1 and len(rows[0]) == 1:
                    print(f"  {name}: {'存在' if rows[0][0] > 0 else '不存在'} ({rows[0][0]})")
                else:
                    print(f"  {name}: {rows}")
            except Exception as e:
                print(f"  {name}: 查询失败 - {e}")
        print()

        # 4. 如果表存在，检查表结构
        print("【4】AI_USAGE_LOGS 表结构（如果存在）")
        try:
            result = conn.execute(text("""
                SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, NULLABLE, DATA_DEFAULT
                FROM USER_TAB_COLUMNS
                WHERE TABLE_NAME = 'AI_USAGE_LOGS'
                ORDER BY COLUMN_ID
            """))
            cols = result.fetchall()
            if cols:
                print(f"  共 {len(cols)} 个字段:")
                for col in cols:
                    print(f"    - {col[0]:20s} {col[1]:12s} 长度={col[2]:6s} 可空={col[3]}")
            else:
                print("  表不存在或无字段")
        except Exception as e:
            print(f"  查询失败: {e}")
        print()

        # 5. 检查表中数据量
        print("【5】AI_USAGE_LOGS 数据量")
        try:
            result = conn.execute(text("SELECT COUNT(*) FROM AI_USAGE_LOGS"))
            count = result.fetchone()[0]
            print(f"  总记录数: {count}")

            if count > 0:
                result = conn.execute(text("""
                    SELECT ID, SESSION_ID, PROVIDER, MODEL, SUCCESS, CREATED_AT
                    FROM AI_USAGE_LOGS
                    ORDER BY CREATED_AT DESC
                    FETCH FIRST 5 ROWS ONLY
                """))
                print("  最近5条记录:")
                for row in result.fetchall():
                    print(f"    ID={row[0]}, Provider={row[2]}, Model={row[3]}, Success={row[4]}, Time={row[5]}")
        except Exception as e:
            print(f"  查询失败: {e}")
        print()

        # 6. 检查序列
        print("【6】序列检查")
        try:
            result = conn.execute(text("""
                SELECT SEQUENCE_NAME FROM USER_SEQUENCES
                WHERE SEQUENCE_NAME LIKE '%AI_USAGE%'
            """))
            seqs = result.fetchall()
            if seqs:
                for s in seqs:
                    print(f"  - {s[0]}")
            else:
                print("  无相关序列")
        except Exception as e:
            print(f"  查询失败: {e}")
        print()

        # 7. 检查触发器
        print("【7】触发器检查")
        try:
            result = conn.execute(text("""
                SELECT TRIGGER_NAME, TABLE_NAME, STATUS
                FROM USER_TRIGGERS
                WHERE TABLE_NAME = 'AI_USAGE_LOGS'
            """))
            trgs = result.fetchall()
            if trgs:
                for t in trgs:
                    print(f"  - {t[0]} (表={t[1]}, 状态={t[2]})")
            else:
                print("  无相关触发器")
        except Exception as e:
            print(f"  查询失败: {e}")
        print()

        # 8. 检查索引
        print("【8】索引检查")
        try:
            result = conn.execute(text("""
                SELECT INDEX_NAME, COLUMN_NAME
                FROM USER_IND_COLUMNS
                WHERE TABLE_NAME = 'AI_USAGE_LOGS'
                ORDER BY INDEX_NAME, COLUMN_POSITION
            """))
            idxs = result.fetchall()
            if idxs:
                for i in idxs:
                    print(f"  - {i[0]} ({i[1]})")
            else:
                print("  无相关索引")
        except Exception as e:
            print(f"  查询失败: {e}")
        print()

    # 9. 检查 models.py 中的 AIUsageLog 定义
    print("【9】models.py 中 AIUsageLog 模型定义")
    try:
        from models import AIUsageLog
        from sqlalchemy.inspection import inspect
        mapper = inspect(AIUsageLog)
        print(f"  表名: {mapper.tables[0].name}")
        print(f"  字段数: {len(mapper.columns)}")
        for col in mapper.columns:
            print(f"    - {col.name}: {col.type}")
    except Exception as e:
        print(f"  检查失败: {e}")
    print()

    # 10. 测试插入
    print("【10】测试插入数据")
    try:
        from models import AIUsageLog
        from database import SessionLocal
        from datetime import datetime
        import json

        db = SessionLocal()
        test_log = AIUsageLog(
            session_id='DIAGNOSE_TEST',
            provider='test',
            provider_name='诊断测试',
            model='test',
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            question_preview='诊断测试问题',
            answer_preview='诊断测试回答',
            success=True,
            tool_calls=json.dumps([{"tool": "test", "status": "ok"}]),
            execution_log=json.dumps([{"step": "test"}]),
            created_at=datetime.now().isoformat(),
        )
        db.add(test_log)
        db.commit()
        print(f"  ✅ 插入成功，ID={test_log.id}")

        # 回滚删除
        db.delete(test_log)
        db.commit()
        print("  ✅ 测试数据已清理")
        db.close()
    except Exception as e:
        print(f"  ❌ 插入失败: {e}")
        import traceback
        traceback.print_exc()
    print()

    # 11. 检查 ai_middleware.py 中的 _log_usage
    print("【11】ai_middleware.py 日志记录方法检查")
    try:
        with open('services/ai_middleware.py', 'r', encoding='utf-8') as f:
            content = f.read()

        has_log_usage = '_log_usage' in content
        has_tool_calls_param = 'tool_calls=' in content
        has_execution_log_param = 'execution_log=' in content
        has_provider_name_param = 'provider_name=' in content

        print(f"  _log_usage 方法存在: {has_log_usage}")
        print(f"  tool_calls 参数: {has_tool_calls_param}")
        print(f"  execution_log 参数: {has_execution_log_param}")
        print(f"  provider_name 参数: {has_provider_name_param}")
    except Exception as e:
        print(f"  检查失败: {e}")
    print()

    print("=" * 80)
    print("诊断完成，请将以上完整输出复制发给我")
    print("=" * 80)

if __name__ == "__main__":
    diagnose()
