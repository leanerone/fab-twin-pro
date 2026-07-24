import { defineStore } from 'pinia'
import { api } from '../api'
import { useWebSocket } from '../composables/useWebSocket'

// 全局状态：机台列表、WebSocket 连接、事件总数等
export const useAppStore = defineStore('app', {
  state: () => ({
    // 机台列表（从 API 获取，WebSocket 实时更新）
    machines: [],
    // KPI 统计
    stats: {
      total: 0, running: 0, idle: 0, error: 0, maint: 0, setup: 0,
      total_wafers: 0, total_alarms: 0, wip: 0, done_lots: 0, hold_lots: 0,
      avg_cycle_time_min: 0, oee: 0,
    },
    // 当前选中机台 ID
    selectedMachineId: null,
    // WebSocket 连接状态
    wsConnected: false,
    // 事件总数
    totalEvents: 0,
    // 最新事件流（用于全局展示）
    recentEvents: [],
    // 后端是否可用（tibrv 连接状态）
    tibrvConnected: false,
    // 待处理的AI跳转请求：{ machine_id, timestamp }
    pendingJump: null,
  }),
  getters: {
    // 当前选中的机台对象
    selectedMachine(state) {
      return state.machines.find(m => m.id === state.selectedMachineId) || null
    },
    // 按产线分组
    line1Machines(state) {
      return state.machines.filter(m => m.line === 1)
    },
    line2Machines(state) {
      return state.machines.filter(m => m.line === 2)
    },
    // 机台总数
    totalMachines(state) {
      return state.machines.length
    },
  },
  actions: {
    // 从 API 获取机台列表
    async fetchMachines() {
      const data = await api.getMachines()
      if (data) {
        this.machines = data
        this.tibrvConnected = true
        // 默认选中第一个机台
        if (!this.selectedMachineId && data.length) {
          this.selectedMachineId = data[0].id
        }
      }
      return data
    },
    // 获取 KPI 统计
    async fetchStats() {
      const data = await api.getMachineStats()
      if (data) {
        this.stats = data
      }
      return data
    },
    // 选择机台
    selectMachine(id) {
      this.selectedMachineId = id
    },
    // 设置AI跳转请求
    setPendingJump(jump) {
      this.pendingJump = jump
    },
    // 消费AI跳转请求（获取后置null）
    consumePendingJump() {
      const j = this.pendingJump
      this.pendingJump = null
      return j
    },
    // 应用 WebSocket 推送的实时事件，更新机台状态
    applyRealtimeEvent(ev) {
      if (!ev) return
      this.totalEvents++
      // 加入最近事件流（保留 200 条）
      this.recentEvents.unshift(ev)
      if (this.recentEvents.length > 200) {
        this.recentEvents.pop()
      }
      // 更新对应机台状态
      const m = this.machines.find(x => x.id === ev.machine_id)
      if (!m) return
      // 事件类型处理
      if (ev.event_type === 'STATE') {
        if (ev.event_code) m.state = ev.event_code
        m.process_step = m.process_step // 状态切换时步骤可由后端更新
      } else if (ev.event_type === 'SENSOR') {
        if (ev.metric === 'temperature') m.temp = ev.value
        if (ev.metric === 'pressure') m.pressure = ev.value
        if (ev.metric === 'gasflow') m.gas_flow = ev.value
        if (ev.metric === 'rf') m.rf_power = ev.value
      } else if (ev.event_type === 'ALARM') {
        m.alarm_count = (m.alarm_count || 0) + 1
      } else if (ev.event_type === 'TRANSFER') {
        // 晶圆卸载时计数增加
        if (ev.event_code && /unload|卸载/i.test(ev.event_code + ev.description)) {
          m.wafer_count = (m.wafer_count || 0) + 1
        }
      }
      m.updated_at = ev.timestamp || new Date().toISOString()
    },
    // 连接 WebSocket
    connectWs() {
      const ws = useWebSocket()
      ws.connect(this)
    },
    // 断开 WebSocket
    disconnectWs() {
      const ws = useWebSocket()
      ws.disconnect()
      this.wsConnected = false
    },
  },
})
