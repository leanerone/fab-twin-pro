"""时间戳解析工具（Oracle NLS 中文时间格式支持）

量产环境 Oracle DB 中 received_ts_utc 是 VARCHAR2 列，存储格式可能为：
1. ISO T 分隔: "2026-07-23T08:00:00" (Python isoformat 写入)
2. 空格分隔:   "2026-07-23 08:00:00" (标准24小时制)
3. NLS 中文:   "2026-7-23 下午12:01:14" (Oracle NLS 默认，月日不补零+12小时制)

由于格式不统一，所有时间过滤/排序必须在 Python 层用 _parse_ts 解析，
绝不能在 SQL 层用 LIKE 前缀或 ORDER BY VARCHAR2 列（结果错乱）。
"""
import re
from datetime import datetime
from typing import Optional


def parse_ts(ts) -> Optional[datetime]:
    """将各种格式的时间戳转换为 datetime 对象

    支持格式（按优先级）：
    1. datetime 对象（直接返回）
    2. Oracle NLS 中文: "2026-7-23 下午12:01:14" / "2026-07-23 上午08:30:00"
    3. "2026-07-21 00:00:00" (标准24小时制空格分隔)
    4. "2026-07-21T00:00:00" (ISO T分隔)
    5. "2026-07-21T00:00:00.000Z" (带Z后缀)
    6. "2026-07-21" (仅日期)
    7. 月日不补零的24小时制: "2026-7-23 8:00:00"

    Returns:
        datetime 对象，解析失败返回 None
    """
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts
    ts = str(ts).strip()
    if not ts:
        return None

    # 先去掉 Z 和时区后缀
    ts_clean = re.sub(r'(Z|[+-]\d{2}:\d{2})$', '', ts)

    # 格式1: Oracle NLS 中文 "2026-7-23 下午12:01:14"
    nls_match = re.match(
        r'^(\d{4})-(\d{1,2})-(\d{1,2})\s+(上午|下午)\s*(\d{1,2}):(\d{2}):(\d{2})$',
        ts_clean
    )
    if nls_match:
        year = int(nls_match.group(1))
        month = int(nls_match.group(2))
        day = int(nls_match.group(3))
        ampm = nls_match.group(4)
        hour = int(nls_match.group(5))
        minute = int(nls_match.group(6))
        second = int(nls_match.group(7))
        if ampm == '下午' and hour != 12:
            hour += 12
        elif ampm == '上午' and hour == 12:
            hour = 0
        try:
            return datetime(year, month, day, hour, minute, second)
        except ValueError:
            pass

    # 格式2-5: 标准格式
    formats = [
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(ts_clean, fmt)
        except ValueError:
            continue

    # 格式7: 不补零的日期+时间（月日不补零，24小时制）
    loose_match = re.match(
        r'^(\d{4})-(\d{1,2})-(\d{1,2})[T ](\d{1,2}):(\d{2}):(\d{2})$',
        ts_clean
    )
    if loose_match:
        try:
            return datetime(
                int(loose_match.group(1)),
                int(loose_match.group(2)),
                int(loose_match.group(3)),
                int(loose_match.group(4)),
                int(loose_match.group(5)),
                int(loose_match.group(6)),
            )
        except ValueError:
            pass

    return None


def normalize_ts(ts) -> str:
    """标准化时间戳为 'YYYY-MM-DD HH:MM:SS' 格式（用于API输出）"""
    dt = parse_ts(ts)
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def extract_date(ts_str: str) -> str:
    """从时间戳字符串中提取日期部分（YYYY-MM-DD）

    支持多种格式：
    - 2026-07-22 15:00:48
    - 2026-7-22 下午3:00:48
    - 2026-07-22T15:00:48
    """
    if not ts_str:
        return ""
    try:
        # 取第一个空格或T之前的部分作为日期
        date_part = str(ts_str).split()[0].split('T')[0]
        parts = date_part.split('-')
        if len(parts) == 3:
            return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
    except Exception:
        pass
    return ""
