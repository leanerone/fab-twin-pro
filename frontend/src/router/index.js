import { createRouter, createWebHashHistory } from 'vue-router'

// 路由配置：主页看板 / 机台详情 / 模型编辑器
const routes = [
  {
    path: '/',
    name: 'dashboard',
    component: () => import('../views/Dashboard.vue'),
  },
  {
    path: '/machine/:id',
    name: 'machine-detail',
    component: () => import('../views/MachineDetail.vue'),
    props: true,
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
