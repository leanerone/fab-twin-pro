# -*- coding: utf-8 -*-
"""AI 数据字典（Schema Catalog）——从 ORM 模型真实派生，供 LLM 生成 SQL 前注入。

设计要点（2026-10-30 AI 真相专项）：

1. **真实派生而非手写**：所有表名 / 字段名 / 类型 / 是否为主键 / 是否有索引，
   一律从 SQLAlchemy ORM 映射（`backend/models.py` 的 `Base`）实时反射得出。
   ORM 一旦加字段，这里的字典自动跟上，不会出现「字典与库不一致」的漂移。
2. **人工只写业务语义**：`TABLE_NOTES` 只补 ORM 表达不出来的东西——这张表是干
   什么的、字段的业务含义、与其它表怎么 JOIN、有什么坑。
3. **安全边界内建**：`READABLE_TABLES` 白名单决定 AI 能查哪些表；敏感表
   （users / roles / perm_data / 含 api_key 的配置表）根本不出现在字典里，
   AI 连表名都看不到，无从问起。
4. **方言陷阱显式告知**：本项目把时间戳存成 ISO 字符串（不是 DATE 类型），
   这是 LLM 生成 SQL 时最容易踩的坑，写进 `ORACLE_DIALECT_NOTES` 强制注入。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger("fabtwin.ai_schema")


# ============ 一、安全边界：AI 只读白名单 ============
# 只有列在这里的表会进入数据字典，也只有它们能被 ai_sql 执行器放行。
# 安全类配置表（含 api_key / password）永不进字典。
READABLE_TABLES = [
    "dt_event_raw",            # 原始事件事实表（AI 取数的主战场）
    "dt_event_raw_cur",        # 每台机台最新一条 RV 消息
    "dt_event_std",            # 标准化事件
    "dt_state_snapshot",       # 状态快照
    "dt_alarm_event",          # 告警事件流
    "machines",                # 机台主数据
    "lots",                    # 批次主数据
    "recipes",                 # 工艺配方
    "chamber_snapshots",       # 腔体级快照
    "oht_positions",           # OHT 天车位置
    "machine_events",          # 机台事件（状态切换/传感器/晶圆转移）
    "alarms",                  # 告警记录
    "dashboard_kpi",           # 预计算 KPI
    "floors",                  # 楼层
    "floor_areas",             # 楼层区域
    "tracks",                  # 天车轨迹
    "vehicles",                # 天车/搬运车
    "machine_tool_mappings",   # 机台 ID ↔ Tool ID 映射
    "machine_model_configs",   # 机台型号配置
    "event_action_mappings",   # 事件 → 动作映射
    "ai_insights",             # AI 分析结果
    "ai_usage_logs",           # AI 调用审计（不含密钥）
]

# 即便在白名单表内，列名命中这些模式也一律从字典中剔除。
_COLUMN_DENY_PAT = re.compile(
    r"password|passwd|secret|token|api_key|apikey|credential|private_key",
    re.I,
)

# 详列字段的核心表（其余表只给表名 + 一句业务说明，控 token）
CORE_TABLES = {
    "dt_event_raw", "machines", "lots", "dt_alarm_event", "alarms",
    "dt_event_std", "chamber_snapshots", "recipes", "machine_events",
    "dashboard_kpi", "dt_state_snapshot",
}


# ============ 二、业务语义（人工维护，ORM 表达不出来的部分）============
TABLE_NOTES: Dict[str, Dict[str, str]] = {
    "dt_event_raw": {
        "desc": "原始事件事实表。所有机台上报的 RV 报文都进这里，是全站唯一可信的事件源头。"
                "查产量、查事件流水、查某段时间发生了什么，一律以本表为准。",
        "raw_id": "事件唯一流水号，主键。字典序可排序（形如 TID.Z{时间戳}{序号}），可用它做增量/分页起点",
        "tool_id": "机台 Tool ID（如 RTM01-OXE-01）。注意：它不等于 machines.id，需经 machine_tool_mappings 关联",
        "source_system": "来源系统标识，如 SIMULATOR / RVMES / ODS",
        "source_message_id": "源侧消息 ID",
        "received_ts_utc": "**字符串型 UTC 时间**，ISO 格式如 2026-10-29T12:34:56.789Z。必须按字符串比较，不能直接当日期做 DATE 运算",
        "event_ts_utc": "事件发生的 UTC 时间（字符串型），可能为空",
        "payload_json": "报文原文 JSON（CLOB）。物化列缺失时才需要解析它",
        "parse_status": "解析状态：NEW / OK / ERROR",
        "lot_id": "批次号（物化列，已从 payload 提取）",
        "event_name": "事件名（物化列），如 WAFERLOADED / PE / ALARM / POD_PLACED",
        "alarm_code": "告警码（物化列），无告警时为空",
        "_hint": "查某机台事件时建议先经 machine_tool_mappings 把 machine_id 翻译成 tool_id；"
                 "时间过滤用 received_ts_utc >= '2026-10-29T00:00:00' 这种字符串比较。",
    },
    "dt_event_raw_cur": {
        "desc": "每台机台最新一条 RV 消息（一个 tool_id 一行）。查「当前状态」用这张，比扫 dt_event_raw 快得多。",
        "tool_id": "机台 Tool ID（主键）",
        "_hint": "只看最新态用本表，不要对 dt_event_raw 做 ORDER BY + 取第一条，那是全表扫描。",
    },
    "dt_event_std": {
        "desc": "标准化事件表：原始报文解析后的结构化结果，带语义化的 machine_state / event_type。",
        "event_type": "事件类型（标准化后）",
        "machine_state": "机台状态，如 RUN / IDLE / DOWN / PM",
        "pod_position": "POD 所在位置（Load Port 序号）",
        "created_ts_utc": "入库 UTC 时间（字符串型）",
        "_hint": "查「机台状态分布 / 状态切换历史」用本表，比解析 payload_json 可靠。",
    },
    "dt_state_snapshot": {
        "desc": "状态快照表：按时间切片保存的机台完整状态。",
        "_hint": "适合做趋势类查询；一次性聚合优先用 dt_event_raw。",
    },
    "dt_alarm_event": {
        "desc": "告警事件流水表。查告警次数、告警类型分布、某机台近期告警，用这张。",
        "_hint": "统计告警 TOP N 用 GROUP BY 告警码列；注意与 alarms 表区分——本表是流水，alarms 是告警定义/记录。",
    },
    "alarms": {
        "desc": "告警记录表（告警实例台账）。",
        "_hint": "与 dt_alarm_event 可能同源不同粒，必要时两表都核对。",
    },
    "machines": {
        "desc": "机台主数据表。查有几个机台、按类型/区域分组、机台当前状态，用这张。",
        "id": "机台业务 ID（如 OXE-51），前端 URL 里传的就是它",
        "name": "机台显示名",
        "type": "机台类型（如 ETCH / LITHO / CMP）",
        "status": "当前状态：RUN / IDLE / DOWN / PM",
        "_hint": "**重要**：dt_event_raw 里的字段叫 tool_id 不叫 machine_id，两者需通过 machine_tool_mappings 关联。"
                 "务必先查该映射表拿到 tool_id，再去查事件表。",
    },
    "machine_tool_mappings": {
        "desc": "机台 ID（machine_id）↔ Tool ID（tool_id）映射表。**这是关联机台主数据与事件表的桥表**。",
        "machine_id": "对应 machines.id",
        "tool_id": "对应 dt_event_raw.tool_id",
        "_hint": "用户问「OXE-51 怎么样」时，标准动作是：先在本表查出 tool_id，再用它过滤 dt_event_raw。",
    },
    "lots": {
        "desc": "批次主数据表。查在制品、批次状态、某批次到哪一步，用这张。",
        "lot_id": "批次号",
        "status": "批次状态（如 RUNNING / WAIT / DONE / HOLD）",
        "_hint": "批次进度常需与 dt_event_raw.lot_id 联合看，event_name 表示流转步骤。",
    },
    "recipes": {
        "desc": "工艺配方表（Recipe 主数据）。",
        "_hint": "问「某机台用什么配方」时，先在本表取 recipe，再关联事件表里的 recipe 字段。",
    },
    "chamber_snapshots": {
        "desc": "腔体级状态快照（OXE 等 4 腔机台的每个腔独立参数）。查腔体温度/压力/是否加工中用这张。",
        "chamber": "腔体编号（如 PM1 / PM2 / PM3 / PM4）",
        "_hint": "这是少有的「有物理量」的表，问温度/压力类问题优先用。",
    },
    "machine_events": {
        "desc": "机台事件表：状态切换 / 传感器采样 / 告警 / 晶圆转移。语义比 dt_event_raw 更明确。",
        "_hint": "若 dt_event_raw 的 event_name 物化列为空（老数据），可以退到此表取事件语义。",
    },
    "dashboard_kpi": {
        "desc": "看板预计算 KPI 指标。指标类问题（OEE/稼动率/产量）若本表有对应指标，直接读它最快。",
        "_hint": "优先复用预计算结果，除非用户明确要看明细。",
    },
    "oht_positions": {"desc": "OHT 天车实时位置（Line 2 SMIF 系统）。查天车在哪、有没有堵料。"},
    "vehicles": {"desc": "天车/搬运车台账。"},
    "tracks": {"desc": "天车轨迹（2D 平面图绘制用）。"},
    "floors": {"desc": "楼层信息表。"},
    "floor_areas": {"desc": "楼层区域表（设备区/过道/电梯/逃生门等）。"},
    "machine_model_configs": {"desc": "机台型号配置：定义一种机型的 2D/3D 视图与部件。"},
    "event_action_mappings": {"desc": "事件 → 部件动作序列映射（驱动动画的配置表）。"},
    "ai_insights": {"desc": "AI 分析结果落库表。"},
    "ai_usage_logs": {
        "desc": "AI 调用审计日志：token 消耗、工具调用明细。查「AI 花了多少钱 / 调用了几次工具」用这张。",
        "_hint": "不含任何密钥字段，可安全查询。",
    },
}

ORACLE_DIALECT_NOTES = """【Oracle 方言与本项目约定 — 生成 SQL 前必读】
1. 时间字段是**字符串**不是 DATE：received_ts_utc / event_ts_utc / created_ts_utc 均为 ISO 字符串
   （例 '2026-10-29T12:34:56.789Z'）。**禁止**对其做 DATE 运算或 TO_DATE；请直接用字符串区间比较：
   received_ts_utc >= '2026-10-29T00:00:00' AND received_ts_utc < '2026-10-30T00:00:00'
2. 分页不要用 LIMIT。用 FETCH FIRST 20 ROWS ONLY（Oracle 12c+），或用 ORDER BY + ROWNUM 子查询。
3. 机台主数据的主键叫 id，事件表里叫 tool_id，两者**不同**；必须经 machine_tool_mappings
   （machine_id → tool_id）转换后再过滤事件表。这是最容易出错的地方。
4. 字符串比较区分大小写，不确定大小写时用 UPPER(col) = UPPER('值')。
5. 只写单条 SELECT，**禁止** INSERT/UPDATE/DELETE/MERGE/CREATE/DROP/ALTER/COMMIT/ROLLBACK/CALL/GRANT。
6. 禁止分号、禁止多语句、禁止注释符（-- 与 /* */）、禁止 UNION 到非白名单表。
7. 能聚合就在 SQL 里聚合（COUNT/SUM/MAX/MIN/AVG/GROUP BY），不要让数据库吐明细行。
8. 结果请自带 LIMIT 意识：默认 FETCH FIRST 200 ROWS ONLY，用户明确要全量时再放宽到 1000。"""


def _py_type_to_cn(col_type: Any) -> str:
    """把 SQLAlchemy 类型转成中文短名，让 LLM 一眼看懂能用什么运算。"""
    s = str(col_type).upper()
    if "DATETIME" in s or "TIMESTAMP" in s:
        return "日期时间"
    if "DATE" in s:
        return "日期"
    if "CLOB" in s or "TEXT" in s:
        return "长文本"
    if "NVARCHAR" in s or "VARCHAR" in s or "CHAR" in s:
        # 本项目把时间存成字符串，单独标注以免 LLM 误判
        return "字符串"
    if "INT" in s or "NUMERIC" in s or "DECIMAL" in s or "NUMBER" in s or "REAL" in s or "FLOAT" in s:
        return "数值"
    if "BOOLEAN" in s:
        return "布尔"
    if "JSON" in s:
        return "JSON"
    return "字符串"


class SchemaCatalog:
    """从 ORM 真实反射出的数据字典。单例使用（见文件底部 `schema_catalog`）。"""

    def __init__(self) -> None:
        self._tables: List[Dict[str, Any]] = []
        self._loaded = False
        self._load_error: Optional[str] = None
        self._all_orm_tables: List[str] = []

    # ---------- 反射 ----------
    def _reflect(self) -> None:
        """延迟反射 ORM：加字段自动跟上，反射失败也不会拖垮 AI 主链路。"""
        if self._loaded:
            return
        self._loaded = True
        try:
            from sqlalchemy import inspect as sa_inspect
            from models import Base  # type: ignore

            wanted = {t.lower(): t for t in READABLE_TABLES}
            for cls in Base.registry.mappers:
                model = cls.class_
                tname = getattr(model, "__tablename__", None)
                if tname:
                    # 全量表清单（含非白名单）：给 SQL 安全层做「越表名」扫描用
                    self._all_orm_tables.append(tname)
                if not tname or tname.lower() not in wanted:
                    continue
                mapper = sa_inspect(model)
                pk_cols = {c.name for c in mapper.primary_key}
                indexed = set()
                try:
                    for ix in getattr(model, "__table__").indexes:
                        indexed |= {c.name for c in ix.columns}
                except Exception:
                    pass

                notes = TABLE_NOTES.get(tname, {})
                columns: List[Dict[str, Any]] = []
                for c in mapper.columns:
                    cname = c.name
                    if _COLUMN_DENY_PAT.search(cname):
                        continue  # 安全：敏感列永不外泄给 LLM
                    note = notes.get(cname, "")
                    columns.append({
                        "name": cname,
                        "type": _py_type_to_cn(c.type),
                        "pk": cname in pk_cols,
                        "indexed": cname in indexed,
                        "nullable": bool(getattr(c, "nullable", True)),
                        "note": note,
                    })
                # 换成统一小写-used 的实际表名（保权威大小写）
                self._tables.append({
                    "name": wanted[tname.lower()],
                    "desc": notes.get("desc", (model.__doc__ or "").strip().split("\n")[0] or "业务表"),
                    "columns": columns,
                    "hint": notes.get("_hint", ""),
                    "core": tname.lower() in CORE_TABLES,
                })
            self._tables.sort(key=lambda t: (not t["core"], t["name"]))
            logger.info("AI schema 反射成功：%d 张可读表", len(self._tables))
        except Exception as exc:  # 反射失败不能让 AI 崩，退化为纯人工 note
            self._load_error = f"{type(exc).__name__}: {exc}"
            logger.warning("AI schema 反射失败，退化为业务说明模式：%s", exc)

    # ---------- 对外 API ----------
    @property
    def load_error(self) -> Optional[str]:
        self._reflect()
        return self._load_error

    def tables(self) -> List[Dict[str, Any]]:
        self._reflect()
        return self._tables

    def table_names(self) -> List[str]:
        self._reflect()
        return [t["name"] for t in self._tables]

    def describe(self, name: str) -> Optional[Dict[str, Any]]:
        self._reflect()
        target = (name or "").strip().lower()
        for t in self._tables:
            if t["name"].lower() == target:
                return t
        return None

    def forbidden_table_names(self) -> List[str]:
        """项目里存在、但**不在**可读白名单中的表名。

        SQL 安全层用它做越名扫描：`FROM a, b` 这种逗号写法容易被 FROM/JOIN 正则漏检，
        但只要语句里出现了任何一张受限表名，一律拒绝——堵住"漏检绕过"。
        """
        self._reflect()
        allowed = {t.lower() for t in self.table_names()}
        return sorted({t.lower() for t in self._all_orm_tables} - allowed)

    def column_names(self, name: str) -> List[str]:
        t = self.describe(name)
        return [c["name"] for c in (t["columns"] if t else [])]

    def has_column(self, table: str, column: str) -> bool:
        return column.strip().lower() in {c.lower() for c in self.column_names(table)}

    # ---------- 生成给 LLM 的文本 ----------
    def to_prompt_text(self, max_rows_per_table: int = 12) -> str:
        """生成注入 system prompt 的数据字典文本。

        分层策略：核心表详列字段（带业务注释），非核心表只给表名 + 一句说明。
        目标是让 LLM 看得懂又不会把上下文撑爆。
        """
        self._reflect()
        lines: List[str] = []
        if self._load_error:
            lines.append("（注：表结构为静态业务说明，实时反射暂不可用）")
        core = [t for t in self._tables if t["core"]]
        rest = [t for t in self._tables if not t["core"]]

        lines.append("## 数据库中可用的表（白名单，只此 %d 张）\n" % len(self._tables))
        for t in core:
            cols = t["columns"]
            pk = [c["name"] for c in cols if c["pk"]]
            notdisplay = 0
            head = f"- **{t['name']}**"
            if pk:
                head += f"（主键 {', '.join(pk)}）"
            lines.append(head + f"：{t['desc']}")
            shown = cols[:max_rows_per_table]
            notdisplay = len(cols) - len(shown)
            for c in shown:
                flag = []
                if c["pk"]:
                    flag.append("PK")
                if c["indexed"]:
                    flag.append("索引")
                if not c["nullable"]:
                    flag.append("非空")
                tail = f"  · {c['name']} [{c['type']}]" + (f"（{'/'.join(flag)}）" if flag else "")
                if c["note"]:
                    tail += f" — {c['note']}"
                lines.append(tail)
            if notdisplay > 0:
                lines.append(f"  · （其余 {notdisplay} 个字段省略，需要时用 ai_describe_table 工具查全量）")
            if t["hint"]:
                lines.append(f"  ⚠ {t['hint']}")
            lines.append("")

        if rest:
            lines.append("## 其它可用表（字段可用 ai_describe_table 工具展开）\n")
            for t in rest:
                lines.append(f"- **{t['name']}**：{t['desc']}")
            lines.append("")

        lines.append(ORACLE_DIALECT_NOTES)
        return "\n".join(lines)

    def to_table_ddl_text(self, name: str) -> str:
        """单表全字段描述（给 ai_describe_table 工具用）。"""
        t = self.describe(name)
        if not t:
            avail = ", ".join(self.table_names())
            return f"表 {name} 不可用。可用表：{avail}"
        out = [f"表 {t['name']}：{t['desc']}"]
        for c in t["columns"]:
            out.append(f"  · {c['name']} [{c['type']}]" + (f" — {c['note']}" if c["note"] else ""))
        if t["hint"]:
            out.append(f"  ⚠ {t['hint']}")
        return "\n".join(out)


schema_catalog = SchemaCatalog()

__all__ = ["schema_catalog", "SchemaCatalog", "READABLE_TABLES", "ORACLE_DIALECT_NOTES"]
