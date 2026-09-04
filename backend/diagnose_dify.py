# -*- coding: utf-8 -*-
"""
FabTwin + Dify 诊断脚本 v1.0
================================================================
运行位置：和 main.py 一样，放在 fab-twin-pro/backend/ 目录下

运行：
    cd backend
    python diagnose_dify.py

然后把所有输出复制给我（不用打码，脚本里不会打印完整 API Key，只打前后 4 位）。
"""
import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# 加载 .env（如果有）
if os.path.exists(os.path.join(HERE, ".env")):
    print("[INFO] 检测到后端 .env，加载环境变量...")
    try:
        with open(os.path.join(HERE, ".env"), "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k not in os.environ:
                    os.environ[k] = v
    except Exception as e:
        print(f"[WARN] 加载 .env 失败: {e}")


print("=" * 80)
print("  Step 1/5: 从 DB (ai_configs 表) 读取当前Dify配置")
print("=" * 80)

try:
    from database import SessionLocal
    from models import AIConfig
    db = SessionLocal()
    rows = db.query(AIConfig).order_by(AIConfig.config_key).all()
    db.close()
except Exception as e:
    print(f"[ERROR] 无法连接 DB 读 ai_configs: {e}")
    print("  提示: Oracle DB 地址不通或 Oracle Client 未初始化，将只使用 .env 默认值")
    rows = []

KEYS = ["dify_enabled", "dify_base_url", "dify_api_key", "dify_app_id",
        "n8n_enabled", "n8n_base_url", "n8n_secret"]

cfg = {}
for r in rows:
    if r.config_key in KEYS:
        cfg[r.config_key] = r.config_value or ""
    print(f"  {r.config_key:20s} = {r.config_value!r}")

if not cfg:
    # DB 没数据 → 用 .env / 默认
    cfg["dify_enabled"] = os.getenv("DIFY_ENABLED", "True")
    cfg["dify_base_url"] = os.getenv("DIFY_BASE_URL", "")
    cfg["dify_api_key"] = os.getenv("DIFY_API_KEY", "")
    cfg["dify_app_id"] = os.getenv("DIFY_APP_ID", "")
    cfg["n8n_enabled"] = os.getenv("N8N_ENABLED", "False")
    cfg["n8n_base_url"] = os.getenv("N8N_BASE_URL", "")
    cfg["n8n_secret"] = os.getenv("N8N_SECRET", "")
    print("[INFO] DB 无记录，使用 .env / 默认值:")
    for k in KEYS:
        print(f"  {k:20s} = {cfg.get(k, '')!r}")


def mask(s, keep=4):
    if not s:
        return "(空)"
    if len(s) <= keep * 2:
        return "*" * len(s)
    return s[:keep] + "*" * (len(s) - keep * 2) + s[-keep:]


print()
print("=" * 80)
print("  Step 2/5: 配置自检")
print("=" * 80)

base = cfg.get("dify_base_url") or ""
key = cfg.get("dify_api_key") or ""
errors = []
warnings = []

# 2.1 base_url 是否看起来像 n8n
if ":5678" in base or "n8n" in base.lower() or "10.30.116.151" in base:
    errors.append(f"❌ DIFY_BASE_URL={base!r} 看起来是 n8n 地址（端口5678/含n8n/IP=10.30.116.151都是n8n，不是Dify）")
if not base:
    errors.append("❌ DIFY_BASE_URL 为空")
elif not base.startswith("http"):
    errors.append(f"❌ DIFY_BASE_URL={base!r} 缺少 http:// 或 https://")
if not key:
    errors.append("❌ DIFY_API_KEY 为空")
elif not key.startswith("app-"):
    warnings.append(f"⚠  DIFY_API_KEY={mask(key)} 不以 'app-' 开头（Dify的API Key 通常以 app- 开头）")
if str(cfg.get("dify_enabled", "True")).lower() not in ("1", "true", "yes", "on"):
    errors.append(f"❌ dify_enabled={cfg.get('dify_enabled')!r} = 未启用")

for e in errors:
    print(e)
for w in warnings:
    print(w)
if not errors and not warnings:
    print("✅ 配置字段看起来没问题。")


print()
print("=" * 80)
print("  Step 3/5: 直接调 Dify API — 模拟后端代码的两轮请求")
print("  这一步会用后端 ai_middleware.py 的逻辑来调，直接复现你网站端的报错。")
print("=" * 80)

import httpx
from urllib.parse import urlparse

base_clean = base.rstrip("/")
if base_clean.endswith("/v1"):
    base_clean = base_clean[:-3]
chat_url = base_clean + "/v1/chat-messages"
headers = {
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json",
}


def run_round(test_name, payload_json, session_label):
    print()
    print(f"---- {test_name} ({session_label}) ----")
    print(f"POST {chat_url}")
    if "conversation_id" in payload_json:
        print(f"  conversation_id = {payload_json['conversation_id']!r}")
    else:
        print(f"  conversation_id = (未传)")
    print(f"  query = {payload_json['query']!r}")
    try:
        r = httpx.post(chat_url, json=payload_json, headers=headers, timeout=30)
    except Exception as e:
        print(f"  [EXCEPTION] httpx 抛错: {type(e).__name__}: {e}")
        return None, str(e)
    print(f"  HTTP {r.status_code}")
    try:
        data = r.json()
    except Exception:
        print(f"  响应不是JSON: {r.text[:500]}")
        return None, r.text[:500]
    if r.status_code != 200:
        detail = data.get("message") or data.get("detail") or json.dumps(data, ensure_ascii=False)
        print(f"  [ERROR] Dify 返回错误: {detail[:600]}")
        return None, detail
    answer = (data.get("answer") or "")[:200]
    cid = data.get("conversation_id")
    print(f"  [OK] 回答(前200字): {answer}")
    print(f"  [OK] Dify 返回的 conversation_id = {cid}")
    return data, None


test_session_id = "sess_diag_" + os.urandom(8).hex()
print(f"本次诊断使用的前端会话ID(会传给后端作为session_id) = {test_session_id}")

# ---- 第 1 轮 ----
payload1 = {
    "inputs": {"machine_id": "", "user_role": "user"},
    "query": "你能帮我干什么",
    "response_mode": "blocking",
    "user": "fabtwin_user",
}
# 注意: 第一轮故意不传 conversation_id (正确做法)
res1, err1 = run_round("Round 1 (正确做法：不传 conversation_id)", payload1, test_session_id)

# ---- 第 2 轮 ----
dify_cid_from_1 = res1.get("conversation_id") if res1 else None
payload2 = {
    "inputs": {"machine_id": "", "user_role": "user"},
    "query": "详细说说机台状态怎么查",
    "response_mode": "blocking",
    "user": "fabtwin_user",
    "conversation_id": dify_cid_from_1 or "PLACEHOLDER_DIFY_NOT_RETURNED",
}
_ = run_round("Round 2 (用Dify返回的UUID)", payload2, test_session_id)

# ---- 第 3 轮 ----
# 这是你网站端现在出错的情况(老代码的做法)：把前端sess_xxx直接当成 conversation_id 传
payload3 = {
    "inputs": {"machine_id": "", "user_role": "user"},
    "query": "复现网站端的报错",
    "response_mode": "blocking",
    "user": "fabtwin_user",
    "conversation_id": test_session_id,  # 传 sess_xxx 这种非UUID
}
_ = run_round("Round 3 (复现报错：传前端 sess_xxx)", payload3, test_session_id)


print()
print("=" * 80)
print("  Step 4/5: 诊断结论")
print("=" * 80)

# 读当前 ai_middleware.py 是否带修复（用文件判断关键字更稳）
try:
    am_path = os.path.join(HERE, "services", "ai_middleware.py")
    am_txt = open(am_path, encoding="utf-8").read()
    has_conv_fix = "_dify_conv_map" in am_txt
    has_n8n_warn = "看起来是 n8n 地址" in am_txt
except Exception:
    has_conv_fix = has_n8n_warn = None

if has_conv_fix is True:
    print("✅ 后端 ai_middleware.py 已包含 conversation_id 修复（_dify_conv_map）")
else:
    print("❌ 后端 ai_middleware.py 还没拉到 conversation_id 修复代码！网站端会一直报错 sess_xxx 非UUID！"
          "\n   解法: 把 fab-twin-pro 整个目录替换成 test1 分支最新版 (git pull origin test1) 然后重启后端服务。")
if has_n8n_warn is True:
    print("✅ 后端 ai_middleware.py 已包含 n8n 地址错用的自动告警")
elif has_n8n_warn is False:
    print("⚠  后端 ai_middleware.py 未带 n8n 地址错用告警（功能非必须，但建议拉最新代码）")

if err1 and ("401" in str(err1) or "Unauthorized" in str(err1)):
    print("❌ Dify API Key 错误（401 Unauthorized）")
    print("   → 去 Dify 应用 → 发布 → 访问 API → 重新复制 API Secret，粘到AI配置页面的Dify API Key框里")
if err1 and "connection" in str(err1).lower():
    print("❌ 根本连不上 Dify 服务器（连接拒绝/超时/找不到主机）")
    print(f"   → 你填的地址是 {base!r}，在 fabtwin 后端机器上打开浏览器访问这个地址，看能不能打开 Dify 网页")

if res1 and dify_cid_from_1 and (not errors):
    print()
    print("🎉 直接调 Dify API 全通过了！你网站端的 conversation_id 报错根源只有 2 种可能:")
    print()
    print("  可能 A（概率90%）：你的后端服务还没重启 —— 即使我本地代码修了，只要后端进程没重启，仍然跑旧代码。")
    print("    确认方法: 看后端控制台有没有出现下面这两行日志:")
    print("      '会话映射已保存: sess_xxx → 550e8400-...-UUID'")
    print("      '_dify_conv_map' 字样（搜索后端启动日志）")
    print("    没看到就代表：后端进程还在跑旧版代码。")
    print()
    print("  可能 B（概率10%）：后端代码不是最新版（_dify_conv_map 不存在）。")
    print("    确认方法: 执行 Step 4/5 里写的 '❌ 后端 ai_middleware.py 还没拉到修复' 那一条。")


print()
print("=" * 80)
print("  Step 5/5: FabTwin 后端接口调用（可选）")
print("=" * 80)
print("""

如果你想进一步模拟网页端真实请求（通过 FabTwin 后端转发而非直接调 Dify），
在 FabTwin 后端正常运行的情况下，另外新开一个 PowerShell 运行：

  python -c "
import httpx, json
r = httpx.post('http://127.0.0.1:8002/api/ai/chat', json={
    'question': '你能帮我干什么',
    'machine_id': '',
    'session_id': 'sess_diag_END2END'
}, timeout=30)
print('HTTP', r.status_code)
print(r.text[:1500])
"

把输出也一起发给我，我就能直接看到后端在"实际返回给前端"时到底传了什么 conversation_id、以及 ai_middleware.py 的修复代码有没有真正生效。
""")
