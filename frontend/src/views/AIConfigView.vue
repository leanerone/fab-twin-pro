<script setup>
import { ref } from 'vue'
import AIConfigPanel from '../components/AIConfigPanel.vue'

const panelRef = ref(null)
</script>

<template>
  <div class="ai-config-view">
    <div class="page-header">
      <h2>🤖 AI 配置管理</h2>
      <p class="sub-title">管理 AI Provider、模型配置、Token 使用量统计</p>
    </div>
    <div class="panel-wrapper">
      <AIConfigPanel ref="panelRef" full-page />
    </div>
  </div>
</template>

<style scoped>
.ai-config-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 20px;
  box-sizing: border-box;
  overflow: hidden;
}
.page-header {
  flex-shrink: 0;
  margin-bottom: 16px;
}
.page-header h2 {
  margin: 0 0 4px;
  font-size: 18px;
  color: var(--text, #e0e6ed);
}
.sub-title {
  margin: 0;
  font-size: 12px;
  color: var(--text-dim, #8a94a6);
}
.panel-wrapper {
  flex: 1;
  min-height: 0;
  border: 1px solid var(--border, #2a3142);
  border-radius: 10px;
  overflow: hidden;
  background: var(--bg-card, #1a1f2e);
}
</style>
