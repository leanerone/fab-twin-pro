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
    path: '/users',
    name: 'user-management',
    component: () => import('../views/UserManagement.vue'),
    meta: { requiresAuth: true, requirePermission: 'user_manage' },
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  if (to.meta.requiresAuth && !isLoggedIn()) {
    next('/login')
    return
  }

  if (to.path === '/login' && isLoggedIn()) {
    next('/')
    return
  }

  if (to.meta.requirePermission && isLoggedIn()) {
    const perms = JSON.parse(localStorage.getItem('fabtwin_permissions') || '[]')
    if (!perms.includes('*') && !perms.includes(to.meta.requirePermission)) {
      next('/')
      return
    }
  }

  next()
})

export default router
