<script setup>
import { computed } from 'vue'
import { useAppStore } from '../stores/app'

// KPI 卡片组：7 个关键指标
const appStore = useAppStore()

const stats = computed(() => appStore.stats)
const total = computed(() => appStore.totalMachines)

// 稼动率
const util = computed(() => {
  if (!total.value) return 0
  return Math.floor((stats.value.running / total.value) * 100)
})
</script>

<template>
  <div class="kpi-row">
    <div class="kpi-card kpi-green">
      <div class="kpi-label">运行中机台</div>
      <div class="kpi-value">{{ stats.running }}/{{ total }}</div>
      <div class="kpi-sub">稼动率 {{ util }}%</div>
    </div>
    <div class="kpi-card kpi-yellow">
      <div class="kpi-label">空闲机台</div>
      <div class="kpi-value">{{ stats.idle }}</div>
      <div class="kpi-sub">等待物料/排程</div>
    </div>
    <div class="kpi-card kpi-red">
      <div class="kpi-label">故障告警</div>
      <div class="kpi-value">{{ stats.total_alarms }}</div>
      <div class="kpi-sub">严重 {{ Math.floor(stats.total_alarms * 0.3) }} / 警告 {{ stats.total_alarms - Math.floor(stats.total_alarms * 0.3) }}</div>
    </div>
    <div class="kpi-card kpi-blue">
      <div class="kpi-label">今日产量</div>
      <div class="kpi-value">{{ stats.total_wafers }}</div>
      <div class="kpi-sub">片晶圆</div>
    </div>
    <div class="kpi-card kpi-purple">
      <div class="kpi-label">在制品 WIP</div>
      <div class="kpi-value">{{ stats.wip }}</div>
      <div class="kpi-sub">批 lot</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">平均节拍</div>
      <div class="kpi-value">{{ stats.avg_cycle_time_min }}<span class="unit"> min</span></div>
      <div class="kpi-sub">单工艺周期</div>
    </div>
    <div class="kpi-card kpi-green">
      <div class="kpi-label">OEE 综合效率</div>
      <div class="kpi-value">{{ stats.oee }}%</div>
      <div class="kpi-sub">目标 85%</div>
    </div>
  </div>
</template>

<style scoped>
.kpi-row {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
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
