<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import ModelUpload from '../components/ModelUpload.vue'
import MotionPreview from '../components/MotionPreview.vue'

const authStore = useAuthStore()

// === 顶部 Tab ===
const activeTab = ref('models')  // models / config / debug / voxel
const models = ref([])
const selectedModel = ref(null)
const newModel = ref({
  model_id: '',
  model_name: '',
  vendor: '',
  process_type: 'ETCH',
  view_mode: 'svg',
  description: '',
})

// === 动画配置编辑（DB 驱动） ===
const editingConfig = ref(null)
const editDirty = ref(false)
const svgPartsCache = ref([])  // ModelUpload 触发 svgPartsExtracted 时缓存的部件列表

// === 动画调试 ===
const debugFlow = ref('PACKING')
const testEvents = ref([])
const debugTestMachine = ref('PODOPENER-1')

// === 体素编辑器 ===
const voxelParts = ref([])
const selectedVoxelIndex = ref(null)

// === Toast ===
const toasts = ref([])
function toast(msg, type = 'info') {
  const id = Date.now() + Math.random()
  toasts.value.push({ id, msg, type })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, 3000)
}

// === 动画原语 action 枚举与字段映射 ===
const ACTION_TYPES = ['translate', 'rotate', 'scale', 'flash', 'visibility', 'color', 'scan', 'signal']
const AXIS_OPTIONS = ['x', 'y', 'z']
const EASING_OPTIONS = ['linear', 'mechanical', 'ease-in', 'ease-out', 'ease-in-out']

// 根据 action 类型返回需要显示的字段列表
function actionFields(action) {
  switch (action) {
    case 'translate':
    case 'rotate':
    case 'scale':
      return ['axis', 'from', 'to', 'duration_ms', 'easing']
    case 'flash':
    case 'color':
    case 'scan':
    case 'signal':
      return ['color', 'duration_ms', 'easing']
    case 'visibility':
      return ['from', 'to', 'duration_ms', 'easing']
    default:
      return []
  }
}

// === 模型管理 ===
async function loadModels() {
  try {
    models.value = await api.getModels()
  } catch (e) {
    console.error('加载模型失败:', e)
    toast(`加载模型失败: ${e.message}`, 'error')
  }
}

async function createModel() {
  if (!newModel.value.model_id) {
    toast('请输入型号ID', 'warn')
    return
  }
  try {
    await api.createModel(newModel.value)
    await loadModels()
    newModel.value = {
      model_id: '', model_name: '', vendor: '',
      process_type: 'ETCH', view_mode: 'svg', description: '',
    }
    toast('模型创建成功', 'success')
  } catch (e) {
    toast(`创建失败: ${e.message}`, 'error')
  }
}

function selectModel(m) {
  selectedModel.value = m
  // 同步加载该机型的动画配置到编辑器
  loadAnimConfig(m)
}

// === 动画配置：从机型 DB 字段 animation_config 读写 ===
function getAnimConfig(model) {
  // 优先使用 DB 中的 animation_config 字段，为空则初始化为空结构
  const cfg = model?.animation_config
  if (cfg && typeof cfg === 'object' && Object.keys(cfg).length > 0) {
    return JSON.parse(JSON.stringify(cfg))
  }
  return {
    machine_type: model?.model_id || '',
    version: '1.0',
    flows: {},
    animations: {},
    targets: {},
  }
}

function loadAnimConfig(model) {
  if (!model) {
    editingConfig.value = null
    editDirty.value = false
    return
  }
  editingConfig.value = getAnimConfig(model)
  editDirty.value = false
  // 默认选中第一个流程（用于调试Tab）
  const flowKeys = Object.keys(editingConfig.value.flows || {})
  if (flowKeys.length > 0 && !flowKeys.includes(debugFlow.value)) {
    debugFlow.value = flowKeys[0]
  }
}

// 配置Tab顶部机型下拉切换
function onConfigModelChange(modelId) {
  const m = models.value.find(x => x.model_id === modelId)
  if (m) {
    selectedModel.value = m
    loadAnimConfig(m)
  }
}

// 保存动画配置到 DB
async function saveAnimConfig() {
  if (!selectedModel.value || !editingConfig.value) {
    toast('请先选择机型', 'warn')
    return
  }
  try {
    await api.updateModel(selectedModel.value.model_id, {
      animation_config: editingConfig.value,
    })
    editDirty.value = false
    // 同步本地缓存
    selectedModel.value.animation_config = JSON.parse(JSON.stringify(editingConfig.value))
    const idx = models.value.findIndex(x => x.model_id === selectedModel.value.model_id)
    if (idx >= 0) {
      models.value[idx].animation_config = JSON.parse(JSON.stringify(editingConfig.value))
    }
    toast('动画配置已保存到DB', 'success')
  } catch (e) {
    toast(`保存失败: ${e.message}`, 'error')
  }
}

// 导出当前配置为 JSON 文件下载
function exportConfig() {
  if (!editingConfig.value) return
  const text = JSON.stringify(editingConfig.value, null, 2)
  const blob = new Blob([text], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${(selectedModel.value?.model_id || 'animation-config').toLowerCase()}.json`
  a.click()
  URL.revokeObjectURL(url)
  toast('配置已导出', 'success')
}

function markDirty() {
  editDirty.value = true
}

// === 部件绑定（targets） ===
function addTarget() {
  if (!editingConfig.value) return
  const idx = Object.keys(editingConfig.value.targets).length + 1
  const key = `part_${idx}`
  editingConfig.value.targets[key] = { view_2d: '', view_3d: '', desc: '' }
  markDirty()
}

function deleteTarget(key) {
  if (!editingConfig.value) return
  if (!confirm(`确定删除部件 "${key}"？`)) return
  delete editingConfig.value.targets[key]
  markDirty()
}

function renameTarget(oldKey, newKey) {
  if (!editingConfig.value || oldKey === newKey) return
  if (!newKey) {
    toast('部件 key 不能为空', 'error')
    return
  }
  if (editingConfig.value.targets[newKey]) {
    toast(`键 "${newKey}" 已存在`, 'error')
    return
  }
  const data = editingConfig.value.targets[oldKey]
  delete editingConfig.value.targets[oldKey]
  editingConfig.value.targets[newKey] = data
  markDirty()
}

// "从SVG提取"按钮：调用 api.extractSvgParts 获取部件列表，自动填充 view_2d 列
async function extractSvgPartsToTargets() {
  if (!selectedModel.value) {
    toast('请先选择机型', 'warn')
    return
  }
  try {
    const resp = await api.extractSvgParts(selectedModel.value.model_id)
    const parts = resp.parts || []
    svgPartsCache.value = parts
    if (parts.length === 0) {
      toast('未提取到任何SVG部件', 'warn')
      return
    }
    // 为每个 SVG 部件确保存在对应的 target，自动填充 view_2d
    for (const p of parts) {
      const id = p.element_id
      if (!id) continue
      // 已存在 view_2d == id 的项则跳过
      const existKey = Object.keys(editingConfig.value.targets).find(
        k => editingConfig.value.targets[k].view_2d === id
      )
      if (existKey) continue
      // 不存在则新建，key 默认为 element_id
      if (!editingConfig.value.targets[id]) {
        editingConfig.value.targets[id] = {
          view_2d: id,
          view_3d: '',
          desc: p.tag || '',
        }
      } else {
        editingConfig.value.targets[id].view_2d = id
      }
    }
    markDirty()
    toast(`已从SVG提取 ${parts.length} 个部件并填充 view_2d`, 'success')
  } catch (e) {
    toast(`提取失败: ${e.message}`, 'error')
  }
}

// ModelUpload 触发 svgPartsExtracted 时，缓存部件列表（供动画配置Tab使用）
function onSvgPartsExtracted(parts) {
  svgPartsCache.value = parts || []
}

// ModelUpload 触发 uploaded 事件时（文件上传成功后），重新拉取机型数据
// 修复：
// 1. 上传 SVG/JSON 后，本地 selectedModel.views_config / animation_config 不会自动刷新
// 2. 上传 JSON 后在任意 Tab 都立即 loadAnimConfig，否则切到调试Tab 拿不到 motionConfig（"没反应"）
async function onModelFileUploaded() {
  if (!selectedModel.value) return
  const currentId = selectedModel.value.model_id
  try {
    const fresh = await api.getModels()
    models.value = fresh || []
    // 重新选中当前机型，使 selectedModel 引用最新数据
    const updated = fresh?.find(m => m.model_id === currentId)
    if (updated) {
      selectedModel.value = updated
      // 上传后无论当前在哪个 Tab，都同步刷新 editingConfig
      // 这样切到调试Tab 时 MotionPreview 能立即拿到最新的 motionConfig
      loadAnimConfig(updated)
      const motionCfg = updated.animation_config
      if (motionCfg && motionCfg.schema_version) {
        toast(`动画配置已加载：v${motionCfg.schema_version}（${motionCfg.motions?.length || 0} 个步骤）`, 'success')
      }
    }
  } catch (e) {
    console.error('[ModelEditor] 上传后刷新机型数据失败:', e)
  }
}

// === 动画原语（animations） ===
function addAnimation() {
  if (!editingConfig.value) return
  const idx = Object.keys(editingConfig.value.animations).length + 1
  const key = `anim_${idx}`
  editingConfig.value.animations[key] = {
    target: '',
    action: 'translate',
    axis: 'y',
    from: 0,
    to: 0,
    duration_ms: 1000,
    easing: 'linear',
  }
  markDirty()
}

function deleteAnimation(key) {
  if (!editingConfig.value) return
  if (!confirm(`确定删除动画 "${key}"？`)) return
  delete editingConfig.value.animations[key]
  markDirty()
}

function renameAnimation(oldKey, newKey) {
  if (!editingConfig.value || oldKey === newKey) return
  if (!newKey) {
    toast('动画 key 不能为空', 'error')
    return
  }
  if (editingConfig.value.animations[newKey]) {
    toast(`键 "${newKey}" 已存在`, 'error')
    return
  }
  const data = editingConfig.value.animations[oldKey]
  delete editingConfig.value.animations[oldKey]
  editingConfig.value.animations[newKey] = data
  markDirty()
}

// === 流程配置（flows） ===
function addFlow() {
  if (!editingConfig.value) return
  const name = prompt('输入流程名称（如 PACKING）：')
  if (!name) return
  const key = name.toUpperCase()
  if (editingConfig.value.flows[key]) {
    toast(`流程 "${key}" 已存在`, 'error')
    return
  }
  editingConfig.value.flows[key] = { phases: [], event_to_phase: {} }
  markDirty()
}

function deleteFlow(flowKey) {
  if (!editingConfig.value) return
  if (!confirm(`确定删除流程 "${flowKey}"？`)) return
  delete editingConfig.value.flows[flowKey]
  markDirty()
}

function addPhase(flowKey) {
  if (!editingConfig.value) return
  const phases = editingConfig.value.flows[flowKey].phases
  phases.push({
    key: `PHASE_${phases.length + 1}`,
    label: '新阶段',
    duration_ms: 1000,
    easing: 'linear',
  })
  markDirty()
}

function deletePhase(flowKey, idx) {
  if (!editingConfig.value) return
  if (!confirm(`确定删除阶段 ${idx + 1}？`)) return
  editingConfig.value.flows[flowKey].phases.splice(idx, 1)
  markDirty()
}

function addEventMapping(flowKey) {
  if (!editingConfig.value) return
  const evtName = prompt('输入事件名（如 POD_PLACED）：')
  if (!evtName) return
  const flow = editingConfig.value.flows[flowKey]
  if (!flow.phases || flow.phases.length === 0) {
    toast('请先添加阶段', 'warn')
    return
  }
  const key = evtName.toUpperCase()
  if (flow.event_to_phase[key]) {
    toast(`事件 "${key}" 已存在`, 'error')
    return
  }
  flow.event_to_phase[key] = {
    phase: flow.phases[0].key,
    anim: '',
    note: '',
  }
  markDirty()
}

function deleteEventMapping(flowKey, evt) {
  if (!editingConfig.value) return
  delete editingConfig.value.flows[flowKey].event_to_phase[evt]
  markDirty()
}

// === 计算属性 ===
const targetKeys = computed(() => {
  if (!editingConfig.value) return []
  return Object.keys(editingConfig.value.targets || {})
})

const animationKeys = computed(() => {
  if (!editingConfig.value) return []
  return Object.keys(editingConfig.value.animations || {})
})

const flowKeys = computed(() => {
  if (!editingConfig.value) return []
  return Object.keys(editingConfig.value.flows || {})
})

// === 动画调试 ===
function manualTriggerEvent(eventName) {
  const fakeEvent = {
    event_code: eventName,
    event_name: eventName,
    timestamp: new Date().toISOString().replace(/Z$/, ''),
    tool_id: debugTestMachine.value,
    machine_state: 'running',
  }
  testEvents.value = [fakeEvent, ...testEvents.value].slice(0, 50)
  toast(`已触发事件: ${eventName}`, 'info')
  console.log('[ModelEditor][Debug] 手动触发事件:', eventName)
}

const manualEvents = computed(() => {
  if (!editingConfig.value) return []
  const flow = editingConfig.value.flows?.[debugFlow.value]
  if (!flow) return []
  return Object.entries(flow.event_to_phase || {}).map(([evt, def]) => ({
    event: evt,
    phase: def.phase,
    anim: def.anim,
    note: def.note || '',
  }))
})

const phaseList = computed(() => {
  if (!editingConfig.value) return []
  return editingConfig.value.flows?.[debugFlow.value]?.phases || []
})

// 跳转到指定阶段：找到该阶段对应的第一个事件并触发
function jumpToPhase(phaseKey) {
  if (!editingConfig.value) return
  const flow = editingConfig.value.flows?.[debugFlow.value]
  if (!flow) return
  const evt = Object.keys(flow.event_to_phase || {}).find(
    k => flow.event_to_phase[k].phase === phaseKey
  )
  if (evt) manualTriggerEvent(evt)
  else toast(`未找到跳转到 ${phaseKey} 的事件`, 'warn')
}

// === 体素编辑器 ===
function addVoxelPart(type) {
  const defaultPart = type === 'box' ? {
    name: `box_${voxelParts.value.length + 1}`,
    type: 'box',
    position: { x: 0, y: 0, z: 0 },
    size: { width: 1, height: 1, depth: 1 },
    color: '#4a90e2'
  } : {
    name: `cylinder_${voxelParts.value.length + 1}`,
    type: 'cylinder',
    position: { x: 0, y: 0, z: 0 },
    size: { radius: 0.5, height: 1 },
    color: '#e94a4a'
  }
  voxelParts.value.push(defaultPart)
  selectedVoxelIndex.value = voxelParts.value.length - 1
  toast(`已添加${type === 'box' ? '盒子' : '圆柱'}部件`, 'success')
}

function removeVoxelPart(idx) {
  voxelParts.value.splice(idx, 1)
  if (selectedVoxelIndex.value === idx) {
    selectedVoxelIndex.value = voxelParts.value.length > 0 ? Math.max(0, idx - 1) : null
  } else if (selectedVoxelIndex.value > idx) {
    selectedVoxelIndex.value -= 1
  }
  toast('已删除部件', 'info')
}

function exportVoxelConfig() {
  if (voxelParts.value.length === 0) {
    toast('没有可导出的部件', 'warn')
    return
  }
  const config = { parts: voxelParts.value }
  const text = JSON.stringify(config, null, 2)
  const blob = new Blob([text], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `voxel-model-${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
  toast('体素配置已导出', 'success')
}

// === SVG 预览 URL（从 views_config.view_2d.svg_source 获取） ===
// 过滤占位符（如 "procedural"），只认 /uploads/ 或 http(s):// 开头的真实 URL
// 否则 <object data="procedural"> 会被当相对路径 → vite SPA fallback → 嵌出主页看板
const svgPreviewUrl = computed(() => {
  if (!selectedModel.value) return ''
  const view2d = selectedModel.value.views_config?.view_2d
  if (!view2d) return ''
  const src = view2d.svg_source || view2d.url || ''
  if (!src || src === 'procedural') return ''
  if (!src.startsWith('/') && !src.startsWith('http')) return ''
  return src
})

// === Motion JSON 导入 ===
const importInput = ref(null)

function triggerImportJson() {
  importInput.value?.click()
}

async function onImportJson(e) {
  const file = e.target.files[0]
  if (!file) return
  e.target.value = ''

  if (!selectedModel.value) {
    toast('请先选择机型', 'warn')
    return
  }

  try {
    const text = await file.text()
    const data = JSON.parse(text)

    // 检测是否为通用 Motion JSON 格式
    if (!data.schema_version) {
      toast('文件中没有 schema_version 字段，不是通用 Motion JSON 格式', 'error')
      return
    }

    // 填入编辑器
    editingConfig.value = data
    editDirty.value = true
    toast(`已导入 Motion JSON v${data.schema_version}（${data.motions?.length || 0} 个步骤）`, 'success')
  } catch (err) {
    toast(`导入失败: ${err.message}`, 'error')
  }
}

// === MotionPreview 绑定 ===
const motionPreviewSvgUrl = computed(() => svgPreviewUrl.value)
const motionPreviewConfig = computed(() => {
  if (!editingConfig.value) return null
  // 如果是通用 Motion JSON 格式，直接返回
  if (editingConfig.value.schema_version) return editingConfig.value
  // 旧格式暂不支持，返回 null
  return null
})

// === 生命周期 ===
onMounted(async () => {
  await loadModels()
})
</script>

<template>
  <div class="model-editor">
    <div class="editor-header">
      <h1>🛠️ 模型编辑器</h1>
      <div class="header-tabs">
        <button
          v-for="tab in [
            { key: 'models', label: '📦 模型管理' },
            { key: 'config', label: '⚙️ 动画配置' },
            { key: 'debug', label: '🔍 动画调试' },
            { key: 'voxel', label: '🧊 体素建模' },
          ]"
          :key="tab.key"
          class="tab-btn"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>
    </div>

    <div class="tab-content-wrapper">
      <!-- ==================== Tab 1: 模型管理 ==================== -->
      <div v-show="activeTab === 'models'" class="models-panel">
        <div class="models-toolbar">
          <button class="btn-primary" @click="loadModels">🔄 刷新</button>
          <span class="toolbar-hint">共 {{ models.length }} 个机台型号</span>
        </div>

        <div class="models-grid">
          <div
            v-for="model in models"
            :key="model.model_id"
            class="model-card"
            :class="{ selected: selectedModel?.model_id === model.model_id }"
            @click="selectModel(model)"
          >
            <div class="model-header">
              <span class="model-id">{{ model.model_id }}</span>
              <span class="model-vendor">{{ model.vendor }}</span>
            </div>
            <div class="model-name">{{ model.model_name }}</div>
            <div class="model-meta">
              <span>{{ model.process_type }}</span>
              <span>{{ model.view_mode }}</span>
            </div>
            <div class="model-desc">{{ model.description }}</div>
          </div>
        </div>

        <!-- 模型文件上传与预览 -->
        <div v-if="selectedModel" class="upload-section">
          <ModelUpload
            :model-id="selectedModel.model_id"
            :model-name="selectedModel.model_name"
            @uploaded="onModelFileUploaded"
            @svg-parts-extracted="onSvgPartsExtracted"
          />
        </div>
        <div v-else class="select-hint">
          <p>👈 请先点击上方卡片选择一个机型，然后上传模型文件</p>
        </div>

        <!-- SVG 预览（views_config.view_2d.svg_source 存在时显示） -->
        <div v-if="selectedModel && svgPreviewUrl" class="svg-preview-section">
          <h3>🖼️ SVG 预览</h3>
          <div class="svg-preview-wrapper">
            <object
              :data="svgPreviewUrl"
              type="image/svg+xml"
              class="svg-preview-object"
            >
              <iframe :src="svgPreviewUrl" class="svg-preview-iframe" title="SVG Preview"></iframe>
            </object>
          </div>
          <div class="svg-preview-url">🔗 {{ svgPreviewUrl }}</div>
        </div>

        <!-- 新建机型表单（需 model_edit 权限） -->
        <div v-if="authStore.hasPermission('model_edit')" class="create-panel">
          <h3>新建机台型号</h3>
          <div class="form-grid">
            <div class="form-item">
              <label>型号ID *</label>
              <input v-model="newModel.model_id" placeholder="如：PODOPENER-1" />
            </div>
            <div class="form-item">
              <label>型号名称</label>
              <input v-model="newModel.model_name" placeholder="如：真空预对准机" />
            </div>
            <div class="form-item">
              <label>厂商</label>
              <input v-model="newModel.vendor" placeholder="如：TEL" />
            </div>
            <div class="form-item">
              <label>工艺类型</label>
              <select v-model="newModel.process_type">
                <option value="ETCH">刻蚀</option>
                <option value="LITHO">光刻</option>
                <option value="CVD">沉积</option>
                <option value="PVD">物理气相沉积</option>
                <option value="CMP">化学机械抛光</option>
                <option value="WET">湿法工艺</option>
                <option value="METAL">金属化</option>
                <option value="INSPECT">检测</option>
              </select>
            </div>
            <div class="form-item">
              <label>视图模式</label>
              <select v-model="newModel.view_mode">
                <option value="svg">SVG 2D</option>
                <option value="threejs">Three.js 3D</option>
                <option value="isometric">2.5D 等角</option>
                <option value="vpo">PODOPENER 2D</option>
                <option value="vpo3d">PODOPENER 3D</option>
                <option value="hybrid">混合模式</option>
              </select>
            </div>
            <div class="form-item full">
              <label>描述</label>
              <textarea v-model="newModel.description" placeholder="型号描述"></textarea>
            </div>
          </div>
          <button class="btn-primary" @click="createModel">创建型号</button>
        </div>

        <div v-if="!authStore.hasPermission('model_edit')" class="no-permission">
          <p>⚠️ 您没有模型编辑权限</p>
          <p>普通用户只能查看模型配置，无法编辑或创建</p>
        </div>
      </div>

      <!-- ==================== Tab 2: 动画配置（DB 驱动） ==================== -->
      <div v-show="activeTab === 'config'" class="config-panel">
        <!-- 顶部工具栏 -->
        <div class="config-toolbar">
          <div class="config-selector">
            <label>选择机型：</label>
            <select
              :value="selectedModel?.model_id"
              @change="onConfigModelChange($event.target.value)"
            >
              <option value="" disabled>请选择机型</option>
              <option v-for="m in models" :key="m.model_id" :value="m.model_id">
                {{ m.model_id }} ({{ m.model_name }})
              </option>
            </select>
          </div>
          <div class="config-actions">
            <button
              class="btn-import"
              :disabled="!selectedModel"
              @click="triggerImportJson"
              title="导入通用 Motion JSON 格式文件"
            >
              📥 导入Motion JSON
            </button>
            <input
              ref="importInput"
              type="file"
              accept=".json"
              style="display: none;"
              @change="onImportJson"
            />
            <button
              class="btn-save"
              :disabled="!editDirty || !selectedModel"
              @click="saveAnimConfig"
            >
              💾 保存到DB
            </button>
            <button
              class="btn-export"
              :disabled="!editingConfig"
              @click="exportConfig"
            >
              📤 导出JSON
            </button>
            <span v-if="editDirty" class="dirty-flag">● 有未保存变更</span>
          </div>
        </div>

        <div v-if="!selectedModel" class="empty-hint">请先在“模型管理”中选择机型，或在此下拉选择</div>
        <div v-else-if="!editingConfig" class="empty-hint">加载中...</div>
        <div v-else class="config-editor">
          <!-- 左右两栏布局 -->
          <div class="config-split-view">
            <!-- ============ 左栏 ============ -->
            <div class="config-left-panel">
              <!-- 左栏上：部件绑定 targets -->
              <div class="left-section">
                <div class="section-header">
                  <h4>🎯 部件绑定（{{ targetKeys.length }} 个）</h4>
                  <div class="section-actions">
                    <button class="btn-small" @click="extractSvgPartsToTargets">🔍 从SVG提取</button>
                    <button class="btn-small" @click="addTarget">+ 添加部件</button>
                  </div>
                </div>
                <div class="data-table target-table">
                  <div class="table-row table-header">
                    <div class="col-key">key</div>
                    <div class="col-2d">view_2d (SVG id)</div>
                    <div class="col-3d">view_3d (Group)</div>
                    <div class="col-desc">desc</div>
                    <div class="col-op">操作</div>
                  </div>
                  <div v-for="key in targetKeys" :key="key" class="table-row">
                    <div class="col-key">
                      <input :value="key" @change="renameTarget(key, $event.target.value)" />
                    </div>
                    <div class="col-2d">
                      <input v-model="editingConfig.targets[key].view_2d" @input="markDirty" />
                    </div>
                    <div class="col-3d">
                      <input v-model="editingConfig.targets[key].view_3d" @input="markDirty" />
                    </div>
                    <div class="col-desc">
                      <input v-model="editingConfig.targets[key].desc" @input="markDirty" />
                    </div>
                    <div class="col-op">
                      <button class="btn-delete" @click="deleteTarget(key)" title="删除">×</button>
                    </div>
                  </div>
                  <div v-if="targetKeys.length === 0" class="empty-row">
                    暂无部件，点击 "+ 添加部件" 或 "从SVG提取"
                  </div>
                </div>
              </div>

              <!-- 左栏下：动画原语 animations -->
              <div class="left-section">
                <div class="section-header">
                  <h4>🎬 动画原语（{{ animationKeys.length }} 个）</h4>
                  <div class="section-actions">
                    <button class="btn-small" @click="addAnimation">+ 添加动画</button>
                  </div>
                </div>
                <div class="anim-grid">
                  <div v-for="aKey in animationKeys" :key="aKey" class="anim-card">
                    <div class="anim-card-header">
                      <input
                        class="anim-key-input"
                        :value="aKey"
                        @change="renameAnimation(aKey, $event.target.value)"
                      />
                      <select
                        v-model="editingConfig.animations[aKey].action"
                        class="anim-action-select"
                        @change="markDirty"
                      >
                        <option v-for="a in ACTION_TYPES" :key="a" :value="a">{{ a }}</option>
                      </select>
                      <button class="btn-delete" @click="deleteAnimation(aKey)" title="删除">×</button>
                    </div>
                    <div class="anim-fields">
                      <div class="anim-field">
                        <label>target</label>
                        <select v-model="editingConfig.animations[aKey].target" @change="markDirty">
                          <option value="">(无)</option>
                          <option v-for="t in targetKeys" :key="t" :value="t">{{ t }}</option>
                        </select>
                      </div>
                      <template v-if="actionFields(editingConfig.animations[aKey].action).includes('axis')">
                        <div class="anim-field">
                          <label>axis</label>
                          <select v-model="editingConfig.animations[aKey].axis" @change="markDirty">
                            <option v-for="ax in AXIS_OPTIONS" :key="ax" :value="ax">{{ ax }}</option>
                          </select>
                        </div>
                      </template>
                      <template v-if="actionFields(editingConfig.animations[aKey].action).includes('from')">
                        <div class="anim-field">
                          <label>from</label>
                          <input
                            type="number"
                            v-model.number="editingConfig.animations[aKey].from"
                            @input="markDirty"
                          />
                        </div>
                      </template>
                      <template v-if="actionFields(editingConfig.animations[aKey].action).includes('to')">
                        <div class="anim-field">
                          <label>to</label>
                          <input
                            type="number"
                            v-model.number="editingConfig.animations[aKey].to"
                            @input="markDirty"
                          />
                        </div>
                      </template>
                      <template v-if="actionFields(editingConfig.animations[aKey].action).includes('color')">
                        <div class="anim-field">
                          <label>color</label>
                          <input
                            type="color"
                            v-model="editingConfig.animations[aKey].color"
                            @input="markDirty"
                          />
                        </div>
                      </template>
                      <template v-if="actionFields(editingConfig.animations[aKey].action).includes('duration_ms')">
                        <div class="anim-field">
                          <label>duration_ms</label>
                          <input
                            type="number"
                            v-model.number="editingConfig.animations[aKey].duration_ms"
                            @input="markDirty"
                          />
                        </div>
                      </template>
                      <template v-if="actionFields(editingConfig.animations[aKey].action).includes('easing')">
                        <div class="anim-field">
                          <label>easing</label>
                          <select v-model="editingConfig.animations[aKey].easing" @change="markDirty">
                            <option v-for="e in EASING_OPTIONS" :key="e" :value="e">{{ e }}</option>
                          </select>
                        </div>
                      </template>
                    </div>
                  </div>
                  <div v-if="animationKeys.length === 0" class="empty-row">
                    暂无动画，点击 "+ 添加动画"
                  </div>
                </div>
              </div>
            </div>

            <!-- ============ 右栏：流程配置 flows ============ -->
            <div class="config-right-panel">
              <div class="section-header">
                <h4>📋 流程配置（{{ flowKeys.length }} 个）</h4>
                <button class="btn-small" @click="addFlow">+ 添加流程</button>
              </div>

              <div v-for="flowKey in flowKeys" :key="flowKey" class="flow-section">
                <div class="flow-section-header">
                  <h4>🔄 {{ flowKey }}</h4>
                  <button class="btn-delete" @click="deleteFlow(flowKey)" title="删除流程">×</button>
                </div>

                <!-- 阶段序列 -->
                <div class="flow-sub-section">
                  <div class="flow-header">
                    <span>阶段序列（{{ editingConfig.flows[flowKey].phases.length }}）</span>
                    <button class="btn-small" @click="addPhase(flowKey)">+ 添加阶段</button>
                  </div>
                  <div class="data-table phase-table">
                    <div class="table-row table-header">
                      <div class="p-key">key</div>
                      <div class="p-label">label</div>
                      <div class="p-dur">duration_ms</div>
                      <div class="p-easing">easing</div>
                      <div class="p-op">操作</div>
                    </div>
                    <div
                      v-for="(p, idx) in editingConfig.flows[flowKey].phases"
                      :key="idx"
                      class="table-row"
                    >
                      <div class="p-key"><input v-model="p.key" @input="markDirty" /></div>
                      <div class="p-label"><input v-model="p.label" @input="markDirty" /></div>
                      <div class="p-dur">
                        <input type="number" v-model.number="p.duration_ms" @input="markDirty" />
                      </div>
                      <div class="p-easing">
                        <select v-model="p.easing" @change="markDirty">
                          <option v-for="e in EASING_OPTIONS" :key="e" :value="e">{{ e }}</option>
                        </select>
                      </div>
                      <div class="p-op">
                        <button class="btn-delete" @click="deletePhase(flowKey, idx)">×</button>
                      </div>
                    </div>
                    <div v-if="editingConfig.flows[flowKey].phases.length === 0" class="empty-row">
                      暂无阶段
                    </div>
                  </div>
                </div>

                <!-- 事件映射 -->
                <div class="flow-sub-section">
                  <div class="flow-header">
                    <span>事件映射（{{ Object.keys(editingConfig.flows[flowKey].event_to_phase).length }}）</span>
                    <button class="btn-small" @click="addEventMapping(flowKey)">+ 添加事件</button>
                  </div>
                  <div class="data-table event-table">
                    <div class="table-row table-header">
                      <div class="e-name">event_name</div>
                      <div class="e-phase">phase</div>
                      <div class="e-anim">anim</div>
                      <div class="e-note">note</div>
                      <div class="e-op">操作</div>
                    </div>
                    <div
                      v-for="(def, evt) in editingConfig.flows[flowKey].event_to_phase"
                      :key="evt"
                      class="table-row"
                    >
                      <div class="e-name"><span class="event-tag">{{ evt }}</span></div>
                      <div class="e-phase">
                        <select v-model="def.phase" @change="markDirty">
                          <option
                            v-for="p in editingConfig.flows[flowKey].phases"
                            :key="p.key"
                            :value="p.key"
                          >
                            {{ p.key }}
                          </option>
                        </select>
                      </div>
                      <div class="e-anim">
                        <select v-model="def.anim" @change="markDirty">
                          <option value="">(无)</option>
                          <option v-for="a in animationKeys" :key="a" :value="a">{{ a }}</option>
                        </select>
                      </div>
                      <div class="e-note"><input v-model="def.note" @input="markDirty" /></div>
                      <div class="e-op">
                        <button class="btn-delete" @click="deleteEventMapping(flowKey, evt)">×</button>
                      </div>
                    </div>
                    <div
                      v-if="Object.keys(editingConfig.flows[flowKey].event_to_phase).length === 0"
                      class="empty-row"
                    >
                      暂无事件
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="flowKeys.length === 0" class="empty-row">暂无流程，点击 "+ 添加流程"</div>
            </div>
          </div>
        </div>
      </div>

      <!-- ==================== Tab 3: 动画调试（MotionPreview） ==================== -->
      <div v-show="activeTab === 'debug'" class="debug-panel">
        <div class="debug-toolbar">
          <div class="debug-selectors">
            <select
              :value="selectedModel?.model_id"
              @change="onConfigModelChange($event.target.value)"
            >
              <option value="" disabled>选择机型</option>
              <option v-for="m in models" :key="m.model_id" :value="m.model_id">
                {{ m.model_id }}
              </option>
            </select>
          </div>
        </div>

        <div v-if="!selectedModel" class="empty-hint">请先选择机型</div>
        <div v-else-if="!motionPreviewConfig" class="empty-hint">
          该机型未配置通用 Motion JSON。
          请到"动画配置" Tab 点击"导入Motion JSON"按钮导入配置文件，
          或上传带 schema_version 的 .json 文件。
        </div>
        <MotionPreview
          v-else
          :svg-url="motionPreviewSvgUrl"
          :motion-config="motionPreviewConfig"
          style="height: calc(100% - 50px);"
        />
      </div>

      <!-- ==================== Tab 4: 体素建模 ==================== -->
      <div v-show="activeTab === 'voxel'" class="voxel-panel">
        <div class="voxel-toolbar">
          <h3>🧊 体素建模编辑器</h3>
          <div class="voxel-actions">
            <button class="btn-primary" @click="addVoxelPart('box')">+ 添加盒子</button>
            <button class="btn-primary" @click="addVoxelPart('cylinder')">+ 添加圆柱</button>
            <button class="btn-export" @click="exportVoxelConfig">💾 导出 JSON</button>
          </div>
        </div>

        <div class="voxel-grid">
          <!-- 左侧：部件列表 -->
          <div class="voxel-left">
            <h4>📦 部件列表（{{ voxelParts.length }}）</h4>
            <div class="voxel-parts-list">
              <div
                v-for="(part, idx) in voxelParts"
                :key="idx"
                class="voxel-part-item"
                :class="{ selected: selectedVoxelIndex === idx }"
                @click="selectedVoxelIndex = idx"
              >
                <span class="part-type">{{ part.type }}</span>
                <span class="part-name">{{ part.name }}</span>
                <button class="btn-delete" @click.stop="removeVoxelPart(idx)">×</button>
              </div>
            </div>
          </div>

          <!-- 右侧：属性编辑 + 预览 -->
          <div class="voxel-right">
            <div v-if="selectedVoxelIndex !== null && voxelParts[selectedVoxelIndex]" class="voxel-editor">
              <h4>✏️ 编辑部件属性</h4>
              <div class="voxel-form">
                <div class="form-row">
                  <label>名称：</label>
                  <input v-model="voxelParts[selectedVoxelIndex].name" type="text" />
                </div>
                <div class="form-row">
                  <label>类型：</label>
                  <span class="type-badge">{{ voxelParts[selectedVoxelIndex].type }}</span>
                </div>
                <div class="form-row">
                  <label>位置 X：</label>
                  <input v-model.number="voxelParts[selectedVoxelIndex].position.x" type="number" step="0.1" />
                </div>
                <div class="form-row">
                  <label>位置 Y：</label>
                  <input v-model.number="voxelParts[selectedVoxelIndex].position.y" type="number" step="0.1" />
                </div>
                <div class="form-row">
                  <label>位置 Z：</label>
                  <input v-model.number="voxelParts[selectedVoxelIndex].position.z" type="number" step="0.1" />
                </div>
                <div class="form-row" v-if="voxelParts[selectedVoxelIndex].type === 'box'">
                  <label>宽度：</label>
                  <input v-model.number="voxelParts[selectedVoxelIndex].size.width" type="number" step="0.1" />
                </div>
                <div class="form-row" v-if="voxelParts[selectedVoxelIndex].type === 'box'">
                  <label>高度：</label>
                  <input v-model.number="voxelParts[selectedVoxelIndex].size.height" type="number" step="0.1" />
                </div>
                <div class="form-row" v-if="voxelParts[selectedVoxelIndex].type === 'box'">
                  <label>深度：</label>
                  <input v-model.number="voxelParts[selectedVoxelIndex].size.depth" type="number" step="0.1" />
                </div>
                <div class="form-row" v-if="voxelParts[selectedVoxelIndex].type === 'cylinder'">
                  <label>半径：</label>
                  <input v-model.number="voxelParts[selectedVoxelIndex].size.radius" type="number" step="0.1" />
                </div>
                <div class="form-row" v-if="voxelParts[selectedVoxelIndex].type === 'cylinder'">
                  <label>高度：</label>
                  <input v-model.number="voxelParts[selectedVoxelIndex].size.height" type="number" step="0.1" />
                </div>
                <div class="form-row">
                  <label>颜色：</label>
                  <input v-model="voxelParts[selectedVoxelIndex].color" type="color" />
                </div>
              </div>
            </div>
            <div v-else class="empty-hint">
              👈 请选择左侧部件进行编辑，或点击上方按钮添加新部件
            </div>

            <div class="voxel-preview">
              <h4>👁️ 配置预览</h4>
              <pre class="preview-code">{{ JSON.stringify({ parts: voxelParts }, null, 2) }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Toast -->
    <div class="toast-container">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="t.type">{{ t.msg }}</div>
    </div>
  </div>
</template>

<style scoped>
.model-editor {
  padding: 20px;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  color: var(--text);
  background: var(--bg);
}
.editor-header {
  margin-bottom: 20px;
  flex-shrink: 0;
}
.editor-header h1 {
  font-size: 20px;
  margin-bottom: 12px;
}
.header-tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.tab-content-wrapper {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  position: relative;
}
.models-panel,
.config-panel,
.debug-panel,
.voxel-panel {
  height: 100%;
  overflow-y: auto;
}
.tab-btn {
  padding: 8px 16px;
  border: 1px solid var(--border);
  background: var(--panel);
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  color: var(--text);
}
.tab-btn:hover { border-color: var(--accent); }
.tab-btn.active {
  background: rgba(0, 212, 255, 0.15);
  border-color: var(--accent);
  color: var(--accent);
}

/* 通用按钮 */
.btn-primary {
  background: var(--accent);
  color: #000;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  font-weight: 700;
  font-size: 13px;
  cursor: pointer;
}
.btn-primary:hover { opacity: 0.9; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-small {
  background: var(--panel-2);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
}
.btn-small:hover { border-color: var(--accent); }
.btn-delete {
  background: transparent;
  color: var(--text-dim);
  border: none;
  font-size: 16px;
  cursor: pointer;
  padding: 2px 6px;
}
.btn-delete:hover { color: var(--red); }
.empty-hint {
  color: var(--text-dim);
  font-style: italic;
  padding: 20px;
  text-align: center;
}
.empty-row {
  color: var(--text-dim);
  font-size: 12px;
  padding: 12px;
  text-align: center;
  font-style: italic;
}

/* ============ 模型管理 Tab ============ */
.models-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 16px;
}
.toolbar-hint { color: var(--text-dim); font-size: 12px; }
.models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.model-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
  cursor: pointer;
  transition: all 0.2s;
}
.model-card:hover { border-color: var(--accent); }
.model-card.selected {
  border-color: var(--accent);
  background: rgba(0, 212, 255, 0.08);
}
.model-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.model-id { font-family: monospace; font-weight: 700; color: var(--accent); }
.model-vendor { font-size: 11px; color: var(--text-dim); }
.model-name { font-weight: 600; margin-bottom: 6px; }
.model-meta { display: flex; gap: 8px; font-size: 11px; color: var(--text-dim); margin-bottom: 8px; }
.model-desc { font-size: 11.5px; color: var(--text-dim); line-height: 1.4; }

.upload-section { margin-top: 16px; }
.select-hint {
  text-align: center;
  padding: 24px;
  background: var(--panel-2);
  border: 1px dashed var(--border);
  border-radius: 10px;
  margin-top: 16px;
  color: var(--text-dim);
  font-size: 13px;
}
.select-hint p { margin: 0; }

/* SVG 预览 */
.svg-preview-section {
  margin-top: 16px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}
.svg-preview-section h3 {
  font-size: 15px;
  margin-bottom: 12px;
  color: var(--accent);
}
.svg-preview-wrapper {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  height: 400px;
}
.svg-preview-object,
.svg-preview-iframe {
  width: 100%;
  height: 100%;
  border: none;
  display: block;
}
.svg-preview-url {
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-dim);
  font-family: monospace;
  word-break: break-all;
}

/* 新建机型表单 */
.create-panel { background: var(--panel); border-radius: 8px; padding: 20px; margin-top: 24px; }
.create-panel h3 { font-size: 15px; margin-bottom: 16px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 16px; }
.form-item.full { grid-column: span 2; }
.form-item label { display: block; font-size: 11px; color: var(--text-dim); margin-bottom: 4px; }
.form-item input, .form-item select, .form-item textarea {
  width: 100%;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 12.5px;
  outline: none;
  box-sizing: border-box;
}
.form-item input:focus, .form-item select:focus, .form-item textarea:focus { border-color: var(--accent); }
.form-item textarea { resize: vertical; min-height: 60px; }
.no-permission {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  padding: 20px;
  text-align: center;
  margin-top: 24px;
}
.no-permission p { margin: 4px 0; color: var(--text-dim); }

/* ============ 动画配置 Tab ============ */
.config-panel { background: var(--panel); border-radius: 8px; }
.config-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
  gap: 8px;
  position: sticky;
  top: 0;
  background: var(--panel);
  z-index: 2;
}
.config-selector label { font-size: 12px; color: var(--text-dim); margin-right: 8px; }
.config-selector select,
.debug-selectors select,
.machine-input {
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 13px;
  outline: none;
}
.config-selector select:focus,
.debug-selectors select:focus { border-color: var(--accent); }
.config-actions { display: flex; gap: 8px; align-items: center; }
.btn-save {
  background: var(--green);
  color: #fff;
  border: none;
  padding: 6px 14px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}
.btn-save:hover { opacity: 0.9; }
.btn-save:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-import {
  background: var(--yellow);
  color: #000;
  border: none;
  padding: 6px 14px;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 700;
  font-size: 13px;
}
.btn-import:hover { opacity: 0.9; }
.btn-import:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-export {
  background: var(--accent);
  color: #000;
  border: none;
  padding: 6px 14px;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 700;
  font-size: 13px;
}
.btn-export:hover { opacity: 0.9; }
.btn-export:disabled { opacity: 0.5; cursor: not-allowed; }
.dirty-flag { color: var(--yellow); font-size: 12px; font-weight: 600; }

.config-editor { padding: 0; }
.config-split-view {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  padding: 16px;
}
@media (max-width: 1100px) {
  .config-split-view { grid-template-columns: 1fr; }
}
.config-left-panel,
.config-right-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

/* 区块标题 */
.left-section,
.flow-section {
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
}
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  flex-wrap: wrap;
  gap: 8px;
}
.section-header h4 {
  color: var(--accent);
  font-size: 13px;
  margin: 0;
}
.section-actions { display: flex; gap: 6px; }

/* 通用表格样式 */
.data-table {
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: var(--bg);
  border-radius: 4px;
  overflow: hidden;
}
.table-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  border-bottom: 1px solid var(--border);
  min-height: 32px;
}
.table-row:last-child { border-bottom: none; }
.table-header {
  background: var(--panel);
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 600;
  border-bottom: 1px solid var(--border-2);
}
.table-row input,
.table-row select {
  width: 100%;
  background: var(--panel);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 3px 6px;
  border-radius: 3px;
  font-size: 12px;
  outline: none;
  min-width: 0;
}
.table-row input:focus,
.table-row select:focus { border-color: var(--accent); }

/* targets 表格列宽 */
.target-table .col-key { flex: 1.2; min-width: 100px; }
.target-table .col-2d { flex: 1.5; min-width: 120px; }
.target-table .col-3d { flex: 1.5; min-width: 120px; }
.target-table .col-desc { flex: 1.5; min-width: 120px; }
.target-table .col-op { width: 36px; flex-shrink: 0; text-align: center; }

/* phase 表格列宽 */
.phase-table .p-key { flex: 1.2; min-width: 100px; }
.phase-table .p-label { flex: 1.5; min-width: 120px; }
.phase-table .p-dur { flex: 1; min-width: 90px; }
.phase-table .p-easing { flex: 1; min-width: 100px; }
.phase-table .p-op { width: 36px; flex-shrink: 0; text-align: center; }

/* event 表格列宽 */
.event-table .e-name { flex: 1.5; min-width: 140px; }
.event-table .e-phase { flex: 1.3; min-width: 110px; }
.event-table .e-anim { flex: 1.3; min-width: 110px; }
.event-table .e-note { flex: 1.5; min-width: 120px; }
.event-table .e-op { width: 36px; flex-shrink: 0; text-align: center; }
.event-tag {
  font-family: monospace;
  font-size: 11px;
  color: var(--yellow);
  font-weight: 600;
  word-break: break-all;
}

/* 动画原语卡片网格 */
.anim-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 8px;
}
.anim-card {
  background: var(--bg);
  border-radius: 6px;
  padding: 10px;
  border: 1px solid var(--border);
}
.anim-card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}
.anim-key-input {
  flex: 1;
  background: var(--panel);
  color: var(--accent);
  border: 1px solid var(--border);
  padding: 3px 6px;
  border-radius: 3px;
  font-size: 12px;
  font-family: monospace;
  outline: none;
  min-width: 0;
}
.anim-key-input:focus { border-color: var(--accent); }
.anim-action-select {
  background: rgba(6, 182, 212, 0.15);
  color: #06b6d4;
  border: 1px solid rgba(6, 182, 212, 0.3);
  padding: 3px 6px;
  border-radius: 10px;
  font-size: 11px;
  outline: none;
  cursor: pointer;
}
.anim-fields { display: flex; flex-direction: column; gap: 4px; }
.anim-field { display: flex; align-items: center; gap: 8px; font-size: 11px; }
.anim-field label {
  color: var(--text-dim);
  min-width: 80px;
  flex-shrink: 0;
}
.anim-field input,
.anim-field select {
  flex: 1;
  background: var(--panel);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  outline: none;
  min-width: 0;
}
.anim-field input:focus,
.anim-field select:focus { border-color: var(--accent); }
.anim-field input[type="color"] {
  height: 22px;
  padding: 1px;
  cursor: pointer;
}

/* 流程区块 */
.flow-section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.flow-section-header h4 {
  color: var(--accent);
  font-size: 14px;
  margin: 0;
}
.flow-sub-section { margin-top: 12px; }
.flow-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--text-dim);
  font-weight: 600;
}

/* ============ 动画调试 Tab ============ */
.debug-panel { background: var(--panel); border-radius: 8px; }
.debug-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
  gap: 8px;
}
.debug-selectors { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.machine-input { width: 150px; }
.debug-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  padding: 16px;
}
@media (max-width: 900px) {
  .debug-grid { grid-template-columns: 1fr; }
}
.debug-left, .debug-right { display: flex; flex-direction: column; }
.debug-left h4, .debug-right h4 {
  color: var(--accent);
  font-size: 13px;
  margin-bottom: 10px;
}
.manual-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 6px;
}
.manual-btn {
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 8px;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s;
}
.manual-btn:hover { background: var(--panel-2); border-color: var(--accent); }
.btn-event { font-weight: 600; color: var(--yellow); font-size: 11px; }
.btn-phase { color: #a0c4ff; font-size: 10px; margin-top: 2px; }
.btn-anim { color: #06b6d4; font-size: 10px; margin-top: 2px; }
.phase-jump { display: flex; flex-wrap: wrap; gap: 4px; }
.phase-btn {
  background: var(--bg);
  color: var(--text-dim);
  border: 1px solid var(--border);
  padding: 4px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 11px;
}
.phase-btn:hover { background: var(--panel-2); color: var(--text); }

.event-log {
  max-height: 500px;
  overflow-y: auto;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
}
.event-log-item {
  display: flex;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}
.event-log-item:last-child { border-bottom: none; }
.log-time { color: var(--text-dim); font-family: monospace; }
.log-event { color: var(--yellow); font-weight: 600; }
.log-tool { color: var(--text-dim); margin-left: auto; }

.debug-tip {
  margin: 0 16px 16px;
  padding: 10px 14px;
  background: rgba(245, 158, 11, 0.1);
  border-left: 3px solid var(--yellow);
  font-size: 12px;
  color: #c0c0a0;
  border-radius: 0 4px 4px 0;
}
.debug-tip a { color: var(--accent); text-decoration: underline; }

/* ============ 体素编辑器 Tab ============ */
.voxel-panel { background: var(--panel); border-radius: 8px; }
.voxel-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
  gap: 8px;
}
.voxel-toolbar h3 { margin: 0; font-size: 15px; color: var(--accent); }
.voxel-actions { display: flex; gap: 8px; }
.voxel-grid {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 16px;
  padding: 16px;
}
@media (max-width: 900px) {
  .voxel-grid { grid-template-columns: 1fr; }
}
.voxel-left {
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--bg);
  border-radius: 6px;
  padding: 12px;
}
.voxel-left h4 {
  color: var(--accent);
  font-size: 13px;
  margin: 0 0 8px 0;
}
.voxel-parts-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 400px;
  overflow-y: auto;
}
.voxel-part-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}
.voxel-part-item:hover { border-color: var(--accent); }
.voxel-part-item.selected {
  background: rgba(0, 212, 255, 0.1);
  border-color: var(--accent);
}
.part-type {
  font-size: 11px;
  padding: 2px 8px;
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent);
  border-radius: 10px;
}
.part-name { flex: 1; font-size: 12px; color: var(--text); }
.voxel-right {
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
}
.voxel-editor { background: var(--bg); border-radius: 6px; padding: 12px; }
.voxel-editor h4 {
  color: var(--accent);
  font-size: 13px;
  margin: 0 0 12px 0;
}
.voxel-form { display: flex; flex-direction: column; gap: 8px; }
.voxel-form .form-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.voxel-form .form-row label {
  min-width: 80px;
  font-size: 12px;
  color: var(--text-dim);
}
.voxel-form .form-row input {
  flex: 1;
  background: var(--panel);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 4px 8px;
  border-radius: 3px;
  font-size: 12px;
}
.voxel-form .form-row input:focus { border-color: var(--accent); }
.type-badge {
  font-size: 11px;
  padding: 3px 10px;
  background: rgba(6, 182, 212, 0.15);
  color: #06b6d4;
  border-radius: 10px;
  font-weight: 600;
}
.voxel-preview {
  background: var(--bg);
  border-radius: 6px;
  padding: 12px;
}
.voxel-preview h4 {
  color: var(--accent);
  font-size: 13px;
  margin: 0 0 8px 0;
}
.preview-code {
  background: var(--panel-2);
  border-radius: 4px;
  padding: 10px;
  font-family: 'Consolas', monospace;
  font-size: 11px;
  line-height: 1.4;
  color: var(--text);
  overflow-x: auto;
  margin: 0;
  max-height: 300px;
  overflow-y: auto;
}

/* ============ Toast ============ */
.toast-container {
  position: fixed;
  bottom: 20px;
  right: 20px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  z-index: 9999;
}
.toast {
  padding: 10px 16px;
  border-radius: 6px;
  font-size: 13px;
  color: #fff;
  animation: slideIn 0.2s;
}
.toast.success { background: var(--green); }
.toast.error { background: var(--red); }
.toast.info { background: var(--blue); }
.toast.warn { background: var(--yellow); }
@keyframes slideIn {
  from { transform: translateX(20px); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}
</style>
