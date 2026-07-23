<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api'

const emit = defineEmits(['close'])

const loading = ref(false)
const testing = ref('')
const activeTab = ref('provider')
const toast = ref({ show: false, type: 'info', msg: '' })

const config = ref({
  provider: 'local',
  base_url: '',
  api_key: '',
  model: 'glm-5.2',
  temperature: 0.7,
  max_tokens: 2048,
  dify_enabled: false,
  dify_base_url: '',
  dify_api_key: '',
  dify_app_id: '',
  n8n_enabled: false,
  n8n_base_url: '',
  n8n_webhook_secret: '',
})

const providerOptions = [
  { value: 'local', label: '本地规则引擎（默认，无需配置）' },
  { value: 'openai', label: 'OpenAI 兼容模型（GLM/GPT/本地私有化）' },
  { value: 'dify', label: 'Dify 应用' },
  { value: 'hybrid', label: '混合模式（Dify优先，失败回退本地）' },
]

function showToast(type, msg) {
  toast.value = { show: true, type, msg }
  setTimeout(() => { toast.value.show = false }, 3000)
}

async function loadConfig() {
  loading.value = true
  try {
    const data = await api.aiGetConfig()
    config.value.provider = data.provider
    config.value.model = data.model
    config.value.temperature = data.temperature
    config.value.max_tokens = data.max_tokens
    config.value.dify_enabled = data.dify_enabled
    config.value.n8n_enabled = data.n8n_enabled
  } catch (e) {
    showToast('error', '加载配置失败')
  } finally {
    loading.value = false
  }
}

async function saveConfig() {
  loading.value = true
  try {
    // 始终发送所有字段（包括空字符串），确保后端能正确更新 provider 等关键字段
    const data = { ...config.value }
    // 只过滤掉 null/undefined，保留空字符串（让后端知道用户清空了某个字段）
    Object.keys(data).forEach(key => {
      if (data[key] === null || data[key] === undefined) {
        delete data[key]
      }
    })
    await api.aiUpdateConfig(data)
    showToast('success', '配置保存成功（运行时生效，重启后需在 env 中持久化）')
  } catch (e) {
    showToast('error', '保存失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function testConnection(type) {
  testing.value = type
  try {
    let testConfig = {}
    if (type === 'openai') {
      testConfig = {
        base_url: config.value.base_url,
        api_key: config.value.api_key,
        model: config.value.model,
      }
    } else if (type === 'dify') {
      testConfig = {
        base_url: config.value.dify_base_url,
        api_key: config.value.dify_api_key,
      }
    } else if (type === 'n8n') {
      testConfig = {
        base_url: config.value.n8n_base_url,
      }
    }
    const result = await api.aiTestConnection(type, testConfig)
    if (result.success) {
      showToast('success', result.message || '连接成功')
    } else {
      showToast('error', result.message || '连接失败')
    }
  } catch (e) {
    showToast('error', '测试失败：' + (e.message || '未知错误'))
  } finally {
    testing.value = ''
  }
}

onMounted(() => {
  loadConfig()
})
</script>

<template>
  <div class="ai-config-panel">
    <div class="config-header">
      <span class="title">AI 配置中心</span>
      <span class="close-btn" @click="emit('close')">✕</span>
    </div>

    <!-- Toast 提示 -->
    <transition name="toast">
      <div v-if="toast.show" :class="['toast', toast.type]">{{ toast.msg }}</div>
    </transition>

    <!-- 标签页导航 -->
    <div class="tab-nav">
      <div v-for="tab in [
        { name: 'provider', label: '全局设置' },
        { name: 'openai', label: '大模型' },
        { name: 'dify', label: 'Dify' },
        { name: 'n8n', label: 'N8N 自动化' },
      ]" :key="tab.name"
        :class="['tab-item', { active: activeTab === tab.name }]"
        @click="activeTab = tab.name">
        {{ tab.label }}
      </div>
    </div>

    <div class="tab-content">
      <!-- 全局设置 -->
      <div v-show="activeTab === 'provider'" class="tab-pane">
        <div class="form-group">
          <label>AI 提供方</label>
          <select v-model="config.provider" class="form-input">
            <option v-for="opt in providerOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </div>
        <div class="hint">
          切换 AI 服务提供方。本地规则引擎无需配置，其他模式需在对应标签页填写配置。
        </div>
      </div>

      <!-- OpenAI兼容模型 -->
      <div v-show="activeTab === 'openai'" class="tab-pane">
        <div class="form-group">
          <label>API 地址</label>
          <input v-model="config.base_url" class="form-input" placeholder="如：https://open.bigmodel.cn/api/paas/v4" />
          <div class="hint">支持所有 OpenAI 兼容接口：智谱GLM、GPT系列、本地私有化模型等</div>
        </div>
        <div class="form-group">
          <label>API Key</label>
          <input v-model="config.api_key" type="password" class="form-input" placeholder="输入API密钥" />
        </div>
        <div class="form-group">
          <label>模型名称</label>
          <input v-model="config.model" class="form-input" placeholder="如：glm-5.2 / gpt-4o / qwen-plus" />
        </div>
        <div class="form-row">
          <div class="form-group half">
            <label>温度 ({{ config.temperature }})</label>
            <input type="range" v-model.number="config.temperature" min="0" max="1" step="0.1" class="form-range" />
          </div>
          <div class="form-group half">
            <label>最大 Token</label>
            <input type="number" v-model.number="config.max_tokens" min="128" max="8192" step="128" class="form-input" />
          </div>
        </div>
        <button class="btn btn-primary" :disabled="testing === 'openai'" @click="testConnection('openai')">
          {{ testing === 'openai' ? '测试中...' : '测试连接' }}
        </button>
      </div>

      <!-- Dify -->
      <div v-show="activeTab === 'dify'" class="tab-pane">
        <div class="form-group">
          <label class="switch-label">
            <input type="checkbox" v-model="config.dify_enabled" />
            <span>启用 Dify</span>
          </label>
        </div>
        <div class="form-group" :class="{ disabled: !config.dify_enabled }">
          <label>Dify API 地址</label>
          <input v-model="config.dify_base_url" :disabled="!config.dify_enabled" class="form-input" placeholder="如：http://localhost:3000/v1" />
        </div>
        <div class="form-group" :class="{ disabled: !config.dify_enabled }">
          <label>Dify API Key</label>
          <input v-model="config.dify_api_key" :disabled="!config.dify_enabled" type="password" class="form-input" placeholder="输入Dify应用密钥" />
        </div>
        <div class="form-group" :class="{ disabled: !config.dify_enabled }">
          <label>应用 ID</label>
          <input v-model="config.dify_app_id" :disabled="!config.dify_enabled" class="form-input" placeholder="输入Dify应用ID" />
        </div>
        <button class="btn btn-primary" :disabled="testing === 'dify' || !config.dify_enabled" @click="testConnection('dify')">
          {{ testing === 'dify' ? '测试中...' : '测试连接' }}
        </button>
        <div class="hint">
          通过 MCP 协议绑定 Dify 应用，支持调用预设工业智能应用：
          设备故障诊断、工艺参数解读、EAP日志解析等。
        </div>
      </div>

      <!-- N8N -->
      <div v-show="activeTab === 'n8n'" class="tab-pane">
        <div class="form-group">
          <label class="switch-label">
            <input type="checkbox" v-model="config.n8n_enabled" />
            <span>启用 N8N</span>
          </label>
        </div>
        <div class="form-group" :class="{ disabled: !config.n8n_enabled }">
          <label>N8N 服务地址</label>
          <input v-model="config.n8n_base_url" :disabled="!config.n8n_enabled" class="form-input" placeholder="如：http://localhost:5678" />
        </div>
        <div class="form-group" :class="{ disabled: !config.n8n_enabled }">
          <label>Webhook 密钥</label>
          <input v-model="config.n8n_webhook_secret" :disabled="!config.n8n_enabled" type="password" class="form-input" placeholder="可选，Webhook验证密钥" />
        </div>
        <button class="btn btn-primary" :disabled="testing === 'n8n' || !config.n8n_enabled" @click="testConnection('n8n')">
          {{ testing === 'n8n' ? '测试中...' : '测试连接' }}
        </button>
        <div class="hint">
          MCP 协议转发 AI 指令至 N8N Webhook，触发自动化工作流：
          异常工单自动生成、设备数据批量导出、产线报表自动推送等。
        </div>
      </div>
    </div>

    <div class="config-footer">
      <button class="btn" @click="emit('close')">取消</button>
      <button class="btn btn-primary" :disabled="loading" @click="saveConfig">
        {{ loading ? '保存中...' : '保存配置' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.ai-config-panel {
  width: 520px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-card, #1a1f2e);
  border: 1px solid var(--border, #2a3142);
  border-radius: 10px;
  overflow: hidden;
  position: relative;
}

.config-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border, #2a3142);
  background: rgba(0, 212, 255, 0.05);
}

.config-header .title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text, #e0e6ed);
}

.close-btn {
  cursor: pointer;
  color: var(--text-dim, #8a94a6);
  font-size: 16px;
  padding: 4px 8px;
  border-radius: 4px;
}
.close-btn:hover {
  background: rgba(255,255,255,0.08);
  color: var(--text, #e0e6ed);
}

/* Toast */
.toast {
  position: absolute;
  top: 60px;
  left: 50%;
  transform: translateX(-50%);
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  z-index: 100;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}
.toast.success { background: #2ecc71; color: #fff; }
.toast.error { background: #e74c3c; color: #fff; }
.toast.info { background: #3498db; color: #fff; }

.toast-enter-active, .toast-leave-active {
  transition: opacity 0.3s, transform 0.3s;
}
.toast-enter-from, .toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-10px);
}

/* 标签页 */
.tab-nav {
  display: flex;
  border-bottom: 1px solid var(--border, #2a3142);
  background: rgba(0,0,0,0.15);
}
.tab-item {
  flex: 1;
  padding: 10px 8px;
  text-align: center;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-dim, #8a94a6);
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}
.tab-item:hover {
  color: var(--text, #e0e6ed);
}
.tab-item.active {
  color: #00d4ff;
  border-bottom-color: #00d4ff;
  background: rgba(0, 212, 255, 0.05);
}

.tab-content {
  flex: 1;
  overflow-y: auto;
  padding: 18px;
}

.form-group {
  margin-bottom: 16px;
}
.form-group label {
  display: block;
  font-size: 12px;
  color: var(--text-dim, #8a94a6);
  margin-bottom: 6px;
  font-weight: 500;
}
.form-group.disabled {
  opacity: 0.5;
}

.form-input {
  width: 100%;
  padding: 8px 10px;
  background: var(--bg, #0f1419);
  border: 1px solid var(--border, #2a3142);
  border-radius: 4px;
  color: var(--text, #e0e6ed);
  font-size: 13px;
  box-sizing: border-box;
}
.form-input:focus {
  outline: none;
  border-color: #00d4ff;
}
.form-input:disabled {
  cursor: not-allowed;
}

.form-range {
  width: 100%;
  accent-color: #00d4ff;
}

.form-row {
  display: flex;
  gap: 16px;
}
.form-group.half {
  flex: 1;
}

.hint {
  font-size: 11px;
  color: var(--text-dim, #8a94a6);
  margin-top: 6px;
  line-height: 1.5;
}

.switch-label {
  display: flex !important;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  margin-bottom: 0 !important;
}
.switch-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  accent-color: #00d4ff;
  cursor: pointer;
}
.switch-label span {
  color: var(--text, #e0e6ed);
  font-size: 13px;
}

/* 按钮 */
.btn {
  padding: 8px 16px;
  border: 1px solid var(--border, #2a3142);
  background: transparent;
  color: var(--text, #e0e6ed);
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}
.btn:hover:not(:disabled) {
  background: rgba(255,255,255,0.08);
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-primary {
  background: #00d4ff;
  border-color: #00d4ff;
  color: #0f1419;
  font-weight: 500;
}
.btn-primary:hover:not(:disabled) {
  background: #00b8d9;
  border-color: #00b8d9;
}

.config-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 18px;
  border-top: 1px solid var(--border, #2a3142);
  background: rgba(0,0,0,0.15);
}
</style>
