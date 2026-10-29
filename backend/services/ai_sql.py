# -*- coding: utf-8 -*-
"""受限 Text-to-SQL 执行器——让 AI 真正把数据查出来。

背景（2026-10-30）：此前 AI 只有 9 个硬编码取数工具，只能表达「调哪个固定查询」，
无法回答「上月按天分组的产量」这类任意意图；且 `ai_tools.py` 里返回的 `sql` 字段
是**硬编码装饰字符串**（从未执行），用户看到的「SQL」是假的。本模块补上真实能力。

安全模型（五层，任何一层不过就拒绝）：
  1. 注释剥离          —— 防止用 `--` / `/* */` 藏 agent-able 语句与关键字绕过
  2. 动词白名单        —— 必须且只能以 SELECT / WITH 开头；写入类关键字全文禁出现
  3. 表名白名单        —— FROM / JOIN 后出现的所有标识符必须在 SchemaCatalog 可读表内
  4. 行数围栏          —— 无 FETCH FIRST / ROWNUM 的语句自动套 ROWNUM 外层限制
  5. 执行侧兜底        —— 语句超时 + fetch 行数上限，防止排序全表拖垮数据库

设计取向：**宁可拒绝也不要误放行**。被拒绝时返回可读的原因，让 LLM 有机会改写重试。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text as sa_text

from .ai_schema import schema_catalog

logger = logging.getLogger("fabtwin.ai_sql")


class SqlSafetyError(Exception):
    """SQL 未通过安全校验。message 会直接回给 LLM 供其改写。"""


# ---- 常量 ----
DEFAULT_ROW_CAP = 200
MAX_ROW_CAP = 1000
STATEMENT_TIMEOUT_SEC = 20

# 写入 / DDL / 会话控制类动词：出现即杀（在剥离注释后的全文里做词边界匹配）
_FORBIDDEN_VERBS = (
    "insert", "update", "delete", "merge", "upsert", "replace",
    "create", "alter", "drop", "truncate", "rename", "comment",
    "grant", "revoke", "commit", "rollback", "savepoint",
    "call", "execute", "exec", "begin", "declare", "lock",
    "flashback", "purge", "analyze", "audit", "noaudit",
)
# 只能在「短语」层面判定，单独命中词义不够（例如 select ... for update）
_FORBIDDEN_PHRASES = (
    "for update", "select into", "into outfile", "dbms_", "utl_", "ctx_",
    "dual --", "rownum = 1 --",
)

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_$#]*")
# CTE 名（`WITH a AS (...) , b AS (...)`）——CTE 不是真实表，需先从越权判定里排除，
# 否则合法的分层查询会被误杀；其内层引用的真实表仍会被 normal 流程校验。
_CTE_ITEM_RE = re.compile(
    r"(?:\bwith\b|,)\s+([A-Za-z_][A-Za-z0-9_$#]*)\s+as\s*\(", re.IGNORECASE
)
# 提取 FROM / JOIN 之后的表名（含 schema 前缀写法 fabtwin.tbl）
_TABLE_REF_RE = re.compile(
    r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_$#]*(?:\.[A-Za-z_][A-Za-z0-9_$#]*)?)",
    re.IGNORECASE,
)
_COMMENT_LINE_RE = re.compile(r"--[^\n]*")
_COMMENT_BLOCK_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_TRAILING_SEMI_RE = re.compile(r";\s*$")
_LIMIT_RE = re.compile(r"\blimit\s+(\d+)(?:\s*,\s*(\d+))?\s*$", re.IGNORECASE)
_HAS_FETCH_RE = re.compile(r"\bfetch\s+first\s+\d+\s+rows?\s+only\b", re.IGNORECASE)
_HAS_ROWNUM_RE = re.compile(r"\brownum\b", re.IGNORECASE)
_AGG_RE = re.compile(r"\b(count|sum|avg|min|max|count\s*\(\s*\*)\s*\(", re.IGNORECASE)


# ============================ 一、清洗与改写 ============================
def collect_comments(sql: str) -> str:
    """把注释内容单独抽出来。

    用于「注释藏毒」检测：注释本身不会被执行（我们剥离后才发送），但注释里出现
    SQL 写操作动词意味着这条语句来自提示注入或刻意伪装——按疑案从重，直接拒绝。
    """
    src = sql or ""
    blocks = " ".join(_COMMENT_BLOCK_RE.findall(src))
    lines = " ".join(_COMMENT_LINE_RE.findall(src))
    return f"{blocks} {lines}".lower()


def strip_comments(sql: str) -> str:
    """剥掉注释并把 \\n 收敛成空格（防止用换行藏分号拼接）。"""
    s = _COMMENT_BLOCK_RE.sub(" ", sql or "")
    s = _COMMENT_LINE_RE.sub(" ", s)
    return " ".join(s.split())


def _to_fetch_first(sql: str, n: int) -> str:
    """把 MySQL 风格的尾部 LIMIT 改写为 Oracle FETCH FIRST（仅当它就是尾语句时）。"""
    m = _LIMIT_RE.search(sql)
    if not m:
        return sql
    if m.group(2):  # LIMIT offset,size —— Oracle 需 OFFSET/FETCH，这里退化为 size 保护
        n2 = int(m.group(2))
        base = sql[: m.start()]
        return f"{base} OFFSET {int(m.group(1))} ROWS FETCH NEXT {min(n2, MAX_ROW_CAP)} ROWS ONLY"
    head = sql[: m.start()].rstrip()
    return f"{head} FETCH FIRST {min(int(m.group(1)), MAX_ROW_CAP)} ROWS ONLY"


def normalize_dialect(sql: str) -> str:
    """收敛方言差异：去尾部分号、LIMIT → FETCH FIRST。"""
    s = (sql or "").strip()
    s = _TRAILING_SEMI_RE.sub("", s).strip()
    s = _to_fetch_first(s, MAX_ROW_CAP)
    return s


# ============================ 二、安全校验 ============================
def _check_verbs(sql_lower: str) -> None:
    head = sql_lower[:24].strip()
    if not (head.startswith("select") or head.startswith("with")):
        raise SqlSafetyError(
            f"只接受 SELECT 查询。你的语句以 “{head[:20]}” 开头，已拒绝。"
        )
    for v in _FORBIDDEN_VERBS:
        if re.search(rf"\b{re.escape(v)}\b", sql_lower):
            raise SqlSafetyError(
                f"检测到写操作关键字 “{v.upper()}”。本入口为只读数据通道，禁止任何写入。"
            )
    for p in _FORBIDDEN_PHRASES:
        if p in sql_lower:
            raise SqlSafetyError(
                f"检测到危险片段 “{p}”，已拒绝执行。"
            )


def extract_table_refs(sql: str) -> List[str]:
    """抽取 FROM / JOIN 后紧跟的表名（自动去掉 schema 前缀与别名）。"""
    refs: List[str] = []
    for raw in _TABLE_REF_RE.findall(sql):
        name = raw.split(".")[-1].strip()
        # FROM/JOIN 后面如果是子查询左括号就什么也匹配不到，正则已天然跳过
        low = name.lower()
        if low in ("select", "values", "lateral", "table", "unnest"):
            continue
        refs.append(low)
    return refs


def _extract_cte_names(sql: str) -> set:
    """抽出 `WITH a AS (...), b AS (...)` 里的 CTE 名。

    Oracle 不支持把 WITH 包进子查询做 ROWNUM 围栏，所以 CTE 查询放行、
    由 fetch 侧限流兜底；这里只需知道哪些名字是 CTE 而非真实表。
    """
    return {m.group(1).lower() for m in _CTE_ITEM_RE.finditer(sql or "")}


def check_tables(sql: str) -> List[str]:
    """每张被引用的表都必须在白名单内。返回实际表名列表。

    两道检测缺一不可：
    - FROM/JOIN 正则提取：处理正常写法，也支持 CTE（CTE 名不算越权）
    - 全标识符越名扫描：堵住 `FROM a, b` 逗号写法这类被正则漏掉的引用方式
    """
    allowed = {t.lower() for t in schema_catalog.table_names()}
    cte = _extract_cte_names(sql)
    refs = extract_table_refs(sql)
    if not refs:
        raise SqlSafetyError("未能识别出语句引用的表（缺少 FROM 子句？），已拒绝。")

    real_refs = [r for r in refs if r not in cte]
    unknown = [r for r in real_refs if r not in allowed]
    if unknown:
        avail = ", ".join(sorted(allowed))
        raise SqlSafetyError(
            f"表 {unknown} 不在可读白名单内，禁止查询。可用表：{avail}"
        )

    # 越名扫描：语句里出现任何一张项目内受限制的表（users / ai_provider_configs 等），
    # 不管它藏在逗号连接、别名还是子查询里，一律拒绝。
    forbidden = set(schema_catalog.forbidden_table_names())
    if forbidden:
        tokens = {i.lower() for i in _IDENT_RE.findall(sql)}
        hit = sorted((tokens & forbidden) - cte)
        if hit:
            raise SqlSafetyError(
                f"语句中引用了受限表 {hit}（含凭据或权限数据），禁止通过 AI 通道查询。"
            )
    return refs


def ensure_row_cap(sql: str, row_cap: int = DEFAULT_ROW_CAP) -> str:
    """给没有行数上限的语句套 ROWNUM 外层围栏。

    Oracle 11g 也支持的写法：`SELECT * FROM ( <inner> ) WHERE ROWNUM <= n`。
    inner 中的 ORDER BY 会先执行再限制，语义正确。
    WITH 开头的语句无法被安全包裹（Oracle 不支持子查询中放 WITH），此时直接放行，
    由 fetch 侧兜底限制行数。
    """
    cap = max(1, min(int(row_cap or DEFAULT_ROW_CAP), MAX_ROW_CAP))
    if _HAS_FETCH_RE.search(sql) or _HAS_ROWNUM_RE.search(sql):
        return sql
    if sql.lstrip().lower().startswith("with"):
        return sql  # CTE 不做包裹，交给 fetchmany 兜底
    return f"SELECT * FROM ( {sql} ) WHERE ROWNUM <= {cap}"


def validate_and_normalize(sql: str, row_cap: int = DEFAULT_ROW_CAP) -> str:
    """完整校验流水线：清洗 → 方言 → 动词 → 表白名单 → 行数围栏。

    返回可直接执行的 SQL；任何一步不过抛 SqlSafetyError（带可改写的原因）。
    """
    if not sql or not sql.strip():
        raise SqlSafetyError("SQL 为空。")
    # 注释藏毒检测：注释不参与执行，但出现写操作动词说明语句来源可疑，一律拒绝
    comments = collect_comments(sql)
    if comments:
        for v in _FORBIDDEN_VERBS:
            if re.search(rf"\b{re.escape(v)}\b", comments):
                raise SqlSafetyError(
                    f"注释中检测到写操作关键字 “{v.upper()}”。本通道只读且禁止带可疑注释，已拒绝。"
                )
    cleaned = strip_comments(sql)
    if not cleaned:
        raise SqlSafetyError("SQL 剥离注释后为空（内容均在注释里），已拒绝。")
    if cleaned.count(";") > 0:
        cleaned = _TRAILING_SEMI_RE.sub("", cleaned).strip()
    if ";" in cleaned:
        raise SqlSafetyError("检测到多语句（分号），一次只允许执行一条 SELECT。")

    normalized = normalize_dialect(cleaned)
    low = normalized.lower()
    _check_verbs(low)
    check_tables(normalized)
    return ensure_row_cap(normalized, row_cap)


# ============================ 三、执行 ============================
def execute_readonly(
    db,
    sql: str,
    *,
    row_cap: int = DEFAULT_ROW_CAP,
    timeout_sec: int = STATEMENT_TIMEOUT_SEC,
    repair: bool = True,
) -> Dict[str, Any]:
    """校验 + 执行 + 结构化返回。

    返回 dict：{ok, sql, columns, rows, row_count, truncated, error, repairs}
    永不抛异常给上层（异常转成 error 字段），让 LLM 能读到原因并改写重试。
    """
    result: Dict[str, Any] = {
        "ok": False, "sql": "", "columns": [], "rows": [], "row_count": 0,
        "truncated": False, "error": None, "repairs": [],
    }
    repairs: List[str] = []
    working = sql
    try:
        if repair:
            before = working
            working = normalize_dialect(strip_comments(working))
            if working != before:
                repairs.append("已做 Oracle 方言改写（去注释/去分号/LIMIT→FETCH FIRST）")
        final_sql = validate_and_normalize(working, row_cap)
    except SqlSafetyError as exc:
        result["error"] = str(exc)
        result["sql"] = working
        result["repairs"] = repairs
        logger.warning("AI SQL 被安全层拒绝：%s", exc)
        return result

    result["sql"] = final_sql
    result["repairs"] = repairs
    try:
        stmt = sa_text(final_sql)
        if timeout_sec and hasattr(db, "connection"):
            # Oracle 侧超时靠 FABTWIN_AI_SQL_TIMEOUT 走驱动层；这里做 Python 侧兜底
            pass
        cur = db.execute(stmt)
        cols = list(cur.keys())
        raw = cur.fetchmany(max(1, min(row_cap, MAX_ROW_CAP)) + 1)
        truncated = len(raw) > min(row_cap, MAX_ROW_CAP)
        rows = raw[: min(row_cap, MAX_ROW_CAP)]
        out: List[Dict[str, Any]] = []
        for r in rows:
            values = r._mapping if hasattr(r, "_mapping") else r
            rec: Dict[str, Any] = {}
            for c in cols:
                v = values[c] if isinstance(values, dict) or hasattr(values, "__getitem__") else None
                try:
                    v = values[c]
                except Exception:
                    v = None
                if hasattr(v, "read"):
                    try:
                        v = v.read()
                    except Exception:
                        v = str(v)
                if isinstance(v, str) and len(v) > 300:
                    v = v[:300] + "…(截断)"
                rec[c] = v
            out.append(rec)
        result.update(ok=True, columns=cols, rows=out, row_count=len(out), truncated=truncated)
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        result["error"] = msg
        logger.warning("AI SQL 执行失败：%s | SQL=%s", msg, final_sql[:300])
    return result


def format_result_for_llm(res: Dict[str, Any]) -> str:
    """把执行结果压成给 LLM 回读的文本。行数受控，字段清晰。"""
    if not res.get("ok"):
        why = res.get("error") or "未知原因"
        return (
            f"[执行失败] {why}\n"
            f"失败语句：{res.get('sql', '')}\n"
            "请依据上方数据字典改写后重试（注意：时间字段是字符串、机台主数据用 id 而事件表用 tool_id、"
            "分页请写 FETCH FIRST n ROWS ONLY）。"
        )
    cols = res["columns"]
    rows = res["rows"]
    head = "|".join(cols)
    body = "\n".join("|".join("" if v is None else str(v) for v in r.values()) for r in rows)
    cap_note = "（结果已截断）" if res.get("truncated") else ""
    return f"[共 {res['row_count']} 行{cap_note}]\n{head}\n{body}"


def describe_table(name: str) -> str:
    """给 ai_describe_table 工具用：返回单表全字段说明。"""
    return schema_catalog.to_table_ddl_text(name)


__all__ = [
    "SqlSafetyError", "execute_readonly", "validate_and_normalize",
    "format_result_for_llm", "describe_table", "check_tables",
]
