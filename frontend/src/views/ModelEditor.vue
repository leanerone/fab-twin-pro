<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue'
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

// v2.5.4: 删除机型（机型卡片右上角 × 按钮）
// 修复"创建的模型无法删除"——之前机型卡片没有删除入口
async function deleteModel(model) {
  if (!confirm(`确认删除机型 ${model.model_id}？\n该操作不可恢复，关联的文件、动画配置将一并清除。`)) return
  try {
    await api.deleteModel(model.model_id)
    await loadModels()
    if (selectedModel.value?.model_id === model.model_id) {
      selectedModel.value = null
    }
    toast(`机型 ${model.model_id} 已删除`, 'success')
  } catch (e) {
    toast(`删除失败: ${e.message}`, 'error')
  }
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

// === Motion JSON 格式检测 ===
const isMotionJson = computed(() => !!editingConfig.value?.schema_version)

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
    // 兼容 Motion JSON（parts 数组）和旧格式（targets 对象）
    if (editingConfig.value.schema_version) {
      // Motion JSON 格式：parts 数组
      // - part_id 不存在 → 新增
      // - part_id 已存在 → 用 SVG 的 tag 更新 part_type / part_name（不强制覆盖用户改过的非空值）
      if (!Array.isArray(editingConfig.value.parts)) editingConfig.value.parts = []
      const idxMap = new Map()
      editingConfig.value.parts.forEach((p, i) => {
        if (p && p.part_id) idxMap.set(p.part_id, i)
      })
      let added = 0
      let updated = 0
      for (const p of parts) {
        const id = p.element_id
        if (!id) continue
        if (idxMap.has(id)) {
          const target = editingConfig.value.parts[idxMap.get(id)]
          if (p.tag && target.part_type !== p.tag) {
            target.part_type = p.tag
            updated++
          }
          // part_name 为空或与 element_id 一致时，刷新为 element_id
          if (!target.part_name || target.part_name === id) {
            target.part_name = id
          }
        } else {
          editingConfig.value.parts.push({
            part_id: id,
            part_name: id,
            part_type: p.tag || '',
            desc: '',
          })
          added++
        }
      }
      markDirty()
      toast(`Motion JSON: SVG 提取 ${parts.length} 个部件，新增 ${added} 个，更新 ${updated} 个`, 'success')
    } else {
      // 旧格式：targets 对象
      if (!editingConfig.value.targets) editingConfig.value.targets = {}
      let added = 0
      let updated = 0
      for (const p of parts) {
        const id = p.element_id
        if (!id) continue
        // 已存在 view_2d === id 的部件 → 更新 desc（若为空）
        const existKey = Object.keys(editingConfig.value.targets).find(
          k => editingConfig.value.targets[k].view_2d === id
        )
        if (existKey) {
          if (!editingConfig.value.targets[existKey].desc && p.tag) {
            editingConfig.value.targets[existKey].desc = p.tag
            updated++
          }
          continue
        }
        if (!editingConfig.value.targets[id]) {
          editingConfig.value.targets[id] = { view_2d: id, view_3d: '', desc: p.tag || '' }
          added++
        } else {
          editingConfig.value.targets[id].view_2d = id
          added++
        }
      }
      markDirty()
      toast(`已从SVG提取 ${parts.length} 个部件，新增 ${added} 个，更新 ${updated} 个`, 'success')
    }
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

// v2.5.10: 导出当前 animation_config 为 JSON 文件
function exportAnimConfigJson() {
  if (!editingConfig.value) return
  const json = JSON.stringify(editingConfig.value, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  const modelId = selectedModel.value?.model_id || 'motion'
  a.href = url
  a.download = `${modelId}_animation_config.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  toast('已导出 animation_config JSON', 'success')
}

// === 拖拽录制模式 ===
const recordMode = ref(false)
const recordActionType = ref('offset')  // offset / rotate / scale / opacity
const recordStepInputRef = ref(null)
// 多选：用数组而非 Set，确保 Vue 响应式可靠追踪
const selectedPartIds = ref([])
// 框选（lasso）状态
const lassoState = ref({
  active: false,
  startX: 0, startY: 0,   // 屏幕坐标
  currentX: 0, currentY: 0,
})
const dragState = ref({
  partId: '',
  startSvgX: 0, startSvgY: 0,
  currentSvgX: 0, currentSvgY: 0,
  dragging: false,
  startBBox: null,
})
const showRecordPanel = ref(false)
const showGroupInput = ref(false)
const groupNameInput = ref('')
const groupInputRef = ref(null)
const recordForm = ref({
  step: '',
  when: 'true',
  actionType: 'offset',
  partId: '',
  partIds: [],  // 多选时多个目标
  offsetX: 0, offsetY: 0,
  angle: 0, pivotX: 0, pivotY: 0,
  scaleX: 1, scaleY: 1,
  opacity: 1,
  duration: 1000,
  easing: 'linear',
})

const ACTION_TYPE_OPTIONS = [
  { value: 'offset', label: '位移', icon: '✥' },
  { value: 'rotate', label: '旋转', icon: '⟳' },
  { value: 'scale', label: '缩放', icon: '⤢' },
  { value: 'opacity', label: '透明度', icon: '◐' },
]

const EVENT_TEMPLATES = [
  { label: '始终触发', when: 'true' },
  { label: 'Port 1', when: "params.port == '1'" },
  { label: 'Port 2', when: "params.port == '2'" },
  { label: 'Chamber 1', when: "params.chamber == '1'" },
  { label: 'Chamber 2', when: "params.chamber == '2'" },
  { label: 'Chamber 3', when: "params.chamber == '3'" },
]

const EASING_OPTIONS = ['linear', 'ease-in', 'ease-out', 'ease-in-out', 'mechanical']

// 已录制动作列表（Motion JSON 的 motions 数组）
const motionList = computed(() => {
  if (!editingConfig.value) return []
  if (!editingConfig.value.schema_version) return []
  return editingConfig.value.motions || []
})

function toggleRecordMode() {
  recordMode.value = !recordMode.value
  if (!recordMode.value) {
    resetDragState()
    showRecordPanel.value = false
    selectedPartIds.value = []
    lassoState.value.active = false
    selectedPartId.value = ''
    highlightSvgPart('')
  }
  toast(recordMode.value ? '录制模式：点击选中，空白处拖拽框选，Ctrl+点击追加' : '录制模式已关闭（仍可多选/框选/组合）', 'info')
}

// 标志位：mousedown 已处理选中时，阻止后续 click 重置选中
let mousedownProcessed = false

// 自动展开部件列表 <details>（高亮才能被看到）
function expandPartsDetails() {
  nextTick(() => {
    const details = document.querySelector('.parts-details')
    if (details && !details.hasAttribute('open')) {
      details.setAttribute('open', '')
    }
  })
}

// 将 SVG 元素置顶（移动到父节点末尾，SVG 渲染顺序=DOM 顺序）
function bringToFront(el) {
  if (!el || !el.parentNode) return
  el.parentNode.appendChild(el)
}

// 高亮多个选中部件（数组版）
function highlightSelectedParts() {
  const container = svgInlineRef.value
  if (!container) return
  container.querySelectorAll('.part-highlight').forEach(prev => {
    prev.classList.remove('part-highlight')
    prev.style.stroke = ''
    prev.style.strokeWidth = ''
    prev.style.filter = ''
    prev.querySelectorAll('*').forEach(el => {
      el.style.stroke = ''
      el.style.strokeWidth = ''
      el.style.filter = ''
    })
  })
  for (const partId of selectedPartIds.value) {
    const escId = partId.replace(/["\\]/g, '\\$&')
    const target = container.querySelector(`[id="${escId}"]`)
    if (target) {
      target.classList.add('part-highlight')
      target.style.stroke = '#ff5722'
      target.style.strokeWidth = '3px'
      target.style.filter = 'drop-shadow(0 0 6px rgba(255, 87, 34, 0.9))'
      const tag = target.tagName.toLowerCase()
      if (tag === 'g' || tag === 'svg') {
        target.querySelectorAll('*').forEach(el => {
          el.style.stroke = '#ff5722'
          el.style.strokeWidth = '2px'
          el.style.filter = 'drop-shadow(0 0 4px rgba(255, 87, 34, 0.7))'
        })
      }
    }
  }
}

function resetDragState() {
  const ds = dragState.value
  if (svgInlineRef.value) {
    for (const partId of selectedPartIds.value) {
      const el = svgInlineRef.value.querySelector(`#${CSS.escape(partId)}`)
      if (el) { el.style.transform = ''; el.style.transformOrigin = '' }
    }
    if (ds.partId) {
      const el = svgInlineRef.value.querySelector(`#${CSS.escape(ds.partId)}`)
      if (el) { el.style.transform = ''; el.style.transformOrigin = '' }
    }
  }
  dragState.value = { partId: '', startSvgX: 0, startSvgY: 0, currentSvgX: 0, currentSvgY: 0, dragging: false, startBBox: null }
}

function screenToSvgCoords(e) {
  const container = svgInlineRef.value
  if (!container) return { x: 0, y: 0 }
  const svg = container.querySelector('svg')
  if (!svg) return { x: 0, y: 0 }
  const pt = svg.createSVGPoint()
  pt.x = e.clientX
  pt.y = e.clientY
  const ctm = svg.getScreenCTM()
  if (!ctm) return { x: 0, y: 0 }
  const svgPt = pt.matrixTransform(ctm.inverse())
  return { x: svgPt.x, y: svgPt.y }
}

// 获取容器屏幕坐标（用于框选矩形定位）
function getContainerOffset() {
  const container = svgInlineRef.value
  if (!container) return { left: 0, top: 0 }
  const rect = container.getBoundingClientRect()
  return { left: rect.left, top: rect.top }
}

// 框选矩形样式（响应式，使用容器相对坐标）
const lassoRectStyle = computed(() => {
  if (!lassoState.value.active) return { display: 'none' }
  const ls = lassoState.value
  const container = svgInlineRef.value
  if (!container) return { display: 'none' }
  const rect = container.getBoundingClientRect()
  const x = Math.min(ls.startX, ls.currentX) - rect.left
  const y = Math.min(ls.startY, ls.currentY) - rect.top
  const w = Math.abs(ls.currentX - ls.startX)
  const h = Math.abs(ls.currentY - ls.startY)
  return { left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px', display: 'block' }
})

// 非部件标签（点击这些元素视为点击空白，触发框选）
const NON_PART_TAGS = new Set(['svg', 'defs', 'style', 'metadata', 'title', 'desc'])
function isPartElement(el, containerRect) {
  if (!el) return false
  const tag = el.tagName ? el.tagName.toLowerCase().replace(/^.*:/, '') : ''
  if (NON_PART_TAGS.has(tag)) return false
  const id = el.getAttribute && el.getAttribute('id')
  if (!id) return false
  // 过滤大面积背景元素（覆盖容器 70% 以上视为背景）
  if (containerRect) {
    try {
      const bbox = el.getBoundingClientRect()
      if (bbox.width > 0 && bbox.height > 0) {
        const areaRatio = (bbox.width * bbox.height) / (containerRect.width * containerRect.height)
        if (areaRatio > 0.7) return false
      }
    } catch(_) {}
  }
  return true
}

function onSvgMouseDown(e) {
  // 多选/框选在非录制模式也可用；拖拽录制仅限录制模式
  const containerRect = svgInlineRef.value?.getBoundingClientRect()
  // 查找点击的部件（跳过 SVG 根、defs、大面积背景等非部件元素）
  let el = e.target
  let partId = ''
  while (el && el !== e.currentTarget) {
    if (isPartElement(el, containerRect)) { partId = el.getAttribute('id'); break }
    el = el.parentElement
  }

  // 标记本次 mousedown 已处理选中，阻止后续 click 重置
  mousedownProcessed = true
  setTimeout(() => { mousedownProcessed = false }, 60)

  if (partId) {
    // === 点击部件：选中 + (录制模式下)开始拖拽 ===
    e.preventDefault()
    const targetEl = svgInlineRef.value?.querySelector(`#${CSS.escape(partId)}`)
    if (targetEl) bringToFront(targetEl)

    const isMulti = e.ctrlKey || e.metaKey
    if (isMulti) {
      // Ctrl+click：添加/移除
      const idx = selectedPartIds.value.indexOf(partId)
      if (idx >= 0) {
        selectedPartIds.value = selectedPartIds.value.filter(id => id !== partId)
      } else {
        selectedPartIds.value = [...selectedPartIds.value, partId]
      }
    } else {
      // 普通点击：如果已有多选且点击的是其中一个，保持多选；否则单选
      if (selectedPartIds.value.length > 1 && selectedPartIds.value.includes(partId)) {
        // 保持当前多选
      } else {
        selectedPartIds.value = [partId]
      }
    }
    selectedPartId.value = partId
    highlightSelectedParts()
    scrollSelectedPartsIntoView()
    expandPartsDetails()

    // 仅在录制模式下开始拖拽录制
    if (recordMode.value) {
      const coords = screenToSvgCoords(e)
      const bbox = targetEl ? (function() { try { return targetEl.getBBox() } catch(_) { return null } })() : null
      dragState.value = {
        partId, startSvgX: coords.x, startSvgY: coords.y,
        currentSvgX: coords.x, currentSvgY: coords.y,
        dragging: true,
        startBBox: bbox ? { x: bbox.x, y: bbox.y, width: bbox.width, height: bbox.height } : null,
      }
      recordForm.value.partId = partId
      recordForm.value.partIds = [...selectedPartIds.value]
      recordForm.value.actionType = recordActionType.value
      if (bbox && recordActionType.value === 'rotate') {
        recordForm.value.pivotX = Math.round(bbox.x + bbox.width / 2)
        recordForm.value.pivotY = Math.round(bbox.y + bbox.height / 2)
      }
    }
  } else {
    // === 点击空白：开始框选（lasso）—— 录制/非录制模式都支持 ===
    e.preventDefault()
    lassoState.value = {
      active: true,
      startX: e.clientX, startY: e.clientY,
      currentX: e.clientX, currentY: e.clientY,
    }
    // 框选时不保留之前的选择（如果未按 Ctrl）
    if (!e.ctrlKey && !e.metaKey) {
      selectedPartIds.value = []
      selectedPartId.value = ''
      highlightSvgPart('')
    }
  }
}

function onSvgMouseMove(e) {
  const ds = dragState.value
  // 框选拖拽
  if (lassoState.value.active) {
    lassoState.value.currentX = e.clientX
    lassoState.value.currentY = e.clientY
    // 实时检测框选范围内的部件
    updateLassoSelection()
    return
  }
  // 部件拖拽
  if (!ds.dragging || !svgInlineRef.value) return
  const coords = screenToSvgCoords(e)
  ds.currentSvgX = coords.x
  ds.currentSvgY = coords.y
  const dx = coords.x - ds.startSvgX
  const dy = coords.y - ds.startSvgY
  const partIds = selectedPartIds.value.length > 0 ? selectedPartIds.value : [ds.partId]
  for (const pid of partIds) {
    const el = svgInlineRef.value.querySelector(`#${CSS.escape(pid)}`)
    if (!el) continue
    switch (recordActionType.value) {
      case 'offset':
        el.style.transform = `translate(${dx}px, ${dy}px)`
        break
      case 'rotate': {
        const angle = Math.round(Math.atan2(dy, dx) * 180 / Math.PI)
        el.style.transformOrigin = `${recordForm.value.pivotX}px ${recordForm.value.pivotY}px`
        el.style.transform = `rotate(${angle}deg)`
        recordForm.value.angle = angle
        break
      }
      case 'scale': {
        const sx = Math.max(0.1, 1 + dx / 100)
        const sy = Math.max(0.1, 1 + dy / 100)
        el.style.transform = `scale(${sx}, ${sy})`
        recordForm.value.scaleX = Math.round(sx * 100) / 100
        recordForm.value.scaleY = Math.round(sy * 100) / 100
        break
      }
    }
  }
}

// 框选：检测哪些 SVG 元素在框选矩形内
function updateLassoSelection() {
  const container = svgInlineRef.value
  if (!container) return
  const ls = lassoState.value
  const containerRect = container.getBoundingClientRect()
  const lx = Math.min(ls.startX, ls.currentX) - containerRect.left
  const ly = Math.min(ls.startY, ls.currentY) - containerRect.top
  const lw = Math.abs(ls.currentX - ls.startX)
  const lh = Math.abs(ls.currentY - ls.startY)
  const allIds = container.querySelectorAll('[id]')
  const newSelection = []
  for (const el of allIds) {
    if (!isPartElement(el, containerRect)) continue
    const eid = el.getAttribute('id')
    let bbox
    try { bbox = el.getBoundingClientRect() } catch(_) { continue }
    if (bbox.width === 0 && bbox.height === 0) continue
    const elLeft = bbox.left - containerRect.left
    const elTop = bbox.top - containerRect.top
    const cx = elLeft + bbox.width / 2
    const cy = elTop + bbox.height / 2
    if (cx >= lx && cx <= lx + lw && cy >= ly && cy <= ly + lh) {
      newSelection.push(eid)
    }
  }
  selectedPartIds.value = newSelection
  if (newSelection.length > 0) {
    selectedPartId.value = newSelection[newSelection.length - 1]
  }
  highlightSelectedParts()
}

function onSvgMouseUp(e) {
  // 框选结束
  if (lassoState.value.active) {
    lassoState.value.active = false
    if (selectedPartIds.value.length > 0) {
      // 框选到部件后，滚动右侧列表到第一个选中项并展开部件列表
      scrollSelectedPartsIntoView()
      expandPartsDetails()
    }
    return
  }
  // 部件拖拽结束
  const ds = dragState.value
  if (!ds.dragging) return
  const coords = screenToSvgCoords(e)
  ds.currentSvgX = coords.x
  ds.currentSvgY = coords.y
  const dx = Math.round(coords.x - ds.startSvgX)
  const dy = Math.round(coords.y - ds.startSvgY)
  if (recordActionType.value === 'offset') {
    recordForm.value.offsetX = dx
    recordForm.value.offsetY = -dy
  }
  showRecordPanel.value = true
  ds.dragging = false
  nextTick(() => {
    if (recordStepInputRef.value) recordStepInputRef.value.focus()
  })
}

// 滚动右侧部件列表到选中项
function scrollSelectedPartsIntoView() {
  if (selectedPartIds.value.length === 0) return
  nextTick(() => {
    // 优先滚动 .parts-mini-list 中的对应行
    const container = document.querySelector('.parts-mini-list')
    if (container) {
      const firstId = selectedPartIds.value[0]
      const escId = firstId.replace(/["\\]/g, '\\$&')
      const row = container.querySelector(`[data-part-id="${escId}"]`)
      if (row) row.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
    // 也尝试 .motion-list（无 data-part-id，跳过）
  })
}

// 将多个选中部件组合为一个 <g> 组（永久分组，可当作单个部件引用）
function startGroupInput() {
  if (selectedPartIds.value.length < 2) {
    toast('请先框选或 Ctrl+点击选中 2 个以上部件', 'warn')
    return
  }
  showGroupInput.value = true
  groupNameInput.value = `GROUP_${Date.now() % 10000}`
  nextTick(() => {
    if (groupInputRef.value) {
      groupInputRef.value.focus()
      groupInputRef.value.select()
    }
  })
}

function confirmGroupCombine() {
  const name = groupNameInput.value.trim()
  if (!name) { toast('请输入组合名称', 'error'); return }
  const container = svgInlineRef.value
  const svg = container?.querySelector('svg')
  if (!svg) { toast('SVG 未加载', 'error'); return }
  const ns = svg.namespaceURI
  const g = document.createElementNS(ns, 'g')
  g.setAttribute('id', name)
  const partIds = [...selectedPartIds.value]
  for (const pid of partIds) {
    const el = container.querySelector(`#${CSS.escape(pid)}`)
    if (el && el.parentNode) {
      g.appendChild(el)
    }
  }
  svg.appendChild(g)
  if (isMotionJson.value) {
    if (!Array.isArray(editingConfig.value.parts)) editingConfig.value.parts = []
    editingConfig.value.parts.push({
      part_id: name, part_name: name, part_type: 'group',
      desc: `组合: ${partIds.join(', ')}`,
    })
  } else {
    if (!editingConfig.value.targets) editingConfig.value.targets = {}
    editingConfig.value.targets[name] = { view_2d: name, view_3d: '', desc: `组合: ${partIds.join(', ')}` }
  }
  markDirty()
  selectedPartIds.value = [name]
  selectedPartId.value = name
  highlightSelectedParts()
  showGroupInput.value = false
  toast(`已创建组合 "${name}"（${partIds.length} 个部件）`, 'success')
}

function cancelGroupCombine() {
  showGroupInput.value = false
  groupNameInput.value = ''
}

function clearSelection() {
  selectedPartIds.value = []
  selectedPartId.value = ''
  highlightSvgPart('')
}

function cancelRecord() {
  resetDragState()
  showRecordPanel.value = false
}

function saveRecord() {
  if (!editingConfig.value) return
  const f = recordForm.value
  if (!f.step.trim()) { toast('请输入 Step 名称', 'error'); return }
  // 目标部件列表（支持多选）
  const targets = (f.partIds && f.partIds.length > 0) ? f.partIds : [f.partId]
  if (!targets[0]) { toast('未选中部件', 'error'); return }
  // 旧格式 → 转 Motion JSON
  if (!editingConfig.value.schema_version) {
    const oldParts = editingConfig.value.parts || []
    editingConfig.value = {
      schema_version: '1.0',
      document: { name: selectedModel.value?.model_id || '', src: 'svg' },
      parts: oldParts,
      motions: [],
      ext: {},
    }
  }
  if (!Array.isArray(editingConfig.value.motions)) editingConfig.value.motions = []
  // 构建 action（所有目标共用同一动作参数）
  let action = { type: f.actionType }
  switch (f.actionType) {
    case 'offset': action.offset_x = f.offsetX; action.offset_y = f.offsetY; break
    case 'rotate': action.angle = f.angle; action.pivot = { x: f.pivotX, y: f.pivotY }; break
    case 'scale': action.scale_x = f.scaleX; action.scale_y = f.scaleY; break
    case 'opacity': action.to = f.opacity; break
  }
  if (f.duration > 0) action.duration = f.duration
  if (f.easing && f.easing !== 'linear') action.easing = f.easing
  // 构建 motion：多目标时生成多条 rules（同一 step 下，每部件一条 rule）
  const rules = targets.map(pid => ({
    when: f.when || 'true',
    target_part_id: pid,
    actions: [JSON.parse(JSON.stringify(action))],
  }))
  const motion = {
    step: f.step.trim().toUpperCase(),
    enabled: true,
    rules,
  }
  editingConfig.value.motions.push(motion)
  markDirty()
  resetDragState()
  showRecordPanel.value = false
  recordForm.value.step = ''
  toast(`已录制: ${motion.step} → ${targets.join(', ')} (${f.actionType}${targets.length > 1 ? `, ${targets.length}个部件` : ''})`, 'success')
}

function deleteMotion(idx) {
  if (!editingConfig.value?.motions) return
  const m = editingConfig.value.motions[idx]
  if (!confirm(`确定删除动作 "${m.step}"？`)) return
  editingConfig.value.motions.splice(idx, 1)
  markDirty()
}

function getMotionSummary(motion) {
  const rules = motion.rules || []
  if (rules.length === 0) return '(无动作)'
  const r = rules[0]
  const actions = r.actions || []
  const parts = actions.map(a => {
    switch (a.type) {
      case 'offset': return `位移(${a.offset_x||0},${a.offset_y||0})`
      case 'rotate': return `旋转${a.angle||0}°`
      case 'scale': return `缩放(${a.scale_x||1},${a.scale_y||1})`
      case 'opacity': return `透明度${a.to??1}`
      default: return a.type
    }
  })
  return `${r.target_part_id}: ${parts.join(', ')}`
}

// === 计算属性 ===
const targetKeys = computed(() => {
  if (!editingConfig.value) return []
  const q = partSearch.value.trim().toLowerCase()
  // Motion JSON：返回 parts 数组索引（字符串形式，便于 v-for key）
  if (isMotionJson.value) {
    const arr = Array.isArray(editingConfig.value.parts) ? editingConfig.value.parts : []
    return arr
      .map((p, i) => ({ p, i: String(i) }))
      .filter(({ p }) => {
        if (!q) return true
        return (
          (p.part_id || '').toLowerCase().includes(q) ||
          (p.part_name || '').toLowerCase().includes(q) ||
          (p.part_type || '').toLowerCase().includes(q)
        )
      })
      .map(({ i }) => i)
  }
  // 旧格式：targets 对象
  const allKeys = Object.keys(editingConfig.value.targets || {})
  if (!q) return allKeys
  return allKeys.filter(k => {
    const t = editingConfig.value.targets[k]
    return (
      k.toLowerCase().includes(q) ||
      (t?.view_2d || '').toLowerCase().includes(q) ||
      (t?.view_3d || '').toLowerCase().includes(q) ||
      (t?.desc || '').toLowerCase().includes(q)
    )
  })
})

// 总部件数（不受搜索过滤）
const totalPartsCount = computed(() => {
  if (!editingConfig.value) return 0
  if (isMotionJson.value) {
    return Array.isArray(editingConfig.value.parts) ? editingConfig.value.parts.length : 0
  }
  return Object.keys(editingConfig.value.targets || {}).length
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

// v2.5.4: SVG 预览改用内联渲染（fetch + v-html），替代 <object> 标签
// 修复 <object> 渲染 SVG 空白 / fallback iframe 嵌主页看板问题
const svgInlineHtml = ref('')
const svgPreviewLoading = ref(false)
async function loadSvgInline(url) {
  if (!url) { svgInlineHtml.value = ''; return }
  svgPreviewLoading.value = true
  try {
    const resp = await fetch(url, { cache: 'no-store' })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const text = await resp.text()
    if (!text.includes('<svg')) throw new Error('返回内容不是 SVG')
    svgInlineHtml.value = text
  } catch (e) {
    svgInlineHtml.value = `<div style="color:#f44336;padding:12px">⚠️ SVG 加载失败: ${e.message}</div>`
  } finally {
    svgPreviewLoading.value = false
  }
}
watch(svgPreviewUrl, (url) => loadSvgInline(url), { immediate: true })

// === SVG 部件交互（点击 SVG 元素 ↔ 部件列表行 双向高亮） ===
const selectedPartId = ref('')
const svgInlineRef = ref(null)
// 部件搜索框
const partSearch = ref('')

// 高亮 SVG 内指定 id 的元素（清除上一个，加 .part-highlight 类）
function highlightSvgPart(partId) {
  const container = svgInlineRef.value
  if (!container) return
  // 清除上一个高亮（包括 inline style）
  const prev = container.querySelector('.part-highlight')
  if (prev) {
    prev.classList.remove('part-highlight')
    // 清除 inline style（避免残留）
    prev.style.stroke = ''
    prev.style.strokeWidth = ''
    prev.style.filter = ''
    // 子元素也清除（<g> 容器情况）
    prev.querySelectorAll('*').forEach(el => {
      el.style.stroke = ''
      el.style.strokeWidth = ''
      el.style.filter = ''
    })
  }
  if (!partId) return
  // SVG 内元素 id 可能含特殊字符，用属性选择器转义
  const escId = partId.replace(/["\\]/g, '\\$&')
  const target = container.querySelector(`[id="${escId}"]`)
  if (target) {
    target.classList.add('part-highlight')
    // v2.5.12: 直接设置 inline style，强制覆盖 SVG attribute（stroke="..."）
    // 原因：CSS 类的 stroke 即使有 !important 也可能被 SVG attribute 覆盖
    target.style.stroke = '#ff5722'
    target.style.strokeWidth = '3px'
    target.style.filter = 'drop-shadow(0 0 6px rgba(255, 87, 34, 0.9))'
    // 如果是 <g> 容器（无 stroke），给子元素也加描边
    const tag = target.tagName.toLowerCase()
    if (tag === 'g' || tag === 'svg') {
      target.querySelectorAll('*').forEach(el => {
        el.style.stroke = '#ff5722'
        el.style.strokeWidth = '2px'
        el.style.filter = 'drop-shadow(0 0 4px rgba(255, 87, 34, 0.7))'
      })
    }
    // 滚动到可见
    try { target.scrollIntoView({ block: 'nearest', inline: 'center' }) } catch (_) { /* ignore */ }
  }
}

// SVG 容器点击事件委托：从 event.target 读取 id
function onSvgClick(e) {
  // 鼠标触发的 click（e.detail >= 1）由 mousedown 处理，这里只处理键盘触发的 click（如 Enter）
  if (e.detail > 0) return
  if (recordMode.value) return  // 录制模式下由 mousedown 处理
  const containerRect = svgInlineRef.value?.getBoundingClientRect()
  let el = e.target
  // 向上查找带 id 的部件祖先（跳过 SVG 根、defs、大面积背景）
  while (el && el !== e.currentTarget) {
    if (isPartElement(el, containerRect)) {
      const id = el.getAttribute('id')
      selectedPartId.value = id
      selectedPartIds.value = [id]
      highlightSelectedParts()
      scrollPartRowIntoView(id)
      expandPartsDetails()
      return
    }
    el = el.parentElement
  }
  // 点击空白处清除高亮
  selectedPartId.value = ''
  selectedPartIds.value = []
  highlightSvgPart('')
}

// 部件列表行点击 → 同步选中 + 高亮 SVG 元素 + 滚动到可见
function selectPartFromList(partId, event) {
  const isMulti = event && (event.ctrlKey || event.metaKey)
  if (isMulti) {
    // Ctrl+click：添加/移除
    const idx = selectedPartIds.value.indexOf(partId)
    if (idx >= 0) {
      selectedPartIds.value = selectedPartIds.value.filter(id => id !== partId)
    } else {
      selectedPartIds.value = [...selectedPartIds.value, partId]
    }
  } else {
    selectedPartIds.value = [partId]
  }
  selectedPartId.value = partId
  highlightSelectedParts()
  scrollSelectedPartsIntoView()
  expandPartsDetails()
}

// 滚动部件列表对应行到容器中间（smooth）
function scrollPartRowIntoView(partId) {
  if (!partId) return
  nextTick(() => {
    // 新模板用 .parts-mini-list，旧模板用 .target-table
    const container = document.querySelector('.parts-mini-list') || document.querySelector('.target-table')
    if (!container) return
    const escId = partId.replace(/["\\]/g, '\\$&')
    const row = container.querySelector(`[data-part-id="${escId}"]`)
    if (row) {
      row.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  })
}

// SVG 重新加载时清除残留高亮
watch(svgInlineHtml, () => {
  selectedPartId.value = ''
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
              <button
                v-if="authStore.hasPermission('model_edit')"
                class="btn-delete-card"
                title="删除机型"
                @click.stop="deleteModel(model)"
              >×</button>
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
            @deleted="onModelFileUploaded"
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
            <div v-if="svgPreviewLoading" class="svg-loading">⏳ 加载中...</div>
            <div v-else class="svg-inline" v-html="svgInlineHtml"></div>
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

      <!-- ==================== Tab 2: 动画配置（拖拽录制） ==================== -->
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
              class="btn-record"
              :class="{ 'recording': recordMode }"
              :disabled="!selectedModel || !svgPreviewUrl"
              @click="toggleRecordMode"
              :title="recordMode ? '点击关闭录制' : '开启后可在SVG上拖拽部件录制动作'"
            >
              {{ recordMode ? '⏹ 停止录制' : '● 开始录制' }}
            </button>
            <button class="btn-import" :disabled="!selectedModel" @click="triggerImportJson" title="导入Motion JSON">
              导入JSON
            </button>
            <input ref="importInput" type="file" accept=".json" style="display:none;" @change="onImportJson" />
            <button class="btn-save" :disabled="!editDirty || !selectedModel" @click="saveAnimConfig">保存</button>
            <button class="btn-export" :disabled="!editingConfig" @click="exportConfig">导出</button>
            <span v-if="editDirty" class="dirty-flag">● 未保存</span>
          </div>
        </div>

        <div v-if="!selectedModel" class="empty-hint">请先选择机型</div>
        <div v-else-if="!svgPreviewUrl" class="empty-hint">该机型未配置SVG文件，请先在"模型管理"上传SVG</div>
        <div v-else-if="!editingConfig" class="empty-hint">加载中...</div>
        <div v-else class="config-editor">
          <!-- 主工作区：SVG + 右侧面板 -->
          <div class="record-main-row">
            <!-- 左：SVG 交互预览 -->
            <div class="record-svg-section">
              <div class="section-header">
                <h4>SVG 预览{{ recordMode ? '（录制中：拖拽部件录制动作）' : '（Ctrl+点击多选，空白处拖拽框选）' }}</h4>
                <div class="record-toolbar-right">
                  <span v-if="selectedPartIds.length > 0" class="selected-count">
                    已选 {{ selectedPartIds.length }} 个
                    <button v-if="selectedPartIds.length >= 2" class="btn-small btn-combine" @click="startGroupInput">组合</button>
                    <button class="btn-small" @click="clearSelection">清除</button>
                  </span>
                  <span v-if="recordMode" class="record-action-selector">
                    动作类型：
                    <select v-model="recordActionType" class="action-type-select">
                      <option v-for="a in ACTION_TYPE_OPTIONS" :key="a.value" :value="a.value">
                        {{ a.icon }} {{ a.label }}
                      </option>
                    </select>
                  </span>
                </div>
              </div>
              <!-- 组合名称输入框 -->
              <div v-if="showGroupInput" class="group-input-bar">
                <input
                  ref="groupInputRef"
                  v-model="groupNameInput"
                  placeholder="组合名称（如 GROUP_1）"
                  class="group-name-input"
                  @keyup.enter="confirmGroupCombine"
                  @keyup.esc="cancelGroupCombine"
                  @blur="confirmGroupCombine"
                />
                <button class="btn-small btn-combine" @click="confirmGroupCombine">确认</button>
                <button class="btn-small" @click="cancelGroupCombine">取消</button>
              </div>
              <div class="svg-preview-wrapper svg-interactive" :class="{ 'recording-mode': recordMode }">
                <div v-if="svgPreviewLoading" class="svg-loading">加载中...</div>
                <div
                  v-else
                  ref="svgInlineRef"
                  class="svg-inline"
                  v-html="svgInlineHtml"
                  @click="onSvgClick"
                  @mousedown="onSvgMouseDown"
                  @mousemove="onSvgMouseMove"
                  @mouseup="onSvgMouseUp"
                  @mouseleave="onSvgMouseUp"
                ></div>
                <!-- 框选矩形（lasso） -->
                <div v-if="lassoState.active" class="lasso-rect" :style="lassoRectStyle"></div>
              </div>
              <div class="svg-preview-url">{{ svgPreviewUrl }}</div>
            </div>

            <!-- 右：已录制动作列表 -->
            <div class="record-motions-section">
              <div class="section-header">
                <h4>已录制动作（{{ motionList.length }}）</h4>
                <div class="section-actions">
                  <button class="btn-small" @click="extractSvgPartsToTargets" title="从SVG提取部件列表">提取部件</button>
                </div>
              </div>
              <!-- 选中部件显示区 -->
              <div v-if="selectedPartIds.length > 0" class="selected-parts-box">
                <div class="selected-parts-title">已选部件（{{ selectedPartIds.length }}）</div>
                <div class="selected-parts-chips">
                  <span v-for="pid in selectedPartIds" :key="pid" class="selected-part-chip">{{ pid }}</span>
                </div>
              </div>
              <!-- 部件搜索 -->
              <div class="part-search-bar">
                <input v-model="partSearch" placeholder="搜索部件..." class="part-search-input" />
                <button v-if="partSearch" class="btn-clear" @click="partSearch = ''">×</button>
              </div>
              <!-- 动作列表 -->
              <div class="motion-list">
                <div v-for="(m, idx) in motionList" :key="idx" class="motion-item" :data-idx="idx">
                  <div class="motion-item-header">
                    <span class="motion-step">{{ m.step }}</span>
                    <button class="btn-delete" @click="deleteMotion(idx)" title="删除">×</button>
                  </div>
                  <div class="motion-summary">{{ getMotionSummary(m) }}</div>
                  <div v-if="m.rules?.[0]?.when && m.rules[0].when !== 'true'" class="motion-when">
                    when: {{ m.rules[0].when }}
                  </div>
                </div>
                <div v-if="motionList.length === 0" class="empty-row">
                  暂无动作{{ recordMode ? '，拖拽SVG部件开始录制' : '' }}
                </div>
              </div>
              <!-- 部件列表（默认展开，可手动折叠；Ctrl+点击列表行多选） -->
              <details class="parts-details" open>
                <summary>部件列表（{{ totalPartsCount }}）{{ selectedPartIds.length > 0 ? ` · 已选 ${selectedPartIds.length}` : '' }}</summary>
                <div class="parts-mini-list">
                  <div
                    v-for="(key, idx) in targetKeys"
                    :key="'p'+idx"
                    class="part-mini-item"
                    :data-part-id="isMotionJson ? editingConfig.parts[idx]?.part_id : key"
                    :class="{ 'row-selected': selectedPartId === (isMotionJson ? editingConfig.parts[idx]?.part_id : key) || selectedPartIds.includes(isMotionJson ? editingConfig.parts[idx]?.part_id : key) }"
                    @click="selectPartFromList(isMotionJson ? editingConfig.parts[idx]?.part_id : key, $event)"
                  >
                    {{ isMotionJson ? editingConfig.parts[idx]?.part_id : key }}
                  </div>
                </div>
              </details>
            </div>
          </div>

          <!-- 录制面板（浮动） -->
          <div v-if="showRecordPanel" class="record-panel">
            <div class="record-panel-header">
              <h4>录制动作</h4>
              <button class="btn-delete" @click="cancelRecord" title="取消">×</button>
            </div>
            <div class="record-panel-body">
              <div class="record-field">
                <label>目标部件</label>
                <input :value="recordForm.partId" disabled class="record-readonly" />
              </div>
              <div class="record-field">
                <label>动作类型</label>
                <input :value="ACTION_TYPE_OPTIONS.find(a => a.value === recordForm.actionType)?.label" disabled class="record-readonly" />
              </div>
              <!-- offset 参数 -->
              <template v-if="recordForm.actionType === 'offset'">
                <div class="record-field-row">
                  <div class="record-field">
                    <label>offset_x</label>
                    <input type="number" v-model.number="recordForm.offsetX" />
                  </div>
                  <div class="record-field">
                    <label>offset_y</label>
                    <input type="number" v-model.number="recordForm.offsetY" />
                  </div>
                </div>
              </template>
              <!-- rotate 参数 -->
              <template v-if="recordForm.actionType === 'rotate'">
                <div class="record-field">
                  <label>angle (°)</label>
                  <input type="number" v-model.number="recordForm.angle" />
                </div>
                <div class="record-field-row">
                  <div class="record-field">
                    <label>pivot_x</label>
                    <input type="number" v-model.number="recordForm.pivotX" />
                  </div>
                  <div class="record-field">
                    <label>pivot_y</label>
                    <input type="number" v-model.number="recordForm.pivotY" />
                  </div>
                </div>
              </template>
              <!-- scale 参数 -->
              <template v-if="recordForm.actionType === 'scale'">
                <div class="record-field-row">
                  <div class="record-field">
                    <label>scale_x</label>
                    <input type="number" step="0.1" v-model.number="recordForm.scaleX" />
                  </div>
                  <div class="record-field">
                    <label>scale_y</label>
                    <input type="number" step="0.1" v-model.number="recordForm.scaleY" />
                  </div>
                </div>
              </template>
              <!-- opacity 参数 -->
              <template v-if="recordForm.actionType === 'opacity'">
                <div class="record-field">
                  <label>opacity (0-1)</label>
                  <input type="number" step="0.1" min="0" max="1" v-model.number="recordForm.opacity" />
                </div>
              </template>
              <!-- 通用参数 -->
              <div class="record-field-row">
                <div class="record-field">
                  <label>duration (ms)</label>
                  <input type="number" v-model.number="recordForm.duration" />
                </div>
                <div class="record-field">
                  <label>easing</label>
                  <select v-model="recordForm.easing">
                    <option v-for="e in EASING_OPTIONS" :key="e" :value="e">{{ e }}</option>
                  </select>
                </div>
              </div>
              <hr class="record-divider" />
              <div class="record-field">
                <label>Step 名称（触发事件）</label>
                <input ref="recordStepInputRef" v-model="recordForm.step" placeholder="如 POD_PLACED" @keyup.enter="saveRecord" />
              </div>
              <div class="record-field">
                <label>When 条件</label>
                <input v-model="recordForm.when" placeholder="如 params.port == '1'" />
                <div class="event-templates">
                  <button v-for="t in EVENT_TEMPLATES" :key="t.when" class="event-template-btn" @click="recordForm.when = t.when">
                    {{ t.label }}
                  </button>
                </div>
              </div>
              <div class="record-panel-actions">
                <button class="btn-save" @click="saveRecord">保存录制</button>
                <button class="btn-cancel-record" @click="cancelRecord">取消</button>
              </div>
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
/* v2.5.4: 机型卡片删除按钮 */
.btn-delete-card {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 50%;
  background: rgba(244, 67, 54, 0.85);
  color: #fff;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.2s;
}
.model-card:hover .btn-delete-card { opacity: 1; }
.btn-delete-card:hover { background: rgba(244, 67, 54, 1); }
.model-header { position: relative; }
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
  overflow: auto;
  height: 400px;
  display: flex;
  justify-content: center;
  align-items: center;
  position: relative;
}
/* v2.5.4: 内联 SVG 渲染容器 */
.svg-inline {
  width: 100%;
  height: 100%;
  display: flex;
  justify-content: center;
  align-items: center;
}
.svg-inline svg {
  max-width: 100%;
  max-height: 100%;
  width: auto;
  height: auto;
}

/* === v2.5.9: SVG 部件交互样式 === */
/* 动画配置 Tab 顶部的交互式 SVG 预览栏 */
.selected-part-tag {
  font-size: 12px;
  color: var(--text-dim);
  background: rgba(255, 87, 34, 0.12);
  border: 1px solid rgba(255, 87, 34, 0.4);
  border-radius: 4px;
  padding: 2px 8px;
}
.selected-part-tag code {
  color: #ff7043;
  font-weight: 600;
}
.svg-interactive {
  height: 60vh;
  min-height: 400px;
  cursor: crosshair;
}
/* SVG 内所有元素强制接收鼠标事件（覆盖 SVG 文件中的 pointer-events 属性） */
.svg-interactive svg,
.svg-interactive svg * {
  pointer-events: all !important;
}
.svg-interactive svg [id] {
  cursor: pointer;
  transition: filter 0.15s ease, outline 0.15s ease;
}
.svg-interactive svg [id]:hover {
  filter: drop-shadow(0 0 4px rgba(255, 87, 34, 0.7));
}
.svg-interactive svg .part-highlight {
  outline: none;
  stroke: #ff5722 !important;
  stroke-width: 3px !important;
  filter: drop-shadow(0 0 6px rgba(255, 87, 34, 0.9));
}
/* <g> 容器无 stroke 时，给子元素也加描边 */
.svg-interactive svg .part-highlight * {
  stroke: #ff5722 !important;
  stroke-width: 2px !important;
}
/* 部件列表行选中态 */
.table-row.row-selected {
  background: rgba(255, 87, 34, 0.15) !important;
  box-shadow: inset 3px 0 0 #ff5722;
}
.table-row.row-selected input {
  background: transparent;
}

/* === v2.5.10: 部件搜索框 + 列表内部滚动 === */
.part-search-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.part-search-input {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
}
.part-search-input:focus {
  outline: none;
  border-color: var(--accent);
}
.btn-clear {
  border: none;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  font-size: 18px;
  padding: 2px 6px;
  line-height: 1;
}
.btn-clear:hover { color: var(--accent); }
/* 部件表格容器内部滚动（不再整页下拉） */
.target-table {
  max-height: 420px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 4px;
}
/* 表头置顶 */
.target-table .table-header {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--panel-2);
}

.svg-loading {
  color: var(--text-dim);
  font-size: 14px;
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

/* === 录制模式布局 === */
.record-main-row {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  align-items: stretch;
}
.record-svg-section { flex: 3; min-width: 0; }
.record-motions-section {
  flex: 2;
  min-width: 280px;
  display: flex;
  flex-direction: column;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  max-height: 70vh;
}
.record-svg-section .svg-interactive {
  height: 70vh;
  min-height: 400px;
}
.recording-mode {
  border: 2px dashed var(--yellow) !important;
  cursor: crosshair;
}
.recording-mode .svg-inline { cursor: grab; }
.recording-mode .svg-inline:active { cursor: grabbing; }
.record-action-selector { display: flex; align-items: center; gap: 6px; font-size: 12px; }
/* 框选矩形 */
.lasso-rect {
  position: absolute;
  border: 2px dashed #06b6d4;
  background: rgba(6, 182, 212, 0.1);
  pointer-events: none;
  z-index: 50;
  border-radius: 2px;
}
/* 选中部件显示区 */
.selected-parts-box {
  background: rgba(6, 182, 212, 0.06);
  border: 1px solid rgba(6, 182, 212, 0.3);
  border-radius: 6px;
  padding: 6px 8px;
  margin-bottom: 8px;
}
.selected-parts-title {
  font-size: 11px;
  color: var(--accent);
  font-weight: 600;
  margin-bottom: 4px;
}
.selected-parts-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  max-height: 60px;
  overflow-y: auto;
}
.selected-part-chip {
  font-size: 10px;
  font-family: monospace;
  background: var(--panel-2);
  color: var(--accent);
  padding: 1px 6px;
  border-radius: 8px;
  border: 1px solid rgba(6, 182, 212, 0.3);
  word-break: break-all;
}
.record-toolbar-right { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.selected-count {
  font-size: 12px;
  color: var(--yellow);
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 4px;
}
.btn-combine {
  background: var(--accent) !important;
  color: #000 !important;
  font-weight: 600;
}
.group-input-bar {
  display: flex;
  gap: 6px;
  padding: 6px 0;
  align-items: center;
}
.group-name-input {
  flex: 1;
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 5px 8px;
  border-radius: 4px;
  font-size: 13px;
  outline: none;
}
.group-name-input:focus { border-color: var(--accent); }
.action-type-select {
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
}
.btn-record {
  background: #e8463a;
  color: #fff;
  border: none;
  padding: 6px 14px;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 700;
  font-size: 13px;
  animation: pulse-rec 1.5s infinite;
}
.btn-record.recording { background: #1dc981; animation: none; }
.btn-record:disabled { opacity: 0.5; cursor: not-allowed; animation: none; }
@keyframes pulse-rec {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}
/* 已录制动作列表 */
.motion-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.motion-item {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.motion-item:hover { border-color: var(--accent); }
.motion-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.motion-step {
  font-family: monospace;
  font-size: 12px;
  color: var(--yellow);
  font-weight: 600;
}
.motion-summary {
  font-size: 12px;
  color: var(--text);
  margin-bottom: 2px;
}
.motion-when {
  font-size: 11px;
  color: var(--text-dim);
  font-family: monospace;
}
.parts-details { margin-top: 8px; font-size: 12px; }
.parts-details summary { cursor: pointer; color: var(--text-dim); padding: 4px 0; }
.parts-mini-list {
  max-height: 150px;
  overflow-y: auto;
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.part-mini-item {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-family: monospace;
  word-break: break-all;
}
.part-mini-item:hover { background: var(--panel-2); }
.part-mini-item.row-selected { background: rgba(6, 182, 212, 0.15); color: var(--accent); }

/* 录制面板 */
.record-panel {
  position: fixed;
  bottom: 20px;
  right: 20px;
  width: 380px;
  max-height: 80vh;
  overflow-y: auto;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
  z-index: 100;
}
.record-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--panel-2);
  border-radius: 12px 12px 0 0;
}
.record-panel-header h4 { margin: 0; font-size: 14px; color: var(--accent); }
.record-panel-body { padding: 12px 16px; }
.record-field { margin-bottom: 8px; }
.record-field label {
  display: block;
  font-size: 11px;
  color: var(--text-dim);
  margin-bottom: 3px;
}
.record-field input, .record-field select {
  width: 100%;
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 5px 8px;
  border-radius: 4px;
  font-size: 13px;
  outline: none;
}
.record-field input:focus, .record-field select:focus { border-color: var(--accent); }
.record-readonly {
  background: var(--panel-2) !important;
  color: var(--text-dim) !important;
}
.record-field-row { display: flex; gap: 8px; }
.record-field-row .record-field { flex: 1; }
.record-divider { margin: 10px 0; border: none; border-top: 1px solid var(--border); }
.event-templates { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.event-template-btn {
  background: var(--panel-2);
  color: var(--text-dim);
  border: 1px solid var(--border);
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
  cursor: pointer;
}
.event-template-btn:hover { border-color: var(--accent); color: var(--accent); }
.record-panel-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
.record-panel-actions .btn-save { flex: 1; }
.btn-cancel-record {
  background: var(--panel-2);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 6px 14px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}
.btn-cancel-record:hover { background: var(--bg); }
@media (max-width: 1100px) {
  .record-main-row { flex-direction: column; }
  .record-motions-section { max-height: 300px; }
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
