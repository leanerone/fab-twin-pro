"""测试WebSocket连接"""
import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://localhost:8002/ws/realtime"
    try:
        async with websockets.connect(uri) as ws:
            print("WebSocket连接成功!")
            # 等待接收消息（最多5秒）
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(msg)
                print(f"收到消息: type={data.get('type')}")
                if data.get('type') == 'machines':
                    print(f"  机台数量: {len(data.get('data', []))}")
                elif data.get('type') == 'raw_event':
                    print(f"  事件: {data.get('data', {}).get('event_name')}")
                elif data.get('type') == 'cur_status':
                    print(f"  当前状态数量: {len(data.get('data', []))}")
            except asyncio.TimeoutError:
                print("5秒内未收到消息")
    except Exception as e:
        print(f"WebSocket连接失败: {e}")

asyncio.run(test_ws())
