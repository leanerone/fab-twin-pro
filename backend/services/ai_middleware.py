"""AI 中间适配层：统一请求/返回结构，兼容多模型、Dify、N8N、MCP协议

架构：
  前端请求 → AI中间层 → 路由分发 → [本地规则引擎 / OpenAI兼容模型 / Dify / N8N]
                       ↑
                   统一结构体

所有AI请求统一走 ai/chat 接口，返回统一格式：
{
  "answer": "AI回答内容",
  "sql": "查询SQL（可选）",
  "jump_timestamp": "跳转时间戳（可选）",
  "table_data": "表格数据（可选）",
  "tool_calls": "工具调用记录（可选）",
  "sources": "参考来源（可选）"
}
"""
import re
import json
import time
import uuid
import requests
from typing import Optional, List, Dict, Any
from datetime import datetime

from config import (
    AI_MCP_ENABLED, AI_MCP_URL, AI_MCP_API_KEY,
    AI_PROVIDER, AI_BASE_URL, AI_API_KEY, AI_MODEL,
    AI_TEMPERATURE, AI_MAX_TOKENS,
    DIFY_ENABLED, DIFY_BASE_URL, DIFY_API_KEY, DIFY_APP_ID,
    N8N_ENABLED, N8N_BASE_URL, N8N_WEBHOOK_SECRET,
)

# 延迟导入DB模型（避免循环导入）
_machine_model = None
_alarm_model = None
_lot_model = None
_dt_event_raw_model = None
_db_session = None


def _get_models():
    """延迟获取数据库模型"""
    global _machine_model, _alarm_model, _lot_model, _dt_event_raw_model, _db_session
    if _machine_model is None:
        from models import Machine, Alarm, Lot, DT_EVENT_RAW
        from database import SessionLocal
        _machine_model = Machine
        _alarm_model = Alarm
        _lot_model = Lot
        _dt_event_raw_model = DT_EVENT_RAW
        _db_session = SessionLocal
    return _machine_model, _alarm_model, _lot_model, _dt_event_raw_model, _db_session


class AIMiddleware:
    """AI 中间适配层 - 统一调度入口"""

    def __init__(self):
        self.provider = AI_PROVIDER  # local / openai / dify / hybrid
        self.base_url = AI_BASE_URL
        self.api_key = AI_API_KEY
        self.model = AI_MODEL
        self.temperature = AI_TEMPERATURE
        self.max_tokens = AI_MAX_TOKENS

        # Dify配置
        self.dify_enabled = DIFY_ENABLED
        self.dify_base_url = DIFY_BASE_URL
        self.dify_api_key = DIFY_API_KEY
        self.dify_app_id = DIFY_APP_ID

        # N8N配置
        self.n8n_enabled = N8N_ENABLED
        self.n8n_base_url = N8N_BASE_URL
        self.n8n_webhook_secret = N8N_WEBHOOK_SECRET

        # 会话存储（内存中，后续可接DB）
        self.sessions = {}  # session_id -> { messages: [...], created_at: ... }

    def chat(self, question: str, session_id: str = None, machine_id: str = None,
             context: Dict = None, user_role: str = "user") -> Dict[str, Any]:
        """统一聊天入口

        Args:
            question: 用户问题
            session_id: 会话ID，不传则新建
            machine_id: 关联机台ID
            context: 额外上下文数据
            user_role: 用户角色（user/admin）

        Returns:
            统一响应结构体
        """
        if not session_id:
            session_id = f"sess_{uuid.uuid4().hex[:16]}"

        # 获取或创建会话
        if session_id not in self.sessions:
            self.sessions[session_id] = {
                "messages": [],
                "created_at": datetime.now().isoformat(),
                "machine_id": machine_id,
            }
        session = self.sessions[session_id]

        # 保存用户消息
        session["messages"].append({
            "role": "user",
            "content": question,
            "timestamp": datetime.now().isoformat(),
        })

        # 构建系统提示词（带上下文）
        system_prompt = self._build_system_prompt(machine_id, context, user_role)

        # 路由到不同provider
        result = None
        try:
            if self.provider == "openai" and self.base_url and self.api_key:
                result = self._call_openai_compatible(question, system_prompt, session["messages"], machine_id)
            elif self.provider == "openai":
                # provider设为openai但未配置base_url/api_key，回退本地
                print(f"[AI] provider=openai 但未配置 base_url 或 api_key，回退本地规则")
                result = self._local_rule_engine(question, machine_id, user_role)
            elif self.provider == "dify":
                result = self._call_dify(question, session_id, machine_id, user_role)
            elif self.provider == "hybrid":
                try:
                    result = self._call_dify(question, session_id, machine_id, user_role)
                except Exception as e:
                    print(f"[AI] Dify调用失败，回退本地规则: {e}")
                    result = self._local_rule_engine(question, machine_id, user_role)
            else:
                result = self._local_rule_engine(question, machine_id, user_role)
        except Exception as e:
            print(f"[AI] 调用失败，回退本地规则: {e}")
            result = self._local_rule_engine(question, machine_id, user_role)

        # 确保返回格式统一
        result = self._normalize_response(result)

        # 保存AI回复
        session["messages"].append({
            "role": "assistant",
            "content": result.get("answer", ""),
            "timestamp": datetime.now().isoformat(),
            "metadata": {k: v for k, v in result.items() if k != "answer"},
        })

        # 限制会话历史长度
        if len(session["messages"]) > 100:
            session["messages"] = session["messages"][-100:]

        result["session_id"] = session_id
        return result

    def _build_system_prompt(self, machine_id: str = None, context: Dict = None,
                             user_role: str = "user") -> str:
        """构建系统提示词"""
        prompt = """你是一个半导体工厂数字孪生平台的AI助手，名为FabTwin AI。
你可以回答关于机台状态、生产数据、报警信息、工艺参数、Lot追踪等问题。

回答要求：
1. 语言简洁专业，使用中文回答
2. 数据准确，不要编造数据
3. 如果涉及时间跳转，在回答最后标注 [JUMP: 时间戳]
4. 如果涉及表格数据，使用 [TABLE] 标签包裹
5. 支持的查询类型：机台状态、报警统计、温度趋势、产量统计、异常检测、Lot查询、工艺参数

你可以调用以下工具（通过N8N工作流）：
- query_machine_status: 查询机台实时状态
- query_alarm_stats: 查询告警统计
- query_lot_info: 查询Lot批次信息
- export_alarm_report: 导出报警报表
- generate_work_order: 生成故障工单
"""
        if machine_id:
            prompt += f"\n当前关联机台: {machine_id}"

        if context:
            prompt += f"\n上下文数据: {json.dumps(context, ensure_ascii=False, default=str)}"

        if user_role == "admin":
            prompt += "\n用户角色: 管理员，可以调用所有MCP工具和N8N工作流"
        else:
            prompt += "\n用户角色: 普通用户，仅可基础问答，不可调用N8N自动化流程"

        return prompt

    def _normalize_response(self, result: Any) -> Dict[str, Any]:
        """统一响应格式"""
        if isinstance(result, dict):
            return {
                "answer": result.get("answer", result.get("content", "")),
                "sql": result.get("sql", ""),
                "jump_timestamp": result.get("jump_timestamp", result.get("jumpTs", None)),
                "table_data": result.get("table_data", result.get("tableData", None)),
                "tool_calls": result.get("tool_calls", []),
                "sources": result.get("sources", []),
            }
        return {
            "answer": str(result),
            "sql": "",
            "jump_timestamp": None,
            "table_data": None,
            "tool_calls": [],
            "sources": [],
        }

    # ==================== Provider: 本地规则引擎 ====================

    def _local_rule_engine(self, question: str, machine_id: str = None,
                           user_role: str = "user") -> Dict[str, Any]:
        """本地规则引擎 - 关键字匹配路由"""
        Machine, Alarm, Lot, DT_EVENT_RAW, SessionLocal = _get_models()
        db = SessionLocal()
        try:
            q = question.lower()

            # N8N 指令识别（仅管理员）
            if user_role == "admin" and self._is_n8n_command(q):
                return self._trigger_n8n_workflow(question, machine_id, user_role)

            # Lot 查询
            if any(k in q for k in ["lot", "批次"]):
                return self._query_lot(db, question, machine_id)

            # 报警/告警
            if any(k in q for k in ["报警", "告警", "alarm", "异常"]):
                if user_role == "admin" and ("导出" in q or "报表" in q):
                    return self._trigger_n8n_workflow(question, machine_id, user_role, "export_alarm_report")
                return self._query_alarms(db, machine_id)

            # 温度/趋势
            if any(k in q for k in ["温度", "temperature", "temp", "趋势"]):
                return self._query_temp_trend(db, machine_id, question)

            # 产量/晶圆
            if any(k in q for k in ["产量", "晶圆", "wafer", "yield", "加工多少", "生产了多少"]):
                return self._query_yield(db, machine_id)

            # 状态/运行情况
            if any(k in q for k in ["状态", "status", "怎么样", "情况", "运行", "当前"]):
                return self._query_machine_status(db, machine_id)

            # 工艺/配方
            if any(k in q for k in ["工艺", "配方", "recipe", "步骤"]):
                return self._query_recipe(db, machine_id)

            # 工单/故障（管理员）
            if user_role == "admin" and any(k in q for k in ["工单", "work order", "故障单"]):
                return self._trigger_n8n_workflow(question, machine_id, user_role, "generate_work_order")

            # 默认：机台状态
            return self._query_machine_status(db, machine_id)
        finally:
            db.close()

    def _is_n8n_command(self, question: str) -> bool:
        """判断是否为N8N自动化指令"""
        keywords = ["导出", "报表", "工单", "批量", "自动", "推送", "生成报告", "生成工单"]
        return any(k in question for k in keywords)

    def _query_machine_status(self, db, machine_id: str = None) -> Dict[str, Any]:
        """查询机台状态"""
        Machine, Alarm, Lot, DT_EVENT_RAW, _ = _get_models()
        if not machine_id:
            machines = db.query(Machine).all()
            running = sum(1 for m in machines if m.state == "run")
            idle = sum(1 for m in machines if m.state == "idle")
            maint = sum(1 for m in machines if m.state == "maint")
            answer = (
                f"当前厂区共 {len(machines)} 台机台：\n"
                f"• 运行中：{running} 台\n"
                f"• 空闲：{idle} 台\n"
                f"• 维护：{maint} 台\n\n"
                f"可以问我具体某台机台的详细状态。"
            )
            return {
                "answer": answer,
                "sql": "SELECT state, COUNT(*) FROM machines GROUP BY state",
            }

        m = db.query(Machine).filter(Machine.id == machine_id).first()
        if not m:
            return {"answer": f"未找到机台 {machine_id}", "sql": ""}

        state_cn = {"run": "运行中", "idle": "空闲", "maint": "维护中", "down": "停机"}.get(m.state, m.state)

        answer = (
            f"机台 {m.id}（{m.name}）当前状态：\n"
            f"• 状态：{state_cn}\n"
            f"• 工艺步骤：{m.process_step}\n"
            f"• 温度：{m.temp} °C\n"
            f"• 压力：{m.pressure} mTorr\n"
            f"• RF 功率：{m.rf_power} W\n"
            f"• 气体流量：{m.gas_flow} sccm\n"
            f"• 累计晶圆：{m.wafer_count} 片\n"
            f"• 告警次数：{m.alarm_count} 次\n"
            f"• 更新时间：{m.updated_at}"
        )
        return {
            "answer": answer,
            "sql": f"SELECT * FROM machines WHERE id = '{machine_id}'",
            "jump_timestamp": m.updated_at,
        }

    def _query_alarms(self, db, machine_id: str = None) -> Dict[str, Any]:
        """查询告警统计"""
        Machine, Alarm, Lot, DT_EVENT_RAW, _ = _get_models()
        q = db.query(Alarm)
        if machine_id:
            q = q.filter(Alarm.machine_id == machine_id)
        alarms = q.order_by(Alarm.timestamp.desc()).limit(50).all()

        crit = sum(1 for a in alarms if a.level == "crit")
        warn = sum(1 for a in alarms if a.level == "warn")
        info = sum(1 for a in alarms if a.level == "info")
        unresolved = sum(1 for a in alarms if not a.resolved)

        scope = f"机台 {machine_id}" if machine_id else "全厂"

        # 表格数据
        table_data = {
            "headers": ["时间", "描述", "等级", "状态"],
            "rows": [
                [a.timestamp, a.description, a.level, "未解决" if not a.resolved else "已解决"]
                for a in alarms[:10]
            ],
        }

        answer = (
            f"{scope} 告警统计（最近50条）：\n"
            f"• 总计：{len(alarms)} 条\n"
            f"• 严重：{crit} 条\n"
            f"• 警告：{warn} 条\n"
            f"• 信息：{info} 条\n"
            f"• 未解决：{unresolved} 条\n\n"
            f"最近 10 条告警见下表。"
        )

        where = f" WHERE machine_id='{machine_id}'" if machine_id else ""
        jump = alarms[0].timestamp if alarms else None

        return {
            "answer": answer,
            "sql": f"SELECT level, COUNT(*) FROM alarms{where} GROUP BY level",
            "table_data": table_data,
            "jump_timestamp": jump,
        }

    def _query_temp_trend(self, db, machine_id: str = None, question: str = "") -> Dict[str, Any]:
        """查询温度趋势"""
        Machine, Alarm, Lot, DT_EVENT_RAW, _ = _get_models()
        if not machine_id:
            return {"answer": "请指定机台 ID 以查询温度趋势。", "sql": ""}

        events = (
            db.query(DT_EVENT_RAW)
            .filter(
                DT_EVENT_RAW.tool_id == machine_id,
            )
            .order_by(DT_EVENT_RAW.event_ts_utc.desc())
            .limit(100)
            .all()
        )

        # 从payload中提取温度（PODOPENER场景可能没有，用machines表数据）
        m = db.query(Machine).filter(Machine.id == machine_id).first()
        if m:
            answer = (
                f"机台 {machine_id} 温度情况：\n"
                f"• 当前温度：{m.temp} °C\n"
                f"• 参考范围：60 - 75 °C\n"
                f"• 状态：{('正常' if 60 <= m.temp <= 75 else '异常')}\n\n"
                f"温度传感器实时采集，每10秒更新一次。"
            )
            return {
                "answer": answer,
                "sql": f"SELECT temp FROM machines WHERE id = '{machine_id}'",
                "jump_timestamp": m.updated_at,
            }

        return {"answer": f"机台 {machine_id} 温度数据暂不可用。", "sql": ""}

    def _query_yield(self, db, machine_id: str = None) -> Dict[str, Any]:
        """查询产量"""
        Machine, Alarm, Lot, DT_EVENT_RAW, _ = _get_models()
        q = db.query(Machine)
        if machine_id:
            q = q.filter(Machine.id == machine_id)
        machines = q.all()
        total = sum(m.wafer_count for m in machines)

        lots = db.query(Lot)
        if machine_id:
            lots = lots.filter(Lot.machine_id == machine_id)
        lot_count = lots.count()
        done = lots.filter(Lot.status == "done").count()
        processing = lots.filter(Lot.status == "processing").count()

        scope = f"机台 {machine_id}" if machine_id else "全厂"

        # 表格数据（最近5个Lot）
        recent_lots = lots.order_by(Lot.start_time.desc()).limit(5).all()
        table_data = {
            "headers": ["Lot ID", "机台", "产品", "晶圆数", "状态"],
            "rows": [
                [l.id, l.machine_id, l.product, l.wafer_count, l.status]
                for l in recent_lots
            ],
        }

        answer = (
            f"{scope} 产量统计：\n"
            f"• 累计晶圆：{total} 片\n"
            f"• Lot 批次：{lot_count} 个\n"
            f"• 已完成：{done} 个\n"
            f"• 加工中：{processing} 个\n\n"
            f"最近 5 个 Lot 见下表。"
        )

        where = f" WHERE id='{machine_id}'" if machine_id else ""
        return {
            "answer": answer,
            "sql": f"SELECT SUM(wafer_count) FROM machines{where}",
            "table_data": table_data,
        }

    def _query_lot(self, db, question: str, machine_id: str = None) -> Dict[str, Any]:
        """查询Lot信息"""
        Machine, Alarm, Lot, DT_EVENT_RAW, _ = _get_models()
        match = re.search(r"LOT\w+", question.upper())
        lot_id = match.group(0) if match else None

        if lot_id:
            lot = db.query(Lot).filter(Lot.id == lot_id).first()
            if lot:
                status_cn = {"done": "已完成", "processing": "加工中", "pending": "等待中", "hold": "暂停"}.get(lot.status, lot.status)
                answer = (
                    f"Lot {lot.id} 详情：\n"
                    f"• 机台：{lot.machine_id}\n"
                    f"• 产品：{lot.product}\n"
                    f"• 晶圆数：{lot.wafer_count} 片\n"
                    f"• 状态：{status_cn}\n"
                    f"• 开始时间：{lot.start_time}\n"
                    f"• 结束时间：{lot.end_time or '进行中'}\n"
                    f"• 优先级：{lot.priority}\n"
                    f"• 工艺配方：{lot.recipe or '未指定'}"
                )
                return {
                    "answer": answer,
                    "sql": f"SELECT * FROM lots WHERE id = '{lot_id}'",
                    "jump_timestamp": lot.start_time,
                }
            return {"answer": f"未找到 Lot {lot_id}。", "sql": ""}

        # 未指定Lot ID，列出最近的
        q = db.query(Lot)
        if machine_id:
            q = q.filter(Lot.machine_id == machine_id)
        lots = q.order_by(Lot.start_time.desc()).limit(10).all()

        if not lots:
            return {"answer": "未找到相关 Lot 记录。", "sql": ""}

        table_data = {
            "headers": ["Lot ID", "机台", "产品", "状态", "开始时间"],
            "rows": [
                [l.id, l.machine_id, l.product, l.status, l.start_time]
                for l in lots
            ],
        }

        answer = f"最近 {len(lots)} 个 Lot：\n"
        answer += "（点击下方表格或输入 Lot ID 查看详情）"

        return {
            "answer": answer,
            "sql": "SELECT * FROM lots ORDER BY start_time DESC LIMIT 10",
            "table_data": table_data,
            "jump_timestamp": lots[0].start_time if lots else None,
        }

    def _query_recipe(self, db, machine_id: str = None) -> Dict[str, Any]:
        """查询工艺配方"""
        Machine, Alarm, Lot, DT_EVENT_RAW, _ = _get_models()
        if not machine_id:
            return {"answer": "请指定机台 ID 以查询工艺配方。", "sql": ""}

        m = db.query(Machine).filter(Machine.id == machine_id).first()
        if not m:
            return {"answer": f"未找到机台 {machine_id}", "sql": ""}

        # PODOPENER特殊说明
        if "PODOPENER" in machine_id or m.process_type == "PODOPENER":
            answer = (
                f"机台 {machine_id}（PODOPENER 开盖机）业务流程：\n\n"
                f"【穿入流程 PACKING - 14步】\n"
                f"1. POD_PLACED - POD放置到位\n"
                f"2. COMPLETED_PORT_LOCK - 端口锁定\n"
                f"3. READ_BATTERY - 读取电池状态\n"
                f"4. READ_TAG - 读取RFID标签\n"
                f"5. BATCH_INFO_FROM_ECUI - 获取批次信息\n"
                f"6. OPEN_POD - 打开POD盖\n"
                f"7. REACH_STAGE - 机械臂到达平台\n"
                f"8. UI_CONFIRM - 操作员确认\n"
                f"9. CLOSE_POD - 关闭POD盖\n"
                f"10. ACK_UI_DOUBLECHECK - 二次确认\n"
                f"11. REACH_POS - 机械臂到位\n"
                f"12. WRITE_TAG - 写入RFID标签\n"
                f"13. COMPLETED_PORT_UNLOCK - 端口解锁\n"
                f"14. POD_REMOVED - POD移走\n\n"
                f"【脱出流程 UNPACKING - 6步】\n"
                f"1. UI_CONFIRM - 操作员确认\n"
                f"2. CLOSE_POD - 关闭POD盖\n"
                f"3. REACH_POS - 机械臂到位\n"
                f"4. WRITE_TAG - 写入RFID标签\n"
                f"5. COMPLETED_PORT_UNLOCK - 端口解锁\n"
                f"6. POD_REMOVED - POD移走"
            )
            return {"answer": answer, "sql": ""}

        answer = (
            f"机台 {machine_id} 工艺信息：\n"
            f"• 工艺类型：{m.process_type}\n"
            f"• 当前步骤：{m.process_step}\n"
            f"• 工艺配方：根据MES系统下发\n\n"
            f"详细配方参数请查询MES系统或RCMS系统。"
        )
        return {"answer": answer, "sql": ""}

    # ==================== Provider: OpenAI 兼容模型 ====================

    def _call_openai_compatible(self, question: str, system_prompt: str,
                                history_messages: List[Dict], machine_id: str = None) -> Dict[str, Any]:
        """调用OpenAI兼容接口（支持GLM、GPT等）"""
        if not self.base_url or not self.api_key:
            return self._local_rule_engine(question, machine_id)

        # 构建消息列表
        messages = [{"role": "system", "content": system_prompt}]
        # 加入历史消息（最近20轮）
        for msg in history_messages[-40:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

        try:
            url = f"{self.base_url.rstrip('/')}/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "stream": False,
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()

            answer = data["choices"][0]["message"]["content"]

            # 提取jump_timestamp
            jump_ts = None
            jump_match = re.search(r'\[JUMP:\s*([^\]]+)\]', answer)
            if jump_match:
                jump_ts = jump_match.group(1).strip()
                answer = answer.replace(jump_match.group(0), "").strip()

            return {
                "answer": answer,
                "sql": "",
                "jump_timestamp": jump_ts,
                "sources": [{"type": "llm", "model": self.model}],
            }
        except Exception as e:
            print(f"[AI] OpenAI兼容接口调用失败: {e}")
            raise

    # ==================== Provider: Dify ====================

    def _call_dify(self, question: str, session_id: str, machine_id: str = None,
                   user_role: str = "user") -> Dict[str, Any]:
        """调用Dify应用"""
        if not self.dify_enabled or not self.dify_base_url or not self.dify_api_key:
            return self._local_rule_engine(question, machine_id, user_role)

        try:
            url = f"{self.dify_base_url.rstrip('/')}/v1/chat-messages"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.dify_api_key}",
            }
            payload = {
                "inputs": {
                    "machine_id": machine_id or "",
                    "user_role": user_role,
                },
                "query": question,
                "response_mode": "blocking",
                "conversation_id": session_id,
                "user": f"fabtwin_{user_role}",
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
            data = resp.json()

            answer = data.get("answer", "")
            conversation_id = data.get("conversation_id", session_id)

            # 提取表格数据
            table_data = None
            if "table_data" in str(data):
                # Dify返回中可能包含结构化数据
                pass

            return {
                "answer": answer,
                "sql": "",
                "jump_timestamp": None,
                "table_data": table_data,
                "sources": [{"type": "dify", "app_id": self.dify_app_id}],
            }
        except Exception as e:
            print(f"[AI] Dify调用失败: {e}")
            raise

    # ==================== N8N 工作流联动 ====================

    def _trigger_n8n_workflow(self, question: str, machine_id: str = None,
                              user_role: str = "user", workflow_type: str = None) -> Dict[str, Any]:
        """触发N8N工作流（MCP协议转发）"""
        if user_role != "admin":
            return {
                "answer": "抱歉，自动化流程操作需要管理员权限。请联系管理员。",
                "sql": "",
            }

        if not self.n8n_enabled or not self.n8n_base_url:
            return {
                "answer": (
                    "N8N 自动化服务未配置。\n"
                    "请在 AI 配置面板中配置 N8N 服务地址后使用此功能。\n\n"
                    "支持的自动化流程：\n"
                    "• 导出报警报表\n"
                    "• 生成故障工单\n"
                    "• 批量导出设备数据\n"
                    "• 产线报表自动推送"
                ),
                "sql": "",
            }

        # 识别工作流类型
        if not workflow_type:
            if "导出" in question and ("报警" in question or "告警" in question):
                workflow_type = "export_alarm_report"
            elif "工单" in question or "故障" in question:
                workflow_type = "generate_work_order"
            elif "导出" in question and "数据" in question:
                workflow_type = "export_machine_data"
            elif "报表" in question and "推送" in question:
                workflow_type = "push_daily_report"
            else:
                workflow_type = "general_query"

        try:
            webhook_url = f"{self.n8n_base_url.rstrip('/')}/webhook/{workflow_type}"
            if self.n8n_webhook_secret:
                webhook_url += f"?secret={self.n8n_webhook_secret}"

            payload = {
                "question": question,
                "machine_id": machine_id,
                "user_role": user_role,
                "workflow_type": workflow_type,
                "timestamp": datetime.now().isoformat(),
            }

            resp = requests.post(webhook_url, json=payload, timeout=120)
            resp.raise_for_status()
            result_data = resp.json()

            answer = result_data.get("answer", result_data.get("message", "工作流已触发，请稍候查看结果。"))

            table_data = None
            if "data" in result_data and isinstance(result_data["data"], list):
                if result_data["data"] and isinstance(result_data["data"][0], dict):
                    headers = list(result_data["data"][0].keys())
                    rows = [list(item.values()) for item in result_data["data"][:20]]
                    table_data = {"headers": headers, "rows": rows}

            return {
                "answer": f"🤖 [N8N自动化] {answer}",
                "sql": result_data.get("sql", ""),
                "table_data": table_data,
                "tool_calls": [{"tool": "n8n", "workflow": workflow_type, "status": "success"}],
                "sources": [{"type": "n8n", "workflow": workflow_type}],
            }
        except Exception as e:
            print(f"[AI] N8N调用失败: {e}")
            return {
                "answer": f"⚠️ N8N 工作流调用失败：{str(e)}\n\n请检查 N8N 服务配置和网络连接。",
                "sql": "",
                "tool_calls": [{"tool": "n8n", "workflow": workflow_type, "status": "failed", "error": str(e)}],
            }

    # ==================== 配置管理 ====================

    def get_config(self) -> Dict[str, Any]:
        """获取当前AI配置（脱敏）"""
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url_masked": self._mask_url(self.base_url),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "dify_enabled": self.dify_enabled,
            "dify_base_url_masked": self._mask_url(self.dify_base_url),
            "dify_app_id_masked": self._mask_key(self.dify_app_id) if self.dify_app_id else "",
            "n8n_enabled": self.n8n_enabled,
            "n8n_base_url_masked": self._mask_url(self.n8n_base_url),
        }

    def update_config(self, config: Dict[str, Any]) -> bool:
        """更新AI配置（运行时更新，不持久化到配置文件）"""
        try:
            if "provider" in config:
                self.provider = config["provider"]
            if "base_url" in config:
                self.base_url = config["base_url"]
            if "api_key" in config:
                self.api_key = config["api_key"]
            if "model" in config:
                self.model = config["model"]
            if "temperature" in config:
                self.temperature = float(config["temperature"])
            if "max_tokens" in config:
                self.max_tokens = int(config["max_tokens"])

            if "dify_enabled" in config:
                self.dify_enabled = bool(config["dify_enabled"])
            if "dify_base_url" in config:
                self.dify_base_url = config["dify_base_url"]
            if "dify_api_key" in config:
                self.dify_api_key = config["dify_api_key"]
            if "dify_app_id" in config:
                self.dify_app_id = config["dify_app_id"]

            if "n8n_enabled" in config:
                self.n8n_enabled = bool(config["n8n_enabled"])
            if "n8n_base_url" in config:
                self.n8n_base_url = config["n8n_base_url"]
            if "n8n_webhook_secret" in config:
                self.n8n_webhook_secret = config["n8n_webhook_secret"]

            return True
        except Exception as e:
            print(f"[AI] 更新配置失败: {e}")
            return False

    def test_connection(self, provider_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """测试连接"""
        try:
            if provider_type == "openai":
                url = f"{config.get('base_url', '').rstrip('/')}/v1/models"
                headers = {"Authorization": f"Bearer {config.get('api_key', '')}"}
                resp = requests.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
                return {"success": True, "message": "连接成功"}

            elif provider_type == "dify":
                url = f"{config.get('base_url', '').rstrip('/')}/v1/parameters"
                headers = {"Authorization": f"Bearer {config.get('api_key', '')}"}
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    return {"success": True, "message": "Dify连接成功"}
                return {"success": False, "message": f"Dify连接失败: HTTP {resp.status_code}"}

            elif provider_type == "n8n":
                url = f"{config.get('base_url', '').rstrip('/')}/healthz"
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    return {"success": True, "message": "N8N连接成功"}
                return {"success": False, "message": f"N8N连接失败: HTTP {resp.status_code}"}

            return {"success": False, "message": "未知的provider类型"}
        except Exception as e:
            return {"success": False, "message": f"连接测试失败: {str(e)}"}

    def _mask_url(self, url: str) -> str:
        """脱敏URL"""
        if not url:
            return ""
        if len(url) > 20:
            return url[:10] + "..." + url[-5:]
        return url

    def _mask_key(self, key: str) -> str:
        """脱敏密钥"""
        if not key:
            return ""
        if len(key) > 10:
            return key[:4] + "****" + key[-4:]
        return "****"

    # ==================== 会话管理 ====================

    def get_session(self, session_id: str) -> Optional[Dict]:
        """获取会话"""
        return self.sessions.get(session_id)

    def clear_session(self, session_id: str) -> bool:
        """清除会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            return True
        return False

    def list_sessions(self, limit: int = 20) -> List[Dict]:
        """列出所有会话（最近的）"""
        sessions = list(self.sessions.values())
        return sorted(sessions, key=lambda s: s.get("created_at", ""), reverse=True)[:limit]


# 全局单例
ai_middleware = AIMiddleware()
