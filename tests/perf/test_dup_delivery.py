"""验证 8a74590 引入的「同一事件被投递两次」风险。

背景：commit 8a74590 把 POST /api/rv/message 的广播体从前端不认的
type="rv_event" 改成 type="raw_event"（前端 useWebSocket.js:135 只认 raw_event）。
但同一行数据仍会被 db_poller 扫到并再广播一次 → 前端同一 raw_id 收到两次。

判定：注入 1 条事件，统计 WS 上该 raw_id 出现次数。
  == 1  → 无重复（说明存在去重或轮询未覆盖该行）
  >= 2  → 确认重复投递

用法：python tests/perf/test_dup_delivery.py [--wait 20]
"""
import argparse
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request

try:
    import websockets
except ImportError:
    print("需要 websockets：pip install websockets")
    sys.exit(2)

BASE = "http://localhost:8002"
WS_URL = "ws://localhost:8002/ws/realtime"
INGEST_KEY = "fabtwin-ingest-demo-key"


def post_event(tool_id, msg_id, event_name):
    body = json.dumps({
        "tool_id": tool_id,
        "source_system": "DUP-TEST",
        "source_message_id": msg_id,
        "payload_json": json.dumps({"event_name": event_name, "lot_id": "L-DUP"}),
    }).encode()
    req = urllib.request.Request(
        BASE + "/api/rv/message",
        data=body,
        headers={"Content-Type": "application/json", "X-API-Key": INGEST_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": e.read().decode()[:200]}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tool", default="PODOPENER-1")
    ap.add_argument("--wait", type=float, default=20)
    ap.add_argument("--event", default="PACKING_START")
    args = ap.parse_args()

    hits = []          # (到达时刻, raw_id)
    got_any = asyncio.Event()

    async def listen():
        try:
            async with websockets.connect(WS_URL, open_timeout=15) as ws:
                deadline = time.time() + args.wait + 5
                while time.time() < deadline:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    if msg.get("type") != "raw_event":
                        continue
                    d = msg.get("data") or {}
                    rid = d.get("raw_id") or ""
                    if "DUP-TEST" in str(d.get("payload")) or rid.startswith("TID.Z"):
                        hits.append((round(time.time() - t0, 2), rid, d.get("event_name")))
                        got_any.set()
        except Exception as e:
            print(f"[WS] 连接失败: {e}")
            raise

    t0 = time.time()
    listener = asyncio.create_task(listen())
    await asyncio.sleep(3)  # 等 WS 就绪

    res = post_event(args.tool, f"DUP-{int(time.time() * 1000)}", args.event)
    print(f"注入结果: {res}")
    if "raw_id" not in res:
        print("注入失败，无法验证")
        listener.cancel()
        return 1
    target = res["raw_id"]

    await asyncio.sleep(args.wait)
    listener.cancel()
    try:
        await listener
    except asyncio.CancelledError:
        pass

    mine = [h for h in hits if h[1] == target]
    print(f"\n目标 raw_id       : {target}")
    print(f"WS 收到 raw_event : {len(hits)} 条")
    print(f"其中目标 raw_id   : {len(mine)} 条  {mine}")

    print("\n" + "=" * 56)
    if len(mine) >= 2:
        gap = round(mine[-1][0] - mine[0][0], 2)
        print(f"✗ 确认重复投递：同一事件被推 {len(mine)} 次，间隔 {gap}s")
        print("  → API 注入后立即广播 1 次 + db_poller 扫到后再广播 1 次")
        print("  → 影响：recentEvents 重复、totalEvents/alarm_count/wafer_count 双倍计")
        print("  → 建议修复：useWebSocket.js 按 raw_id 去重（Set + 短 TTL）")
        return 0
    if len(mine) == 1:
        print("✓ 只投递 1 次，无重复（若日后加 API 直推需复测）")
        return 0
    print("? 未收到目标事件，检查服务端状态")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
