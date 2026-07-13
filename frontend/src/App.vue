<script setup>
import AppHeader from './components/AppHeader.vue'
import { useAppStore } from './stores/app'

// 全局 store：启动时连接 WebSocket
const appStore = useAppStore()
appStore.connectWs()
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
