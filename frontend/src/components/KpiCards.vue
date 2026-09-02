<script setup>
import { computed } from 'vue'
import { useAppStore } from '../stores/app'

const appStore = useAppStore()
const total = computed(() => appStore.totalMachines)
const DT_TOTAL = 905
const dtRate = computed(() => {
  if (!total.value) return 0
  return Math.floor((total.value / DT_TOTAL) * 100)
})
</script>

<template>
  <div class="kpi-row">
    <div class="kpi-card kpi-green">
      <div class="kpi-label">已接入DT机台</div>
      <div class="kpi-value">{{ total }}/{{ DT_TOTAL }}</div>
      <div class="kpi-sub">DT上线率 {{ dtRate }}%</div>
    </div>
  </div>
</template>

<style scoped>
.kpi-row {
  display: grid;
  grid-template-columns: auto;
  gap: 10px;
}
.kpi-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  position: relative;
  overflow: hidden;
}
.kpi-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--accent);
}
.kpi-card.kpi-green::before { background: var(--green); }
.kpi-card.kpi-yellow::before { background: var(--yellow); }
.kpi-card.kpi-red::before { background: var(--red); }
.kpi-card.kpi-blue::before { background: var(--blue); }
.kpi-card.kpi-purple::before { background: var(--accent-2); }
.kpi-label {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  color: var(--text-dim);
  font-weight: 600;
}
.kpi-value {
  font-size: 22px;
  font-weight: 700;
  margin-top: 4px;
  font-variant-numeric: tabular-nums;
}
.kpi-value .unit {
  font-size: 12px;
  color: var(--text-dim);
}
.kpi-sub {
  font-size: 10px;
  color: var(--text-mute);
  margin-top: 2px;
}
</style>
