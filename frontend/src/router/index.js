import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

function isLoggedIn() {
  return !!localStorage.getItem('fabtwin_token')
}

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/Login.vue'),
  },
  {
    path: '/',
    name: 'dashboard',
    component: () => import('../views/Dashboard.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/machine/:id',
    name: 'machine-detail',
    component: () => import('../views/MachineDetail.vue'),
    props: true,
    meta: { requiresAuth: true },
  },
  {
    path: '/model-editor',
    name: 'model-editor',
    component: () => import('../views/ModelEditor.vue'),
    meta: { requiresAuth: true, requirePermission: 'model_edit' },
  },
  {
    path: '/machines',
    name: 'machine-management',
    component: () => import('../views/MachineManagement.vue'),
    meta: { requiresAuth: true, requirePermission: 'model_edit' },
  },
  {
    path: '/users',
    name: 'user-management',
    component: () => import('../views/UserManagement.vue'),
    meta: { requiresAuth: true, requirePermission: 'user_manage' },
  },
  {
    path: '/ai-config',
    name: 'ai-config',
    component: () => import('../views/AIConfigView.vue'),
    meta: { requiresAuth: true, requirePermission: 'ai_config' },
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const loggedIn = isLoggedIn()

  if (to.meta.requiresAuth && !loggedIn) {
    next('/login')
    return
  }

  if (to.path === '/login' && loggedIn) {
    next('/')
    return
  }

  // test31：权限判定统一走 auth store 的 hasPermission（含 admin 角色免检与
  // '*' 通配），消除与 store 的规则分叉——此前 router 只查 permissions 数组，
  // admin 用户若 permissions 为空数组会被路由误拒
  if (to.meta.requirePermission && loggedIn) {
    const authStore = useAuthStore()
    if (!authStore.hasPermission(to.meta.requirePermission)) {
      next('/')
      return
    }
  }

  next()
})

export default router
