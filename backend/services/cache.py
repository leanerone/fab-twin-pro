"""Redis缓存服务：实时状态缓存、热点数据加速"""
import json
import threading
import time

import redis
from cachetools import TTLCache
from redis.backoff import NoBackoff
from redis.retry import Retry

from config import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_ENABLED

# 禁掉 redis-py 8.x 默认的 3 次指数退避重试（本机无监听时单次 ping 实测 47.9s，
# 直接拖死 /api/machines）。缓存只是加速层，连接必须快速失败、由 30s 惰性重连兜底。
_NO_RETRY = Retry(backoff=NoBackoff(), retries=0)


class RedisCache:
    def __init__(self):
        self.enabled = REDIS_ENABLED
        self.r = None
        if self.enabled:
            try:
                self.r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True,
                                     socket_timeout=1, socket_connect_timeout=1,
                                     retry=_NO_RETRY, retry_on_timeout=False)
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


# ============== T7 双层缓存（Garnet 优先、内存兜底）==============
class HybridTTLCache:
    """Garnet(Redis) 优先、进程内存 TTLCache 兜底的双层缓存。

    接口与 LocalTTLCache 一致（get/set/invalidate），T2 调用点零改动。
    - redis 可用：set 双写；get 先 redis，miss 回内存
    - redis 未启用/连接失败/运行时故障：自动降级纯内存，不抛错
    - 故障后每 30s 惰性重连一次（Garnet 恢复后自动切回）
    - 后端重启后 Garnet 侧缓存仍在，首屏不回慢
    """

    RETRY_INTERVAL = 30  # 秒

    def __init__(self, name: str, ttl: int, maxsize: int = 64):
        self.name = name
        self.ttl = ttl
        self._local = LocalTTLCache(name, ttl, maxsize)
        self._r = None
        self._redis_up = False
        self._last_retry = 0.0
        self._connect_lock = threading.Lock()
        self._connect()

    def _connect(self):
        if not REDIS_ENABLED:
            return
        # 任何尝试都计入节流窗口（含 __init__ 首次），避免启动后首个请求立刻重试
        self._last_retry = time.time()
        # 并发请求下只许一个线程发起连接，其余直接走内存兜底，避免惊群
        if not self._connect_lock.acquire(blocking=False):
            return
        try:
            r = redis.Redis(
                host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
                decode_responses=True, socket_timeout=1, socket_connect_timeout=1,
                retry=_NO_RETRY, retry_on_timeout=False,
            )
            r.ping()
            self._r = r
            self._redis_up = True
            print(f"[HybridCache:{self.name}] Garnet 已连接 redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}", flush=True)
        except Exception as e:
            self._r = None
            self._redis_up = False
            print(f"[HybridCache:{self.name}] Garnet 不可用，降级内存缓存: {e}", flush=True)
        finally:
            self._connect_lock.release()

    def _maybe_reconnect(self):
        if self._redis_up or not REDIS_ENABLED:
            return
        now = time.time()
        if now - self._last_retry < self.RETRY_INTERVAL:
            return
        self._last_retry = now
        self._connect()

    def _key(self, key):
        return f"fabtwin:ttl:{self.name}:{key}"

    def get(self, key):
        self._maybe_reconnect()
        if self._redis_up:
            try:
                raw = self._r.get(self._key(key))
                if raw is not None:
                    print(f"[HybridCache:{self.name}] HIT(redis) key={key}", flush=True)
                    return json.loads(raw)
            except Exception as e:
                self._redis_up = False
                print(f"[HybridCache:{self.name}] redis 读故障，降级内存: {e}", flush=True)
        return self._local.get(key)

    def set(self, key, value):
        self._maybe_reconnect()
        # 内存始终写：redis 故障兜底 + redis miss 时的 L1
        self._local.set(key, value)
        if self._redis_up:
            try:
                self._r.set(self._key(key), json.dumps(value, ensure_ascii=False, default=str), ex=self.ttl)
            except Exception as e:
                self._redis_up = False
                print(f"[HybridCache:{self.name}] redis 写故障，仅内存: {e}", flush=True)

    def invalidate(self, key=None):
        """key=None 清空该命名空间全部；否则删除指定 key"""
        self._local.invalidate(key)
        self._maybe_reconnect()
        if self._redis_up:
            try:
                if key is None:
                    for k in self._r.scan_iter(match=self._key("*"), count=100):
                        self._r.delete(k)
                    print(f"[HybridCache:{self.name}] INVALIDATE ALL(redis)", flush=True)
                else:
                    self._r.delete(self._key(key))
                    print(f"[HybridCache:{self.name}] INVALIDATE(redis) key={key}", flush=True)
            except Exception as e:
                self._redis_up = False
                print(f"[HybridCache:{self.name}] redis 失效失败: {e}", flush=True)


# T2 三处缓存点（T7 统一切换为双层缓存：Garnet 优先、内存兜底）
machine_state_ttl = HybridTTLCache("machine_state", ttl=60, maxsize=32)   # derive_machines_state 结果
kpi_stats_ttl = HybridTTLCache("kpi_stats", ttl=60, maxsize=4)            # GET /api/machines/stats
models_config_ttl = HybridTTLCache("models_config", ttl=300, maxsize=8)   # GET /api/models（保存时主动失效）
