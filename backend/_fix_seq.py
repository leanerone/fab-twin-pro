"""修复machine_events表的ID序列"""
from database import engine
from sqlalchemy import text

with engine.connect() as conn:
    # 获取当前最大ID
    r = conn.execute(text("SELECT MAX(ID) FROM MACHINE_EVENTS"))
    max_id = r.scalar() or 0
    print(f"当前最大ID: {max_id}")

    # 获取序列名
    r2 = conn.execute(text("""
        SELECT SEQUENCE_NAME FROM USER_SEQUENCES 
        WHERE SEQUENCE_NAME LIKE '%MACHINE_EVENT%' OR SEQUENCE_NAME LIKE '%ID%SEQ%'
    """))
    seqs = [row[0] for row in r2]
    print(f"相关序列: {seqs}")

    # 查找machine_events表的相关序列
    r3 = conn.execute(text("""
        SELECT S.SEQUENCE_NAME, S.LAST_NUMBER 
        FROM USER_SEQUENCES S
        WHERE S.SEQUENCE_NAME IN (
            SELECT CC.SEQUENCE_NAME 
            FROM USER_TAB_IDENTITY_COLS CC 
            WHERE CC.TABLE_NAME = 'MACHINE_EVENTS'
        )
    """))
    identity_seqs = [(row[0], row[1]) for row in r3]
    print(f"identity序列: {identity_seqs}")

    # 重置序列
    for seq_name, _ in identity_seqs:
        if max_id > 0:
            try:
                conn.execute(text(f"ALTER SEQUENCE {seq_name} RESTART START WITH {max_id + 1}"))
                conn.commit()
                print(f"已重置序列 {seq_name} -> {max_id + 1}")
            except Exception as e:
                # 尝试增量方式
                try:
                    r4 = conn.execute(text(f"SELECT {seq_name}.NEXTVAL FROM DUAL"))
                    curr_val = r4.scalar()
                    diff = max_id - curr_val
                    if diff > 0:
                        conn.execute(text(f"ALTER SEQUENCE {seq_name} INCREMENT BY {diff}"))
                        conn.execute(text(f"SELECT {seq_name}.NEXTVAL FROM DUAL"))
                        conn.execute(text(f"ALTER SEQUENCE {seq_name} INCREMENT BY 1"))
                        conn.commit()
                        print(f"已增量重置序列 {seq_name}: {curr_val} -> {max_id + 1}")
                except Exception as e2:
                    print(f"重置序列 {seq_name} 失败: {e2}")

print("完成!")
