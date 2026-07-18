from database import engine
from sqlalchemy import text

with engine.connect() as conn:
    r = conn.execute(text("""
        SELECT RAW_ID, SOURCE_SYSTEM, SOURCE_MESSAGE_ID, RECEIVED_TS_UTC, EVENT_TS_UTC, PAYLOAD_JSON
        FROM DT_EVENT_RAW
        WHERE TOOL_ID = 'PODOPENER-1'
        ORDER BY RECEIVED_TS_UTC DESC
    """)).first()

    if r:
        conn.execute(text("DELETE FROM DT_EVENT_RAW_CUR WHERE TOOL_ID = 'PODOPENER-1'"))
        conn.execute(text("""
            INSERT INTO DT_EVENT_RAW_CUR (TOOL_ID, RAW_ID, SOURCE_SYSTEM, SOURCE_MESSAGE_ID,
                RECEIVED_TS_UTC, EVENT_TS_UTC, PAYLOAD_JSON, PARSE_STATUS, ERROR_MESSAGE)
            VALUES ('PODOPENER-1', :raw_id, :src_sys, :src_msg_id, :recv_ts, :evt_ts, :payload, 'PARSED', NULL)
        """), {
            "raw_id": r[0],
            "src_sys": r[1],
            "src_msg_id": r[2],
            "recv_ts": r[3],
            "evt_ts": r[4],
            "payload": r[5],
        })
        conn.commit()
        print("CUR表更新完成！最新事件:", r[0])
    else:
        print("没有找到数据")
