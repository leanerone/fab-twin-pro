<script setup>
import { computed } from 'vue'

// 异常统计面板：分类条形图 + MTBF + 告警率 + 告警列表
const props = defineProps({
  // 告警统计 { total, crit, warn, temperature, pressure, rf_drift, gas_leak, resolved, unresolved }
  stats: {
    type: Object,
    default: () => ({ total: 0, crit: 0, warn: 0, temperature: 0, pressure: 0, rf_drift: 0, gas_leak: 0, resolved: 0, unresolved: 0 }),
  },
  // 告警列表
  alarms: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['click-alarm'])

function formatAlarmTime(ts) {
  if (!ts) return '--'
  // 显示完整日期时间：MM-DD HH:MM:SS
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ts.slice(5, 19) || ts
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  const s = String(d.getSeconds()).padStart(2, '0')
  return `${m}-${day} ${h}:${min}:${s}`
}

// 各分类百分比
const total = computed(() => props.stats.total || 1)
const critPct = computed(() => Math.round((props.stats.crit / total.value) * 100))
const warnPct = computed(() => Math.round((props.stats.warn / total.value) * 100))
const tempPct = computed(() => Math.round((props.stats.temperature / total.value) * 100))
const pressPct = computed(() => Math.round((props.stats.pressure / total.value) * 100))
const rfPct = computed(() => Math.round((props.stats.rf_drift / total.value) * 100))
const gasPct = computed(() => Math.round((props.stats.gas_leak / total.value) * 100))

// MTBF 估算
const mtbf = computed(() => {
  const t = props.stats.total || 0
  if (t === 0) return '24.0'
  return (24 / (t / 5 + 1)).toFixed(1)
})

// 告警率
const alarmRate = computed(() => {
  const t = props.stats.total || 0
  return ((t / 80) * 100).toFixed(1)
})
</script>

<template>
  <div class="alarm-stats-panel">
    <div class="section-title">异常统计</div>
    <div class="alarm-stats">
      <div class="alarm-stat-row">
        <span class="asr-label">严重告警</span>
        <div class="asr-bar"><div class="asr-fill" style="background:var(--red)" :style="{ width: critPct + '%' }"></div></div>
        <span class="asr-count" style="color:var(--red)">{{ stats.crit }}</span>
      </div>
      <div class="alarm-stat-row">
        <span class="asr-label">警告</span>
        <div class="asr-bar"><div class="asr-fill" style="background:var(--yellow)" :style="{ width: warnPct + '%' }"></div></div>
        <span class="asr-count" style="color:var(--yellow)">{{ stats.warn }}</span>
      </div>
      <div class="alarm-stat-row">
        <span class="asr-label">温度异常</span>
        <div class="asr-bar"><div class="asr-fill" style="background:#f97316" :style="{ width: tempPct + '%' }"></div></div>
        <span class="asr-count" style="color:#f97316">{{ stats.temperature }}</span>
      </div>
      <div class="alarm-stat-row">
        <span class="asr-label">压力异常</span>
        <div class="asr-bar"><div class="asr-fill" style="background:#8b5cf6" :style="{ width: pressPct + '%' }"></div></div>
        <span class="asr-count" style="color:#8b5cf6">{{ stats.pressure }}</span>
      </div>
      <div class="alarm-stat-row">
        <span class="asr-label">RF 漂移</span>
        <div class="asr-bar"><div class="asr-fill" style="background:#06b6d4" :style="{ width: rfPct + '%' }"></div></div>
        <span class="asr-count" style="color:#06b6d4">{{ stats.rf_drift }}</span>
      </div>
      <div class="alarm-stat-row">
        <span class="asr-label">气体泄漏</span>
        <div class="asr-bar"><div class="asr-fill" style="background:#ec4899" :style="{ width: gasPct + '%' }"></div></div>
        <span class="asr-count" style="color:#ec4899">{{ stats.gas_leak }}</span>
      </div>
    </div>
    <div class="stats-grid">
      <div class="stat-box">
        <div class="sl">MTBF</div>
        <div class="sv green">{{ mtbf }} h</div>
      </div>
      <div class="stat-box">
        <div class="sl">告警率</div>
        <div class="sv yellow">{{ alarmRate }}%</div>
      </div>
    </div>
    <div class="section-title alarm-list-title">
      告警列表
      <span v-if="alarms.length" class="badge">{{ alarms.length }}</span>
    </div>
    <div class="alarm-list">
      <div
        v-for="a in alarms"
        :key="a.id || (a.timestamp + a.alarm_code)"
        class="alarm-row clickable"
        :class="a.level"
        @click="emit('click-alarm', a)"
        title="点击查看该告警时间点"
      >
        <div class="dot"></div>
        <div class="atext">{{ a.description }}</div>
        <div class="atime">{{ formatAlarmTime(a.timestamp) }}</div>
      </div>
      <div v-if="!alarms.length" class="empty-state">暂无告警</div>
    </div>
  </div>
</template>

<style scoped>
.alarm-stats-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.alarm-stats {
  padding: 10px 14px;
}
.alarm-stat-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
  font-size: 11.5px;
}
.asr-bar {
  flex: 1;
  height: 6px;
  background: var(--bg);
  border-radius: 3px;
  overflow: hidden;
}
.asr-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s;
}
.asr-label {
  min-width: 90px;
  color: var(--text-dim);
}
.asr-count {
  min-width: 30px;
  text-align: right;
  font-weight: 700;
  font-family: monospace;
}
.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 10px 14px;
}
.stat-box {
  background: var(--bg);
  border-radius: 6px;
  padding: 8px 10px;
}
.stat-box .sl {
  font-size: 10px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.stat-box .sv {
  font-size: 18px;
  font-weight: 700;
  margin-top: 3px;
}
.stat-box .sv.red { color: var(--red); }
.stat-box .sv.yellow { color: var(--yellow); }
.stat-box .sv.green { color: var(--green); }
.alarm-list-title {
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.badge {
  background: var(--red);
  color: #fff;
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 10px;
  font-weight: 700;
}
.alarm-list {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.alarm-row {
  padding: 8px 14px;
  border-bottom: 1px solid rgba(26, 40, 68, 0.5);
  font-size: 12px;
  display: flex;
  gap: 8px;
  align-items: center;
}
.alarm-row .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.alarm-row.crit .dot { background: var(--red); }
.alarm-row.warn .dot { background: var(--yellow); }
.alarm-row .atext {
  flex: 1;
}
.alarm-row .atime {
  font-size: 10px;
  color: var(--text-dim);
  font-family: monospace;
}
.alarm-row.clickable {
  cursor: pointer;
  transition: background 0.15s;
}
.alarm-row.clickable:hover {
  background: rgba(0, 212, 255, 0.08);
}
</style>
