<template>
  <header class="app-header">
    <button class="header-brand" type="button" aria-label="返回主页看板" @click="goTo('/')">
      <span class="brand-logo" aria-hidden="true">
        <svg viewBox="0 0 32 32" fill="none">
          <rect x="4" y="5" width="24" height="22" rx="3" stroke="currentColor" stroke-width="1.8"/>
          <path d="M9 21v-6m5 6V9m5 12v-9m5 9V7" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>
        </svg>
      </span>
      <span class="brand-text">
        <span class="brand-title">FabTwin <strong>Pro</strong></span>
        <span class="brand-subtitle">半导体数字孪生控制台</span>
      </span>
    </button>

    <nav class="header-nav" aria-label="主导航">
      <button
        v-for="mod in navModules"
        :key="mod.id"
        type="button"
        class="nav-item"
        :class="{ active: isActive(mod) }"
        :aria-current="isActive(mod) ? 'page' : undefined"
        @click="goTo(mod.default_route)"
      >
        <svg v-if="mod.icon === 'dashboard'" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path d="M3 16V9m5 7V4m5 12v-5m4 5V7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
        </svg>
        <svg v-else-if="mod.icon === 'machine'" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <rect x="3" y="4" width="14" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/>
          <path d="M7 8h6m-6 4h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
        <svg v-else-if="mod.icon === 'editor'" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path d="M12.8 3.6l3.6 3.6L8.6 15H5v-3.6l7.8-7.8z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
          <path d="M10.8 5.6l3.6 3.6" stroke="currentColor" stroke-width="1.5"/>
        </svg>
        <svg v-else-if="mod.icon === 'manage'" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <rect x="3" y="4" width="14" height="12" rx="2" stroke="currentColor" stroke-width="1.5"/>
          <path d="M3 8.5h14M8 8.5V16" stroke="currentColor" stroke-width="1.5"/>
        </svg>
        <svg v-else-if="mod.icon === 'ai'" viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <path d="M10 3l1.8 4.7L16.5 9.5l-4.7 1.8L10 16l-1.8-4.7L3.5 9.5l4.7-1.8L10 3z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        </svg>
        <svg v-else viewBox="0 0 20 20" fill="none" aria-hidden="true">
          <circle cx="7.5" cy="7" r="2.6" stroke="currentColor" stroke-width="1.5"/>
          <path d="M3 16.5c.4-2.8 2-4.3 4.5-4.3s4.1 1.5 4.5 4.3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          <circle cx="14.5" cy="8" r="2.1" stroke="currentColor" stroke-width="1.5"/>
          <path d="M14.2 12.4c2 .2 3.4 1.6 3.8 4.1" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
        <span>{{ mod.display_name }}</span>
      </button>
    </nav>

    <div class="header-right">
      <div class="system-status" :class="{ online: appStore.wsConnected }" role="status">
        <span class="status-dot"></span>
        <span class="system-label">{{ appStore.wsConnected ? '实时连接' : '连接中断' }}</span>
      </div>
      <time class="header-clock" :datetime="currentTime.toISOString()">{{ formattedTime }}</time>
      <div ref="userMenuRef" class="user-menu" @keydown.esc="closeUserMenu">
        <button
          ref="userButtonRef"
          class="user-btn"
          type="button"
          aria-haspopup="menu"
          :aria-expanded="showUserMenu"
          @click="showUserMenu = !showUserMenu"
        >
          <span class="user-avatar" aria-hidden="true">
            <svg viewBox="0 0 20 20" fill="none">
              <circle cx="10" cy="7" r="3" stroke="currentColor" stroke-width="1.5"/>
              <path d="M4.5 17c.5-3.3 2.3-5 5.5-5s5 1.7 5.5 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
          </span>
          <span class="user-info">
            <span class="user-name">{{ authStore.user?.name || authStore.user?.username || '未登录' }}</span>
            <span class="user-role">{{ roleLabel }}</span>
          </span>
          <svg class="user-chevron" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="m4 6 4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
        <div v-if="showUserMenu" class="user-dropdown" role="menu">
          <div class="dropdown-header">
            <strong>{{ authStore.user?.name || authStore.user?.username || '未登录' }}</strong>
            <span>{{ authStore.user?.username || '本地会话' }}</span>
          </div>
          <button class="dropdown-item" type="button" role="menuitem" @click="handleLogout">
            <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M8 4H4v12h4m3-8 4 2-4 2m4-2H7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            退出登录
          </button>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const authStore = useAuthStore()
const showUserMenu = ref(false)
const userMenuRef = ref(null)
const userButtonRef = ref(null)
const currentTime = ref(new Date())
let timer = null

const roleLabel = computed(() => ({ admin: '系统管理员', operator: '设备操作员' }[authStore.role] || authStore.role))
const formattedTime = computed(() => currentTime.value.toLocaleTimeString('zh-CN', { hour12: false }))
const machineDetailRoute = computed(() => `/machine/${appStore.selectedMachineId || 'OXE-01'}`)
// 顶部主导航：与路由表一一对应，带权限项按登录人权限过滤（路由层仍有 requirePermission 守卫兜底）
const navModules = computed(() => {
  const items = [
    { id: 'production-monitor', display_name: '主页看板', default_route: '/', icon: 'dashboard' },
    { id: 'machine-detail', display_name: '机台详情', default_route: machineDetailRoute.value, icon: 'machine' },
    { id: 'model-editor', display_name: '模型编辑器', default_route: '/model-editor', icon: 'editor', permission: 'model_edit' },
    { id: 'machine-management', display_name: '机台管理', default_route: '/machines', icon: 'manage', permission: 'model_edit' },
    { id: 'ai-config', display_name: 'AI 配置', default_route: '/ai-config', icon: 'ai', permission: 'ai_config' },
    { id: 'user-management', display_name: '用户管理', default_route: '/users', icon: 'users', permission: 'user_manage' },
  ]
  return items.filter(item => !item.permission || authStore.hasPermission(item.permission))
})

function isActive(mod) {
  if (mod.id === 'production-monitor') return route.path === '/'
  if (mod.id === 'machine-detail') return route.path.startsWith('/machine/')
  return route.path.startsWith(mod.default_route)
}
function goTo(path) { router.push(path) }
function closeUserMenu() {
  if (!showUserMenu.value) return
  showUserMenu.value = false
  userButtonRef.value?.focus()
}
function handleOutside(event) {
  if (showUserMenu.value && !userMenuRef.value?.contains(event.target)) showUserMenu.value = false
}
function handleLogout() {
  showUserMenu.value = false
  authStore.logout()
  router.push('/login')
}
watch(() => route.path, () => { showUserMenu.value = false })

onMounted(() => {
  timer = setInterval(() => { currentTime.value = new Date() }, 1000)
  document.addEventListener('pointerdown', handleOutside)
})
onUnmounted(() => {
  clearInterval(timer)
  document.removeEventListener('pointerdown', handleOutside)
})
</script>

<style scoped>
.app-header {
  position: relative;
  z-index: var(--z-header);
  height: 56px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 28px;
  padding: 0 20px;
  background: #0b121e;
  border-bottom: 1px solid var(--border);
}
.header-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 218px;
  padding: 0;
  color: var(--text);
  text-align: left;
  background: transparent;
  border: 0;
  border-radius: var(--radius-sm);
}
.brand-logo {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  color: var(--accent);
  background: rgba(0, 212, 255, 0.08);
  border: 1px solid rgba(0, 212, 255, 0.24);
  border-radius: var(--radius-md);
}
.brand-logo svg { width: 26px; height: 26px; }
.brand-text { display: flex; flex-direction: column; line-height: 1.25; }
.brand-title { font-size: 17px; font-weight: 650; letter-spacing: 0.2px; }
.brand-title strong { color: var(--accent); font-weight: 650; }
.brand-subtitle { margin-top: 3px; color: var(--text-mute); font-size: 10px; letter-spacing: 0.5px; }
.header-nav { display: flex; align-items: center; gap: 4px; }
.nav-item {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 13px;
  color: var(--text-dim);
  font-size: 13px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
}
.nav-item svg { width: 17px; height: 17px; }
.nav-item:hover { color: var(--text); background: rgba(255, 255, 255, 0.04); }
.nav-item.active { color: var(--accent); background: rgba(0, 212, 255, 0.08); border-color: rgba(0, 212, 255, 0.18); }
.header-right { display: flex; align-items: center; gap: 18px; margin-left: auto; }
.system-status { display: flex; align-items: center; gap: 7px; color: var(--text-mute); font-size: 12px; white-space: nowrap; }
.status-dot { width: 7px; height: 7px; background: var(--red); border-radius: 50%; }
.system-status.online { color: var(--text-dim); }
.system-status.online .status-dot { background: var(--green); box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.1); }
.header-clock { color: var(--text-dim); font-family: 'Consolas', monospace; font-size: 13px; }
.user-menu { position: relative; }
.user-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  padding: 4px 6px;
  color: var(--text);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
}
.user-btn:hover, .user-btn[aria-expanded="true"] { background: var(--panel-2); border-color: var(--border); }
.user-avatar { display: grid; place-items: center; width: 28px; height: 28px; color: var(--accent); background: rgba(0, 212, 255, 0.08); border-radius: var(--radius-sm); }
.user-avatar svg { width: 19px; height: 19px; }
.user-info { display: flex; flex-direction: column; align-items: flex-start; line-height: 1.3; }
.user-name { max-width: 130px; overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.user-role { margin-top: 2px; color: var(--text-mute); font-size: 10px; }
.user-chevron { width: 14px; height: 14px; color: var(--text-mute); }
.user-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 224px;
  overflow: hidden;
  background: var(--panel-2);
  border: 1px solid var(--border-2);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-panel);
}
.dropdown-header { display: flex; flex-direction: column; gap: 3px; padding: 14px; border-bottom: 1px solid var(--border); }
.dropdown-header strong { font-size: 13px; }
.dropdown-header span { overflow: hidden; color: var(--text-mute); font-size: 11px; text-overflow: ellipsis; }
.dropdown-item { display: flex; align-items: center; gap: 9px; width: 100%; padding: 11px 14px; color: var(--text-dim); font-size: 12px; text-align: left; background: transparent; border: 0; }
.dropdown-item svg { width: 17px; height: 17px; }
.dropdown-item:hover { color: var(--red); background: rgba(248, 113, 113, 0.07); }
@media (max-width: 1440px) {
  .app-header { gap: 18px; padding: 0 16px; }
  .header-brand { min-width: 190px; }
  .header-right { gap: 12px; }
  .user-role { display: none; }
}
@media (max-width: 1366px) {
  .brand-subtitle { display: none; }
  .header-brand { min-width: 164px; }
  .system-label { display: none; }
  .nav-item { padding: 0 10px; }
}
@media (max-width: 1280px) {
  .app-header { gap: 12px; padding: 0 12px; }
  .header-brand { min-width: 150px; }
  .header-right { gap: 9px; }
  .header-clock { font-size: 12px; }
  .user-name { max-width: 92px; }
}
</style>
