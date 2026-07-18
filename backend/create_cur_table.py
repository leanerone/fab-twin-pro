import sys
sys.path.insert(0, ".")

from database import engine
from sqlalchemy import text

print("Creating DT_EVENT_RAW_CUR table...")

sql = """
CREATE TABLE DT_EVENT_RAW_CUR (
    tool_id VARCHAR2(255) PRIMARY KEY,
    raw_id VARCHAR2(255),
    source_system VARCHAR2(255) NOT NULL,
    source_message_id VARCHAR2(255) NOT NULL,
    received_ts_utc VARCHAR2(255),
    event_ts_utc VARCHAR2(255),
    payload_json CLOB,
    parse_status VARCHAR2(255) DEFAULT 'NEW',
    error_message VARCHAR2(255)
)
"""

try:
    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()
    print("DT_EVENT_RAW_CUR table created successfully!")
except Exception as e:
    print(f"Error: {e}")
    # 表可能已存在，忽略
    if "name is already used" in str(e):
        print("Table already exists, skipping.")
    else:
        raise
