<script setup>
import { ref, onMounted } from 'vue'
import AppHeader from './components/AppHeader.vue'
import AIFloatingBall from './components/AIFloatingBall.vue'
import { useAppStore } from './stores/app'
import { useModelStore } from './stores/model'
import { useAuthStore } from './stores/auth'
import { useRouter, useRoute } from 'vue-router'

// 全局 store：启动时连接 WebSocket 并预加载机台型号配置与模型资源
const appStore = useAppStore()
const modelStore = useModelStore()
const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()
appStore.connectWs()
modelStore.loadModels()

// Toast 通知
const toasts = ref([])
let toastId = 0
function showToast(msg, type = 'info', duration = 3000) {
  const id = ++toastId
  toasts.value.push({ id, msg, type })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, duration)
}

// 处理全局AI悬浮球的跳转事件
// payload: { machine_id, timestamp, machine_online }
function handleAIJump(payload) {
  if (!payload) return
  let mid = ''
  let ts = ''
  let machineOnline = null
  if (typeof payload === 'string') {
    ts = payload
  } else {
    mid = payload.machine_id || ''
    ts = payload.timestamp || ''
    machineOnline = payload.machine_online
  }
  if (!ts) return

  // 机台未上线检查
  if (mid && machineOnline === false) {
    showToast(`机台 ${mid} 暂未上线平台，暂不支持跳转，待机台上线后再试`, 'warning', 5000)
    return
  }

  // 如果 machine_online 未指定，前端检查机台是否存在
  if (mid && machineOnline === null) {
    const exists = appStore.machines.some(m => m.id === mid)
    if (!exists) {
      showToast(`机台 ${mid} 暂未上线平台，暂不支持跳转，待机台上线后再试`, 'warning', 5000)
      return
    }
  }

  // 当前路由对应的机台ID
  const currentId = route.params && (route.params.id || route.params.machineId)

  // 如果跳转目标与当前机台不同，导航到目标机台，并通过query把时间戳带过去
  if (mid && currentId !== mid) {
    router.push({ path: `/machine/${mid}`, query: { ts: ts } })
    return
  }

  // 同机台或未指定机台：把跳转请求放入全局 store，由 MachineDetail 消费
  appStore.setPendingJump({ machine_id: mid || currentId || '', timestamp: ts })
}

// 确保机台列表已加载
onMounted(async () => {
  if (!appStore.machines.length) {
    try {
      await appStore.fetchMachines()
    } catch (e) {
      console.warn('[AI Jump] 加载机台列表失败:', e)
    }
  }
})
</script>

<template>
  <div class="app-shell">
    <AppHeader />
    <main class="app-main">
      <router-view />
    </main>
    <!-- 全局悬浮AI球（登录后显示） -->
    <AIFloatingBall v-if="authStore.isLoggedIn" @jump="handleAIJump" />
    <!-- 全局 Toast 通知 -->
    <div class="toast-container">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="t.type">{{ t.msg }}</div>
    </div>
  </div>
</template>

<style scoped>
.app-shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.app-main {
  flex: 1;
  overflow: hidden;
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.toast-container {
  position: fixed;
  top: 70px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}
.toast {
  padding: 12px 20px;
  border-radius: 8px;
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
  animation: slideIn 0.3s ease-out;
  max-width: 360px;
  pointer-events: auto;
}
.toast.info { background: #3b82f6; }
.toast.success { background: #10b981; }
.toast.warning { background: #f59e0b; }
.toast.error { background: #ef4444; }
@keyframes slideIn {
  from { opacity: 0; transform: translateX(40px); }
  to { opacity: 1; transform: translateX(0); }
}
</style>
