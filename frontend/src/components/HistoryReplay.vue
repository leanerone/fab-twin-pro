<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import LotList from './LotList.vue'
import AlarmList from './AlarmList.vue'

const props = defineProps({
  machineId: { type: String, required: true },
  machineState: { type: String, default: 'idle' },
  events: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  jumpTimestamp: { type: String, default: '' },
})

const emit = defineEmits(['jump', 'replay-event', 'ai-analyze'])

// 时间戳解析：统一处理东八区时间，去掉Z后缀按本地时间解析
function parseTs(ts) {
  if (!ts) return 0
  const str = String(ts).trim().replace(/Z$/, '').replace(/[+-]\d{2}:\d{2}$/, '')
  const d = new Date(str)
  return isNaN(d.getTime()) ? 0 : d.getTime()
}

const selectedEventId = ref(null)
// 视图：'events' 事件列表 / 'lots' Lot 列表 / 'alarms' 告警列表
const activeView = ref('events')
const selectedLotId = ref('')
const selectedAlarmId = ref('')

// 事件列表一次渲染多少条：量产数据量下一个区段可能上千条事件，
// 全量渲染会生成上万个 DOM 节点，首屏直接卡住
const PAGE_SIZE = 200
const visibleCount = ref(PAGE_SIZE)

// 倒序（最新在前）：打开即看到最新事件，限额也只需截取开头一段
const orderedEvents = computed(() => props.events.slice().reverse())
const visibleEvents = computed(() => orderedEvents.value.slice(0, visibleCount.value))
const hasMore = computed(() => orderedEvents.value.length > visibleCount.value)

function loadMore() {
  visibleCount.value += PAGE_SIZE
}

// 换区段/换机台后事件列表整体变化，重置回第一页
watch(() => props.events, () => {
  visibleCount.value = PAGE_SIZE
})

// 从所选区段事件推导 LOT 列表：
// start_time 取该 Lot 最早事件，product/QTY 取最新非空值，过滤 NULL
// 注：不再推导 status —— run_mode 无法可靠反映 Lot 是否在跑，展示出来是虚假状态
const lots = computed(() => {
  const map = new Map()
  for (const ev of props.events) {
    const lotId = ev.lot_id
    if (!lotId || String(lotId).toUpperCase() === 'NULL') continue
    const payload = ev.payload || {}
    let entry = map.get(lotId)
    if (!entry) {
      entry = {
        id: lotId,
        lot_id: lotId,
        start_time: ev.timestamp,
        end_time: ev.timestamp,
        wafer_count: 25,
        product: '',
      }
      map.set(lotId, entry)
    }
    entry.end_time = ev.timestamp
    if (payload.QTY != null && payload.QTY !== '') entry.wafer_count = payload.QTY
    if (payload.product || payload.PRODUCT) entry.product = payload.product || payload.PRODUCT
  }
  const list = Array.from(map.values())
  list.sort((a, b) => parseTs(b.start_time) - parseTs(a.start_time))
  return list
})

// 从所选区段事件筛选出全部告警，最新在前
// 注：告警事件里的 chamber_id/port_id 等字段是 bridge 误填的告警描述词
//（后端 clean_alarm_event 专门清空），故只取 lot_id 作为上下文，不显示腔体
const alarms = computed(() => {
  const list = props.events
    .filter(ev => ev.event_category === 'alarm')
    .map(ev => ({
      id: ev.raw_id,
      time: ev.timestamp,
      alarm_id: (ev.alarm && ev.alarm.alarm_id) || '',
      severity: (ev.alarm && ev.alarm.severity) || 'warn',
      text: (ev.alarm && ev.alarm.alarm_text) || ev.description || ev.event_name || '',
      context: ev.lot_id ? `Lot: ${ev.lot_id}` : '',
    }))
  list.sort((a, b) => parseTs(b.time) - parseTs(a.time))
  return list
})

// 切换视图：再次点击当前页签则回到事件列表
function toggleView(view) {
  activeView.value = activeView.value === view ? 'events' : view
}

// 选择 Lot：跳转到该 Lot 的开始时间
function onLotSelect(lot) {
  selectedLotId.value = lot.id
  const targetTs = lot.start_time || lot.timestamp
  if (targetTs) emit('jump', targetTs)
}

// 选择告警：跳转到告警发生时间
function onAlarmSelect(alarm) {
  selectedAlarmId.value = alarm.id
  if (alarm.time) emit('jump', alarm.time)
}

function selectEvent(ev) {
  selectedEventId.value = ev.raw_id
  emit('replay-event', ev)
}

// AI 分析当前回放：携带机台ID和当前回放时间戳，父组件切换到 AI Tab 并预填问题
function emitAiAnalyze() {
  const last = props.events.length ? props.events[props.events.length - 1].timestamp : ''
  const ts = props.jumpTimestamp || last
  emit('ai-analyze', {
    machine_id: props.machineId,
    timestamp: ts,
    date: ts ? String(ts).slice(0, 10) : '',
  })
}

function getEventIcon(cat) {
  const map = {
    alarm: '⚠',
    pod: '📦',
    process: '⚙',
    other: '•',
  }
  return map[cat] || '•'
}

function getEventColor(cat) {
  const map = {
    alarm: '#ef4444',
    pod: '#f59e0b',
    process: '#3b82f6',
    other: '#64748b',
  }
  return map[cat] || '#64748b'
}

function getSeverityColor(sev) {
  const map = { crit: '#ef4444', warn: '#f59e0b', info: '#3b82f6' }
  return map[sev] || '#64748b'
}

function formatTime(ts) {
  if (!ts) return '--:--'
  const ms = parseTs(ts)
  if (!ms) return String(ts).slice(11, 16) || '--:--'
  const d = new Date(ms)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// 当 jumpTimestamp 变化时，滚动事件列表到最接近的事件
watch(() => props.jumpTimestamp, (ts) => {
  if (!ts || !props.events.length) return
  const targetMs = parseTs(ts)
  if (!targetMs) return
  // 找到时间最接近的事件
  let bestIdx = 0
  let bestDiff = Infinity
  for (let i = 0; i < props.events.length; i++) {
    const diff = Math.abs(parseTs(props.events[i].timestamp) - targetMs)
    if (diff < bestDiff) {
      bestDiff = diff
      bestIdx = i
    }
  }
  const ev = props.events[bestIdx]
  if (ev) {
    selectedEventId.value = ev.raw_id
    // 列表已倒序且只渲染前 visibleCount 条，索引必须换算成可见序号；
    // 沿用全量索引会滚到无关的事件上（甚至越界不滚动）
    const visIdx = orderedEvents.value.findIndex(e => e.raw_id === ev.raw_id)
    if (visIdx < 0) return
    if (visIdx >= visibleCount.value) visibleCount.value = visIdx + 1
    // 滚动到对应元素
    nextTick(() => {
      if (activeView.value !== 'events') return
      const list = document.querySelector('.hr-list')
      if (!list) return
      const items = list.querySelectorAll('.hr-item')
      if (items[visIdx]) {
        items[visIdx].scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    })
  }
})
</script>

<template>
  <div class="history-replay">
    <!-- 统计栏：LOT / ALARM 概览，点击展开对应列表 -->
    <div class="hr-stats">
      <button
        type="button"
        class="hr-stat lot"
        :class="{ active: activeView === 'lots' }"
        @click="toggleView('lots')"
      >
        <span class="hr-stat-num">{{ lots.length }}</span>
        <span class="hr-stat-label">LOT</span>
      </button>
      <button
        type="button"
        class="hr-stat alarm"
        :class="{ active: activeView === 'alarms' }"
        @click="toggleView('alarms')"
      >
        <span class="hr-stat-num">{{ alarms.length }}</span>
        <span class="hr-stat-label">ALARM</span>
      </button>
    </div>

    <!-- Lot 列表（展开时显示） -->
    <div v-if="activeView === 'lots'" class="hr-lot-wrap">
      <LotList :lots="lots" :selected-lot-id="selectedLotId" @select="onLotSelect" />
    </div>

    <!-- Alarm 列表（展开时显示） -->
    <div v-if="activeView === 'alarms'" class="hr-lot-wrap">
      <AlarmList :alarms="alarms" :selected-alarm-id="selectedAlarmId" @select="onAlarmSelect" />
    </div>

    <!-- 事件列表 -->
    <div v-show="activeView === 'events'" class="hr-list">
      <div v-if="loading" class="hr-loading">加载中...</div>
      <div v-else-if="events.length === 0" class="hr-empty">
        所选时间段内无事件记录
        <div class="hr-empty-hint">请调整顶部日期与时间区段后刷新</div>
      </div>
      <div
        v-for="ev in visibleEvents"
        :key="ev.raw_id"
        class="hr-item"
        :class="{ selected: selectedEventId === ev.raw_id, [ev.event_category]: true }"
        @click="selectEvent(ev)"
      >
        <div class="hr-item-left">
          <div class="hr-item-icon" :style="{ color: getEventColor(ev.event_category) }">
            {{ getEventIcon(ev.event_category) }}
          </div>
          <div class="hr-item-time">{{ formatTime(ev.timestamp) }}</div>
        </div>
        <div class="hr-item-body">
          <div class="hr-item-title">
            <span v-if="ev.event_name === 'EC_ALARM_REPORT' && ev.alarm" class="hr-alarm-badge" :style="{ background: getSeverityColor(ev.alarm.severity) }">
              {{ ev.alarm.alarm_id }}
            </span>
            <span v-else class="hr-event-name">{{ ev.event_name }}</span>
          </div>
          <div v-if="ev.alarm" class="hr-item-desc">
            {{ ev.alarm.alarm_text.length > 50 ? ev.alarm.alarm_text.slice(0, 50) + '...' : ev.alarm.alarm_text }}
          </div>
          <div v-else-if="ev.lot_id" class="hr-item-desc">Lot: {{ ev.lot_id }}</div>
          <div v-else class="hr-item-desc">{{ ev.event_type }}</div>
        </div>
        <div class="hr-item-arrow">▶</div>
      </div>

      <!-- 分页加载：避免一次渲染上千条事件 -->
      <div v-if="hasMore" class="hr-more">
        <button type="button" class="hr-more-btn" @click="loadMore">
          加载更早的 {{ orderedEvents.length - visibleCount }} 条
        </button>
      </div>
    </div>
    <!-- AI 快捷分析栏：点击后切换到 AI Tab 并预填问题 -->
    <div v-if="activeView === 'events' && events.length > 0" class="hr-ai-bar">
      <button class="hr-ai-btn" @click="emitAiAnalyze">
        🤖 AI分析当前回放
      </button>
    </div>
  </div>
</template>

<style scoped>
.history-replay {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* 统计 */
.hr-stats {
  display: flex;
  gap: 4px;
  padding: 6px 12px;
  border-bottom: 1px solid #1e2d44;
}
.hr-stat {
  flex: 1;
  text-align: center;
  padding: 4px 2px;
  border-radius: 4px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s;
  background: transparent;
  color: inherit;
  font-family: inherit;
}
.hr-stat:hover {
  background: #0a1628;
}
.hr-stat.active {
  background: #0a2030;
  border-color: #2a4060;
}
.hr-stat.lot.active { border-color: #06b6d4; }
.hr-stat.alarm.active { border-color: #ef4444; }
.hr-stat-num {
  display: block;
  font-size: 15px;
  font-weight: 700;
  color: #e5e7eb;
}
.hr-stat-label {
  font-size: 10px;
  color: #64748b;
}
.hr-stat.lot .hr-stat-num { color: #06b6d4; }
.hr-stat.alarm .hr-stat-num { color: #ef4444; }

/* Lot 列表容器（展开时占满剩余空间） */
.hr-lot-wrap {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 0;
}

/* 事件列表 */
.hr-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}
.hr-loading, .hr-empty {
  padding: 20px;
  text-align: center;
  color: #64748b;
  font-size: 13px;
}
.hr-empty-hint {
  margin-top: 6px;
  font-size: 11px;
  color: #94a3b8;
}
.hr-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  cursor: pointer;
  border-left: 2px solid transparent;
  transition: all 0.15s;
}
.hr-item:hover {
  background: #0a1628;
}
.hr-item.selected {
  background: #0a2030;
  border-left-color: #3b82f6;
}
.hr-item.alarm.selected { border-left-color: #ef4444; }
.hr-item.pod.selected { border-left-color: #f59e0b; }
.hr-item.process.selected { border-left-color: #3b82f6; }

/* 分页加载 */
.hr-more {
  padding: 8px 12px 12px;
  text-align: center;
}
.hr-more-btn {
  width: 100%;
  padding: 7px 10px;
  border-radius: 6px;
  border: 1px solid #2a4060;
  background: #0a1628;
  color: #94a3b8;
  font-size: 11.5px;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s;
}
.hr-more-btn:hover {
  background: #0a2030;
  border-color: #06b6d4;
  color: #06b6d4;
}

.hr-item-left {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 36px;
}
.hr-item-icon {
  font-size: 14px;
  line-height: 1;
}
.hr-item-time {
  font-size: 10px;
  color: #64748b;
  margin-top: 2px;
}
.hr-item-body {
  flex: 1;
  min-width: 0;
}
.hr-item-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #e5e7eb;
}
.hr-alarm-badge {
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  color: #fff;
}
.hr-event-name {
  color: #94a3b8;
}
.hr-item-desc {
  font-size: 11px;
  color: #64748b;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hr-item-arrow {
  font-size: 10px;
  color: #475569;
  opacity: 0;
  transition: opacity 0.15s;
}
.hr-item:hover .hr-item-arrow {
  opacity: 1;
}

/* AI 快捷分析栏 */
.hr-ai-bar {
  padding: 8px 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}
.hr-ai-btn {
  width: 100%;
  background: linear-gradient(135deg, #0e7490 0%, #0891b2 100%);
  border: 1px solid #06b6d4;
  border-radius: 6px;
  color: #ffffff;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.hr-ai-btn:hover {
  filter: brightness(1.1);
  box-shadow: 0 2px 8px rgba(6, 182, 212, 0.3);
}
</style>
