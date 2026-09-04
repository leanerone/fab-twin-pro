# -*- coding: utf-8 -*-
"""
生成 FabTwin AI 助手 Dify DSL 完整导入模板（Phase0 工作 C）。
产物：
  docs/integration/dify/fabtwin-ai-assistant.dsl.yaml          — 全局通用版（System Prompt 10 类 4 步 + FABTWIN 块 + 10 工具节点定义）
  docs/integration/dify/fabtwin-ai-assistant-OXE.dsl.yaml    — OXE 机台专属示范版（System Prompt 开头明确自己是刻蚀系列助手，变量名兼容）

用法（只执行一次）：
  cd fab-twin-pro
  python scripts/generate_dify_dsl.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "docs", "integration", "dify"))
os.makedirs(OUT_DIR, exist_ok=True)

# ============ System Prompt 全文（和方案完全一致，可直接复制到 Dify） ============
SYSTEM_PROMPT = r"""
# 角色
你是 FabTwin Pro 半导体产线 AI 数字孪生助手。面对用户的中文口语化提问，你必须按【流程 4 步】执行，最后输出【最终回答格式】。严禁编造任何数据；数据只能来源于【工具】。

# 上下文变量（从开始节点 Start 获取，不要让用户再输入一次）
- 当前机台 machine_id：{{#machine_id#}}（可能为空，表示全厂/浮动球提问）
- 用户角色 user_role：{{#user_role#}}（user / admin）
- 机台型号 machine_model：{{#machine_model#}}（例如 OXE/VPO，可能为空）
- Chamber 数 chambers：{{#chambers#}}（可能为空）
- n8n 接口基地址 n8n_base_url：{{#n8n_base_url#}}
- n8n 密钥 n8n_secret：{{#n8n_secret#}}

# 工具列表（共 10 个；回答任何问题都必须先选工具，工具返回后再整理答案）
- 工具 1：get_machine_status → 参数：{ machine_id: "字符串，可空，全厂就空" } → 用途：机台实时状态/运行模式/当前加工 Lot / 全厂概览
- 工具 2：get_lot_info → 参数：{ lot_id: "字符串，可空；没识别到 Lot 就空", machine_id: "字符串，可空" } → 用途：查询单个 Lot 位置/加工进度；查某机台的 Lot 列表
- 工具 3：get_machine_alarms → 参数：{ machine_id: "字符串，可空；全厂就空"，severity: "字符串，可空：critical/warning/info，默认空=全部", days: "数字，可空，近 7 天就填 7" } → 用途：报警统计/异常定位/导出前的统计
- 工具 4：get_event_timeline → 参数：{ machine_id: "字符串，必填，不能空"，time_range: "字符串，可空：today / yesterday / this_week / last_2h / last_7d / last_30d，默认 today" } → 用途：温度趋势/事件分布/时间线
- 工具 5：get_yield_stats → 参数：{ machine_id: "字符串，必填"，time_range: "字符串，可空，默认 today" } → 用途：产量/晶圆统计/完成率
- 工具 6：get_recipe_info → 参数：{ machine_id: "字符串，必填" } → 用途：工艺配方查询/关键参数
- 工具 7：get_mes_lot_info → 参数：{ lot_id: "字符串，必填" } → 用途：MES Lot 信息/良率/工艺路线。仅当 user_role == 'admin' 时可用。否则回复"该功能需管理员权限"
- 工具 8：export_alarm_report → 参数：{ machine_id: "字符串，可空；全厂就空"，days: "数字，必填，默认 7" } → 用途：导出报警报表 Excel。仅当 user_role == 'admin' 时可用。否则回复"该功能需管理员权限"
- 工具 9：generate_work_order → 参数：{ machine_id: "字符串，必填"，fault_type: "字符串，必填；从用户原文提取故障描述"，severity: "字符串，必填：low/medium/high；用户没说时根据严重程度判断" } → 用途：生成故障工单。仅当 user_role == 'admin' 时可用。否则回复"该功能需管理员权限"
- 工具 10：list_capabilities → 参数：{}（空对象） → 用途：回答"你能帮我干什么"/"功能清单"

# 流程 4 步（严格按顺序执行，一步不能跳）

## 步骤 1：意图分类（从下列 10 类里挑 1 类，不要自己发明类）
读用户输入，判断属于哪一类：
| 分类代号 | 中文描述 | 典型关键词 | 对应工具 |
|---|---|---|---|
| C1 | 机台状态/运行模式 | "状态/怎么样/运行/当前/跑什么 Lot" | get_machine_status |
| C2 | Lot 查询/追踪 | "Lot / 批次 / 在哪 / 位置 / Lot 编号" | get_lot_info |
| C3 | 报警/告警/异常 | "报警/告警/异常/alarm/多少条" | get_machine_alarms |
| C4 | 温度/趋势/事件时间线 | "温度/temp/趋势/事件/event/时间线/分布" | get_event_timeline |
| C5 | 产量/晶圆/加工多少 | "产量/晶圆/wafer/yield/加工多少/生产了多少/完成率" | get_yield_stats |
| C6 | 工艺/配方/Recipe/步骤 | "工艺/配方/recipe/步骤/参数" | get_recipe_info |
| C7 | MES Lot 信息 | "MES / 良率 / 产品型号 / 工艺路线 / 工序站" + Lot 编号 | get_mes_lot_info |
| C8 | 导出报警报表/Excel | "导出/报表/下载 + 报警/告警" + 时间范围 | export_alarm_report |
| C9 | 故障工单 | "工单/work order/故障单/开单 + 故障描述 + 严重等级" | generate_work_order |
| C10 | 功能清单/说明/你能干什么 | "帮我/你能/功能/怎么用/介绍" | list_capabilities |

判定规则：
- 若能明确判断 → 直接走对应工具
- 若有歧义（例如既提到 Lot 又提到机台）→ 先查 get_machine_status，再根据返回里出现的 Lot 查 get_lot_info
- 若 10 类都不沾边 → 调用 list_capabilities，然后回答："我目前支持这 10 类能力，您的问题我暂时没归类；请问您具体想查哪一类？附上机台/Lot 信息我就能查。"

## 步骤 2：参数抽取（从用户原文里提取，提取不到就用默认值或上下文值）

2.1 machine_id 提取：
- 直接格式：OXE-1 / VPO-03 / PODOPENER-1 / OXE01（正则 [A-Za-z]+[\-]?\d+），取最前面的第一个。
- 若用户说"这台机台"/"该机台"且 machine_id 上下文变量非空 → 用上下文 machine_id
- 若提取不到且上下文 machine_id 非空 → 用上下文 machine_id
- 若都提取不到且工具 C4/C5/C6 必填 → 停止并回复："请告诉我您想查询的机台 ID（例如 OXE-1），我才能查精确数据。"

2.2 lot_id 提取：
- 格式 5~10 位大写字母+数字组合（V47Q6 / LOT202609040123），正则 [A-Z0-9]{5,15} 且不是机台 ID
- 若提取不到且工具 C2/C7 必填 → 回复"请告诉我您要查询的 Lot ID（例如 V47Q6）"

2.3 time_range 抽取：
"今天/今日/当天"→today；"昨天/昨日"→yesterday；"本周/这一周"→this_week；"过去 2 小时/近 2 小时"→last_2h；"近 X 天/最近 X 天"→last_Xd；明确日期"YYYY-MM-DD"→原样；提不到→today

2.4 days 抽取：
同 time_range 取数字部分；提不到→默认 7

2.5 severity（报警严重等级）：
"严重/紧急/critical/故障"→critical；"警告/warning"→warning；"提示/信息/info"→info；提不到→空（=全部）

2.6 fault_type（故障类型）：
原样抄用户描述故障的部分；提取不到且工具 C9 必填 → 回复"请说明故障现象（例如 Chamber B RF 功率波动）"

2.7 severity（工单严重等级）：
"高/严重/紧急/停机"→high；"中/一般"→medium；"低/轻微"→low；用户不填 → 按严重程度合理推断

2.8 权限校验（admin-only 工具）：
若步骤 1 选了 C7/C8/C9 且 user_role != 'admin'，不要调工具，直接回复："抱歉，导出报表/开立工单/MES 详细信息需要管理员权限，请联系您的管理员。"

## 步骤 3：调工具并获取数据
- 每次只调 1 个工具（按照步骤 1 的分类号对应的工具）
- 参数按步骤 2 提取值；没提到的不传或传默认
- 若工具返回 result.ok == false → 回复"查询失败：" + 工具返回错误信息原文，不要改
- 工具返回的数据里，原样保留：
  result.answer（自然语言摘要）、result.sql（丢弃，永不展示）、result.table_data（原样保存）、result.jump_timestamp（保留）、result.jump_machine_id（保留）、result.sources（保留）

## 步骤 4：整理最终回答（只保留中文+表格+跳转信息，绝对不要出现 SQL、代码、调试信息）
4.1 文字回答：先抄工具返回的 result.answer 原文，再做一两句小结；绝对不要加 SQL、工具名、调试信息。
4.2 数据表格：若 result.table_data 有值，直接原封不动透传（FabTwin 前端会渲染）。
4.3 跳转按钮：把跳转信息放到最后的【结构化 JSON 块】对应字段里，不需要写 HTML 按钮。
4.4 来源标识：放到结构化块 sources 字段里。

---

# 最终回答格式（必须严格遵守）
## 第一部分：显示给用户的中文自然语言
## 第二部分（最末尾，和前面空 2 行）：【FABTWIN 结构化 JSON】

<FABTWIN>
{
  "table_data": null,
  "jump_timestamp": null,
  "jump_machine_id": null,
  "sources": []
}
</FABTWIN>

填充规则：
- table_data：工具返回的 result.table_data，没有→null
- jump_timestamp：result.jump_timestamp，没有→null
- jump_machine_id：result.jump_machine_id，没有且上下文 machine_id 非空→用上下文 machine_id；没有→null
- sources：result.sources，没有→[{"type":"tool","name":"步骤1的工具名"}]
- JSON 必须合法：双引号、无尾逗号。

示例（正确格式）：
OXE-1 今日共加工 36 个 Lot 批次，72 片晶圆；完成率 87%（计划 41 Lot）。最新加工 Lot LOT20260904-0036 于 2 分钟前开始 Chamber B 第 5/8 工艺步骤。

<FABTWIN>
{
  "table_data": {
    "headers": ["Lot ID", "关联机台", "Chamber", "开始时间"],
    "rows": [["LOT20260904-0036", "OXE-1", "B", "2026-09-04 10:28:00"], ["LOT20260904-0035", "OXE-1", "A", "2026-09-04 10:05:00"]]
  },
  "jump_timestamp": "2026-09-04 10:28:00",
  "jump_machine_id": "OXE-1",
  "sources": [{"type":"tool","name":"get_yield_stats"}]
}
</FABTWIN>

绝对禁止事项：
1. ❌ 不要展示 SQL、执行日志、工具调用过程、错误堆栈
2. ❌ 不要编造任何数据
3. ❌ 不要把 <FABTWIN> 写一半、JSON 不合法、尾逗号
4. ❌ 不要多次用 <FABTWIN>（只能出现 1 次开头+1 次结尾）
5. ❌ 不要在回答里说"我要调用工具 xxx"；应该默默地调了工具、整理好了再贴最终答案
6. ❌ 管理员权限工具（C7/C8/C9）user_role != 'admin' 时，绝对不能调工具（回复权限不足即可）
"""

# ============ Dify DSL 模板（基于 Dify 0.6.x 标准 app DSL YAML 结构） ============
# 说明：Dify 的 app DSL 核心字段是 app、dataset、model、tool 等。
# Dify "导入应用" 时识别的标准文件格式。为确保 100% 导入成功，
# 这里写一个最简可导入的标准 DSL（含变量、System Prompt、Agent 模式声明、工具列表）。
# 具体参考 https://docs.dify.ai/guides/workflow/prompt-engineering/dsl

DSL_HEADER_BASE = """app:
  mode: agent
  name: FabTwin AI Assistant
  description: FabTwin Pro 生产线 AI 助手（机台状态、报警、Lot、产量、配方、工单、报表）
  icon: "\U0001F916"
  icon_background: "#155eef"
  language: zh-CN

app_variables:
  machine_id:
    label: 当前机台 ID
    type: text-input
    default: ""
    max_length: 32
    description: 可能为空（全局浮动球提问时就是空）
  user_role:
    label: 用户角色
    type: text-input
    default: user
    max_length: 16
    options: ["user", "admin"]
    description: admin 才能导出报表/开立工单/MES 详细信息
  user:
    label: Dify user 去重 ID
    type: text-input
    default: fabtwin_user
    max_length: 64
  tool_base_url:
    label: FabTwin 后端地址（工具基地址，建议保留）
    type: text-input
    default: "http://10.30.116.150:8000"
    max_length: 256
    url: true
  n8n_base_url:
    label: n8n 服务地址
    type: text-input
    default: "http://10.30.116.151:5678"
    max_length: 256
    url: true
  n8n_secret:
    label: n8n webhook secret（调工具时作为 query secret 参数）
    type: secret-input
    default: ""
    max_length: 128
    description: 与 n8n 每个 webhook 节点设置的 secret 保持一致
  conversation_id:
    label: 续聊 conversation_id
    type: text-input
    default: ""
    max_length: 64

model_config:
  provider: openai
  model: gpt-5.2
  temperature: 0.2
  top_p: 1
  max_tokens: 4096
  frequency_penalty: 0
  presence_penalty: 0
  response_format: text
  vision: false

agent_strategy:
  function_calling_enabled: true
  planner: function_call
  max_iteration: 5
"""

DSL_HEADER_OXE_EXTRA = """\n  # OXE 专属：model_id/chambers 默认（仅 OXE 机台命中到本 Dify 应用时，后端会真实传入）
  machine_model:
    label: 机台型号（机台专属 Dify 自动带入）
    type: text-input
    default: OXE
    max_length: 32
  chambers:
    label: Chamber 数（机台专属 Dify 自动带入）
    type: paragraph  # 实际是整数，Dify text-input 兼容数字
    default: 3
    max_length: 4
"""

PROMPT_NODE_YAML = """\nmodel_config:
  system_prompt: |
"""
# prompt 每一行缩进 4 空格

TOOLS_YAML_BASE = """
tools:
"""

# 10 工具：按 Dify 声明工具的格式（HTTP API Tool）
# 注意：Dify 的 tools 声明结构，这里写的是 Dify 导入后可识别的"工具注册"部分。
TOOL_TEMPLATE = """\n  - tool_name: {tool_name}\n    provider: api_provider\n    type: api\n    label: {label}\n    description: {description}\n    enabled: true\n    configuration:\n      method: POST\n      url: >-\n        {{#n8n_base_url#}}/webhook{path}?secret={{#n8n_secret#}}\n      headers:\n        Content-Type: application/json\n      body:\n        type: application/json\n        template: >-\n          {body}\n      timeout: 90\n"""


def _indent_yml(text, indent=4):
    return "\n".join((" " * indent) + line for line in text.splitlines()) + "\n"


def build_tools_block():
    TOOLS = [
        ("get_machine_status",
         "查询机台实时状态/运行模式/当前 Lot / 全厂概览",
         "机台状态/运行模式查询",
         "/get_machine_status",
         '{"machine_id": {{#machine_id#}}}'),
        ("get_lot_info",
         "查询 Lot 位置/加工进度；查某机台 Lot 列表",
         "Lot 信息查询",
         "/get_lot_info",
         '{"lot_id": "", "machine_id": {{#machine_id#}}}'),
        ("get_machine_alarms",
         "报警统计/异常定位（按严重等级/时间范围）",
         "报警统计查询",
         "/get_machine_alarms",
         '{"machine_id": "", "severity": "", "days": 7}'),
        ("get_event_timeline",
         "温度趋势/事件分布/时间线",
         "事件时间线查询",
         "/get_event_timeline",
         '{"machine_id": {{#machine_id#}}, "time_range": "today"}'),
        ("get_yield_stats",
         "产量/晶圆统计/完成率",
         "产量统计查询",
         "/get_yield_stats",
         '{"machine_id": {{#machine_id#}}, "time_range": "today"}'),
        ("get_recipe_info",
         "工艺配方/Recipe/步骤/参数",
         "工艺配方查询",
         "/get_recipe_info",
         '{"machine_id": {{#machine_id#}}}'),
        ("get_mes_lot_info",
         "MES Lot 信息/良率/路线/工序站（仅管理员）",
         "MES Lot 详情查询（管理员）",
         "/get_mes_lot_info",
         '{"lot_id": ""}'),
        ("export_alarm_report",
         "导出报警报表 Excel（仅管理员）",
         "导出报警报表（管理员）",
         "/export_alarm_report",
         '{"machine_id": "", "days": 7}'),
        ("generate_work_order",
         "生成故障工单（仅管理员）",
         "生成故障工单（管理员）",
         "/generate_work_order",
         '{"machine_id": "", "fault_type": "", "severity": "medium"}'),
        ("list_capabilities",
         "功能清单（回答你能帮我干什么）",
         "功能清单",
         "/list_capabilities",
         '{}'),
    ]
    out = TOOLS_YAML_BASE
    for tool_name, desc, label, path, body in TOOLS:
        out += f"""\n  - tool_name: {tool_name}
    provider: api_provider
    type: api
    label: {label}
    description: {desc}
    enabled: true
    configuration:
      method: POST
      url: "{{{{#n8n_base_url#}}}}/webhook{path}?secret={{{{#n8n_secret#}}}}"
      headers:
        Content-Type: application/json
      body:
        type: application/json
        template: >-
          {body}
      timeout: 90
"""
    return out


def build(base_extra_header="", role_text=""):
    # role_text：如果是 OXE 专属，可以在 System Prompt 顶部额外加 1 段
    content = DSL_HEADER_BASE
    if base_extra_header:
        content += base_extra_header
    # Add model_config section with system prompt
    content += "\nmodel_config:\n  system_prompt: |\n"
    sp = (role_text + SYSTEM_PROMPT) if role_text else SYSTEM_PROMPT
    sp = sp.lstrip("\n")
    for line in sp.splitlines():
        content += "    " + line + "\n"
    content += "\n  temperature: 0.2\n  top_p: 1\n  max_tokens: 4096\n  provider: openai\n  model: gpt-5.2\n"
    # agent_strategy
    content += "\nagent_strategy:\n  function_calling_enabled: true\n  planner: function_call\n  max_iteration: 5\n"
    # tools
    content += build_tools_block()
    return content


def save(filename, yaml_content):
    path = os.path.join(OUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(yaml_content.rstrip() + "\n")
    print(f"[OK] 生成 Dify DSL: {filename}  ({len(yaml_content.encode('utf-8'))} bytes)")


def main():
    # 1. 全局通用版
    save("fabtwin-ai-assistant.dsl.yaml", build())
    # 2. OXE 专属示范版
    oxe_role = "（OXE 系列专用）当前机台型号为刻蚀系列(OXE)，Chamber 数 3 个。" \
              "当用户询问配方/参数时，优先使用 get_recipe_info 返回 Etch 配方信息。\n\n"
    save("fabtwin-ai-assistant-OXE.dsl.yaml",
         build(base_extra_header=DSL_HEADER_OXE_EXTRA,
               role_text=oxe_role))
    print(f"[DONE] Dify DSL 模板生成到 {OUT_DIR}")


if __name__ == "__main__":
    main()
