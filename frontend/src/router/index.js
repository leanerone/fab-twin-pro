import { createRouter, createWebHashHistory } from 'vue-router'

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
  const token = localStorage.getItem('fabtwin_token')
  console.log('[Router Guard] to:', to.path, 'from:', from.path, 'loggedIn:', loggedIn, 'token:', token ? 'exists' : 'null')

  if (to.meta.requiresAuth && !loggedIn) {
    console.log('[Router Guard] Requires auth but not logged in, redirecting to /login')
    next('/login')
    return
  }

  if (to.path === '/login' && loggedIn) {
    console.log('[Router Guard] Already logged in, redirecting to /')
    next('/')
    return
  }

  if (to.meta.requirePermission && loggedIn) {
    const perms = JSON.parse(localStorage.getItem('fabtwin_permissions') || '[]')
    if (!perms.includes('*') && !perms.includes(to.meta.requirePermission)) {
      next('/')
      return
    }
  }

  next()
})

export default router
