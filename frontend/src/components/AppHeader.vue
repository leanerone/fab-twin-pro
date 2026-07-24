<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAppStore } from '../stores/app'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const authStore = useAuthStore()

const clock = ref('')
const showUserMenu = ref(false)
const userMenuRef = ref(null)
let clockTimer = null

function updateClock() {
  clock.value = new Date().toTimeString().slice(0, 8)
}

function goDashboard() {
  router.push('/')
}
function goDetail() {
  const id = appStore.selectedMachineId || 'OXE-01'
  router.push(`/machine/${id}`)
}

function goModelEditor() {
  router.push('/model-editor')
}

function goUserManagement() {
  router.push('/users')
}

function goAIConfig() {
  router.push('/ai-config')
}

function toggleUserMenu() {
  showUserMenu.value = !showUserMenu.value
}

function handleLogout() {
  authStore.logout()
  window.location.hash = '#/login'
}

// 点击外部关闭菜单
function onDocClick(e) {
  if (showUserMenu.value && userMenuRef.value && !userMenuRef.value.contains(e.target)) {
    showUserMenu.value = false
  }
}

const isDashboard = computed(() => route.name === 'dashboard')
const isDetail = computed(() => route.name === 'machine-detail')
const isModelEditor = computed(() => route.name === 'model-editor')
const isUserManagement = computed(() => route.name === 'user-management')
const isAIConfig = computed(() => route.name === 'ai-config')

onMounted(() => {
  updateClock()
  clockTimer = setInterval(updateClock, 1000)
  document.addEventListener('click', onDocClick)
})
onUnmounted(() => {
  if (clockTimer) clearInterval(clockTimer)
  document.removeEventListener('click', onDocClick)
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
      <button
        v-if="authStore.hasPermission('model_edit')"
        class="nav-tab"
        :class="{ active: isModelEditor }"
        @click="goModelEditor"
      >
        模型编辑器
      </button>
      <button
        v-if="authStore.hasPermission('user_manage')"
        class="nav-tab"
        :class="{ active: isUserManagement }"
        @click="goUserManagement"
      >
        用户管理
      </button>
      <button
        v-if="authStore.hasPermission('ai_config') || authStore.isAdmin"
        class="nav-tab"
        :class="{ active: isAIConfig }"
        @click="goAIConfig"
      >
        🤖 AI配置
      </button>
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
      <div ref="userMenuRef" class="user-menu-wrapper">
        <button class="user-btn" @click="toggleUserMenu">
          <span class="user-icon">👤</span>
          <span class="user-name">{{ authStore.user?.display_name || '未登录' }}</span>
          <span class="user-role">[{{ authStore.user?.role || '-' }}]</span>
        </button>
        <div v-if="showUserMenu" class="user-dropdown">
          <div class="dropdown-item">
            <span class="item-label">用户名</span>
            <span class="item-value">{{ authStore.user?.username }}</span>
          </div>
          <div class="dropdown-item">
            <span class="item-label">角色</span>
            <span class="item-value">{{ authStore.user?.role }}</span>
          </div>
          <div class="dropdown-item">
            <span class="item-label">部门</span>
            <span class="item-value">{{ authStore.user?.department || '-' }}</span>
          </div>
          <div class="dropdown-divider"></div>
          <button class="dropdown-item logout-btn" @click="handleLogout">
            <span>🚪</span> 退出登录
          </button>
        </div>
      </div>
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
.user-menu-wrapper {
  position: relative;
  max-width: 200px;
}
.user-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: none;
  background: rgba(0, 212, 255, 0.1);
  border-radius: 6px;
  color: var(--text);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  max-width: 200px;
  overflow: hidden;
}
.user-btn:hover {
  background: rgba(0, 212, 255, 0.2);
}
.user-icon {
  font-size: 14px;
  flex-shrink: 0;
}
.user-name {
  font-weight: 600;
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.user-role {
  color: var(--accent);
  font-size: 11px;
  flex-shrink: 0;
}
.user-dropdown {
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  min-width: 180px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
  z-index: 200;
}
.dropdown-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}
.dropdown-item:hover {
  background: rgba(0, 212, 255, 0.1);
}
.item-label {
  color: var(--text-dim);
}
.item-value {
  color: var(--text);
  font-weight: 600;
}
.dropdown-divider {
  height: 1px;
  background: var(--border);
  margin: 6px 0;
}
.logout-btn {
  width: 100%;
  border: none;
  background: transparent;
  color: #ef4444;
  justify-content: center;
  gap: 6px;
}
.logout-btn:hover {
  background: rgba(239, 68, 68, 0.1);
}
</style>
