import { defineStore } from 'pinia'
import { ref } from 'vue'

// 简化版 auth store - 独立开发版不需要真实登录
export const useAuthStore = defineStore('auth', () => {
  const user = ref({
    username: 'dev',
    role: 'admin',
    permissions: ['model_edit', 'user_manage', 'ai_config'],
  })

  return { user }
})
