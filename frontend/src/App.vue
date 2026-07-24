<script setup>
import AppHeader from './components/AppHeader.vue'
import AIFloatingBall from './components/AIFloatingBall.vue'
import { useAppStore } from './stores/app'
import { useModelStore } from './stores/model'
import { useAuthStore } from './stores/auth'

// 全局 store：启动时连接 WebSocket 并预加载机台型号配置与模型资源
const appStore = useAppStore()
const modelStore = useModelStore()
const authStore = useAuthStore()
appStore.connectWs()
modelStore.loadModels()
</script>

<template>
  <div class="app-shell">
    <AppHeader />
    <main class="app-main">
      <router-view />
    </main>
    <!-- 全局悬浮AI球（登录后显示） -->
    <AIFloatingBall v-if="authStore.isLoggedIn" />
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
