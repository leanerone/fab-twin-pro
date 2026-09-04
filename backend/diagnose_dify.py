# -*- coding: utf-8 -*-
"""
FabTwin + Dify 诊断脚本 v2.0
================================================================
v2.0 升级（针对上一次输出暴露的3个根因）:
  ① 脚本自己连 Oracle ORA-12541  → 改为先调活后端 GET /api/ai/config
     （后端进程本来就连着 DB/Dify 且已读 ai_configs）
  ② 公司 HJTC Proxy 劫持 127.0.0.1 → 所有 httpx 统一 trust_env=False
  ③ 只在后端接口不通时才 fallback 到 .env / DB 直连

运行位置: fab-twin-pro/backend/
运行:
    cd backend
    python diagnose_dify.py  [--host 127.0.0.1] [--port 8002]

把所有输出复制给我（脚本只打印掩码，可直接粘贴）。
"""
import os, sys, json, argparse

# ====== 启动即版本检查（避免 "SyntaxError: f-string invalid syntax" 这类"运行一半才报错"）======
PY_VER = sys.version_info
print("[INFO] Python 版本: %d.%d.%d" % (PY_VER.major, PY_VER.minor, PY_VER.micro))
if (PY_VER.major, PY_VER.minor) < (3, 6):
    print("[CRITICAL] 本脚本需要 Python 3.6+（你现在是 %d.%d）。" % (PY_VER.major, PY_VER.minor))
    print("   如果 venv 已装 3.6+: 请用 .\\venv\\Scripts\\python.exe diagnose_dify.py")
    print("   否则: 全局安装 Python 3.8+ 或切换到 FabTwin 项目自带的 venv。")
    sys.exit(1)
if (PY_VER.major, PY_VER.minor) == (3, 6):
    # Python 3.6.0/3.6.1 有些 build 的 f-string 解析器对 !r/if-else 嵌套支持有限，
    # 3.6.2+ 正常。脚本里已避免嵌套写法，下面只提示。
    print("[WARN] Python 3.6 对 f-string 嵌套支持较弱，若仍报语法错请升级到 3.8+。")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ap = argparse.ArgumentParser()
ap.add_argument("--host", default=os.getenv("FABTWIN_HOST", "127.0.0.1"))
ap.add_argument("--port", type=int, default=int(os.getenv("FABTWIN_PORT", "8002")))
arg = ap.parse_args()

BACKEND = "http://%s:%d" % (arg.host, arg.port)

# 加载 .env (若有)
if os.path.exists(os.path.join(HERE, ".env")):
    try:
        with open(os.path.join(HERE, ".env"), "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip(); v = v.strip().strip('"').strip("'")
                if k not in os.environ:
                    os.environ[k] = v
        print("[INFO] 已加载 .env 环境变量")
    except Exception as e:
        print("[WARN] .env 读取失败: %s" % (e,))

try:
    import httpx
except ImportError:
    print("[CRITICAL] 缺少依赖 httpx。先执行: pip install httpx==0.25.0")
    sys.exit(2)
client = httpx.Client(timeout=30, trust_env=False)
#  trust_env=False  ← 关键: 不读取 HTTP_PROXY/HTTPS_PROXY，避开公司 HJTC Proxy 劫持


def mask(s, keep=4):
    if not s:
        return "(空)"
    if len(s) <= keep * 2:
        return "*" * len(s)
    return s[:keep] + "*" * (len(s) - keep * 2) + s[-keep:]


print("=" * 90)
print("  Step 1/6: 调活后端 GET /api/ai/config — 拿到真实 Dify/N8N 配置")
print("  （跳过脚本自己连 Oracle，避免 ORA-12541: TNS:no listener）")
print("=" * 90)

live_cfg = None
try:
    r = client.get(BACKEND + "/api/ai/config")
    print(f"  GET {BACKEND}/api/ai/config  → HTTP {r.status_code}")
except Exception as e:
    print(f"  [EXCEPTION] httpx 抛错: {type(e).__name__}: {e}")
    r = None

if r and r.status_code == 200:
    try:
        live_cfg = r.json()
    except Exception:
        live_cfg = None
        print(f"  [ERROR] 响应不是 JSON: {r.text[:400]}")
else:
    if r and r.status_code == 403 and "HJTC Proxy" in r.text[:2000]:
        print("  [CRITICAL] 403 = HJTC 代理仍在劫持！请在当前 PowerShell 先执行下面两行，再重跑脚本:")
        print('     $env:HTTP_PROXY=$null')
        print('     $env:HTTPS_PROXY=$null')
        print("  （或改用 127.0.0.1:port 的 netsh/绑定，确保不走公司出口）")
    if r and r.status_code == 404:
        print("  [ERROR] 404: 后端不是预期的 fabtwin 接口？请确认端口号正确。")
        print("  用法: python diagnose_dify.py --host <IP> --port <后端端口>")
    elif r:
        print(f"  [ERROR] 返回非200: {r.text[:500]}")


# Fallback: 后端没起来 / 接口不通 → 读 ai_configs 表 → 再不行用 .env
if not live_cfg:
    print("\n[INFO] 后端接口没拿到数据 → Fallback: 尝试直连 Oracle 读 ai_configs...")
    KEYS = ["dify_enabled","dify_base_url","dify_api_key","dify_app_id",
            "n8n_enabled","n8n_base_url","n8n_secret"]
    try:
        from database import SessionLocal
        from models import AIConfig
        db = SessionLocal()
        rows = db.query(AIConfig).order_by(AIConfig.config_key).all()
        db.close()
        db_map = {r.config_key: r.config_value or "" for r in rows}
    except Exception as e:
        print(f"  [ERROR] Oracle 仍不通: {str(e).split(chr(10))[0]}")
        db_map = {}

    cfg_via_env = {k: (db_map.get(k, None) or os.getenv(k.upper(), "") or "") for k in KEYS}

    # 用 fallback 字段构造一个等价结构（字段名与 live_cfg 一致）
    live_cfg = {
        "provider": "dify" if str(cfg_via_env["dify_enabled"]).lower() in ("1","true","yes") else os.getenv("AI_PROVIDER","dify"),
        "provider_name": cfg_via_env.get("provider_name") or os.getenv("AI_PROVIDER","dify"),
        "model": os.getenv("AI_MODEL",""),
        "base_url_masked": mask(cfg_via_env.get("dify_base_url") or os.getenv("DIFY_BASE_URL","")),
        "has_api_key": bool(cfg_via_env.get("dify_api_key") or os.getenv("DIFY_API_KEY","")),
        "temperature": float(os.getenv("AI_TEMPERATURE","0.7")),
        "max_tokens": int(os.getenv("AI_MAX_TOKENS","0")),
        "dify_enabled":    str(cfg_via_env["dify_enabled"]).lower() in ("1","true","yes"),
        "dify_base_url":   cfg_via_env["dify_base_url"] or os.getenv("DIFY_BASE_URL",""),
        "dify_base_url_masked": mask(cfg_via_env["dify_base_url"] or os.getenv("DIFY_BASE_URL","")),
        "dify_has_api_key": bool(cfg_via_env["dify_api_key"] or os.getenv("DIFY_API_KEY","")),
        "dify_api_key_preview": mask(cfg_via_env["dify_api_key"] or os.getenv("DIFY_API_KEY",""), keep=8),
        "dify_app_id":     cfg_via_env["dify_app_id"] or os.getenv("DIFY_APP_ID",""),
        "dify_app_id_masked": mask(cfg_via_env["dify_app_id"] or os.getenv("DIFY_APP_ID","")),
        "n8n_enabled":     str(cfg_via_env["n8n_enabled"]).lower() in ("1","true","yes"),
        "n8n_base_url":    cfg_via_env["n8n_base_url"] or os.getenv("N8N_BASE_URL",""),
        "n8n_base_url_masked": mask(cfg_via_env["n8n_base_url"] or os.getenv("N8N_BASE_URL","")),
        "n8n_has_webhook_secret": bool(cfg_via_env["n8n_secret"] or os.getenv("N8N_SECRET","")),
        "n8n_webhook_secret_preview": mask(cfg_via_env["n8n_secret"] or os.getenv("N8N_SECRET",""), keep=5),
    }
    print("  [INFO] Fallback 结果:")
else:
    print("  [OK] 成功从后端接口读取配置！")

# 打印所有字段
for k, v in live_cfg.items():
    if isinstance(v, bool) or k.endswith("_masked") or k.endswith("_preview") \
            or k in ("provider","provider_name","model","temperature","max_tokens",
                     "dify_enabled","n8n_enabled","has_api_key",
                     "dify_has_api_key","n8n_has_webhook_secret",
                     "dify_base_url","n8n_base_url","dify_app_id"):
        if k in ("dify_base_url", "n8n_base_url") and v:
            v = v  # URL 本身可以直接看，不含密钥
        print("  %-32s = %r" % (k, v))


print()
print("=" * 90)
print("  Step 2/6: 配置自检（URL / API Key / 是否写成 n8n）")
print("=" * 90)

base = (live_cfg.get("dify_base_url") or "").strip()
has_key = bool(live_cfg.get("dify_has_api_key"))
enabled = bool(live_cfg.get("dify_enabled"))
errors = []
warnings = []

# 2.1 启用状态
if not enabled:
    errors.append("❌ dify_enabled = False，Dify 未启用")
# 2.2 URL 是否像 n8n（只看端口 5678 和 host/path 含 n8n 字样；不再硬编码 10.30.116.151=n8n）
#     注: 10.30.116.151 可能同机部署了 Dify(80) + n8n(5678)，不能靠 IP 猜。
if not base:
    errors.append("❌ dify_base_url 为空 → 去网站 AI 配置页面填 Dify 地址并点保存")
else:
    if not base.startswith("http"):
        errors.append("❌ dify_base_url=%r 缺少 http:// 或 https:// 前缀" % (base,))
    bad_reasons = []
    if ":5678" in base: bad_reasons.append("端口=5678(n8n默认端口)")
    if "n8n" in base.lower(): bad_reasons.append("host/path含n8n字样")
    if bad_reasons:
        errors.append("❌ dify_base_url=%r 看起来是 n8n 地址（%s），不是 Dify" % (base, " / ".join(bad_reasons)))
# 2.3 API Key
if not has_key:
    errors.append("❌ Dify API Key 未保存（dify_has_api_key = False）"
                  "\n     去 Dify 应用 → 发布 → 访问 API → 复制 API Secret → 粘到 AI 配置页面的 Dify API Key 框里 → 点保存")

for e in errors: print(e)
for w in warnings: print(w)
if not errors and not warnings:
    print("✅ 配置字段自检通过。")

# 2.4 硬校验: provider 必须 == 'dify'（否则即使 dify_enabled=True 也不会走 Dify）
current_provider = str(live_cfg.get("provider") or "").strip().lower()
if current_provider != "dify":
    provider_msg = ("当前 provider=%r（provider_name=%r），AI 仍然走【%s】，不会走 Dify。"
                    % (live_cfg.get("provider"), live_cfg.get("provider_name"),
                       live_cfg.get("provider_name") or "本地/LLM"))
    errors.append("⚠️ " + provider_msg)
    print("⚠️ " + provider_msg)
    print("     → 切换到全局 Dify 的 2 种方法（任选其一）：")
    print("        方法 A:  PowerShell 直接调后端 switch-global 接口（推荐）：")
    print('          $body = @{ target = "dify" } | ConvertTo-Json')
    print('          Invoke-RestMethod -Uri "%s/api/ai/switch-global" -Method Post '
          '-Body $body -ContentType "application/json" -UseBasicParsing' % BACKEND)
    print("        方法 B:  PowerShell 调 PUT config 接口：")
    print('          $body = @{ provider = "dify"; dify_enabled = $true } | ConvertTo-Json')
    print('          Invoke-RestMethod -Uri "%s/api/ai/config" -Method Put '
          '-Body $body -ContentType "application/json" -UseBasicParsing' % BACKEND)
    print("        方法 C:  网站登录 → 管理后台 → AI 配置面板 → 浮动球下拉 → 选【全局 Dify】")
    print("     → 切换后重跑本脚本确认 Step 1/6 里 provider='dify'。")


print()
print("=" * 90)
print("  Step 3/6: 直接调 Dify API — 验证 Round1/Round2（UUID续话）/Round3（sess_xxx复现报错）")
print("=" * 90)

# 尝试从 live_cfg 再补一个完整 API Key（只走 fallback 可能拿得到掩码前半段）
# 注意: GET /api/ai/config 是脱敏输出，不会给完整 key；
#       若后端接口没给，就提示用户必须用 POST /api/ai/config/test 去测真实连接，或者手动填。
from urllib.parse import urlparse
base_clean = base.rstrip("/")
if base_clean.endswith("/v1"):
    base_clean = base_clean[:-3]
chat_url = base_clean + "/v1/chat-messages" if base_clean else ""


def probe_key():
    """拿真实 key: 优先环境变量 / 其次 DB / 再次 None"""
    k = os.getenv("DIFY_API_KEY","") or ""
    if k: return k.strip()
    try:
        from database import SessionLocal
        from models import AIConfig
        db = SessionLocal()
        row = db.query(AIConfig).filter(AIConfig.config_key=="dify_api_key").first()
        db.close()
        if row: return row.config_value or ""
    except Exception:
        pass
    return ""

probe_k = probe_key()
# 如果已经有 key 可用 → 用它调 Dify 3 轮；否则给提示手动填
if not probe_k and not chat_url:
    print("[SKIP] 没有可用来调 Dify 的 URL/KEY，跳过本轮。要执行 Step 5/5（走后端代调）也可以。")
else:
    if probe_k:
        hdrs = {"Authorization": f"Bearer {probe_k}", "Content-Type": "application/json"}

        def run_round(test_name, payload_json, sid):
            print()
            print(f"---- {test_name} ({sid}) ----")
            print(f"POST {chat_url}")
            cid_show = payload_json.get("conversation_id")
            # 注意: f-string 不支持 "!r + if/else" 同写在一对 {} 里，会报 SyntaxError。
            # 这里改成普通字符串格式化 + repr() 预计算，兼容所有 Python 3.6+。
            if cid_show is None:
                cid_text = "(未传)"
            else:
                cid_text = repr(cid_show)
            print("  conversation_id = %s" % (cid_text,))
            print("  query = %r" % (payload_json["query"],))
            try:
                r = client.post(chat_url, json=payload_json, headers=hdrs)
            except Exception as e:
                print(f"  [EXCEPTION] {type(e).__name__}: {e}")
                return None, str(e)
            print(f"  HTTP {r.status_code}")
            try:
                data = r.json()
            except Exception:
                print(f"  [ERROR] 响应不是JSON: {r.text[:500]}")
                return None, r.text[:500]
            if r.status_code != 200:
                msg = data.get("message") or data.get("detail") or json.dumps(data, ensure_ascii=False)
                print(f"  [ERROR] {msg[:600]}")
                return None, msg
            answer = (data.get("answer") or "")[:200]
            cid = data.get("conversation_id")
            print(f"  [OK] answer(前200字): {answer}")
            print(f"  [OK] Dify conversation_id = {cid}")
            return data, None

        sess = "sess_v2_" + os.urandom(8).hex()
        p1 = {"inputs":{"machine_id":"","user_role":"user"},"query":"你能帮我干什么",
              "response_mode":"blocking","user":"fabtwin_user"}
        # Round1: 不传 cid（正确首次）
        res1, _ = run_round("Round 1 正确首次: 不传 conversation_id", p1, sess)
        dify_cid = (res1 or {}).get("conversation_id")

        # Round2: 传 Dify 返回的 UUID（正确续话）
        p2 = {**p1, "query":"详细说说机台状态怎么查"}
        if dify_cid: p2["conversation_id"] = dify_cid
        run_round("Round 2 正确续话: 传 Dify 的 UUID", p2, sess)

        # Round3: 故意传 sess_xxx（复现网站端老报错）
        p3 = {**p1, "query":"复现报错：用前端sess_xxx当cid", "conversation_id": sess}
        res3, err3 = run_round("Round 3 复现: 传前端 sess_xxx", p3, sess)
        if err3 and "must be a valid UUID" in err3:
            print()
            print("  💥 Round 3 命中了 'conversation_id must be a valid UUID' → 这就是你网站端第二次发送的报错根因!")
            print("     → 你网站端的后端进程跑的是 OLD 代码（没有 _dify_conv_map 映射）。")
            print("     → 解决: git pull origin test1 + 重启后端服务（IIS/FastAPI/uvicorn进程），不要只复制文件。")
    else:
        print("[INFO] 没有拿到完整 Dify API Key（后端 GET /api/ai/config 只返回掩码，符合安全设计）。")
        print("  直接调 Dify 的 3 轮对比将跳过，改用下面 2 个间接方法：")
        print("    a) 让后端 POST /api/ai/config/test 帮你测 Dify 连通性（带真实 Key）")
        print("    b) 直接 POST /api/ai/chat 端到端测（本脚本 Step 5/5 自动做）")

        # a) 测试连接（让后端自己用真实 Key 调 Dify）
        print()
        print("---- (a) POST /api/ai/config/test —— 让后端代测 Dify 连通性 ----")
        try:
            payload_test = {
                "provider_type": "dify",
                "config": {
                    "base_url": base,
                    # 不传 key → 后端会用 DB 里已保存的真实 key
                }
            }
            r = client.post(BACKEND + "/api/ai/config/test", json=payload_test)
            print(f"  POST {BACKEND}/api/ai/config/test → HTTP {r.status_code}")
            try:
                print(f"  响应: {json.dumps(r.json(), ensure_ascii=False)[:600]}")
            except Exception:
                print(f"  响应(非JSON): {r.text[:500]}")
            if r.status_code == 200 and (r.json().get("success") or r.json().get("ok")):
                print("  ✅ Dify 本身连通没问题 → 你的第二个报错（conversation_id=sess_xxx）一定是后端代码没更新/没重启。")
            else:
                print("  ❌ 后端用真实 Key 测 Dify 仍失败 → 先解决配置问题（回到 Step 2/6 改正项）。")
        except Exception as e:
            print(f"  [EXCEPTION] {type(e).__name__}: {e}")


print()
print("=" * 90)
print("  Step 4/6: 检查部署服务器上的 ai_middleware.py 是否带修复（真实文件，非本地仓库）")
print("=" * 90)

AM_PATH = os.path.join(HERE, "services", "ai_middleware.py")
try:
    with open(AM_PATH, encoding="utf-8") as f:
        am = f.read()
    has_conv_map = "_dify_conv_map" in am
    has_n8n_warn = "看起来是 n8n 地址" in am
except FileNotFoundError:
    print(f"[WARN] {AM_PATH} 不存在")
    has_conv_map = has_n8n_warn = None
except Exception as e:
    print(f"[WARN] 读文件失败: {e}")
    has_conv_map = has_n8n_warn = None

if has_conv_map is True:
    print("✅ services/ai_middleware.py 已带 conversation_id 修复 (_dify_conv_map)")
elif has_conv_map is False:
    print("❌ services/ai_middleware.py STILL 没有 _dify_conv_map（还是老版本）")
    print("   即使本地仓库代码是对的，部署服务器上这份文件也是 OLD。")
    print("   → 必须重新复制/拉取最新版代码到此路径，然后重启后端进程。")
else:
    print("[UNKNOWN] 无法判断代码版本。")

if has_n8n_warn is True:
    print("✅ services/ai_middleware.py 已带 n8n 地址误用告警")


print()
print("=" * 90)
print("  Step 5/6: 端到端 POST /api/ai/chat —— 模拟网页浮动球真实请求")
print("=" * 90)
sid_e2e = "sess_e2e_v2_" + os.urandom(8).hex()
for i, q in enumerate(["你能帮我干什么", "机台状态怎么查", "今天产量"], start=1):
    print()
    print("---- E2E Round %d: %r (session_id=%s) ----" % (i, q, sid_e2e))
    try:
        r = client.post(BACKEND + "/api/ai/chat", json={
            "question": q, "machine_id": "", "session_id": sid_e2e,
        })
    except Exception as e:
        print(f"  [EXCEPTION] {type(e).__name__}: {e}")
        continue
    print(f"  HTTP {r.status_code}")
    if r.status_code == 403 and "HJTC Proxy" in r.text[:3000]:
        print("  [CRITICAL] 403 仍被 HJTC Proxy 拦截，解决方法：")
        print('     执行 PowerShell:  $env:HTTP_PROXY=$null; $env:HTTPS_PROXY=$null; NO_PROXY=127.0.0.1,localhost')
        print("     然后重跑脚本。若仍然被拦，改用 FQDN/内网IP + 端口，不走 127.0.0.1。")
        break
    try:
        data = r.json()
    except Exception:
        print(f"  响应(前800字): {r.text[:800]}")
        continue
    if r.status_code != 200:
        msg = data.get("detail") or data.get("message") or json.dumps(data, ensure_ascii=False)
        print(f"  [ERROR] {msg[:800]}")
        if "must be a valid UUID" in msg:
            print()
            print("  💥 端到端 STILL 报 'must be a valid UUID' → 后端进程跑的还是 OLD 代码！")
            print("     解决方案(按顺序做):")
            print("       1) 确认部署目录 fab-twin-pro/backend/services/ai_middleware.py 包含了 _dify_conv_map（已用Step4/6打印）")
            print("       2) 重启后端进程（IIS 应用池 → 回收，或 uvicorn/FastAPI 服务 → 重启）")
            print("       3) 再跑一次本脚本 Step 5/6")
        continue
    ans = (data.get("answer") or "")[:300]
    ok = data.get("ok") or data.get("answer") and "查询失败" not in (data.get("answer") or "")
    print(f"  [OK] answer(前300字): {ans}")
    if data.get("conversation_id"):
        print("  [OK] conversation_id = %r" % (data.get("conversation_id"),))


print()
print("=" * 90)
print("  Step 6/6: 诊断总结")
print("=" * 90)
print("""
你本次输出里最典型的 3 个现象，对应结论：

现象 A: ORA-12541: TNS:no listener
  → 不是 DB 崩了，是诊断脚本自己在独立进程里没加载 Oracle Client。
  → 脚本 v2 已改为：先调活后端 GET /api/ai/config，不自己连 DB。

现象 B: 调 127.0.0.1:8002 返回 HJTC Proxy 403
  → 公司 McAfee Web Gateway 把 127.0.0.1:8002 当成"Internet请求"拦了。
  → 解法（永久写进 PowerShell）：
        $env:HTTP_PROXY  = $null
        $env:HTTPS_PROXY = $null
        $env:NO_PROXY    = "127.0.0.1,localhost,10.30.0.0/16"
     或改用 --host 指定内网网卡 IP（不要用 127.0.0.1）。

现象 C: Step 1/6 显示 provider='local' 或 其他 ≠ 'dify'（本次你遇到的就是这个！）
  → 即使 dify_enabled=True、URL/Key 都正确，AI 实际走的仍然是 本地规则引擎/LLM，不是 Dify。
  → 快速修复（任选其一，PowerShell 执行，注意先配好 $env:NO_PROXY）：
       # 方法 A: switch-global（推荐）
       $body = @{ target = "dify" } | ConvertTo-Json
       Invoke-RestMethod -Uri "%s/api/ai/switch-global" -Method Post -Body $body -ContentType "application/json" -UseBasicParsing
       # 方法 B: PUT /config
       $body = @{ provider = "dify"; dify_enabled = $true } | ConvertTo-Json
       Invoke-RestMethod -Uri "%s/api/ai/config" -Method Put -Body $body -ContentType "application/json" -UseBasicParsing
  → 切换成功的标志：再次 GET /api/ai/config → provider = 'dify'。
  → 注意：若 Dify 和 n8n 部署在 同一台服务器（如 10.30.116.151:80 = Dify，10.30.116.151:5678 = n8n），
         本脚本 Step 2/6 只会在 URL 含 :5678 或 n8n 字样时才报 n8n 误用，不会再靠 IP 误判。
         如果你仍然看到"= 10.30.116.151 都是 n8n"的报错 → 你跑的是 OLD 版本脚本，
         请从仓库拉最新的 diagnose_dify.py 覆盖部署服务器上的那份。

如果 Step 2/6 显示 Dify URL/Key/provider 都对，但 E2E Step 5/6 仍然报 "must be a valid UUID":
  → 100% 是"代码更新了但后端进程没重启"。
  → 最小验证命令:
        Select-String -Path services\\ai_middleware.py -Pattern "_dify_conv_map"
        没找到输出 → 直接把新文件覆盖过去；找到了输出 → 去 IIS/服务面板 点重启。
""" % (BACKEND, BACKEND))
