<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import LotList from './LotList.vue'

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
const showLots = ref(false)
const selectedLotId = ref('')

// 从所选区段事件推导 LOT 列表（语义与后端 /lots 一致）：
// 最新事件决定 status/product/QTY（默认25），start_time 取该 Lot 最早事件，过滤 NULL
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
        status: 'pending',
        wafer_count: 25,
        product: '',
      }
      map.set(lotId, entry)
    }
    entry.end_time = ev.timestamp
    entry.status = payload.run_mode != null && payload.run_mode !== '' ? 'run' : 'done'
    if (payload.QTY != null && payload.QTY !== '') entry.wafer_count = payload.QTY
    if (payload.product || payload.PRODUCT) entry.product = payload.product || payload.PRODUCT
  }
  const list = Array.from(map.values())
  list.sort((a, b) => parseTs(b.start_time) - parseTs(a.start_time))
  return list
})

// 选择 Lot：跳转到该 Lot 的开始时间
function onLotSelect(lot) {
  selectedLotId.value = lot.id
  const targetTs = lot.start_time || lot.timestamp
  if (targetTs) emit('jump', targetTs)
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
    // 滚动到对应元素
    nextTick(() => {
      if (showLots.value) return
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
    <!-- 统计栏：LOT 概览，点击展开/收起 Lot 列表（内容与原 Lot 页签一致） -->
    <div class="hr-stats">
      <button type="button" class="hr-stat lot" :class="{ active: showLots }" @click="showLots = !showLots">
        <span class="hr-stat-num">{{ lots.length }}</span>
        <span class="hr-stat-label">LOT</span>
      </button>
    </div>

    <!-- Lot 列表（展开时显示） -->
    <div v-if="showLots" class="hr-lot-wrap">
      <LotList :lots="lots" :selected-lot-id="selectedLotId" @select="onLotSelect" />
    </div>

    <!-- 事件列表 -->
    <div v-show="!showLots" class="hr-list">
      <div v-if="loading" class="hr-loading">加载中...</div>
      <div v-else-if="events.length === 0" class="hr-empty">
        所选时间段内无事件记录
        <div class="hr-empty-hint">请调整顶部日期与时间区段后刷新</div>
      </div>
      <div
        v-for="ev in events"
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
    <!-- AI 快捷分析栏：点击后切换到 AI Tab 并预填问题 -->
    <div v-if="!showLots && events.length > 0" class="hr-ai-bar">
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
