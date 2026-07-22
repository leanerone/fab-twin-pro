<template>
  <div class="login-page">
    <div class="login-container">
      <div class="login-header">
        <div class="logo">
          <div class="logo-icon">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect x="4" y="8" width="40" height="32" rx="4" fill="#1e3a5f"/>
              <rect x="8" y="12" width="32" height="24" rx="2" fill="#0f2942"/>
              <rect x="12" y="16" width="8" height="16" rx="1" fill="#00d4ff"/>
              <rect x="22" y="16" width="8" height="16" rx="1" fill="#22c55e"/>
              <rect x="32" y="16" width="4" height="16" rx="1" fill="#f59e0b"/>
            </svg>
          </div>
          <div class="logo-text">
            <h1>FabTwin</h1>
            <p>半导体厂数字孪生系统</p>
          </div>
        </div>
      </div>

      <div class="login-form">
        <!-- Windows NT 登录模式（默认） -->
        <template v-if="!passwordMode">
          <div v-if="!loggingIn" class="login-info">
            <div class="info-icon">🔐</div>
            <h2>Windows NT 自动登录</h2>
            <p>系统将自动获取您的 Windows 域账号进行身份验证</p>
          </div>

          <div v-else class="loading-state">
            <div class="spinner"></div>
            <p>正在验证身份...</p>
          </div>

          <button
            v-if="!loggingIn"
            @click="handleNtLogin"
            class="login-btn"
          >
            登录系统
          </button>

          <div class="divider">
            <span>或</span>
          </div>

          <button
            v-if="!loggingIn"
            @click="passwordMode = true"
            class="admin-btn"
          >
            账号密码登录
          </button>
        </template>

        <!-- 账号密码登录模式 -->
        <template v-else>
          <div v-if="!loggingIn" class="login-info">
            <div class="info-icon">🔑</div>
            <h2>账号密码登录</h2>
            <p>请输入您的工号和密码进行身份验证</p>
          </div>

          <div v-else class="loading-state">
            <div class="spinner"></div>
            <p>正在验证身份...</p>
          </div>

          <div class="input-group">
            <label>用户名</label>
            <input v-model="username" type="text" placeholder="请输入用户名" @keyup.enter="handleAdminLogin" />
          </div>

          <div class="input-group">
            <label>密码</label>
            <div class="password-wrapper">
              <input v-model="password" :type="showPassword ? 'text' : 'password'" placeholder="请输入密码" @keyup.enter="handleAdminLogin" />
              <button type="button" class="toggle-pwd" @click="showPassword = !showPassword">
                {{ showPassword ? '隐藏' : '显示' }}
              </button>
            </div>
          </div>

          <button
            v-if="!loggingIn"
            @click="handleAdminLogin"
            class="login-btn"
          >
            登录
          </button>

          <button
            v-if="!loggingIn"
            @click="backToNt"
            class="back-btn"
          >
            返回 NT 登录
          </button>
        </template>

        <div v-if="error" class="error-message">
          {{ error }}
        </div>
      </div>

      <div class="login-footer">
        <p>FabTwin v1.0 · 半导体数字孪生平台</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const loggingIn = ref(false)
const error = ref('')
const passwordMode = ref(false)
const username = ref('')
const password = ref('')
const showPassword = ref(false)

async function handleNtLogin() {
  loggingIn.value = true
  error.value = ''

  try {
    const aspResult = await api.getWindowsUser()
    if (!aspResult.success || !aspResult.username) {
      passwordMode.value = true
      error.value = '无法获取Windows用户名，请使用账号密码登录'
      loggingIn.value = false
      return
    }
    
    const result = await api.loginWindows(aspResult.username)
    if (result.token) {
      authStore.login(result.token, result.user, result.permissions)
      await router.push('/')
    } else {
      error.value = '登录失败，请联系管理员'
    }
  } catch (e) {
    console.error('NT Login error:', e)
    error.value = 'Windows登录失败，请尝试账号密码登录: ' + e.message
    passwordMode.value = true
  } finally {
    loggingIn.value = false
  }
}

async function handleAdminLogin() {
  if (!username.value || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  loggingIn.value = true
  error.value = ''

  try {
    const result = await api.loginWithPassword(username.value, password.value)
    if (result.token) {
      authStore.login(result.token, result.user, result.permissions)
      console.log('[Login] Token saved:', localStorage.getItem('fabtwin_token'))
      console.log('[Login] Router pushing to /')
      await router.push('/')
      console.log('[Login] Router pushed, current path:', router.currentRoute.value.path)
    } else {
      error.value = '登录失败，用户名或密码错误'
    }
  } catch (e) {
    console.error('Login error:', e)
    error.value = '用户名或密码错误'
  } finally {
    loggingIn.value = false
  }
}

function backToNt() {
  passwordMode.value = false
  error.value = ''
  username.value = ''
  password.value = ''
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0a1628 0%, #1e3a5f 100%);
  padding: 20px;
}

.login-container {
  width: 100%;
  max-width: 420px;
  background: rgba(15, 37, 66, 0.95);
  border-radius: 16px;
  padding: 40px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
  border: 1px solid rgba(0, 212, 255, 0.2);
}

.login-header {
  text-align: center;
  margin-bottom: 30px;
}

.logo {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.logo-icon {
  width: 64px;
  height: 64px;
}

.logo-text h1 {
  font-size: 28px;
  font-weight: 700;
  color: #00d4ff;
  margin: 0;
}

.logo-text p {
  font-size: 13px;
  color: #64748b;
  margin: 4px 0 0 0;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.login-info {
  text-align: center;
  padding: 20px;
  background: rgba(0, 212, 255, 0.05);
  border-radius: 12px;
  border: 1px solid rgba(0, 212, 255, 0.2);
}

.info-icon {
  font-size: 48px;
  margin-bottom: 12px;
}

.login-info h2 {
  font-size: 18px;
  color: #ffffff;
  margin: 0 0 8px 0;
}

.login-info p {
  font-size: 13px;
  color: #94a3b8;
  margin: 0;
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 20px;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid rgba(0, 212, 255, 0.2);
  border-top-color: #00d4ff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-state p {
  color: #94a3b8;
  font-size: 14px;
}

.login-btn {
  width: 100%;
  padding: 14px 24px;
  font-size: 16px;
  font-weight: 600;
  color: #ffffff;
  background: linear-gradient(135deg, #00d4ff 0%, #0ea5e9 100%);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.login-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 25px rgba(0, 212, 255, 0.4);
}

.login-btn:active {
  transform: translateY(0);
}

.admin-btn {
  width: 100%;
  padding: 12px 24px;
  font-size: 14px;
  font-weight: 500;
  color: #94a3b8;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.admin-btn:hover {
  color: #ffffff;
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.2);
}

.back-btn {
  width: 100%;
  padding: 12px 24px;
  font-size: 14px;
  font-weight: 500;
  color: #94a3b8;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.back-btn:hover {
  color: #ffffff;
  border-color: rgba(255, 255, 255, 0.2);
}

.divider {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #64748b;
  font-size: 12px;
}

.divider::before,
.divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: rgba(255, 255, 255, 0.1);
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input-group label {
  font-size: 13px;
  color: #94a3b8;
  font-weight: 500;
}

.input-group input {
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  color: #ffffff;
  font-size: 14px;
  outline: none;
  transition: all 0.3s;
}

.input-group input:focus {
  border-color: #00d4ff;
  box-shadow: 0 0 0 3px rgba(0, 212, 255, 0.1);
}

.input-group input::placeholder {
  color: #64748b;
}

.password-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.password-wrapper input {
  flex: 1;
  width: 100%;
  padding: 12px 60px 12px 16px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  color: #ffffff;
  font-size: 14px;
  outline: none;
  transition: all 0.3s;
}

.password-wrapper input:focus {
  border-color: #00d4ff;
  box-shadow: 0 0 0 3px rgba(0, 212, 255, 0.1);
}

.password-wrapper input::placeholder {
  color: #64748b;
}

.toggle-pwd {
  position: absolute;
  right: 8px;
  padding: 4px 10px;
  font-size: 12px;
  color: #00d4ff;
  background: rgba(0, 212, 255, 0.1);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.2s;
}

.toggle-pwd:hover {
  background: rgba(0, 212, 255, 0.2);
}

.error-message {
  padding: 12px 16px;
  background: rgba(239, 68, 68, 0.15);
  border-radius: 8px;
  color: #ef4444;
  font-size: 13px;
  text-align: center;
}

.login-footer {
  text-align: center;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.login-footer p {
  font-size: 12px;
  color: #64748b;
  margin: 0;
}
</style>
