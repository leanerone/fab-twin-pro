<script setup>
import AppHeader from './components/AppHeader.vue'
import { useAppStore } from './stores/app'
import { useModelStore } from './stores/model'

// 全局 store：启动时连接 WebSocket 并预加载机台型号配置与模型资源
const appStore = useAppStore()
const modelStore = useModelStore()
appStore.connectWs()
modelStore.loadModels()
</script>

<template>
  <div class="app-shell">
    <AppHeader />
    <main class="app-main">
      <router-view />
    </main>
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
}
</style>
