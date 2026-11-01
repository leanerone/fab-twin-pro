#!/bin/bash
# n8n 自动初始化：等端口 → 初始化 owner → 登录 → 建两个真实工作流 → 激活 → 验证 webhook
# 用法: bash n8n_setup.sh <FABTWIN_BEARER_TOKEN>
set -e
TOKEN="$1"
BASE="http://localhost:5678"
CJ=$(mktemp)

echo "== 1. 等待 n8n 端口 =="
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 3 "$BASE/healthz" || true)
  [ "$code" = "200" ] && { echo "n8n 已就绪"; break; }
  sleep 2
  [ $i -eq 60 ] && { echo "n8n 未就绪"; exit 1; }
done

echo "== 2. Owner 初始化 =="
curl -s -X POST "$BASE/rest/owner/setup" -H "Content-Type: application/json" \
  -d '{"email":"admin@fabtwin.local","password":"FabTwin#2026!N8n","firstName":"FabTwin","lastName":"Admin"}' | head -c 200
echo ""

echo "== 3. 登录 =="
curl -s -c "$CJ" -X POST "$BASE/rest/login" -H "Content-Type: application/json" \
  -d '{"emailOrLdapLoginId":"admin@fabtwin.local","password":"FabTwin#2026!N8n"}' -o /dev/null -w "login HTTP %{http_code}\n"

echo "== 4. 创建工作流 =="
WF_GENERAL=$(cat <<'EOF'
{"name":"FabTwin 通用查询（真实链路验证）","settings":{"executionOrder":"v1"},
 "nodes":[
  {"parameters":{"httpMethod":"POST","path":"general_query","responseMode":"responseNode","options":{}},
   "name":"Webhook","type":"n8n-nodes-base.webhook","typeVersion":2,"position":[-200,0],"webhookId":"fabtwin-general-query"},
  {"parameters":{"respondWith":"json","responseBody":"={{ { answer: 'N8N 工作流执行正常。收到问题：' + $json.body.question, workflow: 'general_query', executionId: $execution.id, timestamp: $now.iso() } }}","options":{}},
   "name":"Respond","type":"n8n-nodes-base.respondToWebhook","typeVersion":1.1,"position":[200,0]}
 ],
 "connections":{"Webhook":{"main":[[{"node":"Respond","type":"main","index":0}]]}}}
EOF
)
WF_ALARM=$(cat <<EOF
{"name":"FabTwin 报警报表导出（真实数据链路）","settings":{"executionOrder":"v1"},
 "nodes":[
  {"parameters":{"httpMethod":"POST","path":"export_alarm_report","responseMode":"responseNode","options":{}},
   "name":"Webhook","type":"n8n-nodes-base.webhook","typeVersion":2,"position":[-400,0],"webhookId":"fabtwin-export-alarm"},
  {"parameters":{"url":"=http://localhost:8002/api/alarms?machine_id={{ \$json.body.machine_id || 'OXE-51' }}","sendHeaders":true,"headerParameters":{"parameters":[{"name":"Authorization","value":"Bearer $TOKEN"}]},"options":{}},
   "name":"Query FabTwin","type":"n8n-nodes-base.httpRequest","typeVersion":4.2,"position":[-100,0]},
  {"parameters":{"jsCode":"const resp = \$input.first().json;\\nconst list = Array.isArray(resp) ? resp : (resp.alarms || resp.data || []);\\nreturn [{ json: {\\n  answer: '报警报表导出完成：共 ' + list.length + ' 条告警（来源：FabTwin API 实时查询）',\\n  data: list.slice(0, 10),\\n  executionId: \$execution.id,\\n}}];"},
   "name":"Build Report","type":"n8n-nodes-base.code","typeVersion":2,"position":[200,0]},
  {"parameters":{"respondWith":"firstIncomingItem","options":{}},
   "name":"Respond","type":"n8n-nodes-base.respondToWebhook","typeVersion":1.1,"position":[500,0]}
 ],
 "connections":{"Webhook":{"main":[[{"node":"Query FabTwin","type":"main","index":0}]]},
                "Query FabTwin":{"main":[[{"node":"Build Report","type":"main","index":0}]]},
                "Build Report":{"main":[[{"node":"Respond","type":"main","index":0}]]}}}
EOF
)

for pair in "general_query|$WF_GENERAL" "export_alarm_report|$WF_ALARM"; do
  wf_type="${pair%%|*}"; wf_json="${pair#*|}"
  echo "-- 创建 $wf_type --"
  RESP=$(curl -s -b "$CJ" -X POST "$BASE/rest/workflows" -H "Content-Type: application/json" -d "$wf_json")
  WF_ID=$(echo "$RESP" | python -c "import json,sys; d=json.load(sys.stdin); print(d.get('data',{}).get('id') or d.get('id',''))" 2>/dev/null)
  echo "  id=$WF_ID"
  if [ -n "$WF_ID" ]; then
    curl -s -b "$CJ" -X POST "$BASE/rest/workflows/$WF_ID/activate" -o /dev/null -w "  activate HTTP %{http_code}\n"
  else
    echo "  创建响应: $(echo "$RESP" | head -c 300)"
  fi
done

echo "== 5. 直连 webhook 验证（真实 HTTP）=="
sleep 2
curl -s -m 15 -X POST "$BASE/webhook/general_query" -H "Content-Type: application/json" \
  -d '{"question":"直连测试","machine_id":"OXE-51","workflow_type":"general_query"}' | head -c 300
echo ""
echo "== 完成 =="
