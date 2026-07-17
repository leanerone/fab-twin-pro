import { ref, computed } from 'vue'

const user = ref(null)
const permissions = ref([])
const isLoggedIn = ref(false)

function loadUser() {
  const storedUser = localStorage.getItem('fabtwin_user')
  const storedPerms = localStorage.getItem('fabtwin_permissions')
  const token = localStorage.getItem('fabtwin_token')
  console.log('[useAuth] loadUser called, token:', !!token)

  if (token) {
    isLoggedIn.value = true
    if (storedUser) {
      try {
        user.value = JSON.parse(storedUser)
        console.log('[useAuth] user loaded:', user.value)
      } catch { user.value = null }
    }
    if (storedPerms) {
      try { permissions.value = JSON.parse(storedPerms) } catch { permissions.value = [] }
    }
  } else {
    isLoggedIn.value = false
    user.value = null
    permissions.value = []
    console.log('[useAuth] no token found')
  }
}

loadUser()

// 监听其他标签页的登录状态变化
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key === 'fabtwin_token' || e.key === 'fabtwin_user') {
      loadUser()
    }
  })
}

export function useAuth() {
  function hasPermission(permId) {
    if (!isLoggedIn.value) return false
    if (user.value?.role === 'admin') return true
    return permissions.value.includes(permId)
  }

  const isAdmin = computed(() => {
    return user.value?.role === 'admin'
  })

  const isEngineer = computed(() => {
    return user.value?.role === 'engineer'
  })

  const isUser = computed(() => {
    return user.value?.role === 'user'
  })

  function logout() {
    localStorage.removeItem('fabtwin_token')
    localStorage.removeItem('fabtwin_user')
    localStorage.removeItem('fabtwin_permissions')
    isLoggedIn.value = false
    user.value = null
    permissions.value = []
    window.location.hash = '#/login'
  }

  function refreshUser(newUser, newPerms) {
    user.value = newUser
    permissions.value = newPerms
    localStorage.setItem('fabtwin_user', JSON.stringify(newUser))
    localStorage.setItem('fabtwin_permissions', JSON.stringify(newPerms))
  }

  return {
    user,
    permissions,
    isLoggedIn,
    hasPermission,
    isAdmin,
    isEngineer,
    isUser,
    logout,
    refreshUser,
    loadUser,
  }
}