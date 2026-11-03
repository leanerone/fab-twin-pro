<script setup>
// Alarm 告警列表：列出所选时间段内的全部报警，内容完整展示不截断
defineProps({
  alarms: {
    type: Array,
    default: () => [],
  },
  selectedAlarmId: { type: String, default: '' },
})

const emit = defineEmits(['select'])

// 严重等级：文案与配色
const SEV_LABEL = { crit: '严重', warn: '警告', info: '提示' }
const SEV_CLASS = { crit: 'sev-crit', warn: 'sev-warn', info: 'sev-info' }

function severityLabel(s) {
  return SEV_LABEL[s] || '报警'
}

function severityClass(s) {
  return SEV_CLASS[s] || 'sev-warn'
}

// 格式化时间：与 Lot 列表一致，取时间部分并精确到秒
function formatTime(t) {
  if (!t) return '--:--:--'
  try {
    const str = String(t).trim()
    // 中文格式 2026-7-22 下午3:00:48（需先判断，避免被下面的冒号匹配误伤）
    if (str.includes('下午') || str.includes('上午')) {
      const parts = str.split(' ')
      if (parts.length >= 3) {
        let h = parseInt(parts[2].split(':')[0]) || 0
        const m = parts[2].split(':')[1] || '00'
        const s = parts[2].split(':')[2] || '00'
        if (parts[1] === '下午' && h !== 12) h += 12
        if (parts[1] === '上午' && h === 12) h = 0
        return `${String(h).padStart(2, '0')}:${m}:${s}`
      }
    }
    // 2026-07-22 15:00:48 / 2026-07-22T15:00:48
    if (str.includes(' ') || str.includes('T')) {
      const timePart = str.slice(11, 19)
      if (timePart.length === 8) return timePart
    }
    return str
  } catch {
    return '--:--:--'
  }
}

function selectAlarm(alarm) {
  emit('select', alarm)
}
</script>

<template>
  <div class="alarm-list-panel">
    <div class="section-title">Alarm 告警列表</div>
    <div class="alarm-list">
      <button
        v-for="a in alarms"
        :key="a.id"
        type="button"
        class="alarm-row"
        :class="{ selected: selectedAlarmId === a.id }"
        @click="selectAlarm(a)"
      >
        <div class="alarm-head">
          <span class="alarm-sev" :class="severityClass(a.severity)">{{ severityLabel(a.severity) }}</span>
          <span v-if="a.alarm_id" class="alarm-id">#{{ a.alarm_id }}</span>
        </div>
        <div class="alarm-text">{{ a.text }}</div>
        <div class="alarm-meta">
          <span>{{ a.context }}</span>
          <span>{{ formatTime(a.time) }}</span>
        </div>
      </button>
      <div v-if="!alarms.length" class="empty-state">所选时间段内无 Alarm 记录</div>
    </div>
  </div>
</template>

<style scoped>
.alarm-list-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.alarm-list {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.alarm-row {
  display: block;
  width: 100%;
  padding: 8px 14px;
  background: transparent;
  color: inherit;
  font-family: inherit;
  text-align: left;
  border: none;
  border-bottom: 1px solid rgba(26, 40, 68, 0.5);
  font-size: 11.5px;
  cursor: pointer;
  overflow: hidden;
}
.alarm-row:hover {
  background: var(--panel-2);
}
.alarm-row.selected {
  background: rgba(239, 68, 68, 0.1);
}
.alarm-head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.alarm-sev {
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 9px;
  font-weight: 700;
}
.alarm-sev.sev-crit { background: rgba(239, 68, 68, 0.25); color: var(--red); }
.alarm-sev.sev-warn { background: rgba(245, 158, 11, 0.25); color: var(--yellow); }
.alarm-sev.sev-info { background: rgba(59, 130, 246, 0.25); color: var(--blue); }
.alarm-id {
  color: var(--text-dim);
  font-family: monospace;
  font-size: 10px;
}
/* 告警内容完整展示：允许换行，不做省略截断 */
.alarm-text {
  margin-top: 3px;
  color: var(--text);
  font-size: 11.5px;
  line-height: 1.45;
  white-space: normal;
  word-break: break-all;
}
.alarm-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-top: 3px;
  color: var(--text-dim);
  font-size: 10.5px;
}
.alarm-meta > span:first-child {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.alarm-meta > span:last-child {
  flex-shrink: 0;
  white-space: nowrap;
  color: var(--red);
  font-family: monospace;
}
</style>
