<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAppStore } from '../stores/app'

// 顶部导航栏：Logo + 导航 + 实时状态
const router = useRouter()
const route = useRoute()
const appStore = useAppStore()

const clock = ref('')
let clockTimer = null

// 实时时钟
function updateClock() {
  clock.value = new Date().toTimeString().slice(0, 8)
}

// 导航到页面
function goDashboard() {
  router.push('/')
}
function goDetail() {
  // 若有选中机台则跳转，否则跳转默认
  const id = appStore.selectedMachineId || 'ETCH-201'
  router.push(`/machine/${id}`)
}

// 是否当前页
const isDashboard = computed(() => route.name === 'dashboard')
const isDetail = computed(() => route.name === 'machine-detail')

onMounted(() => {
  updateClock()
  clockTimer = setInterval(updateClock, 1000)
})
onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer)
})
</script>

<template>
  <header class="header">
    <div class="logo">
      <div class="logo-mark">F</div>
      FabTwin <span>半导体厂数字孪生系统</span>
    </div>
    <nav class="nav-tabs">
      <button class="nav-tab" :class="{ active: isDashboard }" @click="goDashboard">主页看板</button>
      <button class="nav-tab" :class="{ active: isDetail }" @click="goDetail">机台详情</button>
    </nav>
    <div class="header-right">
      <div class="header-item">
        <span class="live-dot" :class="{ offline: !appStore.wsConnected }"></span>
        tibrv <b>{{ appStore.wsConnected ? '已连接' : '断开' }}</b>
      </div>
      <div class="header-item">Oracle <b>19c</b></div>
      <div class="header-item">机台总数 <b>{{ appStore.totalMachines }}</b></div>
      <div class="header-item">事件 <b>{{ appStore.totalEvents }}</b></div>
      <div class="header-item"><b>{{ clock }}</b></div>
    </div>
  </header>
</template>

<style scoped>
.header {
  height: 52px;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 24px;
  flex-shrink: 0;
  z-index: 100;
}
.logo {
  font-size: 17px;
  font-weight: 800;
  color: var(--accent);
  letter-spacing: 1.5px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.logo-mark {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: #fff;
  font-weight: 900;
}
.logo span {
  color: var(--text-dim);
  font-weight: 400;
  font-size: 12px;
}
.nav-tabs {
  display: flex;
  gap: 4px;
}
.nav-tab {
  padding: 6px 16px;
  border: none;
  background: transparent;
  color: var(--text-dim);
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
}
.nav-tab:hover {
  color: var(--text);
}
.nav-tab.active {
  background: rgba(0, 212, 255, 0.12);
  color: var(--accent);
}
.header-right {
  margin-left: auto;
  display: flex;
  gap: 18px;
  align-items: center;
  font-size: 12px;
}
.header-item {
  color: var(--text-dim);
  display: flex;
  align-items: center;
  gap: 6px;
}
.header-item b {
  color: var(--text);
  font-weight: 600;
}
</style>
