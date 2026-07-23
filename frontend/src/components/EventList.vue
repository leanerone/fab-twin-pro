<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  events: {
    type: Array,
    default: () => [],
  },
})

const listRef = ref(null)

watch(() => props.events.length, async () => {
  await nextTick()
  if (listRef.value) {
    listRef.value.scrollTop = listRef.value.scrollHeight
  }
})

function tagClass(type) {
  return 'tag-' + (type || 'INFO').toUpperCase()
}

// 格式化时间：显示 YYYY-MM-DD HH:MM:SS 完整时间戳
function formatTime(timestamp) {
  if (!timestamp) return '-- --:--:--'
  const str = String(timestamp).trim()
  try {
    // Oracle NLS 中文格式: "2026-7-23 下午12:01:14"
    const nlsMatch = str.match(/^(\d{4})-(\d{1,2})-(\d{1,2})\s+(上午|下午)\s*(\d{1,2}):(\d{2}):(\d{2})$/)
    if (nlsMatch) {
      const year = nlsMatch[1]
      const month = String(nlsMatch[2]).padStart(2, '0')
      const day = String(nlsMatch[3]).padStart(2, '0')
      let h = parseInt(nlsMatch[5], 10)
      const m = nlsMatch[6]
      const s = nlsMatch[7]
      const ampm = nlsMatch[4]
      if (ampm === '下午' && h !== 12) h += 12
      if (ampm === '上午' && h === 12) h = 0
      return `${year}-${month}-${day} ${String(h).padStart(2, '0')}:${m}:${s}`
    }

    // ISO 格式: "2026-07-23T12:01:14" / "2026-07-23 12:01:14" / "2026-07-23T12:01:14.000Z"
    const stdMatch = str.match(/^(\d{4})-(\d{1,2})-(\d{1,2})[T ](\d{1,2}):(\d{2}):(\d{2})/)
    if (stdMatch) {
      const month = String(stdMatch[2]).padStart(2, '0')
      const day = String(stdMatch[3]).padStart(2, '0')
      return `${stdMatch[1]}-${month}-${day} ${stdMatch[4]}:${stdMatch[5]}:${stdMatch[6]}`
    }

    // fallback: 手动提取
    const sep = str.includes('T') ? 'T' : ' '
    if (str.includes(sep)) {
      const [datePart, timePart] = str.split(sep)
      const parts = (datePart || '').split('-')
      if (parts.length >= 3) {
        return `${parts[0]}-${String(parts[1]).padStart(2, '0')}-${String(parts[2]).padStart(2, '0')} ${(timePart || '').slice(0, 8)}`
      }
    }
    return '-- --:--:--'
  } catch {
    return '-- --:--:--'
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
        <span class="edesc">{{ e.description || e.event_code || e.event_name || '' }}</span>
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
  min-width: 130px;
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
.tag-VFEI { background: rgba(0, 212, 255, 0.2); color: var(--accent); }
.tag-HOST { background: rgba(124, 58, 237, 0.2); color: var(--accent-2); }
.event-row .edesc {
  flex: 1;
  color: var(--text);
  line-height: 1.4;
  word-break: break-all;
}
</style>
