<script setup>
import { ref, computed } from 'vue'
import { useAppStore } from '../stores/app'

// 机台列表侧边栏：产线选择 + 机台列表
const appStore = useAppStore()

const props = defineProps({
  // 当前选中机台 ID
  selectedId: { type: String, default: '' },
})

const emit = defineEmits(['select'])

// 当前查看的产线
const viewLine = ref(1)

// 机台名称搜索（非空时跨产线按 id/name/model 模糊匹配）
const searchQuery = ref('')

// 当前显示的机台列表：有搜索词时跨产线搜索，否则按产线过滤
const lineMachines = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    return appStore.machines.filter(
      (m) =>
        (m.id && m.id.toLowerCase().includes(q)) ||
        (m.name && m.name.toLowerCase().includes(q)) ||
        (m.model && m.model.toLowerCase().includes(q))
    )
  }
  return appStore.machines.filter((m) => m.line === viewLine.value)
})

// 选择机台
function selectMachine(m) {
  appStore.selectMachine(m.id)
  emit('select', m)
}
</script>

<template>
  <div class="machine-sidebar">
    <div class="sidebar-title">产线 & 机台</div>
    <div class="line-selector">
      <button class="line-btn" :class="{ active: viewLine === 1 && !searchQuery }" @click="viewLine = 1">
        Line 1<span class="smif-tag">无 SMIF</span>
      </button>
      <button class="line-btn" :class="{ active: viewLine === 2 && !searchQuery }" @click="viewLine = 2">
        Line 2<span class="smif-tag">SMIF / OHT</span>
      </button>
    </div>
    <div class="search-box">
      <span class="search-icon">🔍</span>
      <input
        v-model="searchQuery"
        class="search-input"
        placeholder="搜索机台ID/名称/型号"
      />
      <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''">✕</button>
    </div>
    <div class="machine-list">
      <div
        v-for="m in lineMachines"
        :key="m.id"
        class="mach-item"
        :class="{ selected: selectedId === m.id }"
        @click="selectMachine(m)"
      >
        <div class="status-dot" :class="m.state"></div>
        <div class="mach-info">
          <div class="mach-id">{{ m.id }}</div>
          <div class="mach-sub">{{ m.model }} · {{ m.process_type }}</div>
        </div>
        <span v-if="m.alarm_count" class="mach-alarm-badge">{{ m.alarm_count }}</span>
      </div>
      <div v-if="!lineMachines.length" class="empty-state">
        {{ searchQuery ? '无匹配机台' : '加载中...' }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.machine-sidebar {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  height: 100%;
}
.sidebar-title {
  padding: 12px 14px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-dim);
  border-bottom: 1px solid var(--border);
  background: var(--panel-2);
}
.line-selector {
  display: flex;
  padding: 10px;
  gap: 6px;
  border-bottom: 1px solid var(--border);
}
.line-btn {
  flex: 1;
  padding: 8px 0;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-dim);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
}
.line-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.line-btn.active {
  background: rgba(0, 212, 255, 0.1);
  border-color: var(--accent);
  color: var(--accent);
}
.smif-tag {
  font-size: 9px;
  display: block;
  margin-top: 2px;
  opacity: 0.7;
  font-weight: 400;
}
.search-box {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  background: var(--panel-2);
}
.search-icon {
  font-size: 12px;
  opacity: 0.6;
}
.search-input {
  flex: 1;
  min-width: 0;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 5px 8px;
  color: var(--text);
  font-size: 12px;
  outline: none;
}
.search-input:focus {
  border-color: var(--accent);
}
.search-clear {
  border: none;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  font-size: 12px;
  padding: 2px 4px;
}
.search-clear:hover {
  color: var(--text);
}
.machine-list {
  flex: 1;
  overflow-y: auto;
}
.mach-item {
  padding: 10px 14px;
  border-bottom: 1px solid rgba(26, 40, 68, 0.5);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 10px;
}
.mach-item:hover {
  background: var(--panel-2);
}
.mach-item.selected {
  background: rgba(0, 212, 255, 0.06);
  border-left: 2px solid var(--accent);
  padding-left: 12px;
}
.mach-info {
  flex: 1;
  min-width: 0;
}
.mach-id {
  font-weight: 600;
  font-size: 13px;
}
.mach-sub {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 2px;
}
.mach-alarm-badge {
  background: var(--red);
  color: #fff;
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 8px;
  font-weight: 700;
}
</style>
