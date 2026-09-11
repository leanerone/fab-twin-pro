<script setup>
// Lot 批次列表：点击 Lot 触发 select 事件
// 注意：Lot 状态（进行中/已完成等）无法从 run_mode 可靠推导，已移除，不再显示
defineProps({
  lots: {
    type: Array,
    default: () => [],
  },
  selectedLotId: { type: String, default: '' },
})

const emit = defineEmits(['select'])

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
    <div class="lot-list">
      <button
        v-for="lot in lots"
        :key="lot.id"
        type="button"
        class="lot-row"
        :class="{ selected: selectedLotId === lot.id }"
        @click="selectLot(lot)"
      >
        <div class="lot-id">{{ lot.id }}</div>
        <div class="lot-meta">
          <span>{{ lot.product }} · {{ lot.wafer_count }}片</span>
          <span>{{ formatTime(lot.start_time) }}</span>
        </div>
      </button>
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
.lot-list {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.lot-row {
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
</style>
