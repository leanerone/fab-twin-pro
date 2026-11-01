#!/bin/bash
# AI 对接真实性端到端测试（n8n 真实链路）
# 前置：n8n 已初始化且工作流已激活（n8n_setup.sh / 重建脚本）；后端 8002 运行中
# 断言链：/api/ai/chat（admin）→ 中文意图识别 → 真实 HTTP → n8n 2.8.4 工作流执行
#        → （报警流）n8n 反查 FabTwin API → Oracle 真数据 → 结构化回传 → AI 答案
# 注意：中文请求体必须走 UTF-8 文件（--data-binary @req_xxx.json），
#       Git Bash 内联中文会被转码导致后端 400（本测试的两个 req_*.json 已预生成）
set -e
cd "$(dirname "$0")"
BASE="http://localhost:8002"
N8N="http://localhost:5678"
PASS=0; FAIL=0
ck() { if [ "$1" = "1" ]; then PASS=$((PASS+1)); echo "[PASS] $2  $3"; else FAIL=$((FAIL+1)); echo "[FAIL] $2  $3"; fi }

echo "== 0. 后端配置 n8n 对接 =="
TOKEN=$(curl -s -m 10 -X POST "$BASE/api/auth/login-password" -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python -c "import json,sys; print(json.load(sys.stdin)['token'])")
[ -n "$TOKEN" ] && ck 1 "登录获取token" || ck 0 "登录获取token"
ST=$(curl -s -m 10 -X PUT "$BASE/api/ai/config" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"n8n_enabled":true,"n8n_base_url":"http://localhost:5678"}' -o /dev/null -w "%{http_code}")
ck "$([ "$ST" = "200" ] && echo 1)" "写入 n8n 配置" "HTTP $ST"

echo "== 1. 直连 n8n webhook（真实服务存活）=="
RESP=$(curl -s -m 15 -X POST "$N8N/webhook/general_query" -H "Content-Type: application/json" \
  -d '{"question":"liveness","machine_id":"OXE-51","workflow_type":"general_query"}')
echo "$RESP" | grep -q "executionId" && ck 1 "n8n general_query 真实执行" || ck 0 "n8n general_query 真实执行" "$(echo "$RESP" | head -c 120)"

echo "== 2. AI 对话触发 n8n（真实链路：AI → 意图识别 → HTTP → n8n 执行）=="
RESP=$(curl -s -m 60 -X POST "$BASE/api/ai/chat" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  --data-binary @req_general.json)
echo "$RESP" | grep -q "N8N" && echo "$RESP" | grep -q "工作流执行正常" && ck 1 "AI 答案带 N8N 执行标记" "$(echo "$RESP" | grep -oP '"executionId":"[^"]*"' | head -1)" || ck 0 "AI 答案带 N8N 执行标记" "$(echo "$RESP" | head -c 160)"

echo "== 3. 真实数据链路（AI → n8n → FabTwin API → Oracle → 表格回传）=="
RESP=$(curl -s -m 60 -X POST "$BASE/api/ai/chat" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  --data-binary @req_alarm.json)
ROWS=$(echo "$RESP" | python -c "
import json,sys
d = json.load(sys.stdin)
td = d.get('table_data') or {}
print(len(td.get('rows', [])))")
echo "$RESP" | grep -q "N8N" && ck 1 "报警报表由 n8n 实时查询生成" "table_data ${ROWS} 行" || ck 0 "报警报表由 n8n 实时查询生成" "$(echo "$RESP" | head -c 160)"
ck "$([ "$ROWS" -gt 0 ] 2>/dev/null && echo 1)" "结构化表格数据回传（非空）" "Oracle 真实告警 ${ROWS} 条经 n8n 回传"

echo "== 4. 用量与来源标记 =="
echo "$RESP" | python -c "
import json,sys
d = json.load(sys.stdin)
src = d.get('sources') or []
ok = any(s.get('type') == 'n8n' and s.get('workflow') == 'export_alarm_report' for s in src)
print('sources-n8n:', 'OK' if ok else 'MISSING')
" | grep -q OK && ck 1 "sources 标记 n8n 来源" || ck 0 "sources 标记 n8n 来源"

echo ""
echo "================================================================"
echo "AI-n8n 对接真实性测试：$PASS 通过 / $FAIL 失败"
[ $FAIL -eq 0 ]
