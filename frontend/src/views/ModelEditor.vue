<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import { useAnimationConfig } from '../composables/useAnimationConfig.js'
import ModelUpload from '../components/ModelUpload.vue'

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
  view_mode: 'threejs',
  description: '',
})

// === 动画配置编辑 ===
const animConfigs = ref([])
const selectedAnimConfig = ref('podopener')
const animConfigStore = useAnimationConfig('podopener')
const editingConfig = ref(null)
const editDirty = ref(false)
const editSubTab = ref(null)  // 不再需要子Tab，采用左右两栏布局

// === 动画调试 ===
const debugFlow = ref('PACKING')
const testEvents = ref([])
const debugTestMachine = ref('PODOPENER-1')

// === Toast ===
const toasts = ref([])
function toast(msg, type = 'info') {
  const id = Date.now() + Math.random()
  toasts.value.push({ id, msg, type })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, 3000)
}

// === 模型管理 ===
async function loadModels() {
  try {
    models.value = await api.getModels()
  } catch (e) {
    console.error('加载模型失败:', e)
  }
}

async function createModel() {
  if (!newModel.value.model_id) return
  try {
    await api.createModel(newModel.value)
    await loadModels()
    newModel.value = { model_id: '', model_name: '', vendor: '', process_type: 'ETCH', view_mode: 'threejs', description: '' }
    toast('模型创建成功', 'success')
  } catch (e) {
    toast(`创建失败: ${e.message}`, 'error')
  }
}

function selectModel(m) {
  selectedModel.value = m
}

// === 动画配置：发现可用配置 ===
async function discoverAnimConfigs() {
  const modules = import.meta.glob('../configs/machine-animations/*.json', { eager: true, as: 'raw' })
  const list = []
  for (const [path, raw] of Object.entries(modules)) {
    const match = path.match(/\/([^/]+)\.json$/)
    if (!match) continue
    const name = match[1]
    if (name === '_schema') continue
    try {
      const data = JSON.parse(raw)
      list.push({
        name,
        machine_type: data.machine_type,
        version: data.version,
        desc: data.description || '',
        flows: Object.keys(data.flows || {}),
        phase_count: Object.values(data.flows || {}).reduce((s, f) => s + (f.phases?.length || 0), 0),
      })
    } catch { /* ignore */ }
  }
  animConfigs.value = list
}

async function loadAnimConfig(name) {
  selectedAnimConfig.value = name
  await animConfigStore.loadConfig(name)
  editingConfig.value = JSON.parse(JSON.stringify(animConfigStore.config.value || {}))
  editDirty.value = false
  // 默认选中第一个流程
  const flowKeys = Object.keys(editingConfig.value.flows || {})
  if (flowKeys.length > 0 && !flowKeys.includes(debugFlow.value)) {
    debugFlow.value = flowKeys[0]
  }
}

function applyConfigChanges() {
  if (!editingConfig.value) return
  try {
    animConfigStore.updateConfig(editingConfig.value)
    editDirty.value = false
    toast('配置已应用（当前会话生效）', 'success')
  } catch (e) {
    toast(`应用失败: ${e.message}`, 'error')
  }
}

function exportConfig() {
  const cfg = editingConfig.value || animConfigStore.config.value
  if (!cfg) return
  const text = JSON.stringify(cfg, null, 2)
  const blob = new Blob([text], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${selectedAnimConfig.value.toLowerCase()}.json`
  a.click()
  URL.revokeObjectURL(url)
  toast('配置已导出，请覆盖到 frontend/src/configs/machine-animations/ 目录', 'success')
}

function onPhaseDurationChange(flowKey, idx, val) {
  if (!editingConfig.value) return
  editingConfig.value.flows[flowKey].phases[idx].duration_ms = parseInt(val) || 100
  editDirty.value = true
}

function onEventPhaseChange(flowKey, evt, newPhase) {
  if (!editingConfig.value) return
  editingConfig.value.flows[flowKey].event_to_phase[evt].phase = newPhase
  editDirty.value = true
}

function onAnimChange(animKey, field, val) {
  if (!editingConfig.value) return
  editingConfig.value.animations[animKey][field] = val
  editDirty.value = true
}

function addEventMapping(flowKey) {
  if (!editingConfig.value) return
  const evtName = prompt('输入事件名（如 POD_PLACED）：')
  if (!evtName) return
  const phases = editingConfig.value.flows[flowKey].phases
  if (!phases || phases.length === 0) return
  editingConfig.value.flows[flowKey].event_to_phase[evtName.toUpperCase()] = {
    phase: phases[0].key,
    anim: '',
    note: '手动添加',
  }
  editDirty.value = true
}

function removeEventMapping(flowKey, evt) {
  if (!editingConfig.value) return
  delete editingConfig.value.flows[flowKey].event_to_phase[evt]
  editDirty.value = true
}

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
}

// === 体素编辑器 ===
const voxelParts = ref([])
const selectedVoxelIndex = ref(null)

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

// === 生命周期 ===
onMounted(async () => {
  await discoverAnimConfigs()
  await loadModels()
  await loadAnimConfig('podopener')
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
    <!-- 模型管理 Tab -->
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
        />
      </div>
      <div v-else class="select-hint">
        <p>👈 请先点击上方卡片选择一个机型，然后上传模型文件</p>
      </div>

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
              <option value="threejs">Three.js 3D</option>
              <option value="svg">SVG 2D</option>
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

    <!-- 动画配置 Tab -->
    <div v-show="activeTab === 'config'" class="config-panel">
      <div class="config-toolbar">
        <div class="config-selector">
          <label>选择机台配置：</label>
          <select v-model="selectedAnimConfig" @change="loadAnimConfig(selectedAnimConfig)">
            <option v-for="c in animConfigs" :key="c.name" :value="c.name">
              {{ c.name }} ({{ c.machine_type }}) - {{ c.phase_count }}阶段
            </option>
          </select>
        </div>
        <div class="config-actions">
          <button @click="applyConfigChanges" :disabled="!editDirty" class="btn-apply">
            ✅ 应用变更
          </button>
          <button @click="exportConfig" class="btn-export">
            💾 导出 JSON
          </button>
          <span v-if="editDirty" class="dirty-flag">有未保存变更</span>
        </div>
      </div>

      <div v-if="editingConfig" class="config-editor">
        <div class="config-meta">
          <div class="meta-item">
            <span class="meta-label">机台类型</span>
            <span class="meta-value">{{ editingConfig.machine_type }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">配置版本</span>
            <span class="meta-value">{{ editingConfig.version }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">流程数</span>
            <span class="meta-value">{{ Object.keys(editingConfig.flows || {}).length }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">动画原语</span>
            <span class="meta-value">{{ Object.keys(editingConfig.animations || {}).length }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">目标部件</span>
            <span class="meta-value">{{ Object.keys(editingConfig.targets || {}).length }}</span>
          </div>
        </div>

        <!-- 左右两栏布局 -->
        <div class="config-split-view">
          <!-- 左侧：部件清单 -->
          <div class="config-left-panel">
            <h4>🎯 部件清单（{{ Object.keys(editingConfig.targets || {}).length }} 个）</h4>
            <div class="target-list">
              <div v-for="(tgt, key) in editingConfig.targets" :key="key" class="target-row">
                <span class="target-key">{{ key }}</span>
                <div class="target-views">
                  <div class="target-view">
                    <span class="view-label">2D:</span>
                    <span class="view-value">{{ tgt.view_2d || '-' }}</span>
                  </div>
                  <div class="target-view">
                    <span class="view-label">3D:</span>
                    <span class="view-value">{{ tgt.view_3d || '-' }}</span>
                  </div>
                </div>
                <span v-if="tgt.desc" class="target-desc">{{ tgt.desc }}</span>
              </div>
            </div>

            <!-- 动画原语库 -->
            <h4 style="margin-top: 24px;">🎬 动画原语库（{{ Object.keys(editingConfig.animations || {}).length }} 个）</h4>
            <div class="anim-list">
              <div v-for="(anim, key) in editingConfig.animations" :key="key" class="anim-card">
                <div class="anim-header">
                  <span class="anim-key">{{ key }}</span>
                  <span class="anim-action">{{ anim.action }}</span>
                </div>
                <div class="anim-fields">
                  <div class="anim-field">
                    <label>target</label>
                    <input :value="anim.target" @change="onAnimChange(key, 'target', $event.target.value)" />
                  </div>
                  <div v-if="anim.axis" class="anim-field">
                    <label>axis</label>
                    <span class="anim-value">{{ anim.axis }}</span>
                  </div>
                  <div v-if="anim.from !== undefined" class="anim-field">
                    <label>from</label>
                    <input type="number" :value="anim.from"
                           @change="onAnimChange(key, 'from', parseFloat($event.target.value))" />
                  </div>
                  <div v-if="anim.to !== undefined" class="anim-field">
                    <label>to</label>
                    <input type="number" :value="anim.to"
                           @change="onAnimChange(key, 'to', parseFloat($event.target.value))" />
                  </div>
                  <div v-if="anim.duration_ms" class="anim-field">
                    <label>duration</label>
                    <input type="number" :value="anim.duration_ms"
                           @change="onAnimChange(key, 'duration_ms', parseInt($event.target.value))" />
                    <span class="unit">ms</span>
                  </div>
                  <div v-if="anim.color" class="anim-field">
                    <label>color</label>
                    <input type="color" :value="anim.color"
                           @change="onAnimChange(key, 'color', $event.target.value)" />
                  </div>
                </div>
                <div v-if="anim.note" class="anim-note">{{ anim.note }}</div>
              </div>
            </div>
          </div>

          <!-- 右侧：事件动作 -->
          <div class="config-right-panel">
            <div v-for="(flow, flowKey) in editingConfig.flows" :key="flowKey" class="flow-section">
              <h4>📋 {{ flowKey }} 流程（{{ flow.phases?.length || 0 }} 个阶段）</h4>
              <div class="phase-list">
                <div v-for="(p, idx) in flow.phases" :key="p.key" class="phase-edit-row">
                  <span class="phase-index">{{ idx + 1 }}</span>
                  <span class="phase-key">{{ p.key }}</span>
                  <span class="phase-label">{{ p.label }}</span>
                  <div class="phase-duration">
                    <input type="number" v-model.number="p.duration_ms" min="100" step="100"
                           @change="onPhaseDurationChange(flowKey, idx, $event.target.value)" />
                    <span class="unit">ms</span>
                  </div>
                </div>
              </div>

              <div class="flow-header" style="margin-top: 16px;">
                <h4>🔗 事件映射（{{ Object.keys(flow.event_to_phase || {}).length }} 个）</h4>
                <button class="btn-small" @click="addEventMapping(flowKey)">+ 添加事件</button>
              </div>
              <div class="event-map-list">
                <div v-for="(def, evt) in flow.event_to_phase" :key="evt" class="event-edit-row">
                  <span class="event-key">{{ evt }}</span>
                  <span class="arrow">→</span>
                  <select v-model="def.phase" @change="onEventPhaseChange(flowKey, evt, $event.target.value)">
                    <option v-for="p in flow.phases" :key="p.key" :value="p.key">
                      {{ p.key }} ({{ p.label }})
                    </option>
                  </select>
                  <span v-if="def.anim" class="anim-tag">{{ def.anim }}</span>
                  <button class="btn-delete" @click="removeEventMapping(flowKey, evt)" title="删除">×</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="empty-hint">加载中...</div>
    </div>

    <!-- 动画调试 Tab -->
    <div v-show="activeTab === 'debug'" class="debug-panel">
      <div class="debug-toolbar">
        <div class="debug-selectors">
          <select v-model="selectedAnimConfig" @change="loadAnimConfig(selectedAnimConfig)">
            <option v-for="c in animConfigs" :key="c.name" :value="c.name">{{ c.name }}</option>
          </select>
          <select v-model="debugFlow">
            <option v-for="f in (editingConfig?.flows ? Object.keys(editingConfig.flows) : [])"
                    :key="f" :value="f">{{ f }}</option>
          </select>
          <input v-model="debugTestMachine" placeholder="测试机台ID" class="machine-input" />
        </div>
        <div class="debug-actions">
          <button class="btn-primary" @click="testEvents = []">清空事件记录</button>
        </div>
      </div>

      <div class="debug-grid">
        <!-- 左侧：手动触发 -->
        <div class="debug-left">
          <h4>🎯 手动触发事件（{{ debugFlow }}）</h4>
          <div class="manual-grid">
            <button v-for="m in manualEvents" :key="m.event"
                    class="manual-btn"
                    @click="manualTriggerEvent(m.event)">
              <div class="btn-event">{{ m.event }}</div>
              <div class="btn-phase">→ {{ m.phase }}</div>
              <div v-if="m.anim" class="btn-anim">动画: {{ m.anim }}</div>
            </button>
          </div>

          <h4 style="margin-top: 20px;">⏭️ 阶段跳转</h4>
          <div class="phase-jump">
            <button v-for="(p, idx) in phaseList" :key="p.key"
                    class="phase-btn"
                    @click="jumpToPhase(p.key)">
              {{ idx + 1 }}. {{ p.label }}
            </button>
          </div>
        </div>

        <!-- 右侧：时间轴 + 事件记录 -->
        <div class="debug-right">
          <h4>📊 时间轴</h4>
          <div class="timeline-container">
            <div class="timeline-track">
              <div class="track-label">事件</div>
              <div class="track-line">
                <div v-for="(e, idx) in testEvents.slice(0, 20).reverse()" :key="idx"
                     class="track-marker event-marker"
                     :style="{ left: ((idx + 1) / Math.max(testEvents.slice(0,20).length, 1)) * 100 + '%' }">
                  <span class="marker-dot"></span>
                  <span class="marker-label">{{ e.event_code }}</span>
                </div>
              </div>
            </div>
          </div>

          <h4 style="margin-top: 20px;">📝 事件记录（最近 {{ testEvents.length }} 条）</h4>
          <div v-if="testEvents.length === 0" class="empty-hint">点击左侧按钮手动触发事件</div>
          <div v-else class="event-log">
            <div v-for="(e, idx) in testEvents.slice(0, 15)" :key="idx" class="event-log-item">
              <span class="log-time">{{ e.timestamp.slice(11, 19) }}</span>
              <span class="log-event">{{ e.event_code }}</span>
              <span class="log-tool">{{ e.tool_id }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="debug-tip">
        💡 提示：手动触发的事件仅在本页面记录。要看到 2D/3D 动画效果，请打开
        <router-link :to="`/machine/${debugTestMachine}`" target="_blank">
          {{ debugTestMachine }} 机台详情页
        </router-link>
        ，并在 WinForm 模拟器或实时模式下观察。
      </div>
    </div>

    <!-- 体素编辑器 Tab -->
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
            <div v-for="(part, idx) in voxelParts" :key="idx" class="voxel-part-item"
                 :class="{ selected: selectedVoxelIndex === idx }"
                 @click="selectedVoxelIndex = idx">
              <span class="part-type">{{ part.type }}</span>
              <span class="part-name">{{ part.name }}</span>
              <button class="btn-delete" @click.stop="removeVoxelPart(idx)">×</button>
            </div>
          </div>
        </div>

        <!-- 右侧：属性编辑 -->
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

          <!-- 预览区域 -->
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
.editor-header h1 {
  font-size: 20px;
  margin-bottom: 12px;
}
.header-tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
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
.tab-btn:hover {
  border-color: var(--accent);
}
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

/* 模型上传区域 */
.upload-section {
  margin-top: 16px;
}
.select-hint {
  text-align: center;
  padding: 24px;
  background: var(--panel-2);
  border: 1px dashed var(--border);
  border-radius: 10px;
  margin-top: 16px;
  color: var(--text-muted);
  font-size: 13px;
}
.select-hint p { margin: 0; }

.btn-delete {
  background: transparent;
  color: var(--text-dim);
  border: none;
  font-size: 16px;
  cursor: pointer;
  padding: 2px 6px;
}
.btn-delete:hover { color: #ef4444; }
.empty-hint {
  color: var(--text-dim);
  font-style: italic;
  padding: 20px;
  text-align: center;
}

/* 模型管理 */
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
.create-panel { background: var(--panel); border-radius: 8px; padding: 20px; }
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
}
.no-permission p { margin: 4px 0; color: var(--text-dim); }

/* 动画配置 */
.config-panel { background: var(--panel); border-radius: 8px; }
.config-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
  gap: 8px;
}
.config-selector label { font-size: 12px; color: var(--text-dim); margin-right: 8px; }
.config-selector select {
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 13px;
}
.config-actions { display: flex; gap: 8px; align-items: center; }
.btn-apply {
  background: #10b981;
  color: #fff;
  border: none;
  padding: 6px 14px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}
.btn-apply:disabled { opacity: 0.5; cursor: not-allowed; }
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
.dirty-flag { color: #f59e0b; font-size: 12px; }
.config-meta {
  display: flex;
  gap: 20px;
  padding: 12px 16px;
  background: rgba(0, 212, 255, 0.05);
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}
.meta-item { display: flex; flex-direction: column; }
.meta-label { font-size: 11px; color: var(--text-dim); }
.meta-value { font-size: 14px; font-weight: 600; color: var(--accent); }
.config-subtabs {
  display: flex;
  gap: 4px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
}
.config-subtabs button {
  background: transparent;
  color: var(--text-dim);
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}
.config-subtabs button:hover { color: var(--text); background: var(--panel-2); }
.config-subtabs button.active {
  color: var(--accent);
  background: rgba(0, 212, 255, 0.1);
}
.sub-content { padding: 16px; }

/* 左右两栏布局 */
.config-split-view {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  padding: 16px;
  height: calc(100% - 120px);
  overflow-y: auto;
}
@media (max-width: 1000px) {
  .config-split-view { grid-template-columns: 1fr; }
}
.config-left-panel,
.config-right-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.config-left-panel h4,
.config-right-panel h4 {
  color: var(--accent);
  font-size: 13px;
  margin-bottom: 8px;
}
.flow-section { margin-bottom: 24px; }
.flow-section > h4 { color: var(--accent); margin-bottom: 10px; font-size: 14px; }
.flow-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.flow-header h4 { margin: 0; color: var(--accent); font-size: 14px; }

/* 阶段编辑行 */
.phase-list { display: flex; flex-direction: column; gap: 2px; }
.phase-edit-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  background: var(--bg);
  border-radius: 4px;
}
.phase-index {
  width: 24px;
  height: 24px;
  background: var(--accent);
  color: #000;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}
.phase-key { font-family: monospace; min-width: 180px; font-size: 12px; color: #a78bfa; }
.phase-label { flex: 1; font-size: 12px; color: var(--text); }
.phase-duration { display: flex; align-items: center; gap: 4px; }
.phase-duration input {
  width: 80px;
  background: var(--panel-2);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 3px 6px;
  border-radius: 3px;
  font-size: 12px;
  text-align: right;
}
.unit { font-size: 11px; color: var(--text-dim); }

/* 事件映射 */
.event-map-list { display: flex; flex-direction: column; gap: 4px; }
.event-edit-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  background: var(--bg);
  border-radius: 4px;
}
.event-key { font-family: monospace; min-width: 200px; font-size: 12px; color: #f59e0b; font-weight: 600; }
.arrow { color: var(--text-dim); }
.event-edit-row select {
  background: var(--panel-2);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 3px 8px;
  border-radius: 3px;
  font-size: 12px;
}
.anim-tag { color: #06b6d4; font-size: 11px; }

/* 动画原语 */
.anim-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
}
.anim-card {
  background: var(--bg);
  border-radius: 6px;
  padding: 12px;
  border: 1px solid var(--border);
}
.anim-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}
.anim-key { font-family: monospace; font-size: 12px; color: #06b6d4; font-weight: 600; }
.anim-action {
  font-size: 11px;
  padding: 2px 8px;
  background: rgba(6, 182, 212, 0.15);
  color: #06b6d4;
  border-radius: 10px;
}
.anim-fields { display: flex; flex-direction: column; gap: 4px; }
.anim-field { display: flex; align-items: center; gap: 8px; font-size: 11px; }
.anim-field label { color: var(--text-dim); min-width: 60px; }
.anim-field input {
  flex: 1;
  background: var(--panel);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  min-width: 0;
}
.anim-value { color: var(--accent); font-family: monospace; }
.anim-note { margin-top: 6px; font-size: 11px; color: var(--text-dim); font-style: italic; }

/* 部件目标 */
.target-list { display: flex; flex-direction: column; gap: 4px; }
.target-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 10px;
  background: var(--bg);
  border-radius: 4px;
  flex-wrap: wrap;
}
.target-key { font-family: monospace; font-size: 13px; color: #f59e0b; font-weight: 600; min-width: 120px; }
.target-views { display: flex; gap: 20px; flex: 1; }
.target-view { display: flex; gap: 6px; font-size: 12px; }
.view-label { color: var(--text-dim); }
.view-value { font-family: monospace; color: var(--text); }
.target-desc { color: var(--text-dim); font-size: 11px; }

/* 体素编辑器 */
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
  height: calc(100% - 80px);
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
}

/* 动画调试 */
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
.debug-selectors select, .machine-input {
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 13px;
}
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
.btn-event { font-weight: 600; color: #f59e0b; font-size: 11px; }
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

/* 时间轴 */
.timeline-container {
  background: #1a1a2a;
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 12px;
}
.timeline-track { display: flex; align-items: center; height: 40px; }
.track-label { width: 50px; color: var(--text-dim); font-size: 11px; flex-shrink: 0; }
.track-line { flex: 1; height: 100%; position: relative; }
.track-marker {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
}
.marker-dot { width: 8px; height: 8px; border-radius: 50%; background: #f59e0b; }
.marker-label {
  font-size: 9px;
  color: var(--text-dim);
  white-space: nowrap;
  max-width: 60px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.event-marker .marker-dot { background: #f59e0b; }

.event-log { max-height: 300px; overflow-y: auto; }
.event-log-item {
  display: flex;
  gap: 8px;
  padding: 4px 8px;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}
.log-time { color: var(--text-dim); font-family: monospace; }
.log-event { color: #f59e0b; font-weight: 600; }
.log-tool { color: var(--text-dim); margin-left: auto; }

.debug-tip {
  margin: 0 16px 16px;
  padding: 10px 14px;
  background: rgba(245, 158, 11, 0.1);
  border-left: 3px solid #f59e0b;
  font-size: 12px;
  color: #c0c0a0;
  border-radius: 0 4px 4px 0;
}
.debug-tip a { color: var(--accent); text-decoration: underline; }

/* 开发指南 */
.guide-container { display: flex; gap: 20px; }
.guide-sidebar { width: 260px; flex-shrink: 0; }
.section-btn {
  width: 100%;
  padding: 10px 12px;
  border: none;
  background: var(--panel);
  border-radius: 6px;
  text-align: left;
  font-size: 12px;
  margin-bottom: 6px;
  cursor: pointer;
  color: var(--text);
}
.section-btn:hover { background: var(--panel-2); }
.guide-content { flex: 1; }
.guide-section {
  background: var(--panel);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 16px;
}
.guide-section h2 { font-size: 15px; margin-bottom: 12px; color: var(--accent); }
.section-body pre {
  font-family: 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  color: var(--text);
  margin: 0;
}

/* 事件代码 */
.events-panel h2 { font-size: 16px; margin-bottom: 16px; }
.events-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.event-category { background: var(--panel); border-radius: 8px; padding: 14px; }
.category-title { font-weight: 700; font-size: 13px; margin-bottom: 10px; color: var(--accent); }
.event-codes { display: flex; flex-wrap: wrap; gap: 6px; }
.event-code {
  padding: 4px 10px;
  background: var(--bg);
  border-radius: 12px;
  font-size: 11px;
  font-family: monospace;
  color: var(--text);
}

/* Toast */
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
.toast.success { background: #10b981; }
.toast.error { background: #ef4444; }
.toast.info { background: #3b82f6; }
.toast.warn { background: #f59e0b; }
@keyframes slideIn {
  from { transform: translateX(20px); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}
</style>
