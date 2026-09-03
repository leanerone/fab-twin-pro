import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/model-editor',
  },
  {
    path: '/model-editor',
    name: 'model-editor',
    component: () => import('../views/ModelEditor.vue'),
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
