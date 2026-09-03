<script setup>
// 独立开发版 App - 只有模型编辑器，不需要登录
</script>

<template>
  <div class="app-wrap">
    <div class="app-header">
      <span class="logo">🔧 FabTwin 模型编辑器</span>
      <span class="badge">独立开发版 · 无后端</span>
    </div>
    <router-view />
  </div>
</template>

<style scoped>
.app-wrap {
  width: 100%;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.app-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 20px;
  height: 48px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.logo {
  font-size: 16px;
  font-weight: 600;
  color: var(--primary);
}
.badge {
  font-size: 11px;
  padding: 2px 8px;
  background: rgba(74, 158, 255, 0.15);
  color: var(--primary);
  border-radius: 10px;
}
</style>
