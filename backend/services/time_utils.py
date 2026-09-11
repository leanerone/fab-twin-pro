"""时间戳解析工具（兼容多种字符串格式 + DATE/TIMESTAMP 对象）

时间列有两种形态，随部署环境而异（判定见 routers/history.py 的 _ts_columns_are_temporal）：
- 量产 Oracle: DT_EVENT_RAW.RECEIVED_TS_UTC / EVENT_TS_UTC 是 TIMESTAMP(6)
- 本地建表  : 是 VARCHAR2(255)，存字符串，格式可能是：
    1. "2026-07-23 08:00:00"    空格分隔、补零
    2. "2026-07-23T08:00:00"    ISO T 分隔
    3. "2026-7-23 下午12:01:14" NLS 中文渲染（月日不补零 + 12 小时制）

注意：第 3 种容易被误认为「列里存的中文时间串」，其实那是 TIMESTAMP 列的
客户端 NLS 渲染结果，并非存储内容 —— 字符串形态只在 VARCHAR2 部署下出现。

字符串格式不统一，因此 Python 层的过滤/排序必须走 parse_ts，
不要直接按字符串比较或排序。
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


def build_date_like_patterns(date_str: str) -> list:
    """为日期生成匹配多种字符串时间格式的LIKE模式

    ⚠️ 仅适用于 VARCHAR2 形态的时间列。若列是 DATE/TIMESTAMP（量产形态），
    用这些模式做 LIKE 会恒不匹配且不抛错，必须改用半开区间比较
    （见 routers/history.py 的 _date_scope_clause）。

    字符串形态下格式可能为：
    1. "2026-07-23T08:00:00" (ISO T分隔，补零)
    2. "2026-07-23 08:00:00" (空格分隔，补零)
    3. "2026-7-23 下午12:01:14" (NLS中文，月日不补零)

    本函数生成LIKE模式列表，用于在SQL层缩小查询范围，
    避免全表扫描后在Python层逐条解析过滤。

    Returns:
        LIKE模式列表，如 ['2026-07-23%', '2026-7-23%']
        输入无效时返回空列表
    """
    if not date_str:
        return []
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return []

    patterns = []
    # 标准补零格式: 2026-07-23 (匹配 ISO T分隔 和 空格分隔)
    iso_date = dt.strftime("%Y-%m-%d")
    patterns.append(f'{iso_date}%')
    # NLS不补零格式: 2026-7-23 (月或日为单位数时与ISO格式不同)
    nls_date = f"{dt.year}-{dt.month}-{dt.day}"
    if nls_date != iso_date:
        patterns.append(f'{nls_date}%')
    return patterns
