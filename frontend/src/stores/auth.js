import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const permissions = ref([])
  const isLoggedIn = ref(false)

  function loadUser() {
    const storedUser = localStorage.getItem('fabtwin_user')
    const storedPerms = localStorage.getItem('fabtwin_permissions')
    const token = localStorage.getItem('fabtwin_token')

    if (token) {
      isLoggedIn.value = true
      if (storedUser) {
        try { user.value = JSON.parse(storedUser) } catch { user.value = null }
      }
      if (storedPerms) {
        try { permissions.value = JSON.parse(storedPerms) } catch { permissions.value = [] }
      }
    } else {
      isLoggedIn.value = false
      user.value = null
      permissions.value = []
    }
  }

  function login(token, userData, perms) {
    localStorage.setItem('fabtwin_token', token)
    localStorage.setItem('fabtwin_user', JSON.stringify(userData))
    localStorage.setItem('fabtwin_permissions', JSON.stringify(perms))
    isLoggedIn.value = true
    user.value = userData
    permissions.value = perms
  }

  function logout() {
    localStorage.removeItem('fabtwin_token')
    localStorage.removeItem('fabtwin_user')
    localStorage.removeItem('fabtwin_permissions')
    isLoggedIn.value = false
    user.value = null
    permissions.value = []
  }

  const hasPermission = computed(() => (permId) => {
    if (!isLoggedIn.value) return false
    if (user.value?.role === 'admin') return true
    // 支持 * 通配符（admin 默认全权限）
    if (permissions.value.includes('*')) return true
    return permissions.value.includes(permId)
  })

  const isAdmin = computed(() => user.value?.role === 'admin')
  const isEngineer = computed(() => user.value?.role === 'engineer')
  const isUser = computed(() => user.value?.role === 'user')

  // 初始化时加载
  loadUser()

  return {
    user,
    permissions,
    isLoggedIn,
    hasPermission,
    isAdmin,
    isEngineer,
    isUser,
    loadUser,
    login,
    logout,
  }
})