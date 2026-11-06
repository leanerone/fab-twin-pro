<template>
  <div class="login-page">
    <div class="login-container">
      <div class="login-header">
        <div class="logo-icon" aria-hidden="true">
          <svg viewBox="0 0 40 40" fill="none">
            <rect x="5" y="5" width="30" height="30" rx="5" stroke="currentColor" stroke-width="1.8"/>
            <path d="M12 27v-8m6 8V13m6 14v-6m5 6V10" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
          </svg>
        </div>
        <span class="login-eyebrow">OPERATIONS CONSOLE</span>
        <h1>FabTwin <strong>Pro</strong></h1>
        <p>半导体数字孪生系统</p>
      </div>

      <div class="login-form">
        <div v-if="!passwordMode" class="login-info">
          <div class="info-icon" aria-hidden="true">
            <svg viewBox="0 0 32 32" fill="none">
              <rect x="6" y="14" width="20" height="14" rx="3" stroke="currentColor" stroke-width="2"/>
              <path d="M10 14V9a6 6 0 0 1 12 0v5M16 20v3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </div>
          <div>
            <h2>Windows 身份登录</h2>
            <p>由受信服务器验证当前 Windows 身份，无需重复输入密码。</p>
          </div>
        </div>

        <div v-if="passwordMode" class="login-info">
          <div class="info-icon" aria-hidden="true">
            <svg viewBox="0 0 32 32" fill="none">
              <circle cx="11" cy="16" r="6" stroke="currentColor" stroke-width="2"/>
              <path d="m16 16 11 0m-4 0v4m-4-4v3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
            </svg>
          </div>
          <div>
            <h2>本地账户登录</h2>
            <p>使用管理员分配的用户名和密码进入系统。</p>
          </div>
        </div>

        <div v-if="error" class="error-message" role="alert">{{ error }}</div>

        <button v-if="!passwordMode" class="login-btn login-btn-primary" :disabled="loggingIn" @click="handleWindowsLogin">
          <span v-if="loggingIn" class="spinner" aria-hidden="true"></span>
          {{ loggingIn ? '正在验证身份…' : '使用 Windows 身份登录' }}
        </button>

        <template v-if="passwordMode">
          <div class="input-group">
            <label for="login-username">用户名</label>
            <input id="login-username" v-model="username" type="text" autocomplete="username" placeholder="请输入用户名" :disabled="loggingIn" @keyup.enter="handleAdminLogin" />
          </div>
          <div class="input-group">
            <label for="login-password">密码</label>
            <div class="password-input">
              <input id="login-password" v-model="password" :type="showPassword ? 'text' : 'password'" autocomplete="current-password" placeholder="请输入密码" :disabled="loggingIn" @keyup.enter="handleAdminLogin" />
              <button class="toggle-password" type="button" :aria-label="showPassword ? '隐藏密码' : '显示密码'" :aria-pressed="showPassword" :disabled="loggingIn" @click="showPassword = !showPassword">
                <svg v-if="showPassword" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M3 3l18 18M10.6 10.6a2 2 0 0 0 2.8 2.8M9.9 4.3A10.8 10.8 0 0 1 12 4c5.5 0 10 8 10 8a18 18 0 0 1-2.1 3.1M6.6 6.6C3.7 8.6 2 12 2 12s4.5 8 10 8a9.8 9.8 0 0 0 4.1-.9" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                <svg v-else viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d="M2 12s4.5-8 10-8 10 8 10 8-4.5 8-10 8S2 12 2 12Z" stroke="currentColor" stroke-width="1.8"/>
                  <circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.8"/>
                </svg>
              </button>
            </div>
          </div>
          <button class="login-btn login-btn-primary" :disabled="loggingIn || !username || !password" @click="handleAdminLogin">
            <span v-if="loggingIn" class="spinner" aria-hidden="true"></span>
            {{ loggingIn ? '登录中…' : '登录系统' }}
          </button>
        </template>

        <div class="divider"><span>其他方式</span></div>
        <button v-if="!passwordMode" class="login-btn login-btn-secondary" :disabled="loggingIn" @click="passwordMode = true">
          使用本地账户
        </button>
        <button v-else class="login-btn login-btn-secondary" :disabled="loggingIn" @click="passwordMode = false; error = ''">
          返回 Windows 登录
        </button>
      </div>

      <div class="login-footer">
        <span class="footer-status" aria-hidden="true"></span>
        <p>受信身份验证 · 加密凭据存储 · 会话隔离</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/api'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()
const passwordMode = ref(false)
const username = ref('')
const password = ref('')
const showPassword = ref(false)
const error = ref('')
const loggingIn = ref(false)

async function handleWindowsLogin() {
  if (loggingIn.value) return
  error.value = ''
  loggingIn.value = true
  try {
    const result = await api.loginWindows()
    if (result.need_password_login) {
      passwordMode.value = true
      error.value = '当前环境未启用 Windows 登录，请使用本地账户。'
      return
    }
    if (result.token) {
      authStore.login(result.token, result.user, result.permissions)
      await router.push('/')
    } else {
      error.value = result.error || 'Windows 身份验证失败，请改用本地账户。'
    }
  } catch (e) {
    error.value = e.message || 'Windows 身份验证失败，请改用本地账户。'
  } finally {
    loggingIn.value = false
  }
}

async function handleAdminLogin() {
  if (loggingIn.value) return
  error.value = ''
  if (!username.value || !password.value) {
    error.value = '请输入用户名和密码。'
    return
  }
  loggingIn.value = true
  try {
    const result = await api.loginWithPassword(username.value, password.value)
    if (result.token) {
      authStore.login(result.token, result.user, result.permissions)
      await router.push('/')
    } else {
      error.value = result.error || '用户名或密码错误。'
    }
  } catch (e) {
    error.value = e.message || '登录失败，请检查网络连接。'
  } finally {
    loggingIn.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100%;
  padding: 28px 20px;
  background:
    radial-gradient(circle at 50% 15%, rgba(0, 212, 255, 0.08), transparent 35%),
    linear-gradient(145deg, #070b13 0%, #0a1220 60%, #080d16 100%);
}
.login-container {
  width: min(100%, 440px);
  padding: 30px 34px 24px;
  background: rgba(14, 22, 35, 0.97);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-panel);
}
.login-header { margin-bottom: 26px; text-align: center; }
.logo-icon {
  display: grid;
  place-items: center;
  width: 54px;
  height: 54px;
  margin: 0 auto 15px;
  color: var(--accent);
  background: rgba(0, 212, 255, 0.07);
  border: 1px solid rgba(0, 212, 255, 0.22);
  border-radius: var(--radius-md);
}
.logo-icon svg { width: 40px; height: 40px; }
.login-eyebrow { display: block; margin-bottom: 5px; color: var(--text-mute); font-size: 9px; font-weight: 600; letter-spacing: 2px; }
.login-header h1 { font-size: 29px; font-weight: 650; letter-spacing: -0.5px; }
.login-header h1 strong { color: var(--accent); font-weight: 650; }
.login-header p { margin-top: 5px; color: var(--text-dim); font-size: 13px; }
.login-form { display: flex; flex-direction: column; gap: 15px; }
.login-info { display: grid; grid-template-columns: 36px 1fr; gap: 12px; align-items: start; padding: 15px; background: #101b2a; border: 1px solid var(--border); border-radius: var(--radius-md); }
.info-icon { display: grid; place-items: center; width: 34px; height: 34px; color: var(--accent); }
.info-icon svg { width: 30px; height: 30px; }
.login-info h2 { margin: 0 0 4px; font-size: 14px; font-weight: 600; }
.login-info p { color: var(--text-dim); font-size: 12px; line-height: 1.55; }
.error-message { padding: 10px 12px; color: #fca5a5; font-size: 12px; line-height: 1.5; background: rgba(248, 113, 113, 0.08); border: 1px solid rgba(248, 113, 113, 0.3); border-radius: var(--radius-sm); }
.login-btn { display: inline-flex; align-items: center; justify-content: center; gap: 9px; min-height: var(--control-lg); padding: 0 18px; font-size: 13px; font-weight: 600; border-radius: var(--radius-md); }
.login-btn-primary { color: #04131a; background: var(--accent); border: 1px solid var(--accent); }
.login-btn-primary:hover:not(:disabled) { background: var(--accent-hover); border-color: var(--accent-hover); box-shadow: 0 4px 16px rgba(0, 212, 255, 0.16); }
.login-btn-primary:disabled { color: var(--text-mute); background: var(--panel-3); border-color: var(--border); }
.login-btn-secondary { color: var(--text-dim); background: transparent; border: 1px solid var(--border-2); }
.login-btn-secondary:hover:not(:disabled) { color: var(--text); background: var(--panel-2); border-color: var(--text-mute); }
.spinner { width: 15px; height: 15px; border: 2px solid rgba(4, 19, 26, 0.3); border-top-color: #04131a; border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.divider { display: flex; align-items: center; gap: 12px; color: var(--text-mute); font-size: 11px; }
.divider::before, .divider::after { content: ''; flex: 1; height: 1px; background: var(--border); }
.input-group { display: flex; flex-direction: column; gap: 6px; }
.input-group label { color: var(--text-dim); font-size: 12px; font-weight: 500; }
.input-group input { width: 100%; height: var(--control-lg); padding: 0 12px; color: var(--text); font-size: 13px; background: #0a111d; border: 1px solid var(--border-2); border-radius: var(--radius-sm); outline: none; }
.input-group input::placeholder { color: var(--text-mute); }
.input-group input:focus { border-color: var(--accent); }
.password-input { position: relative; }
.password-input input { padding-right: 44px; }
.toggle-password { position: absolute; top: 4px; right: 4px; display: grid; place-items: center; width: 34px; height: 34px; padding: 0; color: var(--text-mute); background: transparent; border: 0; border-radius: var(--radius-sm); }
.toggle-password:hover:not(:disabled) { color: var(--accent); background: rgba(0, 212, 255, 0.06); }
.toggle-password svg { width: 19px; height: 19px; }
.login-footer { display: flex; align-items: center; justify-content: center; gap: 7px; margin-top: 24px; padding-top: 17px; color: var(--text-mute); font-size: 10px; border-top: 1px solid var(--border); }
.footer-status { width: 5px; height: 5px; background: var(--green); border-radius: 50%; }
@media (max-height: 800px) {
  .login-page { padding: 18px; }
  .login-container { padding: 22px 30px 18px; }
  .login-header { margin-bottom: 18px; }
  .logo-icon { width: 46px; height: 46px; margin-bottom: 10px; }
  .logo-icon svg { width: 34px; height: 34px; }
  .login-form { gap: 12px; }
  .login-footer { margin-top: 18px; padding-top: 13px; }
}
@media (max-width: 480px) {
  .login-container { padding: 24px 20px; }
}
@media (prefers-reduced-motion: reduce) {
  .spinner { animation-duration: 1.8s; }
}
</style>
