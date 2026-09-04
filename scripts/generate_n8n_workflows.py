# -*- coding: utf-8 -*-
"""
生成 10 个 n8n workflow JSON 模板（FabTwin Phase0 工作 B）。
每个 workflow = Webhook 触发器 + Parse(JS) + Oracle SQL Query + Format(JS) + Respond to Webhook，共 5 节点。
产物写入 docs/integration/n8n/ 目录：
  F1_get_machine_status.json
  F2_get_lot_info.json
  F3_get_machine_alarms.json
  F4_get_event_timeline.json
  F5_get_yield_stats.json
  F6_get_recipe_info.json
  F7_get_mes_lot_info.json
  F8_export_alarm_report.json
  F9_generate_work_order.json
  F10_list_capabilities.json

用法（只在 Phase0 执行一次，产完就不用再跑）：
  cd fab-twin-pro
  python scripts/generate_n8n_workflows.py

导入提示：用户只需在 n8n「导入」后，双击【Query Oracle】节点，
把 Credential（凭证）改成自己的 Oracle DB 连接（user/password/tns/sid），
其他节点内容、返回格式、Webhook 路径、执行 ID 模板全部 OK，无需手动改。
"""
import json
import os
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "docs", "integration", "n8n"))
os.makedirs(OUT_DIR, exist_ok=True)

# ============ 公共工具 ============
def _node(klass, name, params, type_version, pos, cred=None, extra=None):
    node = {
        "parameters": params,
        "name": name,
        "type": klass,
        "typeVersion": type_version,
        "position": list(pos),
    }
    if cred:
        node["credentials"] = cred
    if extra:
        node.update(extra)
    return node


def webhook_node(webhook_path):
    """Webhook：POST 路径 = webhook_path（对齐 Dify 工具的 URL 后缀），responseNode 模式"""
    return _node(
        "n8n-nodes-base.webhook", "Webhook",
        {
            "httpMethod": "POST",
            "path": webhook_path,
            "responseMode": "responseNode",
            "options": {},
        },
        2, (240, 300),
        extra={"webhookId": webhook_path + "-webhook-id"},
    )


def parse_node(js_code):
    """Parse：提取 body 参数 + 防注入。输出 $json.machine_id 等变量。"""
    return _node(
        "n8n-nodes-base.code", "Parse",
        {"jsCode": js_code, "options": {}},
        2, (460, 300),
    )


def oracle_node(sql):
    """Oracle：直接执行 SQL。凭证留空（用户导入后选）。"""
    return _node(
        "n8n-nodes-base.oracle", "Query Oracle",
        {"operation": "executeQuery", "query": sql, "options": {}},
        1, (680, 300),
        cred={"oracleApi": {"id": "", "name": "FabTwin Oracle"}},
    )


def format_node(js_code):
    """Format：根据 Oracle 行构造 {ok, answer, table_data, jump_timestamp, jump_machine_id, sources}"""
    return _node(
        "n8n-nodes-base.code", "Format",
        {"jsCode": js_code, "options": {}},
        2, (900, 300),
    )


def respond_node():
    """Respond：200 + JSON。"""
    return _node(
        "n8n-nodes-base.respondToWebhook", "Respond",
        {"responseCode": 200, "responseBody": "={{ JSON.stringify($json) }}", "options": {}},
        1, (1120, 300),
    )


def connections(conn_tuples):
    """conn_tuples: [(src, dest), ...]"""
    out = {}
    for (src, dest) in conn_tuples:
        out[src] = {"main": [[{"node": dest, "type": "main", "index": 0}]]}
    return out


def save(name, title, nodes, conns):
    payload = {
        "name": title,
        "nodes": nodes,
        "pinData": {},
        "connections": conns,
        "active": False,
        "settings": {"executionOrder": "v1"},
        "versionId": str(uuid.uuid4()),
        "meta": {"templateCredsSetupCompleted": True, "instanceId": "fabtwin-local"},
        "id": str(uuid.uuid4()),
        "tags": [],
    }
    path = os.path.join(OUT_DIR, name + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[OK] 生成: {os.path.basename(path)}  —  {title}")


# ============ 参数提取 JS（通用）============
PARSE_MID = r"""
const body = $input.first().json.body || $input.first().json;
const clean = (s) => String(s == null ? '' : s).replace(/[^A-Za-z0-9_ \u4e00-\u9fa5\-\.%\:#\/]/g, '').trim();
const machineId = clean(body.machine_id);
return {
  json: {
    machine_id: machineId,
    machine_id_like: machineId ? (machineId + '%') : '',
  }
};
"""

PARSE_MID_LOT = r"""
const body = $input.first().json.body || $input.first().json;
const clean = (s) => String(s == null ? '' : s).replace(/[^A-Za-z0-9_ \u4e00-\u9fa5\-\.%\:#\/]/g, '').trim();
const numClean = (s) => { const x = parseInt(s, 10); return Number.isFinite(x) ? x : null; };
const mid = clean(body.machine_id);
const lid = clean(body.lot_id).toUpperCase();
return {
  json: {
    machine_id: mid,
    machine_id_like: mid ? (mid + '%') : '',
    lot_id: lid,
    lot_id_like: lid ? (lid + '%') : '',
  }
};
"""

PARSE_ALARM = r"""
const body = $input.first().json.body || $input.first().json;
const clean = (s) => String(s == null ? '' : s).replace(/[^A-Za-z0-9_ \u4e00-\u9fa5\-\.%\:#\/]/g, '').trim();
const numClean = (s) => { const x = parseInt(s, 10); return Number.isFinite(x) && x > 0 ? x : 7; };
return {
  json: {
    machine_id: clean(body.machine_id),
    machine_id_like: clean(body.machine_id) ? (clean(body.machine_id) + '%') : '',
    severity: clean(body.severity).toLowerCase(),
    days: numClean(body.days),
  }
};
"""

PARSE_TIMELINE = r"""
const body = $input.first().json.body || $input.first().json;
const clean = (s) => String(s == null ? '' : s).replace(/[^A-Za-z0-9_ \u4e00-\u9fa5\-\.%\:#\/]/g, '').trim();
const mid = clean(body.machine_id);
return {
  json: {
    machine_id: mid,
    machine_id_like: mid ? (mid + '%') : '',
    time_range: clean(body.time_range) || 'today',
  }
};
"""

PARSE_YIELD = PARSE_TIMELINE

PARSE_MES_LOT = r"""
const body = $input.first().json.body || $input.first().json;
const clean = (s) => String(s == null ? '' : s).replace(/[^A-Za-z0-9_ \u4e00-\u9fa5\-\.%\:#\/]/g, '').trim();
return {
  json: {
    lot_id: clean(body.lot_id).toUpperCase(),
    lot_id_like: clean(body.lot_id) ? (clean(body.lot_id).toUpperCase() + '%') : '',
  }
};
"""

PARSE_FAULT = r"""
const body = $input.first().json.body || $input.first().json;
const clean = (s) => String(s == null ? '' : s).replace(/[^A-Za-z0-9_ \u4e00-\u9fa5\-\.%\:#\/]/g, '').trim();
const numClean = (s) => {
  const x = clean(s).toLowerCase();
  if (['high','medium','low'].includes(x)) return x;
  return 'medium';
};
return {
  json: {
    machine_id: clean(body.machine_id),
    fault_type: clean(body.fault_type) || '未说明故障现象',
    severity: numClean(body.severity || 'medium'),
    days: parseInt(body.days, 10) || 7,
  }
};
"""

# ============ 格式化 JS（7 字段）============
FMT_MACHINE_STATUS = r"""
const rows = Array.isArray($input.first().json) ? $input.first().json : [$input.first().json];
const m = rows && rows[0];
if (!m || !m.id) {
  return { json: { ok: false, answer: '未找到该机器（请确认机台ID正确）', table_data: null, jump_timestamp: null, jump_machine_id: null, sources: [{ type: 'n8n', workflow: 'get_machine_status', execution_id: $execution.id }] } };
}
const headers = ['机台ID','型号','状态','当前Lot','最近事件时间'];
const vals = [[String(m.id||''), String(m.model||''), String(m.status||''), String(m.current_lot_id||''), String(m.last_event_ts||'')]];
let answer = `机台 ${m.id}：状态 ${m.status || '未知'}；型号 ${m.model || '未知'}；当前Lot ${m.current_lot_id || '无'}`;
if (m.last_event_ts) answer += `；最近事件 ${m.last_event_ts}`;
return { json: { ok: true, answer, table_data: { headers, rows: vals }, jump_timestamp: m.last_event_ts ? String(m.last_event_ts) : null, jump_machine_id: String(m.id), sources: [{ type: 'n8n', workflow: 'get_machine_status', execution_id: $execution.id }] } };
"""

FMT_LOT_INFO = r"""
const rows = Array.isArray($input.first().json) ? $input.first().json : [$input.first().json];
const rs = rows.filter(r => r && r.lot_id);
if (!rs.length) {
  return { json: { ok: false, answer: '没有查询到相关 Lot 记录（请确认 Lot ID/机台正确）', table_data: null, jump_timestamp: null, jump_machine_id: null, sources: [{ type: 'n8n', workflow: 'get_lot_info', execution_id: $execution.id }] } };
}
const headers = ['Lot ID','关联机台','Chamber','工艺步骤','开始时间'];
const vals = rs.slice(0, 100).map(r => [String(r.lot_id||''), String(r.machine_id||''), String(r.chamber||''), String(r.step||''), String(r.start_ts||'')]);
const latest = rs[0];
let answer = `共 ${rs.length} 条 Lot 记录。最新 ${latest.lot_id}：机台 ${latest.machine_id||''}，步骤 ${latest.step||''}`;
if (latest.start_ts) answer += `，开始时间 ${latest.start_ts}`;
return { json: { ok: true, answer, table_data: { headers, rows: vals }, jump_timestamp: (latest && latest.start_ts) ? String(latest.start_ts) : null, jump_machine_id: latest && latest.machine_id ? String(latest.machine_id) : null, sources: [{ type: 'n8n', workflow: 'get_lot_info', execution_id: $execution.id }] } };
"""

FMT_ALARMS = r"""
const rows = Array.isArray($input.first().json) ? $input.first().json : [$input.first().json];
const rs = rows.filter(r => r && r.id);
const total = rs.length;
const critical = rs.filter(r => String(r.severity||'').toLowerCase().includes('crit')).length;
const warning  = rs.filter(r => String(r.severity||'').toLowerCase().includes('warn')).length;
const info     = total - critical - warning;
let answer = `合计 ${total} 条报警：严重 ${critical} 条、警告 ${warning} 条、提示 ${info} 条。`;
if (critical > 0) answer += ' 严重报警请优先现场排查。';
const headers = ['报警ID','机台ID','严重等级','描述','时间'];
const vals = rs.slice(0, 80).map(r => [String(r.id||''), String(r.machine_id||''), String(r.severity||''), String(r.description||''), String(r.ts||'')]);
const latest = rs[0];
return { json: { ok: true, answer, table_data: total>0 ? { headers, rows: vals } : null, jump_timestamp: latest ? String(latest.ts) : null, jump_machine_id: latest && latest.machine_id ? String(latest.machine_id) : null, sources: [{ type: 'n8n', workflow: 'get_machine_alarms', execution_id: $execution.id }] } };
"""

FMT_TIMELINE = r"""
const rows = Array.isArray($input.first().json) ? $input.first().json : [$input.first().json];
const rs = rows.filter(r => r && r.id);
const groups = {};
rs.forEach(r => { const t = String(r.event_type||'OTHER'); groups[t] = (groups[t]||0)+1; });
const groupText = Object.keys(groups).map(k => `${k}×${groups[k]}`).join(' / ');
let answer = `近两小时事件分布：${groupText || '无事件'}。共 ${rs.length} 条。`;
const headers = ['事件ID','机台ID','事件类型','模式','时间'];
const vals = rs.slice(0, 120).map(r => [String(r.id||''), String(r.machine_id||''), String(r.event_type||''), String(r.mode||''), String(r.ts||'')]);
const latest = rs[0];
return { json: { ok: true, answer, table_data: rs.length>0 ? { headers, rows: vals } : null, jump_timestamp: latest ? String(latest.ts) : null, jump_machine_id: latest && latest.machine_id ? String(latest.machine_id) : null, sources: [{ type: 'n8n', workflow: 'get_event_timeline', execution_id: $execution.id }] } };
"""

FMT_YIELD = r"""
const rows = Array.isArray($input.first().json) ? $input.first().json : [$input.first().json];
const rs = rows.filter(r => r && r.lot_count != null);
const totalLots = rs.reduce((s,r)=>s+(parseInt(r.lot_count,10)||0),0);
const totalWafers = rs.reduce((s,r)=>s+(parseInt(r.wafer_count,10)||0),0);
let answer = `今日加工 ${totalLots} 个 Lot 批次，${totalWafers} 片晶圆。`;
if (rs.length && rs[0].plan_lots) {
  const plan = parseInt(rs[0].plan_lots,10)||0;
  const rate = plan > 0 ? Math.round(totalLots/plan*100) : 0;
  answer += `；计划 ${plan} Lot，完成率 ${rate}%。`;
}
const headers = ['日期','机台ID','Lot数量','晶圆数量','计划Lot','完成率'];
const vals = rs.slice(0, 60).map(r => {
  const plan = parseInt(r.plan_lots,10)||0;
  const lotc = parseInt(r.lot_count,10)||0;
  const rate = plan>0 ? Math.round(lotc/plan*100) : '';
  return [String(r.dt||''), String(r.machine_id||''), String(r.lot_count||0), String(r.wafer_count||0), String(r.plan_lots||''), String(rate)+(rate? '%':'')];
});
const latest = rs[0];
return { json: { ok: true, answer, table_data: totalLots>0 ? { headers, rows: vals } : null, jump_timestamp: (latest && latest.last_lot_ts) ? String(latest.last_lot_ts) : null, jump_machine_id: (latest && latest.machine_id) ? String(latest.machine_id) : null, sources: [{ type: 'n8n', workflow: 'get_yield_stats', execution_id: $execution.id }] } };
"""

FMT_RECIPE = r"""
const rows = Array.isArray($input.first().json) ? $input.first().json : [$input.first().json];
const rs = rows.filter(r => r && r.recipe_id);
if (!rs.length) {
  return { json: { ok: false, answer: '没有该机器的配方记录（请确认机台是否绑定配方）', table_data: null, jump_timestamp: null, jump_machine_id: null, sources: [{ type: 'n8n', workflow: 'get_recipe_info', execution_id: $execution.id }] } };
}
const latest = rs[0];
let answer = `当前 Recipe：${latest.recipe_id||''}（版本 ${latest.recipe_ver||'未知'}，更新 ${latest.updated_at||'未知'}）。`;
const kvs = [];
['rf_power','pressure','gas_flow_cf4','gas_flow_sf6','etch_time','temperature'].forEach(k => { if (latest[k] != null) kvs.push(`${k}=${latest[k]}`); });
if (kvs.length) answer += ' 关键参数：' + kvs.join('、');
const headers = ['Recipe ID','版本','更新时间','RF Power(W)','Pressure(mTorr)','Gas CF4(sccm)','Etch Time(s)'];
const vals = rs.slice(0, 10).map(r => [String(r.recipe_id||''), String(r.recipe_ver||''), String(r.updated_at||''), String(r.rf_power||''), String(r.pressure||''), String(r.gas_flow_cf4||''), String(r.etch_time||'')]);
return { json: { ok: true, answer, table_data: { headers, rows: vals }, jump_timestamp: latest.updated_at ? String(latest.updated_at) : null, jump_machine_id: latest.machine_id ? String(latest.machine_id) : null, sources: [{ type: 'n8n', workflow: 'get_recipe_info', execution_id: $execution.id }] } };
"""

FMT_MES_LOT = r"""
const rows = Array.isArray($input.first().json) ? $input.first().json : [$input.first().json];
const m = rows[0];
if (!m || !m.lot_id) {
  return { json: { ok: false, answer: 'MES 中未找到该 Lot（请确认 Lot ID 正确）', table_data: null, jump_timestamp: null, jump_machine_id: null, sources: [{ type: 'n8n', workflow: 'get_mes_lot_info', execution_id: $execution.id }] } };
}
let answer = `【MES 数据】Lot ${m.lot_id}：产品 ${m.product_id||'未知'}，路线 ${m.route_id||'未知'}，良率 ${m.yield_rate_pct||'未知'}（${m.good_qty||0}/${m.input_qty||0}），工序站 ${m.step_no||'未知'} / ${m.total_steps||'?'}，操作员 ${m.operator_name||'未知'}，预计完工 ${m.planned_finish_ts||'未知'}`;
const headers = ['Lot ID','产品ID','工艺路线','良率(%)','合格/投入','当前工序/总步骤','操作员','预计完工'];
const vals = [[String(m.lot_id), String(m.product_id||''), String(m.route_id||''), String(m.yield_rate_pct||''), `${m.good_qty||0}/${m.input_qty||0}`, `${m.step_no||''}/${m.total_steps||''}`, String(m.operator_name||''), String(m.planned_finish_ts||'')]];
return { json: { ok: true, answer, table_data: { headers, rows: vals }, jump_timestamp: null, jump_machine_id: String(m.machine_id||''), sources: [{ type: 'n8n', workflow: 'get_mes_lot_info', execution_id: $execution.id }] } };
"""

FMT_EXPORT_ALARM = r"""
const rows = Array.isArray($input.first().json) ? $input.first().json : [$input.first().json];
const first = rows[0] || {};
if (first.ok === false) {
  return { json: { ok: false, answer: first.error || '报表生成失败（请检查报表服务器）', table_data: null, jump_timestamp: null, jump_machine_id: null, sources: [{ type: 'n8n', workflow: 'export_alarm_report', execution_id: $execution.id }] } };
}
const dl = String(first.download_url || '');
const size = first.size_kb ? `${first.size_kb}KB` : '';
const rowCount = first.row_count != null ? `（共 ${first.row_count} 行）` : '';
let answer = `🤖 [n8n 自动化] 最近 ${first.days||7} 天 ${first.machine_label||'全产线'} 报警报表已生成。`;
if (dl) answer += ` 下载链接：${dl}`;
if (size || rowCount) answer += `（${size}${rowCount}）`;
answer += ` 执行 ID：${$execution.id}`;
return { json: { ok: true, answer, table_data: null, jump_timestamp: null, jump_machine_id: null, sources: [{ type: 'n8n', workflow: 'export_alarm_report', execution_id: $execution.id, download_url: dl, size_kb: first.size_kb, row_count: first.row_count }] } };
"""

FMT_GEN_WO = r"""
const rows = Array.isArray($input.first().json) ? $input.first().json : [$input.first().json];
const first = rows[0] || {};
if (first.ok === false) {
  return { json: { ok: false, answer: first.error || '创建工单失败（请检查工单系统/权限）', table_data: null, jump_timestamp: null, jump_machine_id: null, sources: [{ type: 'n8n', workflow: 'generate_work_order', execution_id: $execution.id }] } };
}
const wo_id = first.wo_id || '';
const link = first.wo_link || '';
let answer = `🤖 [n8n 自动化] 故障工单 ${wo_id ? ('WO-' + wo_id) : ''} 已创建`;
if (first.owner) answer += `，指派给 ${first.owner} 组`;
if (link) answer += `；工单链接：${link}`;
answer += `（执行 ID：${$execution.id}）`;
return { json: { ok: true, answer, table_data: null, jump_timestamp: null, jump_machine_id: first.machine_id ? String(first.machine_id) : null, sources: [{ type: 'n8n', workflow: 'generate_work_order', execution_id: $execution.id, wo_id, wo_link: link, owner: first.owner }] } };
"""

FMT_CAPABILITIES = r"""
const answer = '我作为 FabTwin Pro AI 助手，可以帮您查询与处理以下 10 类事项：\n① 机台实时状态（运行模式/当前加工 Lot/全厂概览）\n② Lot 批次位置/进度追踪（单 Lot 或机台 Lot 列表）\n③ 报警统计与异常定位（按严重等级/时间范围）\n④ 温度趋势与事件时间线（事件分布/回放线索）\n⑤ 产量与完成率统计（Lot/晶圆/计划对比）\n⑥ 工艺配方查询（Recipe ID/版本/关键参数）\n⑦ MES Lot 详情【管理员】（良率/路线/工序站）\n⑧ 导出报警报表 Excel【管理员】\n⑨ 生成故障工单【管理员】\n⑩ 功能清单（就是本回复）。\n请告诉我您想查哪一类，并附上机台 ID（如 OXE-1）或 Lot ID，我就能精确查询。';
return { json: { ok: true, answer, table_data: null, jump_timestamp: null, jump_machine_id: null, sources: [{ type: 'n8n', workflow: 'list_capabilities', execution_id: $execution.id }] } };
"""

# ============ 10 个 workflow 定义 ============
DEFINITIONS = [
    # F1
    {
        "file": "F1_get_machine_status",
        "title": "F1. 查询机台状态（FabTwin 工具 get_machine_status）",
        "path": "get_machine_status",
        "parse_js": PARSE_MID,
        "sql": r"""
SELECT id, model, status, current_lot_id, last_event_ts
FROM (
  SELECT id, model, status, current_lot_id, last_event_ts
  FROM machines
  WHERE id = '{{ $json.machine_id }}' AND LENGTH('{{ $json.machine_id }}') > 0
  UNION ALL
  SELECT id, model, status, current_lot_id, last_event_ts
  FROM machines
  WHERE LENGTH('{{ $json.machine_id }}') = 0
  ORDER BY status DESC, id
) WHERE ROWNUM <= 1
""".strip(),
        "fmt_js": FMT_MACHINE_STATUS,
    },
    # F2
    {
        "file": "F2_get_lot_info",
        "title": "F2. 查询 Lot 信息（FabTwin 工具 get_lot_info）",
        "path": "get_lot_info",
        "parse_js": PARSE_MID_LOT,
        "sql": r"""
SELECT lot_id, machine_id, chamber, step, start_ts
FROM (
  SELECT d.lot_id, d.machine_id, d.chamber, d.step, d.start_ts
  FROM dt_lots d
  WHERE (LENGTH('{{ $json.lot_id }}')>0 AND d.lot_id LIKE '{{ $json.lot_id_like }}')
     OR (LENGTH('{{ $json.lot_id }}')=0 AND LENGTH('{{ $json.machine_id }}')>0 AND d.machine_id LIKE '{{ $json.machine_id_like }}')
  ORDER BY d.start_ts DESC
) WHERE ROWNUM <= 100
""".strip(),
        "fmt_js": FMT_LOT_INFO,
    },
    # F3
    {
        "file": "F3_get_machine_alarms",
        "title": "F3. 报警统计（FabTwin 工具 get_machine_alarms）",
        "path": "get_machine_alarms",
        "parse_js": PARSE_ALARM,
        "sql": r"""
SELECT id, machine_id, severity, description, ts
FROM (
  SELECT a.id, a.machine_id, a.severity, a.description, a.ts
  FROM dt_alarms a
  WHERE a.ts >= TRUNC(SYSDATE) - ({{ $json.days }} - 0)
    AND (LENGTH('{{ $json.machine_id }}')=0 OR a.machine_id LIKE '{{ $json.machine_id_like }}')
    AND (LENGTH('{{ $json.severity }}')=0 OR LOWER(a.severity) LIKE '%{{ $json.severity }}%')
  ORDER BY a.ts DESC
) WHERE ROWNUM <= 200
""".strip(),
        "fmt_js": FMT_ALARMS,
    },
    # F4
    {
        "file": "F4_get_event_timeline",
        "title": "F4. 事件时间线（FabTwin 工具 get_event_timeline）",
        "path": "get_event_timeline",
        "parse_js": PARSE_TIMELINE,
        "sql": r"""
SELECT id, machine_id, event_type, mode, ts
FROM (
  SELECT e.id, e.machine_id, e.event_type, e.mode, e.ts
  FROM dt_event_raw e
  WHERE (
    CASE
      WHEN '{{ $json.time_range }}' = 'last_2h'  THEN 1
      ELSE 0
    END = 1 AND e.ts >= SYSDATE - 2/24
  )
  OR (
    CASE WHEN '{{ $json.time_range }}' IN ('today','') THEN 1 ELSE 0 END = 1
    AND e.ts >= TRUNC(SYSDATE)
  )
  AND (LENGTH('{{ $json.machine_id }}')>0 AND e.machine_id = '{{ $json.machine_id }}')
  ORDER BY e.ts DESC
) WHERE ROWNUM <= 300
""".strip(),
        "fmt_js": FMT_TIMELINE,
    },
    # F5
    {
        "file": "F5_get_yield_stats",
        "title": "F5. 产量统计（FabTwin 工具 get_yield_stats）",
        "path": "get_yield_stats",
        "parse_js": PARSE_YIELD,
        "sql": r"""
SELECT TRUNC(ts) AS dt, machine_id, COUNT(DISTINCT lot_id) AS lot_count,
       COUNT(DISTINCT wafer_id) AS wafer_count,
       0 AS plan_lots, MAX(ts) AS last_lot_ts
FROM dt_event_raw e
WHERE e.ts >= TRUNC(SYSDATE)
  AND e.machine_id = '{{ $json.machine_id }}'
  AND e.event_type IN ('UNLOAD','WAFERLOADED')
GROUP BY TRUNC(ts), machine_id
ORDER BY dt DESC
""".strip(),
        "fmt_js": FMT_YIELD,
    },
    # F6
    {
        "file": "F6_get_recipe_info",
        "title": "F6. 工艺配方查询（FabTwin 工具 get_recipe_info）",
        "path": "get_recipe_info",
        "parse_js": PARSE_MID,
        "sql": r"""
SELECT r.id AS recipe_id, r.version AS recipe_ver, r.updated_at, r.machine_id,
       r.rf_power, r.pressure, r.gas_flow_cf4, r.gas_flow_sf6, r.etch_time, r.temperature
FROM machine_recipes r
WHERE r.machine_id = '{{ $json.machine_id }}'
ORDER BY r.updated_at DESC
FETCH FIRST 10 ROWS ONLY
""".strip(),
        "fmt_js": FMT_RECIPE,
    },
    # F7 （MES 外部调用，这里写 placeholder；实际用户若 MES 走 MCP/n8n，需用户改该节点）
    {
        "file": "F7_get_mes_lot_info",
        "title": "F7. MES Lot 信息（FabTwin 工具 get_mes_lot_info）",
        "path": "get_mes_lot_info",
        "parse_js": PARSE_MES_LOT,
        "sql": None,  # 不用 Oracle，下面用 Code 节点直接占位返回
        "fmt_js": FMT_MES_LOT,
        "custom_nodes": [
            # Replace Oracle 节点 → 占位 Code：实际上线需接 MES DB/MCP
            ("Query Oracle",
             _node("n8n-nodes-base.code", "MES 占位（请替换为您真实 MES DB/MCP 节点）",
                   {"jsCode": r"""
const body = $input.first().json;
return { json: {
  lot_id: body.lot_id || '',
  product_id: 'PCHIP-V2（示例，需替换真实 MES 查询）',
  route_id: 'ROUTE-A07',
  yield_rate_pct: '98.3',
  good_qty: 59, input_qty: 60,
  step_no: 12, total_steps: 25,
  operator_name: '张三',
  planned_finish_ts: '2026-09-04 16:30:00',
  machine_id: ''
} };
""", "options": {}}, 2, (680, 300))),
        ],
    },
    # F8
    {
        "file": "F8_export_alarm_report",
        "title": "F8. 导出报警报表（FabTwin 工具 export_alarm_report）",
        "path": "export_alarm_report",
        "parse_js": PARSE_ALARM,
        "sql": None,
        "fmt_js": FMT_EXPORT_ALARM,
        "custom_nodes": [
            ("Query Oracle",
             _node("n8n-nodes-base.code", "报表生成（请替换真实报表节点）",
                   {"jsCode": r"""
const b = $input.first().json;
const mid = b.machine_id;
const days = b.days || 7;
return { json: {
  ok: true,
  days,
  machine_label: mid ? mid : '全产线',
  download_url: 'http://report-server.example.com/reports/alarm_' + (mid||'all') + '_' + days + 'd.xlsx',
  size_kb: 236,
  row_count: 58
} };
""", "options": {}}, 2, (680, 300))),
        ],
    },
    # F9
    {
        "file": "F9_generate_work_order",
        "title": "F9. 生成故障工单（FabTwin 工具 generate_work_order）",
        "path": "generate_work_order",
        "parse_js": PARSE_FAULT,
        "sql": None,
        "fmt_js": FMT_GEN_WO,
        "custom_nodes": [
            ("Query Oracle",
             _node("n8n-nodes-base.code", "工单系统（请替换真实工单接口/RCM）",
                   {"jsCode": r"""
const b = $input.first().json;
const ts = Date.now().toString().slice(-6);
return { json: {
  ok: true,
  machine_id: b.machine_id || '',
  wo_id: '20260904-' + ts,
  wo_link: 'http://rcm.example.com/wo/WO-20260904-' + ts,
  owner: '维护组',
} };
""", "options": {}}, 2, (680, 300))),
        ],
    },
    # F10
    {
        "file": "F10_list_capabilities",
        "title": "F10. 功能清单（FabTwin 工具 list_capabilities）",
        "path": "list_capabilities",
        "parse_js": PARSE_MID,  # 占位即可
        "sql": None,
        "fmt_js": FMT_CAPABILITIES,
        "custom_nodes": [
            ("Query Oracle",
             _node("n8n-nodes-base.code", "功能清单（无 DB 操作，直通 Format）",
                   {"jsCode": "return { json: {} };"},
                   2, (680, 300))),
        ],
    },
]


def make_workflow(defn):
    n1 = webhook_node(defn["path"])
    n2 = parse_node(defn["parse_js"])
    # n3：Oracle or 占位
    if defn.get("custom_nodes"):
        (label, n3) = defn["custom_nodes"][0]
    else:
        if not defn["sql"]:
            raise ValueError(f"缺少 SQL: {defn['file']}")
        n3 = oracle_node(defn["sql"])
    n4 = format_node(defn["fmt_js"])
    n5 = respond_node()
    nodes = [n1, n2, n3, n4, n5]
    conns = connections([
        ("Webhook", "Parse"),
        ("Parse", n3["name"]),
        (n3["name"], "Format"),
        ("Format", "Respond"),
    ])
    return nodes, conns


def main():
    for d in DEFINITIONS:
        nodes, conns = make_workflow(d)
        save(d["file"], d["title"], nodes, conns)
    print(f"[DONE] 生成 {len(DEFINITIONS)} 个 n8n workflow 模板到 {OUT_DIR}")


if __name__ == "__main__":
    main()
