<script setup>
import { computed } from 'vue'

// Lot 批次列表：统计卡片 + Lot 列表，点击 Lot 触发 select 事件
const props = defineProps({
  lots: {
    type: Array,
    default: () => [],
  },
  selectedLotId: { type: String, default: '' },
})

const emit = defineEmits(['select'])

// 统计
const stats = computed(() => ({
  running: props.lots.filter(l => l.status === 'run').length,
  done: props.lots.filter(l => l.status === 'done').length,
  pending: props.lots.filter(l => l.status === 'pending').length,
  hold: props.lots.filter(l => l.status === 'hold').length,
}))

// 状态标签
function statusLabel(s) {
  return { run: '进行中', done: '已完成', pending: '等待中', hold: '异常HOLD' }[s] || s
}

// 格式化时间
function formatTime(t) {
  if (!t) return '--:--'
  try {
    const str = String(t).trim()
    // 支持 2026-07-22 15:00:48 格式
    if (str.includes(' ')) return str.slice(11, 16)
    // 支持 2026-07-22T15:00:48 格式
    if (str.includes('T')) return str.slice(11, 16)
    // 支持中文格式 2026-7-22 下午3:00:48
    if (str.includes('下午') || str.includes('上午')) {
      const parts = str.split(' ')
      if (parts.length >= 3) {
        let h = parseInt(parts[2].split(':')[0]) || 0
        const m = parts[2].split(':')[1] || '00'
        if (parts[1] === '下午' && h !== 12) h += 12
        if (parts[1] === '上午' && h === 12) h = 0
        return `${String(h).padStart(2, '0')}:${m}`
      }
    }
    return str.slice(0, 5)
  } catch {
    return '--:--'
  }
}

// 选择 Lot
function selectLot(lot) {
  emit('select', lot)
}
</script>

<template>
  <div class="lot-list-panel">
    <div class="section-title">Lot 批次管理</div>
    <div class="stats-grid">
      <div class="stat-box">
        <div class="sl">进行中</div>
        <div class="sv green">{{ stats.running }}</div>
      </div>
      <div class="stat-box">
        <div class="sl">已完成</div>
        <div class="sv">{{ stats.done }}</div>
      </div>
      <div class="stat-box">
        <div class="sl">等待中</div>
        <div class="sv yellow">{{ stats.pending }}</div>
      </div>
      <div class="stat-box">
        <div class="sl">异常 Hold</div>
        <div class="sv red">{{ stats.hold }}</div>
      </div>
    </div>
    <div class="section-title lot-list-title">Lot 列表</div>
    <div class="lot-list">
      <div
        v-for="lot in lots"
        :key="lot.id"
        class="lot-row"
        :class="{ selected: selectedLotId === lot.id }"
        @click="selectLot(lot)"
      >
        <div class="lot-id">
          {{ lot.id }}
          <span class="lot-badge" :class="lot.status">{{ statusLabel(lot.status) }}</span>
        </div>
        <div class="lot-meta">
          <span>{{ lot.product }} · {{ lot.wafer_count }}片</span>
          <span>{{ formatTime(lot.start_time) }}</span>
        </div>
      </div>
      <div v-if="!lots.length" class="empty-state">暂无 Lot 数据</div>
    </div>
  </div>
</template>

<style scoped>
.lot-list-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
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
.lot-list-title {
  border-top: 1px solid var(--border);
}
.lot-list {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.lot-row {
  padding: 8px 14px;
  border-bottom: 1px solid rgba(26, 40, 68, 0.5);
  font-size: 11.5px;
  cursor: pointer;
  overflow: hidden;
}
.lot-row:hover {
  background: var(--panel-2);
}
.lot-row.selected {
  background: rgba(0, 212, 255, 0.08);
}
.lot-id {
  font-weight: 700;
  color: var(--accent);
  font-family: monospace;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.lot-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-top: 3px;
  color: var(--text-dim);
  font-size: 10.5px;
}
.lot-meta > span:first-child {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.lot-meta > span:last-child {
  flex-shrink: 0;
  white-space: nowrap;
  color: var(--accent);
  font-family: monospace;
}
.lot-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 9px;
  font-weight: 700;
  margin-left: 6px;
}
.lot-badge.run { background: rgba(16, 185, 129, 0.2); color: var(--green); }
.lot-badge.done { background: rgba(59, 130, 246, 0.2); color: var(--blue); }
.lot-badge.pending { background: rgba(245, 158, 11, 0.2); color: var(--yellow); }
.lot-badge.hold { background: rgba(239, 68, 68, 0.2); color: var(--red); }
</style>
