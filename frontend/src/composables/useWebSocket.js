// WebSocket 连接管理：实时事件推送 + 自动重连 + VFEI事件解析
import { ref } from 'vue'

let wsInstance = null
let reconnectTimer = null
let reconnectAttempts = 0
const MAX_RECONNECT_DELAY = 8000

// VFEI事件类型映射
const VFEI_EVENT_TYPES = {
  'EC_ALARM_REPORT': 'alarm',
  'STATE_CHANGE': 'state',
  'POD_ATTACH': 'pod',
  'POD_DETACH': 'pod',
  'ATTACH_POD_PLACE': 'pod',
  'ATTACH_POD_UP': 'pod',
  'ATTACH_CST_PLACE': 'pod',
  'ATTACH_POD_DOWN': 'pod',
  'ATTACH_POD_REMOVE': 'pod',
  'DETACH_POD_PLACE': 'pod',
  'DETACH_POD_UP': 'pod',
  'DETACH_CST_REMOVE': 'pod',
  'DETACH_POD_DOWN': 'pod',
  'DETACH_POD_REMOVE': 'pod',
  'POD_LOCK': 'pod',
  'POD_UNLOCK': 'pod',
  'READ_TAG': 'pod',
  'WRITE_TAG': 'pod',
  'BATCH_START': 'process',
  'UI_CONFIRM': 'process',
  'UI_DOUBLECHECK': 'process',
  'WaferLoaded': 'transfer',
  'WaferUnloaded': 'transfer',
  'PS': 'process',
  'PE': 'process',
}

// 解析VFEI事件
function parseVfeiEvent(rawEvent) {
  const event = { ...rawEvent }
  
  // 标准化事件类型
  const evtName = (event.event_name || event.event_type || '').toUpperCase()
  event.event_category = VFEI_EVENT_TYPES[evtName] || 'other'
  
  // 解析告警
  if (evtName === 'EC_ALARM_REPORT' || event.event_type === 'ALARM') {
    event.is_alarm = true
    event.alarm_id = event.alarm_id || event.alarm_code || ''
    event.alarm_text = event.alarm_text || event.description || ''
    event.alarm_severity = event.alarm_severity || 'warn'
    if (['9004', '0201'].includes(event.alarm_id)) event.alarm_severity = 'crit'
  }
  
  // 解析Pod动作
  if (evtName.includes('ATTACH')) {
    event.pod_action = 'attach'
  } else if (evtName.includes('DETACH')) {
    event.pod_action = 'detach'
  }
  
  // 解析状态
  if (event.machine_state) {
    event.machine_state = event.machine_state.toLowerCase()
  }
  
  // 时间戳标准化
  if (!event.timestamp && event.event_ts_utc) {
    event.timestamp = event.event_ts_utc
  }
  
  return event
}

// 单例：返回 WebSocket 管理对象
export function useWebSocket() {
  if (wsInstance) return wsInstance

  wsInstance = {
    ws: null,
    pingTimer: null,
    // 连接 WebSocket，传入 store 用于事件分发
    connect(store) {
      if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
        return
      }
      // WebSocket 连接策略：
      // - IIS 部署（port 80/443）：优先通过 IIS 代理 /ws/realtime（ARR 反向代理）
      //   如果失败，fallback 直连后端 8002
      // - Vite dev/preview（其他端口）：走 Vite proxy（原生支持 ws 升级）
      const wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:'
      const wsUrl = `${wsProto}//${location.host}/ws/realtime`
      console.log('[WS] Connecting to:', wsUrl)
      try {
        this.ws = new WebSocket(wsUrl)
      } catch (e) {
        console.error('[WS] 创建失败:', e)
        this._scheduleReconnect(store)
        return
      }

      this.ws.onopen = () => {
        reconnectAttempts = 0
        store.wsConnected = true
        console.log('[WS] 已连接实时事件流')
        // 启动心跳 ping（每 25 秒），防止 IIS/代理因空闲断开
        if (this.pingTimer) clearInterval(this.pingTimer)
        this.pingTimer = setInterval(() => {
          if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ type: 'ping' }))
          }
        }, 25000)
      }

      this.ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data)
          // 消息格式: { type: "event" | "machines" | "raw_event" | "cur_status", data: {...} }
          if (msg.type === 'event' && msg.data) {
            // 解析VFEI事件
            const parsedEvent = parseVfeiEvent(msg.data)
            store.applyRealtimeEvent(parsedEvent)
          } else if (msg.type === 'machines' && Array.isArray(msg.data)) {
            // 批量机台状态更新
            store.machines = msg.data
          } else if (msg.type === 'vfei_event' && msg.data) {
            // VFEI事件流
            const parsedEvent = parseVfeiEvent(msg.data)
            store.applyRealtimeEvent(parsedEvent)
          } else if (msg.type === 'raw_event' && msg.data) {
                // DB轮询推送的原始事件（db_poller）
                const raw = msg.data
                console.log('[WS] 收到DB轮询事件:', raw.event_name, 'tool_id=', raw.tool_id, 'ts=', raw.timestamp)
                const parsedEvent = parseVfeiEvent({
                  ...raw.payload,
                  machine_id: raw.tool_id,
                  tool_id: raw.tool_id,
                  event_name: raw.event_name,
                  event_type: raw.event_type || 'VFEI',
                  event_category: raw.category || 'other',
                  timestamp: raw.timestamp,
                  description: raw.description || raw.payload?.alarm_text || raw.payload?.description || raw.event_name,
                  raw_id: raw.raw_id,
                  lot_id: raw.lot_id,
                  cassette_id: raw.cassette_id,
                  alarm_info: raw.alarm_info,
                })
                store.applyRealtimeEvent(parsedEvent)
              } else if (msg.type === 'cur_status' && Array.isArray(msg.data)) {
            // 当前状态更新（CUR表）
            msg.data.forEach(cur => {
              const m = store.machines.find(x => x.id === cur.tool_id)
              if (m) {
                m.updated_at = cur.timestamp || new Date().toISOString()
                if (cur.event_name) m.process_step = cur.event_name
              }
            })
          }
        } catch (e) {
          console.warn('[WS] 消息解析失败:', e)
        }
      }

      this.ws.onerror = (e) => {
        console.warn('[WS] 错误:', e)
      }

      this.ws.onclose = () => {
        store.wsConnected = false
        if (this.pingTimer) {
          clearInterval(this.pingTimer)
          this.pingTimer = null
        }
        console.log('[WS] 连接关闭，准备重连...')
        this._scheduleReconnect(store)
      }
    },

    // 发送事件（用于RV Bridge模拟）
    send(event) {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify(event))
      }
    },

    // 断开连接
    disconnect() {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
      if (this.pingTimer) {
        clearInterval(this.pingTimer)
        this.pingTimer = null
      }
      if (this.ws) {
        this.ws.onclose = null
        this.ws.close()
        this.ws = null
      }
    },

    // 自动重连（指数退避）
    _scheduleReconnect(store) {
      if (reconnectTimer) clearTimeout(reconnectTimer)
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), MAX_RECONNECT_DELAY)
      reconnectAttempts++
      reconnectTimer = setTimeout(() => {
        console.log(`[WS] 第 ${reconnectAttempts} 次重连...`)
        this.connect(store)
      }, delay)
    },
  }

  return wsInstance
}
