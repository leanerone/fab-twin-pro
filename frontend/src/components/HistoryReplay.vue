<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import api from '@/api'

const props = defineProps({
  machineId: { type: String, required: true },
  machineState: { type: String, default: 'idle' },
  externalDate: { type: String, default: '' },
  jumpTimestamp: { type: String, default: '' },
})

const emit = defineEmits(['jump', 'replay-event', 'date-change', 'ai-analyze'])

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
const loadingMore = ref(false)
const hasMore = ref(false)
const nextRawId = ref(null)
const totalCount = ref(0)
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
    // 使用较大limit以覆盖当天所有事件；后端已支持 start_time 锚点自动定位
    const params = { start_time: start, end_time: end, limit: 2000 }
    if (filterCategory.value) {
      params.event_category = filterCategory.value
    }
    const data = await api.getHistory(props.machineId, params)
    events.value = data.events || []
    hasMore.value = !!(data.next_raw_id && events.value.length >= 2000)
    nextRawId.value = data.next_raw_id
    totalCount.value = data.total || events.value.length
  } catch (e) {
    console.error('[HistoryReplay] 加载事件失败:', e)
    events.value = []
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (!props.machineId || !hasMore.value || !nextRawId.value || loading.value) return
  loadingMore.value = true
  try {
    const start = `${selectedDate.value}T00:00:00`
    const end = `${selectedDate.value}T23:59:59.999`
    const params = {
      start_time: start,
      end_time: end,
      limit: 2000,
      before_raw_id: nextRawId.value,
    }
    if (filterCategory.value) {
      params.event_category = filterCategory.value
    }
    const data = await api.getHistory(props.machineId, params)
    const more = data.events || []
    // 追加，去重
    const seen = new Set(events.value.map(e => e.raw_id))
    for (const e of more) {
      if (!seen.has(e.raw_id)) {
        events.value.push(e)
      }
    }
    events.value.sort((a, b) => (a.timestamp > b.timestamp ? 1 : -1))
    hasMore.value = !!(data.next_raw_id && more.length >= 2000)
    nextRawId.value = data.next_raw_id
  } catch (e) {
    console.error('[HistoryReplay] 加载更多事件失败:', e)
  } finally {
    loadingMore.value = false
  }
}

function refresh() {
  loadTimeline()
  loadEvents()
}

// 滚动到底部自动加载更多
function onListScroll(e) {
  if (!hasMore.value || loadingMore.value) return
  const el = e.target
  if (el.scrollHeight - el.scrollTop - el.clientHeight < 100) {
    loadMore()
  }
}

function selectEvent(ev) {
  selectedEventId.value = ev.raw_id
  emit('replay-event', ev)
}

function jumpToHour(hour) {
  const ts = `${selectedDate.value}T${String(hour).padStart(2, '0')}:00:00.000`
  emit('jump', ts)
  // 同步滚动事件列表到对应小时
  const hourStr = String(hour).padStart(2, '0')
  const list = document.querySelector('.hr-list')
  if (!list) return
  const items = list.querySelectorAll('.hr-item')
  for (const item of items) {
    const timeEl = item.querySelector('.hr-item-time')
    // timeEl.textContent 格式为 "15:00"，匹配小时部分
    if (timeEl && timeEl.textContent.startsWith(hourStr + ':')) {
      item.scrollIntoView({ behavior: 'smooth', block: 'center' })
      break
    }
  }
}

// AI 分析当前回放：携带机台ID和当前回放时间戳，父组件切换到 AI Tab 并预填问题
function emitAiAnalyze() {
  const ts = props.jumpTimestamp || `${selectedDate.value}T00:00:00`
  emit('ai-analyze', {
    machine_id: props.machineId,
    timestamp: ts,
    date: selectedDate.value,
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

// 当 jumpTimestamp 变化时，滚动事件列表到最接近的事件
watch(() => props.jumpTimestamp, (ts) => {
  if (!ts || !events.value.length) return
  const targetMs = parseTs(ts)
  if (!targetMs) return
  // 找到时间最接近的事件
  let bestIdx = 0
  let bestDiff = Infinity
  for (let i = 0; i < events.value.length; i++) {
    const diff = Math.abs(parseTs(events.value[i].timestamp) - targetMs)
    if (diff < bestDiff) {
      bestDiff = diff
      bestIdx = i
    }
  }
  const ev = events.value[bestIdx]
  if (ev) {
    selectedEventId.value = ev.raw_id
    // 滚动到对应元素
    nextTick(() => {
      const list = document.querySelector('.hr-list')
      if (!list) return
      const items = list.querySelectorAll('.hr-item')
      if (items[bestIdx]) {
        items[bestIdx].scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    })
  }
})
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
        <span v-for="h in 24" :key="h-1">{{ (h-1) % 6 === 0 ? (h-1) : '' }}</span>
      </div>
    </div>

    <!-- 事件列表 -->
    <div class="hr-list" @scroll.passive="onListScroll">
      <div v-if="loading" class="hr-loading">加载中...</div>
      <div v-else-if="filteredEvents.length === 0" class="hr-empty">
        {{ selectedDate }} 该日期无事件记录
        <div class="hr-empty-hint">请尝试选择其他日期（数据可能集中在特定日期）</div>
      </div>
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
      <div v-if="hasMore" class="hr-load-more">
        <button @click="loadMore" :disabled="loadingMore">
          {{ loadingMore ? '加载中...' : `加载更多 (已显示 ${events.length})` }}
        </button>
      </div>
    </div>
    <!-- AI 快捷分析栏：点击后切换到 AI Tab 并预填问题 -->
    <div v-if="filteredEvents.length > 0" class="hr-ai-bar">
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
  gap: 1px;
  height: 40px;
  align-items: flex-end;
}
.hr-tl-bar {
  flex: 1;
  min-width: 0;
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
  margin-top: 4px;
  font-size: 9px;
  color: #475569;
}
.hr-tl-hours span {
  flex: 1;
  text-align: center;
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

.hr-load-more {
  padding: 8px 12px;
  text-align: center;
}
.hr-load-more button {
  background: #1e2d44;
  border: 1px solid #2a4060;
  border-radius: 4px;
  color: #94a3b8;
  padding: 6px 16px;
  font-size: 12px;
  cursor: pointer;
  width: 100%;
  transition: all 0.15s;
}
.hr-load-more button:hover:not(:disabled) {
  background: #2a4060;
  color: #e5e7eb;
}
.hr-load-more button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
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
