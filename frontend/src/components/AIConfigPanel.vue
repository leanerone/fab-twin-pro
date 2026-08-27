<script setup>
import { ref, onMounted, computed } from 'vue'
import { api } from '../api'

const props = defineProps({
  fullPage: { type: Boolean, default: false }
})
const emit = defineEmits(['close'])

const loading = ref(false)
const testing = ref('')
const activeTab = ref('configs')
const toast = ref({ show: false, type: 'info', msg: '' })

// 配置列表
const configs = ref([])
const providerPresets = ref([])
const currentConfigId = ref(null)

// 编辑/创建表单
const showForm = ref(false)
const editingId = ref(null)
const form = ref({
  name: '',
  provider: 'zhipu',
  base_url: '',
  api_key: '',
  model: '',
  temperature: 0.7,
  max_tokens: 2048,
  description: '',
})

// 使用量统计
const usageStats = ref({
  total_calls: 0,
  total_tokens: 0,
  provider_breakdown: {},
  daily_stats: [],
})
const usageDays = ref(30)

// Dify/N8N 配置
const difyConfig = ref({
  dify_enabled: false,
  dify_base_url: '',
  dify_api_key: '',
  dify_app_id: '',
  n8n_enabled: false,
  n8n_base_url: '',
  n8n_webhook_secret: '',
})
const testingDify = ref(false)
const testingN8n = ref(false)

// MCP Server (N8N) 配置
const mcpConfig = ref({
  mcp_n8n_enabled: false,
  mcp_n8n_url: 'http://10.30.116.137/mcp-server/http',
  mcp_n8n_token: '',
  mcp_n8n_timeout: 30,
})
const testingMcp = ref(false)
const mcpTools = ref([])
const mcpTokenSet = ref(false)
const mcpTokenPreview = ref('')

// ========== 使用日志 ==========
const logsLoading = ref(false)
const logs = ref([])
const logsTotal = ref(0)
const logFilters = ref({
  start_date: '',
  end_date: '',
  provider: '',
  success: '',
})
const logPage = ref(1)
const logPageSize = ref(20)
const logDetailVisible = ref(false)
const logDetail = ref(null)
const logDetailLoading = ref(false)

const providerOptions = [
  { value: '', label: '全部 Provider' },
  { value: 'local', label: '本地规则' },
  { value: 'openai', label: 'OpenAI 兼容' },
  { value: 'zhipu', label: '智谱 GLM' },
  { value: 'dify', label: 'Dify' },
  { value: 'hybrid', label: 'Hybrid 混合' },
]

const successOptions = [
  { value: '', label: '全部' },
  { value: 'true', label: '成功' },
  { value: 'false', label: '失败' },
]

const selectedPreset = computed(() => {
  return providerPresets.value.find(p => p.id === form.value.provider) || null
})

function showToast(type, msg) {
  toast.value = { show: true, type, msg }
  setTimeout(() => { toast.value.show = false }, 3000)
}

async function loadConfigs() {
  loading.value = true
  try {
    // 独立加载，避免一个失败导致全部失败
    let configsRes = { configs: [] }
    let providersRes = { providers: [], current_config_id: null }
    try {
      configsRes = await api.aiGetModelConfigs()
    } catch (e) {
      console.error('加载模型配置失败', e)
      showToast('error', '加载模型配置列表失败')
    }
    try {
      providersRes = await api.aiGetProviders()
    } catch (e) {
      console.error('加载Provider预设失败', e)
    }
    configs.value = configsRes.configs || []
    providerPresets.value = providersRes.providers || []
    currentConfigId.value = providersRes.current_config_id || null
  } finally {
    loading.value = false
  }
}

async function loadUsage() {
  try {
    const res = await api.aiGetUsageStats(usageDays.value)
    usageStats.value = res
  } catch (e) {
    console.error('加载使用量统计失败', e)
  }
}

// Dify/N8N 配置加载与保存
async function loadDifyConfig() {
  try {
    const res = await api.aiGetConfig()
    difyConfig.value = {
      dify_enabled: res.dify_enabled || false,
      dify_base_url: res.dify_base_url || '',
      dify_api_key: res.dify_api_key || '',
      dify_app_id: res.dify_app_id || '',
      n8n_enabled: res.n8n_enabled || false,
      n8n_base_url: res.n8n_base_url || '',
      n8n_webhook_secret: res.n8n_webhook_secret || '',
    }
  } catch (e) {
    console.error('加载Dify/N8N配置失败', e)
  }
}

async function saveDifyConfig() {
  loading.value = true
  try {
    await api.aiUpdateConfig(difyConfig.value)
    showToast('success', 'Dify/N8N 配置已保存')
  } catch (e) {
    showToast('error', '保存失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function testDifyConnection() {
  if (!difyConfig.value.dify_base_url) {
    showToast('error', '请先填写 Dify 服务地址')
    return
  }
  testingDify.value = true
  try {
    const result = await api.aiTestConnection('dify', {
      base_url: difyConfig.value.dify_base_url,
      api_key: difyConfig.value.dify_api_key,
    })
    if (result.success) {
      showToast('success', result.message || 'Dify 连接成功')
    } else {
      showToast('error', result.message || 'Dify 连接失败')
    }
  } catch (e) {
    showToast('error', '测试失败：' + (e.message || '未知错误'))
  } finally {
    testingDify.value = false
  }
}

async function testN8nConnection() {
  if (!difyConfig.value.n8n_base_url) {
    showToast('error', '请先填写 N8N 服务地址')
    return
  }
  testingN8n.value = true
  try {
    const result = await api.aiTestConnection('n8n', {
      base_url: difyConfig.value.n8n_base_url,
    })
    if (result.success) {
      showToast('success', result.message || 'N8N 连接成功')
    } else {
      showToast('error', result.message || 'N8N 连接失败')
    }
  } catch (e) {
    showToast('error', '测试失败：' + (e.message || '未知错误'))
  } finally {
    testingN8n.value = false
  }
}

// ========== MCP Server (N8N) 配置 ==========
async function loadMcpConfig() {
  try {
    const res = await fetch('/api/ai/mcp/config')
    const data = await res.json()
    mcpConfig.value.mcp_n8n_enabled = data.enabled || false
    mcpConfig.value.mcp_n8n_url = data.url || 'http://10.30.116.137/mcp-server/http'
    mcpConfig.value.mcp_n8n_timeout = data.timeout || 30
    mcpTokenSet.value = data.token_set || false
    mcpTokenPreview.value = data.token_preview || ''
    // 如果已配置 Token，输入框显示占位符而非真实值
    if (mcpTokenSet.value) {
      mcpConfig.value.mcp_n8n_token = ''
    }
  } catch (e) {
    console.error('加载 MCP 配置失败', e)
  }
}

async function saveMcpConfig() {
  loading.value = true
  try {
    const payload = { ...mcpConfig.value }
    // 如果 Token 输入框为空且之前已配置，不覆盖
    if (!payload.mcp_n8n_token && mcpTokenSet.value) {
      delete payload.mcp_n8n_token
    }
    const res = await fetch('/api/ai/mcp/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await res.json()
    if (data.success) {
      showToast('success', 'MCP 配置已保存')
      await loadMcpConfig()
    } else {
      showToast('error', data.detail || '保存失败')
    }
  } catch (e) {
    showToast('error', '保存失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function testMcpConnection() {
  if (!mcpConfig.value.mcp_n8n_url) {
    showToast('error', '请先填写 MCP Server 地址')
    return
  }
  testingMcp.value = true
  try {
    const res = await fetch('/api/ai/mcp/test', { method: 'POST' })
    const data = await res.json()
    if (data.success) {
      showToast('success', data.message || 'MCP 连接成功')
      mcpTools.value = data.tools || []
    } else {
      showToast('error', data.message || 'MCP 连接失败')
      mcpTools.value = []
    }
  } catch (e) {
    showToast('error', '测试失败：' + (e.message || '未知错误'))
  } finally {
    testingMcp.value = false
  }
}

function openCreate() {
  editingId.value = null
  form.value = {
    name: '',
    provider: 'zhipu',
    base_url: '',
    api_key: '',
    model: '',
    temperature: 0.7,
    max_tokens: 2048,
    description: '',
  }
  showForm.value = true
}

function openEdit(cfg) {
  editingId.value = cfg.id
  form.value = {
    name: cfg.name,
    provider: cfg.provider,
    base_url: cfg.base_url,
    api_key: '',
    model: cfg.model,
    temperature: cfg.temperature,
    max_tokens: cfg.max_tokens,
    description: cfg.description,
  }
  showForm.value = true
}

function onProviderChange() {
  const preset = selectedPreset.value
  if (!preset) return
  if (preset.default_url && !form.value.base_url) {
    // 默认地址也去除 /v1 后缀，保持统一
    form.value.base_url = preset.default_url.replace(/\/v1\/?$/, '')
  }
  if (preset.default_model && !form.value.model) {
    form.value.model = preset.default_model
  }
}

async function saveConfig() {
  if (!form.value.name) {
    showToast('error', '配置名称必填')
    return
  }
  if (!form.value.provider) {
    showToast('error', '请选择 AI Provider')
    return
  }
  loading.value = true
  try {
    const data = { ...form.value }
    // 去除 base_url 末尾斜杠和 /v1 后缀，由后端统一拼接
    data.base_url = (data.base_url || '').replace(/\/v1\/?$/, '').trim()
    if (!data.api_key) delete data.api_key
    if (editingId.value) {
      await api.aiUpdateModelConfig(editingId.value, data)
      showToast('success', '配置已更新')
    } else {
      await api.aiCreateModelConfig(data)
      showToast('success', '配置已创建')
    }
    showForm.value = false
    await loadConfigs()
  } catch (e) {
    console.error('保存配置失败', e)
    showToast('error', '保存失败：' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

async function deleteConfig(id, name) {
  if (!confirm(`确定删除配置 "${name}" 吗？`)) return
  try {
    await api.aiDeleteModelConfig(id)
    showToast('success', '配置已删除')
    await loadConfigs()
  } catch (e) {
    showToast('error', '删除失败')
  }
}

async function setDefault(id) {
  try {
    await api.aiSetDefaultModelConfig(id)
    showToast('success', '已设为默认配置')
    await loadConfigs()
  } catch (e) {
    showToast('error', '设置失败')
  }
}

async function toggleConfig(id) {
  try {
    await api.aiToggleModelConfig(id)
    await loadConfigs()
  } catch (e) {
    showToast('error', '操作失败')
  }
}

async function switchConfig(id) {
  try {
    const res = await api.aiSwitchModelConfig(id)
    currentConfigId.value = id
    showToast('success', res.message || '配置已切换')
    await loadConfigs()
  } catch (e) {
    showToast('error', '切换失败')
  }
}

async function testConnection() {
  if (!form.value.base_url) {
    showToast('error', '请先填写 API 基础地址')
    return
  }
  testing.value = 'openai'
  try {
    const testConfig = {
      base_url: form.value.base_url,
      api_key: form.value.api_key,
      model: form.value.model,
    }
    const result = await api.aiTestConnection('openai', testConfig)
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

function formatNumber(n) {
  if (!n) return '0'
  return n.toLocaleString('zh-CN')
}

// ========== 使用日志 ==========
async function loadLogs() {
  logsLoading.value = true
  try {
    const params = {
      limit: logPageSize.value,
      offset: (logPage.value - 1) * logPageSize.value,
    }
    if (logFilters.value.start_date) params.start_date = logFilters.value.start_date
    if (logFilters.value.end_date) params.end_date = logFilters.value.end_date
    if (logFilters.value.provider) params.provider = logFilters.value.provider
    if (logFilters.value.success !== '') params.success = logFilters.value.success === 'true'
    const res = await api.aiGetUsageLogs(params)
    logs.value = res.logs || []
    logsTotal.value = res.total || 0
  } catch (e) {
    console.error('加载使用日志失败', e)
    showToast('error', '加载日志失败')
  } finally {
    logsLoading.value = false
  }
}

async function viewLogDetail(logId) {
  logDetailVisible.value = true
  logDetailLoading.value = true
  logDetail.value = null
  try {
    const res = await api.aiGetUsageLogDetail(logId)
    logDetail.value = res
  } catch (e) {
    console.error('加载日志详情失败', e)
    showToast('error', '加载详情失败')
  } finally {
    logDetailLoading.value = false
  }
}

function searchLogs() {
  logPage.value = 1
  loadLogs()
}

function resetLogFilters() {
  logFilters.value = { start_date: '', end_date: '', provider: '', success: '' }
  logPage.value = 1
  loadLogs()
}

function onLogPageChange(page) {
  logPage.value = page
  loadLogs()
}

const logTotalPages = computed(() => Math.max(1, Math.ceil(logsTotal.value / logPageSize.value)))

const executionSteps = computed(() => {
  if (!logDetail.value?.execution_log) return []
  const steps = logDetail.value.execution_log
  if (Array.isArray(steps)) return steps
  if (typeof steps === 'object') {
    // 如果是对象格式，尝试转为数组
    return Object.entries(steps).map(([k, v]) => ({ step: k, ...v }))
  }
  return []
})

const toolCallsParsed = computed(() => {
  if (!logDetail.value?.tool_calls) return []
  const tc = logDetail.value.tool_calls
  if (Array.isArray(tc)) return tc
  if (typeof tc === 'string') {
    try { return JSON.parse(tc) } catch { return [] }
  }
  return []
})

onMounted(() => {
  loadConfigs()
  loadUsage()
  loadDifyConfig()
  loadMcpConfig()
})

function onTabChange(tab) {
  activeTab.value = tab
  if (tab === 'dify' && !difyConfig.value.dify_base_url && !difyConfig.value.n8n_base_url) {
    loadDifyConfig()
  }
  if (tab === 'dify') {
    loadMcpConfig()
  }
  if (tab === 'usage') {
    loadUsage()
  }
  if (tab === 'logs') {
    loadLogs()
  }
}
</script>

<template>
  <div :class="['ai-config-panel', { 'full-page': props.fullPage }]">
    <div class="config-header">
      <span class="title">AI 配置中心</span>
      <span v-if="!props.fullPage" class="close-btn" @click="emit('close')">&#10005;</span>
    </div>

    <!-- Toast -->
    <transition name="toast">
      <div v-if="toast.show" :class="['toast', toast.type]">{{ toast.msg }}</div>
    </transition>

    <!-- 标签页 -->
    <div class="tab-nav">
      <div v-for="tab in [
        { name: 'configs', label: '模型配置' },
        { name: 'dify', label: 'Dify/N8N' },
        { name: 'usage', label: '使用统计' },
        { name: 'logs', label: '使用日志' },
      ]" :key="tab.name"
        :class="['tab-item', { active: activeTab === tab.name }]"
        @click="onTabChange(tab.name)">
        {{ tab.label }}
      </div>
    </div>

    <div class="tab-content">
      <!-- 配置列表 -->
      <div v-show="activeTab === 'configs'" class="tab-pane">
        <div class="toolbar">
          <div class="toolbar-left">
            <button class="btn btn-primary" @click="openCreate">+ 添加配置</button>
            <button class="btn btn-ghost" @click="loadConfigs" :disabled="loading">{{ loading ? '刷新中...' : '刷新' }}</button>
          </div>
          <span class="hint-text">当前使用: {{ configs.find(c => c.id === currentConfigId)?.name || '本地规则引擎' }}</span>
        </div>

        <div class="config-list">
          <div v-for="cfg in configs" :key="cfg.id"
            :class="['config-card', { 'current': cfg.id === currentConfigId, 'disabled': !cfg.is_enabled }]">
            <div class="card-header">
              <div class="cfg-name">
                <span class="badge" :class="cfg.is_default ? 'default' : ''">{{ cfg.is_default ? '默认' : '' }}</span>
                {{ cfg.name }}
              </div>
              <div class="cfg-actions">
                <button v-if="cfg.id !== currentConfigId && cfg.is_enabled" class="btn-icon" title="切换使用" @click="switchConfig(cfg.id)">&#9658;</button>
                <button v-if="cfg.id === currentConfigId" class="btn-icon active" title="当前使用中">&#9679;</button>
                <button class="btn-icon" title="设为默认" @click="setDefault(cfg.id)">&#9733;</button>
                <button class="btn-icon" :title="cfg.is_enabled ? '禁用' : '启用'" @click="toggleConfig(cfg.id)">
                  {{ cfg.is_enabled ? '&#10004;' : '&#10008;' }}
                </button>
                <button class="btn-icon" title="编辑" @click="openEdit(cfg)">&#9998;</button>
                <button class="btn-icon danger" title="删除" @click="deleteConfig(cfg.id, cfg.name)">&#10005;</button>
              </div>
            </div>
            <div class="card-body">
              <span class="tag">{{ providerPresets.find(p => p.id === cfg.provider)?.name || cfg.provider }}</span>
              <span class="tag">{{ cfg.model || '未设置模型' }}</span>
              <span class="tag dim">{{ cfg.base_url || '无API地址' }}</span>
              <span class="tag" :class="cfg.has_api_key ? 'ok' : 'warn'">{{ cfg.has_api_key ? '已配置Key' : '未配置Key' }}</span>
            </div>
          </div>

          <div v-if="configs.length === 0" class="empty">
            暂无AI配置，点击"添加配置"创建第一个配置
          </div>
        </div>
      </div>

      <!-- Dify/N8N 配置 -->
      <div v-show="activeTab === 'dify'" class="tab-pane">
        <!-- Dify 配置 -->
        <div class="dify-section">
          <div class="section-header">
            <span class="section-title">Dify 应用对接</span>
            <label class="switch">
              <input type="checkbox" v-model="difyConfig.dify_enabled" />
              <span class="slider"></span>
            </label>
          </div>
          <div class="hint-box">
            Dify 是开源的 LLM 应用开发平台。配置后，AI 助手的问题将转发到 Dify 应用处理。
          </div>
          <div class="form-group">
            <label>Dify 服务地址</label>
            <input v-model="difyConfig.dify_base_url" class="form-input" placeholder="如：http://localhost:3000" />
          </div>
          <div class="form-group">
            <label>Dify API Key</label>
            <input v-model="difyConfig.dify_api_key" type="password" class="form-input" placeholder="Dify 应用的 API Key" />
          </div>
          <div class="form-group">
            <label>Dify App ID（可选）</label>
            <input v-model="difyConfig.dify_app_id" class="form-input" placeholder="Dify 应用 ID" />
          </div>
          <div class="form-actions">
            <button class="btn btn-ghost" :disabled="testingDify" @click="testDifyConnection">
              {{ testingDify ? '测试中...' : '测试连接' }}
            </button>
          </div>
        </div>

        <hr class="divider" />

        <!-- N8N 配置 -->
        <div class="dify-section">
          <div class="section-header">
            <span class="section-title">N8N 工作流联动</span>
            <label class="switch">
              <input type="checkbox" v-model="difyConfig.n8n_enabled" />
              <span class="slider"></span>
            </label>
          </div>
          <div class="hint-box">
            N8N 是开源的工作流自动化工具。配置后，可通过 AI 助手触发 N8N 工作流（如导出报表、生成工单等），需管理员权限。
          </div>
          <div class="form-group">
            <label>N8N 服务地址</label>
            <input v-model="difyConfig.n8n_base_url" class="form-input" placeholder="如：http://localhost:5678" />
          </div>
          <div class="form-group">
            <label>Webhook Secret（可选）</label>
            <input v-model="difyConfig.n8n_webhook_secret" type="password" class="form-input" placeholder="N8N Webhook 验证密钥" />
          </div>
          <div class="form-actions">
            <button class="btn btn-ghost" :disabled="testingN8n" @click="testN8nConnection">
              {{ testingN8n ? '测试中...' : '测试连接' }}
            </button>
          </div>
        </div>

        <hr class="divider" />

        <!-- MCP Server (N8N) 配置 -->
        <div class="dify-section">
          <div class="section-header">
            <span class="section-title">MCP Server (N8N 工具调用)</span>
            <label class="switch">
              <input type="checkbox" v-model="mcpConfig.mcp_n8n_enabled" />
              <span class="slider"></span>
            </label>
          </div>
          <div class="hint-box">
            通过 MCP 协议（Model Context Protocol）调用 N8N 上的工作流工具（如 MES_LotInfo_Query）。
            配置后，AI 助手可通过 GPT-4o 的 Function Calling 自动调用 N8N 工具查询 MES 数据。
          </div>
          <div class="form-group">
            <label>MCP Server 地址</label>
            <input v-model="mcpConfig.mcp_n8n_url" class="form-input" placeholder="http://10.30.116.137/mcp-server/http" />
          </div>
          <div class="form-group">
            <label>Bearer Token</label>
            <input
              v-model="mcpConfig.mcp_n8n_token"
              type="password"
              class="form-input"
              :placeholder="mcpTokenSet ? `已配置（${mcpTokenPreview}），留空则不修改` : '请填入 N8N MCP Token'"
            />
          </div>
          <div class="form-group">
            <label>超时时间（秒）</label>
            <input v-model.number="mcpConfig.mcp_n8n_timeout" type="number" min="5" max="120" class="form-input" />
          </div>
          <div class="form-actions">
            <button class="btn btn-ghost" :disabled="testingMcp" @click="testMcpConnection">
              {{ testingMcp ? '测试中...' : '测试连接' }}
            </button>
            <button class="btn btn-primary" :disabled="loading" @click="saveMcpConfig">
              {{ loading ? '保存中...' : '保存 MCP 配置' }}
            </button>
          </div>

          <!-- 已发现的工具列表 -->
          <div v-if="mcpTools.length" class="mcp-tools-list">
            <h4>已发现工具（{{ mcpTools.length }}）</h4>
            <div v-for="t in mcpTools" :key="t.name" class="mcp-tool-item">
              <span class="tool-name">{{ t.name }}</span>
              <span class="tool-desc">{{ t.description || '无描述' }}</span>
            </div>
          </div>
        </div>

        <div class="form-actions" style="margin-top: 16px;">
          <button class="btn btn-primary" :disabled="loading" @click="saveDifyConfig">
            {{ loading ? '保存中...' : '保存全部配置' }}
          </button>
        </div>
      </div>

      <!-- 使用量统计 -->
      <div v-show="activeTab === 'usage'" class="tab-pane">
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-value">{{ formatNumber(usageStats.total_calls) }}</div>
            <div class="stat-label">总调用次数</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ formatNumber(usageStats.total_tokens) }}</div>
            <div class="stat-label">总Token消耗</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ formatNumber(usageStats.total_prompt_tokens) }}</div>
            <div class="stat-label">输入Token</div>
          </div>
          <div class="stat-card">
            <div class="stat-value">{{ formatNumber(usageStats.total_completion_tokens) }}</div>
            <div class="stat-label">输出Token</div>
          </div>
        </div>

        <div class="section-title">Provider 分布</div>
        <div class="provider-list">
          <div v-for="(stat, provider) in usageStats.provider_breakdown" :key="provider" class="provider-row">
            <span class="provider-name">{{ provider }}</span>
            <span class="provider-bar"><span class="bar-fill" :style="{ width: Math.min((stat.tokens / Math.max(usageStats.total_tokens, 1)) * 100, 100) + '%' }"></span></span>
            <span class="provider-stat">{{ formatNumber(stat.calls) }}次 / {{ formatNumber(stat.tokens) }}token</span>
          </div>
        </div>
      </div>

      <!-- 使用日志 -->
      <div v-show="activeTab === 'logs'" class="tab-pane">
        <!-- 筛选栏 -->
        <div class="logs-filter-bar">
          <div class="filter-group">
            <label>起始日期</label>
            <input type="date" v-model="logFilters.start_date" class="filter-input" />
          </div>
          <div class="filter-group">
            <label>结束日期</label>
            <input type="date" v-model="logFilters.end_date" class="filter-input" />
          </div>
          <div class="filter-group">
            <label>Provider</label>
            <select v-model="logFilters.provider" class="filter-input">
              <option v-for="opt in providerOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </div>
          <div class="filter-group">
            <label>结果</label>
            <select v-model="logFilters.success" class="filter-input">
              <option v-for="opt in successOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
          </div>
          <div class="filter-actions">
            <button class="btn btn-primary" @click="searchLogs">查询</button>
            <button class="btn btn-ghost" @click="resetLogFilters">重置</button>
          </div>
        </div>

        <!-- 日志表格 -->
        <div v-if="logsLoading" class="logs-loading">加载中...</div>
        <div v-else-if="logs.length === 0" class="empty">暂无日志记录</div>
        <div v-else class="logs-table-wrap">
          <table class="logs-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>Provider</th>
                <th>模型</th>
                <th>Tokens (入/出/总)</th>
                <th>问题预览</th>
                <th>结果</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="log in logs" :key="log.id" :class="{ 'log-fail': !log.success }">
                <td class="col-time">{{ log.created_at }}</td>
                <td>
                  <span class="log-provider">{{ log.provider }}</span>
                  <span v-if="log.provider_name" class="log-provider-name">{{ log.provider_name }}</span>
                </td>
                <td class="col-model">{{ log.model || '-' }}</td>
                <td class="col-tokens">
                  <span class="tk-in">{{ log.prompt_tokens }}</span> /
                  <span class="tk-out">{{ log.completion_tokens }}</span> /
                  <span class="tk-total">{{ log.total_tokens }}</span>
                </td>
                <td class="col-question" :title="log.question_preview">{{ log.question_preview?.substring(0, 50) }}{{ log.question_preview?.length > 50 ? '...' : '' }}</td>
                <td>
                  <span class="log-badge" :class="log.success ? 'ok' : 'fail'">{{ log.success ? '✅ 成功' : '❌ 失败' }}</span>
                </td>
                <td>
                  <button class="btn btn-ghost" @click="viewLogDetail(log.id)">查看详情</button>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- 分页 -->
          <div class="logs-pagination">
            <span class="page-info">共 {{ logsTotal }} 条，第 {{ logPage }}/{{ logTotalPages }} 页</span>
            <div class="page-btns">
              <button class="btn btn-ghost" :disabled="logPage <= 1" @click="onLogPageChange(logPage - 1)">上一页</button>
              <button class="btn btn-ghost" :disabled="logPage >= logTotalPages" @click="onLogPageChange(logPage + 1)">下一页</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 日志详情抽屉 -->
    <transition name="drawer">
      <div v-if="logDetailVisible" class="log-drawer-overlay" @click.self="logDetailVisible = false">
        <div class="log-drawer">
          <div class="drawer-header">
            <span>AI 调用日志详情 #{{ logDetail?.id }}</span>
            <span class="close-btn" @click="logDetailVisible = false">&#10005;</span>
          </div>
          <div class="drawer-body">
            <div v-if="logDetailLoading" class="logs-loading">加载中...</div>
            <div v-else-if="logDetail" class="detail-content">
              <!-- 1. 基本信息 -->
              <div class="detail-section">
                <div class="detail-section-title">基本信息</div>
                <div class="detail-grid">
                  <div><span class="dk">时间</span><span class="dv">{{ logDetail.created_at }}</span></div>
                  <div><span class="dk">会话ID</span><span class="dv">{{ logDetail.session_id || '-' }}</span></div>
                  <div><span class="dk">配置ID</span><span class="dv">{{ logDetail.config_id || '-' }}</span></div>
                  <div><span class="dk">Provider</span><span class="dv">{{ logDetail.provider }}{{ logDetail.provider_name ? ' / ' + logDetail.provider_name : '' }}</span></div>
                  <div><span class="dk">模型</span><span class="dv">{{ logDetail.model || '-' }}</span></div>
                  <div><span class="dk">Tokens</span><span class="dv">{{ logDetail.prompt_tokens }} / {{ logDetail.completion_tokens }} / {{ logDetail.total_tokens }}</span></div>
                  <div><span class="dk">结果</span><span class="dv"><span class="log-badge" :class="logDetail.success ? 'ok' : 'fail'">{{ logDetail.success ? '✅ 成功' : '❌ 失败' }}</span></span></div>
                </div>
              </div>

              <!-- 2. 用户问题 -->
              <div class="detail-section">
                <div class="detail-section-title">用户问题</div>
                <div class="detail-text-box">{{ logDetail.question_preview || '(无)' }}</div>
              </div>

              <!-- 3. AI回答 -->
              <div class="detail-section">
                <div class="detail-section-title">AI 回答</div>
                <div class="detail-text-box">{{ logDetail.answer_preview || '(无回答)' }}</div>
              </div>

              <!-- 4. 工具调用链 -->
              <div v-if="toolCallsParsed.length > 0" class="detail-section">
                <div class="detail-section-title">工具调用链 ({{ toolCallsParsed.length }})</div>
                <div class="tool-call-list">
                  <div v-for="(tc, idx) in toolCallsParsed" :key="idx" class="tool-call-item">
                    <span class="tc-name">{{ tc.name || tc.function?.name || `工具#${idx + 1}` }}</span>
                    <pre class="tc-args">{{ JSON.stringify(tc.arguments || tc.function?.arguments || {}, null, 2) }}</pre>
                    <span v-if="tc.result || tc.response" class="tc-result">{{ JSON.stringify(tc.result || tc.response, null, 2) }}</span>
                  </div>
                </div>
              </div>

              <!-- 5. 执行日志时间轴 -->
              <div v-if="executionSteps.length > 0" class="detail-section">
                <div class="detail-section-title">执行日志时间轴 ({{ executionSteps.length }} 步)</div>
                <div class="exec-timeline">
                  <div v-for="(step, idx) in executionSteps" :key="idx"
                    :class="['exec-step', { 'exec-error': step.error || step.status === 'error' || (typeof step.step === 'string' && step.step.includes('error')) }]">
                    <div class="exec-dot" :class="{ 'exec-dot-error': step.error || step.status === 'error' || (typeof step.step === 'string' && step.step.includes('error')) }"></div>
                    <div class="exec-content">
                      <span class="exec-step-name">{{ step.step || step.name || `Step ${idx + 1}` }}</span>
                      <span v-if="step.timestamp || step.ts || step.time" class="exec-ts">{{ step.timestamp || step.ts || step.time }}</span>
                      <div v-if="step.message || step.msg || step.detail" class="exec-msg">{{ step.message || step.msg || step.detail }}</div>
                      <div v-if="step.error" class="exec-err-msg">{{ step.error }}</div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 6. 错误详情 -->
              <div v-if="logDetail.error_msg" class="detail-section">
                <div class="detail-section-title" style="color: #e74c3c;">错误详情</div>
                <div class="error-box">{{ logDetail.error_msg }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- 创建/编辑弹窗 -->
    <div v-if="showForm" class="modal-overlay" @click.self="showForm = false">
      <div class="modal">
        <div class="modal-header">
          <span>{{ editingId ? '编辑配置' : '添加配置' }}</span>
          <span class="close-btn" @click="showForm = false">&#10005;</span>
        </div>
        <div class="modal-body">
          <div class="hint-box">
            系统会自动在 API 地址后拼接 <code>/v1/chat/completions</code> 进行调用，因此基础地址只需填写到版本号之前。例如 OpenAI 填写 <code>https://api.openai.com</code> 即可，无需加 <code>/v1</code>。
          </div>
          <div class="form-row">
            <div class="form-group" style="flex: 1.2;">
              <label>配置名称 *</label>
              <input v-model="form.name" class="form-input" placeholder="如：智谱GLM-生产环境" />
            </div>
            <div class="form-group" style="flex: 1;">
              <label>AI Provider *</label>
              <select v-model="form.provider" class="form-input" @change="onProviderChange">
                <option v-for="p in providerPresets.filter(p => p.requires_key !== false || p.id === 'local')" :key="p.id" :value="p.id">{{ p.name }}</option>
              </select>
            </div>
          </div>
          <div class="form-group">
            <label>API 基础地址</label>
            <input v-model="form.base_url" class="form-input" :placeholder="selectedPreset?.default_url || 'https://...'" />
            <div v-if="selectedPreset?.default_url" class="hint">
              默认: {{ selectedPreset.default_url.replace(/\/v1\/?$/, '') }}
              <span class="link" @click="form.base_url = selectedPreset.default_url.replace(/\/v1\/?$/, '')">使用默认</span>
            </div>
          </div>
          <div class="form-group">
            <label>API Key {{ editingId ? '(留空则不修改)' : '' }}</label>
            <input v-model="form.api_key" type="password" class="form-input" placeholder="输入API密钥" />
          </div>
          <div class="form-row">
            <div class="form-group" style="flex: 1.2;">
              <label>模型名称</label>
              <input v-model="form.model" class="form-input" :placeholder="selectedPreset?.default_model || '如：glm-5.2'" />
              <div v-if="selectedPreset?.default_model" class="hint">
                推荐: {{ selectedPreset.default_model }}
                <span class="link" @click="form.model = selectedPreset.default_model">使用推荐</span>
              </div>
            </div>
            <div class="form-group half">
              <label>最大 Token</label>
              <input type="number" v-model.number="form.max_tokens" min="128" max="8192" step="128" class="form-input" />
            </div>
          </div>
          <div class="form-row">
            <div class="form-group half">
              <label>温度 ({{ form.temperature }})</label>
              <input type="range" v-model.number="form.temperature" min="0" max="1" step="0.1" class="form-range" />
            </div>
            <div class="form-group half">
              <label>配置说明</label>
              <input v-model="form.description" class="form-input" placeholder="可选：配置用途说明" />
            </div>
          </div>
          <button class="btn btn-primary" :disabled="testing === 'openai'" @click="testConnection">
            {{ testing === 'openai' ? '测试中...' : '测试连接' }}
          </button>
        </div>
        <div class="modal-footer">
          <button class="btn" @click="showForm = false">取消</button>
          <button class="btn btn-primary" :disabled="loading || !form.name" @click="saveConfig">
            {{ loading ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ai-config-panel {
  width: 720px;
  max-width: 95vw;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-card, #1a1f2e);
  border: 1px solid var(--border, #2a3142);
  border-radius: 10px;
  overflow: hidden;
  position: relative;
}
.ai-config-panel.full-page {
  width: 100%;
  max-width: 100%;
  max-height: 100%;
  height: 100%;
  border: none;
  border-radius: 0;
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
  z-index: 200;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}
.toast.success { background: #2ecc71; color: #fff; }
.toast.error { background: #e74c3c; color: #fff; }
.toast-enter-active, .toast-leave-active { transition: opacity 0.3s, transform 0.3s; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(-50%) translateY(-10px); }

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
.tab-item:hover { color: var(--text, #e0e6ed); }
.tab-item.active {
  color: #00d4ff;
  border-bottom-color: #00d4ff;
  background: rgba(0, 212, 255, 0.05);
}

.tab-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

/* 工具栏 */
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.hint-text {
  font-size: 12px;
  color: var(--text-dim, #8a94a6);
}

/* 配置卡片 */
.config-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.config-card {
  background: rgba(0,0,0,0.2);
  border: 1px solid var(--border, #2a3142);
  border-radius: 6px;
  padding: 10px 12px;
}
.config-card.current {
  border-color: #00d4ff;
  background: rgba(0, 212, 255, 0.05);
}
.config-card.disabled {
  opacity: 0.5;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.cfg-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text, #e0e6ed);
  display: flex;
  align-items: center;
  gap: 6px;
}
.badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 3px;
  background: #555;
  color: #fff;
}
.badge.default {
  background: #f0ad4e;
  color: #1a1f2e;
}
.cfg-actions {
  display: flex;
  gap: 4px;
}
.btn-icon {
  background: none;
  border: none;
  color: var(--text-dim, #8a94a6);
  cursor: pointer;
  font-size: 13px;
  padding: 2px 6px;
  border-radius: 3px;
}
.btn-icon:hover {
  background: rgba(255,255,255,0.08);
  color: var(--text, #e0e6ed);
}
.btn-icon.active {
  color: #00d4ff;
}
.btn-icon.danger:hover {
  color: #e74c3c;
}
.card-body {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 3px;
  background: rgba(255,255,255,0.05);
  color: var(--text-dim, #8a94a6);
}
.tag.dim {
  background: transparent;
  padding-left: 0;
}
.tag.ok {
  color: #2ecc71;
}
.tag.warn {
  color: #f0ad4e;
}

.empty {
  text-align: center;
  padding: 40px;
  color: var(--text-dim, #8a94a6);
  font-size: 13px;
}

/* 统计 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 20px;
}
.stat-card {
  background: rgba(0,0,0,0.2);
  border: 1px solid var(--border, #2a3142);
  border-radius: 6px;
  padding: 14px;
  text-align: center;
}
.stat-value {
  font-size: 22px;
  font-weight: 600;
  color: #00d4ff;
}
.stat-label {
  font-size: 11px;
  color: var(--text-dim, #8a94a6);
  margin-top: 4px;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text, #e0e6ed);
  margin-bottom: 10px;
}
.provider-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.provider-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
}
.provider-name {
  width: 80px;
  color: var(--text-dim, #8a94a6);
}
.provider-bar {
  flex: 1;
  height: 6px;
  background: rgba(255,255,255,0.05);
  border-radius: 3px;
  overflow: hidden;
}
.bar-fill {
  display: block;
  height: 100%;
  background: #00d4ff;
  border-radius: 3px;
}
.provider-stat {
  width: 120px;
  text-align: right;
  color: var(--text-dim, #8a94a6);
  font-size: 11px;
}

/* 弹窗 */
.modal-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 150;
}
.modal {
  width: 640px;
  max-width: 95vw;
  max-height: 90vh;
  background: var(--bg-card, #1a1f2e);
  border: 1px solid var(--border, #2a3142);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border, #2a3142);
  font-size: 14px;
  font-weight: 600;
  color: var(--text, #e0e6ed);
}
.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 14px 20px;
  border-top: 1px solid var(--border, #2a3142);
}

/* 表单 */
.form-group {
  margin-bottom: 18px;
}
.form-group label {
  display: block;
  font-size: 13px;
  color: var(--text-dim, #8a94a6);
  margin-bottom: 6px;
  font-weight: 500;
}
.form-input {
  width: 100%;
  padding: 10px 12px;
  background: var(--bg, #0f1419);
  border: 1px solid var(--border, #2a3142);
  border-radius: 6px;
  color: var(--text, #e0e6ed);
  font-size: 14px;
  box-sizing: border-box;
  min-height: 38px;
}
.form-input:focus {
  outline: none;
  border-color: #00d4ff;
}
.form-range {
  width: 100%;
  accent-color: #00d4ff;
}
.form-row {
  display: flex;
  gap: 18px;
}
.form-group.half {
  flex: 1;
}
.hint {
  font-size: 12px;
  color: var(--text-dim, #8a94a6);
  margin-top: 6px;
}
.link {
  color: #00d4ff;
  cursor: pointer;
  text-decoration: underline;
  margin-left: 4px;
}
.hint-box {
  background: rgba(0, 212, 255, 0.06);
  border: 1px solid rgba(0, 212, 255, 0.15);
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 12px;
  color: var(--text-dim, #8a94a6);
  margin-bottom: 18px;
  line-height: 1.5;
}

/* 按钮 */
.btn {
  padding: 7px 14px;
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
.toolbar-left {
  display: flex;
  gap: 8px;
}
.btn-ghost {
  background: transparent;
  border: 1px solid var(--border, #2a3142);
  color: var(--text-dim, #8a94a6);
  font-size: 12px;
  padding: 6px 12px;
}
.btn-ghost:hover:not(:disabled) {
  color: var(--text, #e0e6ed);
  border-color: var(--text-dim, #8a94a6);
}

/* Dify/N8N 配置区 */
.dify-section {
  margin-bottom: 16px;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.divider {
  border: none;
  border-top: 1px solid var(--border, #2a3142);
  margin: 20px 0;
}
.form-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

/* 开关组件 */
.switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
}
.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}
.slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background: #2a3142;
  border-radius: 24px;
  transition: 0.3s;
}
.slider::before {
  content: "";
  position: absolute;
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background: #8a94a6;
  border-radius: 50%;
  transition: 0.3s;
}
.switch input:checked + .slider {
  background: rgba(0, 212, 255, 0.3);
}
.switch input:checked + .slider::before {
  transform: translateX(20px);
  background: #00d4ff;
}

/* MCP 工具列表样式 */
.mcp-tools-list {
  margin-top: 16px;
  padding: 12px;
  background: rgba(0, 212, 255, 0.05);
  border: 1px solid rgba(0, 212, 255, 0.2);
  border-radius: 8px;
}
.mcp-tools-list h4 {
  margin: 0 0 8px 0;
  font-size: 13px;
  color: #00d4ff;
}
.mcp-tool-item {
  display: flex;
  flex-direction: column;
  padding: 8px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}
.mcp-tool-item:last-child {
  border-bottom: none;
}
.mcp-tool-item .tool-name {
  font-size: 13px;
  font-weight: 600;
  color: #e0e0e0;
  font-family: 'Consolas', 'Monaco', monospace;
}
.mcp-tool-item .tool-desc {
  font-size: 12px;
  color: #888;
  margin-top: 2px;
}

/* ========== 使用日志 ========== */
.logs-filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
  margin-bottom: 16px;
  padding: 12px;
  background: rgba(0,0,0,0.2);
  border: 1px solid var(--border, #2a3142);
  border-radius: 6px;
}
.filter-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.filter-group label {
  font-size: 11px;
  color: var(--text-dim, #8a94a6);
}
.filter-input {
  padding: 6px 8px;
  background: var(--bg, #0f1419);
  border: 1px solid var(--border, #2a3142);
  border-radius: 4px;
  color: var(--text, #e0e6ed);
  font-size: 13px;
  min-height: 32px;
}
.filter-input:focus {
  outline: none;
  border-color: #00d4ff;
}
.filter-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.logs-loading {
  text-align: center;
  padding: 40px;
  color: var(--text-dim, #8a94a6);
  font-size: 13px;
}

.logs-table-wrap {
  overflow-x: auto;
}
.logs-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.logs-table th {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 2px solid var(--border, #2a3142);
  color: var(--text-dim, #8a94a6);
  font-weight: 600;
  white-space: nowrap;
}
.logs-table td {
  padding: 8px 10px;
  border-bottom: 1px solid rgba(255,255,255,0.05);
  color: var(--text, #e0e6ed);
}
.logs-table tr.log-fail {
  background: rgba(231, 76, 60, 0.05);
}
.logs-table tr.log-fail:hover {
  background: rgba(231, 76, 60, 0.1);
}
.logs-table tbody tr:hover {
  background: rgba(0, 212, 255, 0.03);
}
.col-time {
  white-space: nowrap;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 11px;
}
.col-model {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 11px;
}
.col-tokens {
  white-space: nowrap;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 11px;
}
.col-question {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tk-in { color: #8a94a6; }
.tk-out { color: #f0ad4e; }
.tk-total { color: #00d4ff; font-weight: 600; }

.log-provider {
  font-size: 11px;
  font-weight: 600;
  color: #00d4ff;
}
.log-provider-name {
  display: block;
  font-size: 10px;
  color: var(--text-dim, #8a94a6);
}

.log-badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
  white-space: nowrap;
}
.log-badge.ok {
  background: rgba(46, 204, 113, 0.15);
  color: #2ecc71;
}
.log-badge.fail {
  background: rgba(231, 76, 60, 0.15);
  color: #e74c3c;
}

.logs-pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}
.page-info {
  font-size: 12px;
  color: var(--text-dim, #8a94a6);
}
.page-btns {
  display: flex;
  gap: 8px;
}

/* ========== 日志详情抽屉 ========== */
.log-drawer-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0,0,0,0.5);
  z-index: 160;
  display: flex;
  justify-content: flex-end;
}
.log-drawer {
  width: 55%;
  min-width: 500px;
  max-width: 800px;
  height: 100%;
  background: var(--bg-card, #1a1f2e);
  border-left: 1px solid var(--border, #2a3142);
  display: flex;
  flex-direction: column;
  box-shadow: -4px 0 20px rgba(0,0,0,0.3);
}
.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border, #2a3142);
  font-size: 14px;
  font-weight: 600;
  color: var(--text, #e0e6ed);
  background: rgba(0, 212, 255, 0.05);
}
.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 18px;
}
.detail-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.detail-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.detail-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text, #e0e6ed);
  padding-bottom: 4px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}
.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
}
.detail-grid > div {
  display: flex;
  gap: 8px;
  align-items: baseline;
}
.dk {
  font-size: 11px;
  color: var(--text-dim, #8a94a6);
  min-width: 60px;
}
.dv {
  font-size: 12px;
  color: var(--text, #e0e6ed);
  word-break: break-all;
}
.detail-text-box {
  background: rgba(0,0,0,0.2);
  border: 1px solid var(--border, #2a3142);
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 12px;
  color: var(--text, #e0e6ed);
  line-height: 1.6;
  max-height: 150px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

/* 工具调用链 */
.tool-call-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.tool-call-item {
  background: rgba(0,0,0,0.2);
  border: 1px solid var(--border, #2a3142);
  border-radius: 6px;
  padding: 10px 12px;
}
.tc-name {
  font-size: 12px;
  font-weight: 600;
  color: #00d4ff;
  font-family: 'Consolas', 'Monaco', monospace;
}
.tc-args {
  margin: 6px 0 0 0;
  font-size: 11px;
  color: var(--text-dim, #8a94a6);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 120px;
  overflow-y: auto;
}
.tc-result {
  display: block;
  margin-top: 6px;
  font-size: 11px;
  color: #2ecc71;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 120px;
  overflow-y: auto;
}

/* 执行日志时间轴 */
.exec-timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-left: 8px;
}
.exec-step {
  display: flex;
  gap: 10px;
  padding: 6px 0;
  position: relative;
}
.exec-step::before {
  content: '';
  position: absolute;
  left: 5px;
  top: 18px;
  bottom: -6px;
  width: 2px;
  background: rgba(255,255,255,0.08);
}
.exec-step:last-child::before {
  display: none;
}
.exec-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #00d4ff;
  flex-shrink: 0;
  margin-top: 4px;
  position: relative;
  z-index: 1;
  border: 2px solid var(--bg-card, #1a1f2e);
}
.exec-dot-error {
  background: #e74c3c;
}
.exec-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.exec-step-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text, #e0e6ed);
}
.exec-error .exec-step-name {
  color: #e74c3c;
}
.exec-ts {
  font-size: 10px;
  color: var(--text-dim, #8a94a6);
  font-family: 'Consolas', 'Monaco', monospace;
}
.exec-msg {
  font-size: 11px;
  color: var(--text-dim, #8a94a6);
  word-break: break-all;
}
.exec-err-msg {
  font-size: 11px;
  color: #e74c3c;
  word-break: break-all;
}
.error-box {
  background: rgba(231, 76, 60, 0.08);
  border: 1px solid rgba(231, 76, 60, 0.3);
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 12px;
  color: #e74c3c;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
}

/* 抽屉动画 */
.drawer-enter-active, .drawer-leave-active {
  transition: opacity 0.3s;
}
.drawer-enter-active .log-drawer,
.drawer-leave-active .log-drawer {
  transition: transform 0.3s;
}
.drawer-enter-from, .drawer-leave-to {
  opacity: 0;
}
.drawer-enter-from .log-drawer,
.drawer-leave-to .log-drawer {
  transform: translateX(100%);
}
</style>
