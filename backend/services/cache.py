"""Redis缓存服务：实时状态缓存、热点数据加速"""
import json
import threading

import redis
from cachetools import TTLCache

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


# ============== T2 进程内 TTL 缓存（cachetools）==============
# 适用前提：当前为单进程 uvicorn，进程内缓存有效；
# Garnet 就绪后由 T7 统一切换到「Garnet 优先、内存兜底」，RedisCache 本体暂不动。
class LocalTTLCache:
    """轻量 TTL 缓存封装：线程安全 + hit/miss 日志（便于验收与调 TTL）"""

    def __init__(self, name: str, ttl: int, maxsize: int = 64):
        self.name = name
        self._store = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            hit = key in self._store
            value = self._store.get(key) if hit else None
        print(f"[TTLCache:{self.name}] {'HIT' if hit else 'MISS'} key={key}", flush=True)
        return value

    def set(self, key, value):
        with self._lock:
            self._store[key] = value

    def invalidate(self, key=None):
        """key=None 清空全部；否则删除指定 key"""
        with self._lock:
            if key is None:
                self._store.clear()
                print(f"[TTLCache:{self.name}] INVALIDATE ALL", flush=True)
            else:
                existed = self._store.pop(key, None) is not None
                print(f"[TTLCache:{self.name}] INVALIDATE key={key} existed={existed}", flush=True)


# T2 三处缓存点
machine_state_ttl = LocalTTLCache("machine_state", ttl=60, maxsize=32)   # derive_machines_state 结果
kpi_stats_ttl = LocalTTLCache("kpi_stats", ttl=60, maxsize=4)            # GET /api/machines/stats
models_config_ttl = LocalTTLCache("models_config", ttl=300, maxsize=8)   # GET /api/models（保存时主动失效）
