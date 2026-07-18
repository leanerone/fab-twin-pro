<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import api from '@/api'

const props = defineProps({
  machineId: { type: String, required: true },
  machineState: { type: String, default: 'idle' },
  externalDate: { type: String, default: '' },
})

const emit = defineEmits(['jump', 'replay-event', 'date-change'])

// 时间戳解析：统一处理东八区时间，去掉Z后缀按本地时间解析
function parseTs(ts) {
  if (!ts) return 0
  const str = String(ts).trim().replace(/Z$/, '').replace(/[+-]\d{2}:\d{2}$/, '')
  const d = new Date(str)
  return isNaN(d.getTime()) ? 0 : d.getTime()
}

const selectedDate = ref(props.externalDate || getToday())

// 外部日期变化时同步
watch(() => props.externalDate, (newDate) => {
  if (newDate && newDate !== selectedDate.value) {
    selectedDate.value = newDate
  }
})

// 内部日期变化时通知外部
watch(selectedDate, (newDate) => {
  emit('date-change', newDate)
})
const timeline = ref([])
const events = ref([])
const loading = ref(false)
const selectedEventId = ref(null)
const filterCategory = ref('') // '' = all, 'alarm', 'pod', 'process'

function getToday() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

async function loadTimeline() {
  if (!props.machineId) return
  try {
    const data = await api.getHistoryTimeline(props.machineId, selectedDate.value)
    timeline.value = data.timeline || []
  } catch (e) {
    console.error('[HistoryReplay] 加载时间轴失败:', e)
    timeline.value = []
  }
}

async function loadEvents() {
  if (!props.machineId) return
  loading.value = true
  try {
    const start = `${selectedDate.value}T00:00:00`
    const end = `${selectedDate.value}T23:59:59.999`
    const params = { start_time: start, end_time: end, limit: 500 }
    if (filterCategory.value) {
      params.event_category = filterCategory.value
    }
    const data = await api.getHistory(props.machineId, params)
    events.value = data.events || []
  } catch (e) {
    console.error('[HistoryReplay] 加载事件失败:', e)
    events.value = []
  } finally {
    loading.value = false
  }
}

function refresh() {
  loadTimeline()
  loadEvents()
}

function selectEvent(ev) {
  selectedEventId.value = ev.raw_id
  emit('replay-event', ev)
}

function jumpToHour(hour) {
  const ts = `${selectedDate.value}T${String(hour).padStart(2, '0')}:00:00.000`
  emit('jump', ts)
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

function formatDate(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  if (isNaN(d)) return ts.slice(0, 10)
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const filteredEvents = computed(() => {
  if (!filterCategory.value) return events.value
  return events.value.filter(e => e.event_category === filterCategory.value)
})

const eventCounts = computed(() => {
  const c = { alarm: 0, pod: 0, process: 0, other: 0 }
  events.value.forEach(e => { c[e.event_category] = (c[e.event_category] || 0) + 1 })
  return c
})

watch(() => props.machineId, refresh, { immediate: true })
watch(selectedDate, refresh)
watch(filterCategory, loadEvents)
</script>

<template>
  <div class="history-replay">
    <!-- 事件统计 -->
    <div class="hr-stats">
      <div class="hr-stat" :class="{ active: filterCategory === '' }" @click="filterCategory = ''">
        <span class="hr-stat-num">{{ events.length }}</span>
        <span class="hr-stat-label">全部</span>
      </div>
      <div class="hr-stat alarm" :class="{ active: filterCategory === 'alarm' }" @click="filterCategory = 'alarm'">
        <span class="hr-stat-num">{{ eventCounts.alarm }}</span>
        <span class="hr-stat-label">告警</span>
      </div>
      <div class="hr-stat pod" :class="{ active: filterCategory === 'pod' }" @click="filterCategory = 'pod'">
        <span class="hr-stat-num">{{ eventCounts.pod }}</span>
        <span class="hr-stat-label">Pod</span>
      </div>
      <div class="hr-stat process" :class="{ active: filterCategory === 'process' }" @click="filterCategory = 'process'">
        <span class="hr-stat-num">{{ eventCounts.process }}</span>
        <span class="hr-stat-label">工艺</span>
      </div>
    </div>

    <!-- 24小时时间轴 -->
    <div class="hr-timeline">
      <div class="hr-tl-label">24h</div>
      <div class="hr-tl-bars">
        <div
          v-for="h in timeline"
          :key="h.hour"
          class="hr-tl-bar"
          :class="{ has: h.has_events }"
          @click="jumpToHour(h.hour)"
          :title="`${h.hour}:00 事件:${h.total_count}`"
        >
          <div v-if="h.alarm_count > 0" class="hr-tl-seg alarm" :style="{ height: Math.min(100, h.alarm_count * 20) + '%' }"></div>
          <div v-if="h.pod_count > 0" class="hr-tl-seg pod" :style="{ height: Math.min(100, h.pod_count * 20) + '%' }"></div>
          <div v-if="h.process_count > 0" class="hr-tl-seg process" :style="{ height: Math.min(100, h.process_count * 20) + '%' }"></div>
        </div>
      </div>
      <div class="hr-tl-hours">
        <span v-for="h in [0,6,12,18,23]" :key="h">{{ h }}</span>
      </div>
    </div>

    <!-- 事件列表 -->
    <div class="hr-list">
      <div v-if="loading" class="hr-loading">加载中...</div>
      <div v-else-if="filteredEvents.length === 0" class="hr-empty">暂无事件</div>
      <div
        v-for="ev in filteredEvents"
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

/* 头部 */
.hr-header {
  display: flex;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid #1e2d44;
  align-items: center;
}
.hr-date {
  flex: 1;
  background: #0a1120;
  border: 1px solid #1e2d44;
  border-radius: 4px;
  color: #e5e7eb;
  padding: 5px 8px;
  font-size: 13px;
}
.hr-refresh {
  background: #1e2d44;
  border: 1px solid #2a4060;
  border-radius: 4px;
  color: #94a3b8;
  padding: 5px 10px;
  font-size: 14px;
  cursor: pointer;
}
.hr-refresh:hover {
  background: #2a4060;
  color: #e5e7eb;
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
}
.hr-stat:hover {
  background: #0a1628;
}
.hr-stat.active {
  background: #0a2030;
  border-color: #2a4060;
}
.hr-stat.alarm.active { border-color: #ef4444; }
.hr-stat.pod.active { border-color: #f59e0b; }
.hr-stat.process.active { border-color: #3b82f6; }
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
.hr-stat.alarm .hr-stat-num { color: #ef4444; }
.hr-stat.pod .hr-stat-num { color: #f59e0b; }
.hr-stat.process .hr-stat-num { color: #3b82f6; }

/* 时间轴 */
.hr-timeline {
  padding: 8px 12px;
  border-bottom: 1px solid #1e2d44;
}
.hr-tl-label {
  font-size: 10px;
  color: #64748b;
  margin-bottom: 4px;
}
.hr-tl-bars {
  display: flex;
  gap: 2px;
  height: 40px;
  align-items: flex-end;
}
.hr-tl-bar {
  flex: 1;
  height: 100%;
  background: #0a1120;
  border-radius: 2px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  overflow: hidden;
  transition: background 0.15s;
}
.hr-tl-bar:hover {
  background: #1e2d44;
}
.hr-tl-bar.has {
  background: #0f1a2e;
}
.hr-tl-seg {
  width: 100%;
  min-height: 2px;
}
.hr-tl-seg.alarm { background: #ef4444; }
.hr-tl-seg.pod { background: #f59e0b; }
.hr-tl-seg.process { background: #3b82f6; }
.hr-tl-hours {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-size: 9px;
  color: #475569;
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
.hr-item.alarm { border-left-color: transparent; }
.hr-item.alarm.selected { border-left-color: #ef4444; }
.hr-item.pod.selected { border-left-color: #f59e0b; }
.hr-item.process.selected { border-left-color: #3b82f6; }

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
</style>
