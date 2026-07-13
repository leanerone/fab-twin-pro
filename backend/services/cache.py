"""Redis缓存服务：实时状态缓存、热点数据加速"""
import json
import redis
from config import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_ENABLED


class RedisCache:
    def __init__(self):
        self.enabled = REDIS_ENABLED
        self.r = None
        if self.enabled:
            try:
                self.r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
                self.r.ping()
                print("[Redis] 连接成功")
            except Exception as e:
                print(f"[Redis] 连接失败，将使用内存缓存: {e}")
                self.enabled = False
                self.r = None

    def set_machine_state(self, machine_id, state_data):
        """缓存机台实时状态"""
        if not self.enabled:
            return
        try:
            key = f"machine:{machine_id}:state"
            self.r.set(key, json.dumps(state_data), ex=60)
        except Exception as e:
            print(f"[Redis] set_machine_state error: {e}")

    def get_machine_state(self, machine_id):
        """获取机台缓存状态"""
        if not self.enabled:
            return None
        try:
            key = f"machine:{machine_id}:state"
            data = self.r.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            print(f"[Redis] get_machine_state error: {e}")
            return None

    def set_latest_events(self, machine_id, events):
        """缓存最新事件列表"""
        if not self.enabled:
            return
        try:
            key = f"machine:{machine_id}:events"
            self.r.set(key, json.dumps(events), ex=30)
        except Exception as e:
            print(f"[Redis] set_latest_events error: {e}")

    def get_latest_events(self, machine_id):
        """获取缓存的最新事件"""
        if not self.enabled:
            return None
        try:
            key = f"machine:{machine_id}:events"
            data = self.r.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            print(f"[Redis] get_latest_events error: {e}")
            return None

    def set_kpi_stats(self, stats):
        """缓存KPI统计数据"""
        if not self.enabled:
            return
        try:
            key = "dashboard:kpi"
            self.r.set(key, json.dumps(stats), ex=60)
        except Exception as e:
            print(f"[Redis] set_kpi_stats error: {e}")

    def get_kpi_stats(self):
        """获取缓存的KPI统计"""
        if not self.enabled:
            return None
        try:
            key = "dashboard:kpi"
            data = self.r.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            print(f"[Redis] get_kpi_stats error: {e}")
            return None

    def set_oht_positions(self, positions):
        """缓存OHT天车位置"""
        if not self.enabled:
            return
        try:
            key = "oht:positions"
            self.r.set(key, json.dumps(positions), ex=5)
        except Exception as e:
            print(f"[Redis] set_oht_positions error: {e}")

    def get_oht_positions(self):
        """获取缓存的OHT位置"""
        if not self.enabled:
            return None
        try:
            key = "oht:positions"
            data = self.r.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            print(f"[Redis] get_oht_positions error: {e}")
            return None

    def publish_event(self, channel, event):
        """发布事件到Redis频道（用于实时推送）"""
        if not self.enabled:
            return
        try:
            self.r.publish(channel, json.dumps(event))
        except Exception as e:
            print(f"[Redis] publish_event error: {e}")


cache = RedisCache()
