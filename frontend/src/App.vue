<script setup>
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

// 处理全局AI悬浮球的跳转事件
// payload: { machine_id, timestamp } 或兼容纯字符串
function handleAIJump(payload) {
  if (!payload) return
  let mid = ''
  let ts = ''
  if (typeof payload === 'string') {
    ts = payload
  } else {
    mid = payload.machine_id || ''
    ts = payload.timestamp || ''
  }
  if (!ts) return

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
</script>

<template>
  <div class="app-shell">
    <AppHeader />
    <main class="app-main">
      <router-view />
    </main>
    <!-- 全局悬浮AI球（登录后显示） -->
    <AIFloatingBall v-if="authStore.isLoggedIn" @jump="handleAIJump" />
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
</style>
