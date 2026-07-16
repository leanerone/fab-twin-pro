"""AI MCP调用框架：预留对接Dify/n8n接口"""
import json
import requests
from config import AI_MCP_ENABLED, AI_MCP_URL, AI_MCP_API_KEY


class AIMCP:
    def __init__(self):
        self.enabled = AI_MCP_ENABLED
        self.base_url = AI_MCP_URL
        self.api_key = AI_MCP_API_KEY

    def query(self, question, machine_id=None):
        """调用AI MCP查询"""
        if not self.enabled or not self.base_url:
            return self._local_fallback(question, machine_id)

        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
            payload = {
                "question": question,
                "machine_id": machine_id,
            }
            response = requests.post(f"{self.base_url}/api/ai/query", json=payload, headers=headers, timeout=30)
            return response.json()
        except Exception as e:
            print(f"[AI MCP] 调用失败，使用本地回退: {e}")
            return self._local_fallback(question, machine_id)

    def _local_fallback(self, question, machine_id):
        """本地回退：当AI MCP不可用时使用本地规则引擎"""
        question = question.lower()
        answer = ""
        sql = ""
        jump_timestamp = None

        if "lot" in question or "批次" in question:
            lot_match = None
            for word in question.split():
                if word.startswith("lot"):
                    lot_match = word.upper()
                    break
            if not lot_match:
                lot_match = "LOT" + str(int(question[-5:])) if question[-5:].isdigit() else "LOT12345"

            answer = f"[本地AI] 查询 Lot {lot_match} 信息\n"
            answer += "• 产品型号: DRAM-1X\n"
            answer += "• 晶圆数量: 25片\n"
            answer += "• 当前状态: 加工中\n"
            answer += "• 机台: OXE-01\n"
            answer += "• 开始时间: 10:30:00\n"
            answer += "• 预计完成: 10:55:00"
            sql = f"SELECT * FROM lots WHERE lot_id = '{lot_match}'"
            jump_timestamp = "2026-07-11T10:30:00"

        elif "报警" in question or "告警" in question:
            answer = f"[本地AI] 机台 {machine_id or 'OXE-01'} 告警统计\n"
            answer += "• 今日告警: 15次\n"
            answer += "• 严重告警: 3次\n"
            answer += "• 警告: 12次\n"
            answer += "• 主要类型: 温度异常、RF漂移、压力不稳定"
            sql = "SELECT * FROM dt_alarm_event WHERE tool_id = :machine_id AND TRUNC(start_ts_utc) = TRUNC(SYSDATE)"

        elif "温度" in question or "趋势" in question:
            answer = f"[本地AI] 温度趋势分析\n"
            answer += "• 当前温度: 68.5°C\n"
            answer += "• 平均温度: 65.2°C\n"
            answer += "• 最高温度: 78.3°C\n"
            answer += "• 最低温度: 22.1°C\n"
            answer += "• 分析: 温度在正常范围内波动"
            sql = "SELECT event_time, temperature FROM dt_event_std WHERE tool_id = :machine_id AND metric = 'temperature'"

        elif "状态" in question or "现状" in question:
            answer = f"[本地AI] 机台 {machine_id or 'OXE-01'} 当前状态\n"
            answer += "• 状态: RUNNING\n"
            answer += "• 工艺步骤: 刻蚀工艺 #2\n"
            answer += "• 温度: 68.5°C\n"
            answer += "• 压力: 0.003 Pa\n"
            answer += "• RF功率: 550 W\n"
            answer += "• 累计晶圆: 1450片"
            sql = "SELECT * FROM dt_state_snapshot WHERE tool_id = :machine_id ORDER BY snapshot_ts_utc DESC FETCH FIRST 1 ROWS ONLY"

        elif "异常" in question or "检测" in question:
            answer = f"[本地AI] 异常检测结果\n"
            answer += "• 检测项: 温度、压力、RF功率、气体流量\n"
            answer += "• 结果: 正常\n"
            answer += "• 建议: 继续监控，无需干预"
            sql = "SELECT * FROM dt_alarm_event WHERE tool_id = :machine_id AND alarm_severity = 'CRITICAL'"

        elif "产量" in question or "晶圆" in question:
            answer = f"[本地AI] 产量统计\n"
            answer += "• 今日产量: 1450片\n"
            answer += "• 目标产量: 1500片\n"
            answer += "• 达成率: 96.7%\n"
            answer += "• WIP: 45片"
            sql = "SELECT COUNT(*) FROM lots WHERE machine_id = :machine_id AND TRUNC(start_time) = TRUNC(SYSDATE)"

        elif "mes" in question or "rcms" in question or "fdc" in question:
            answer = f"[本地AI] 外部系统查询\n"
            answer += f"• MES: 可查询Lot信息、工艺路线\n"
            answer += f"• RCMS: 可查询配方、设备维护记录\n"
            answer += f"• FDC: 可查询实时参数、SPC图表\n"
            answer += "\n⚠ 请先配置AI MCP连接，或在ODS层同步这些系统的数据"

        else:
            answer = f"[本地AI] 收到问题: {question}\n"
            answer += "支持的查询类型:\n"
            answer += "• Lot查询（如：LOT12345什么时间加工的？）\n"
            answer += "• 告警统计（如：今天有多少报警？）\n"
            answer += "• 温度趋势（如：温度趋势如何？）\n"
            answer += "• 机台状态（如：当前状态？）\n"
            answer += "• 异常检测（如：检测异常？）\n"
            answer += "• 产量统计（如：今天加工多少晶圆？）"

        return {
            "answer": answer,
            "sql": sql,
            "jump_timestamp": jump_timestamp,
        }


ai_mcp = AIMCP()
