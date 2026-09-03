import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// 简化版 auth store - 独立开发版不需要真实登录
export const useAuthStore = defineStore('auth', () => {
  const user = ref({
    username: 'dev',
    role: 'admin',
    permissions: ['model_edit', 'user_manage', 'ai_config'],
  })

  const isAdmin = computed(() => user.value.role === 'admin')

  function hasPermission(perm) {
    return user.value.permissions.includes(perm)
  }

  function hasRole(role) {
    return user.value.role === role
  }

  return { user, isAdmin, hasPermission, hasRole }
})
