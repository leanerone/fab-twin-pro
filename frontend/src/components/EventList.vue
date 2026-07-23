<script setup>
import { ref, watch, nextTick } from 'vue'

// 事件流列表：时间 + 类型标签 + 描述，自动滚动到最新
const props = defineProps({
  events: {
    type: Array,
    default: () => [],
  },
})

const listRef = ref(null)

// 监听事件变化，自动滚动到底部
watch(() => props.events.length, async () => {
  await nextTick()
  if (listRef.value) {
    listRef.value.scrollTop = listRef.value.scrollHeight
  }
})

// 事件类型标签样式映射
function tagClass(type) {
  return 'tag-' + (type || 'INFO').toUpperCase()
}

// 格式化时间（只显示时分秒）
function formatTime(timestamp) {
  if (!timestamp) return '--:--:--'
  try {
    const d = new Date(timestamp)
    if (isNaN(d.getTime())) {
      // fallback: 手动提取时间部分
      const sep = timestamp.includes('T') ? 'T' : ' '
      const timePart = timestamp.split(sep)[1]
      return timePart ? timePart.slice(0, 8) : '--:--:--'
    }
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    const ss = String(d.getSeconds()).padStart(2, '0')
    return `${hh}:${mm}:${ss}`
  } catch {
    return '--:--:--'
  }
}
</script>

<template>
  <div class="event-list-panel">
    <div class="section-title">实时事件流</div>
    <div ref="listRef" class="event-list">
      <div v-for="e in events" :key="e.id || (e.timestamp + e.event_code)" class="event-row">
        <span class="etime">{{ formatTime(e.timestamp) }}</span>
        <span class="etag" :class="tagClass(e.event_type)">{{ e.event_type }}</span>
        <span class="edesc">{{ e.description }}</span>
      </div>
      <div v-if="!events.length" class="empty-state">等待事件...</div>
    </div>
  </div>
</template>

<style scoped>
.event-list-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.event-list {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.event-row {
  padding: 7px 14px;
  border-bottom: 1px solid rgba(26, 40, 68, 0.5);
  font-size: 11.5px;
  display: flex;
  gap: 7px;
  align-items: flex-start;
}
.event-row .etime {
  color: var(--text-dim);
  font-family: monospace;
  font-size: 10px;
  white-space: nowrap;
  padding-top: 1px;
  min-width: 58px;
  flex-shrink: 0;
}
.event-row .etag {
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 9px;
  font-weight: 700;
  white-space: nowrap;
}
.tag-STATE { background: rgba(0, 212, 255, 0.15); color: var(--accent); }
.tag-ALARM { background: rgba(239, 68, 68, 0.15); color: var(--red); }
.tag-SENSOR { background: rgba(124, 58, 237, 0.15); color: var(--accent-2); }
.tag-WAFER { background: rgba(16, 185, 129, 0.15); color: var(--green); }
.tag-TRANSFER { background: rgba(245, 158, 11, 0.15); color: var(--yellow); }
.tag-INFO { background: rgba(107, 122, 148, 0.15); color: var(--text-dim); }
.event-row .edesc {
  flex: 1;
  color: var(--text);
  line-height: 1.4;
}
</style>
