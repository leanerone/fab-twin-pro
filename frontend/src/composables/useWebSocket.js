// WebSocket 连接管理：实时事件推送 + 自动重连
import { ref } from 'vue'

let wsInstance = null
let reconnectTimer = null
let reconnectAttempts = 0
const MAX_RECONNECT_DELAY = 8000

// 单例：返回 WebSocket 管理对象
export function useWebSocket() {
  if (wsInstance) return wsInstance

  wsInstance = {
    ws: null,
    // 连接 WebSocket，传入 store 用于事件分发
    connect(store) {
      if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
        return
      }
      // 通过 Vite proxy 代理 ws，或直连后端
      const wsUrl = `ws://${location.hostname}:8001/ws/realtime`
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
      }

      this.ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data)
          // 消息格式: { type: "event" | "machines", data: {...} }
          if (msg.type === 'event' && msg.data) {
            store.applyRealtimeEvent(msg.data)
          } else if (msg.type === 'machines' && Array.isArray(msg.data)) {
            // 批量机台状态更新
            store.machines = msg.data
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
        console.log('[WS] 连接关闭，准备重连...')
        this._scheduleReconnect(store)
      }
    },

    // 断开连接
    disconnect() {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
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
