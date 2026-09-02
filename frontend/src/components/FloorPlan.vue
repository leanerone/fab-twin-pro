<script setup>
import { ref, onMounted, onUnmounted, watch, computed, reactive } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'

const props = defineProps({
  floorId: { type: Number, default: 1 },
})

const emit = defineEmits(['select-machine'])

const authStore = useAuthStore()

// === 缩放/平移 ===
const zoom = ref(1)          // 缩放倍率，1=原始大小
const canvasInnerRef = ref(null)  // 内层画布 ref（用于坐标计算）
function zoomIn() { zoom.value = Math.min(5, +(zoom.value + 0.25).toFixed(2)) }
function zoomOut() { zoom.value = Math.max(0.5, +(zoom.value - 0.25).toFixed(2)) }
function zoomReset() { zoom.value = 1 }
function onWheel(e) {
  e.preventDefault()
  if (e.deltaY < 0) zoomIn()
  else zoomOut()
}

const floorData = ref(null)
const machines = ref([])
const areas = ref([])
const tracks = ref([])
const vehicles = ref([])
const isLoading = ref(true)
const editMode = ref(false)
const selectedMachine = ref(null)
// 选中机台名称编辑草稿（保存时才提交后端）
const editMachineName = ref('')
const savingMachine = ref(false)
const selectedArea = ref(null)
const hoverVehicle = ref(null)
const mousePos = ref({ x: 0, y: 0 })

// === 多选/框选/调整大小 ===
// 多选集合：存 "machine:ID" / "area:ID" 形式
const multiSelection = ref(new Set())
// 框选矩形（拖拽空白处时）
const boxSelect = ref(null)
// 当前拖拽类型：'move' | 'resize-<handle>' | 'box-select' | 'multi-move'
const dragMode = ref(null)
// 区域 resize 手柄名（tl/tr/bl/br/t/r/b/l）
const resizeHandle = ref(null)
// 多选移动时的起始点 + 各项起始坐标
const multiMoveStart = ref(null)

// 编辑工具: select/machine/area/track/vehicle
const editTool = ref('select')
// 新机台表单
const newMachine = ref({ id: '', name: '', model: '', process_type: 'ETCH', line: 1 })
// 画框区域
const drawingArea = ref(null)
const dragInfo = ref(null)
// 新区域表单
const newArea = ref({ name: '', area_type: 'equipment', color: '#1e3a5f' })
// 选中区域编辑草稿（名称/颜色），保存时才提交后端
const editAreaName = ref('')
const editAreaColor = ref('#1e3a5f')
const savingArea = ref(false)
// 选中区域尺寸/位置编辑草稿（D-#1：手动输入长宽度+坐标）
const editAreaX = ref(0)
const editAreaY = ref(0)
const editAreaW = ref(10)
const editAreaH = ref(10)
// 草稿 - 米制换算（按楼层宽高换算；若楼层宽高没填则 fallback 100×100）
const editAreaWM = computed(() => {
  const w = floorData.value?.width
  const scale = typeof w === 'number' && w > 0 ? w / 100 : 1
  return +(editAreaW.value * scale).toFixed(2)
})
const editAreaHM = computed(() => {
  const h = floorData.value?.height
  const scale = typeof h === 'number' && h > 0 ? h / 100 : 1
  return +(editAreaH.value * scale).toFixed(2)
})
// 把米制改回百分比（用户手动填写米时反向）
function applyAreaMeters(mW, mH) {
  const w = floorData.value?.width || 100
  const h = floorData.value?.height || 100
  editAreaW.value = clampPct((+mW / (w || 100)) * 100, 0.5, 100)
  editAreaH.value = clampPct((+mH / (h || 100)) * 100, 0.5, 100)
}
function clampPct(v, min = 0, max = 100) {
  if (Number.isNaN(+v)) return min
  return Math.max(min, Math.min(max, +v))
}
// 后端返回统一友好错误：err.response?.data?.detail（FastAPI 400/500 的 JSON body.detail）
// 顺序：detail > message > 默认 fallback
function errMsg(err, fallback = '请求失败') {
  if (!err) return fallback
  const d = (err && err.response && err.response.data && err.response.data.detail) || err.detail
  if (d) {
    if (typeof d === 'string') return d
    if (Array.isArray(d)) return d.map(x => x?.msg || String(x)).join('；')
    if (typeof d === 'object') return Object.values(d).map(x => String(x)).join('；')
  }
  return err.message || String(err) || fallback
}
// 轨迹绘制
const drawingTrack = ref([])  // 正在绘制的轨迹点 [[x,y],...]
const newTrack = ref({ name: '', color: '#00d4ff', speed: 1.0 })
// 新天车
const newVehicle = ref({ id: '', name: '', track_id: null })

const stateColors = {
  run: '#10b981',
  idle: '#f59e0b',
  error: '#ef4444',
  maint: '#3b82f6',
  setup: '#7c3aed',
}

const areaTypeIcons = {
  equipment: '⚙',
  pump: '💧',
  walkway: '🚶',
  elevator: '⬆',
  exit: '🚪',
  stk: '📦',
}

const areaTypeColors = {
  equipment: '#1e3a5f',
  pump: '#2d1b4e',
  walkway: '#3a3a3a',
  elevator: '#4a3728',
  exit: '#8b0000',
  stk: '#1a4a3a',
}

const processTypes = ['ETCH', 'WAT', 'WS', 'STK', 'CMP', 'PVD', 'LITHO', 'IMP']

// 模型配置列表（用于新建机台时绑定）
const modelConfigs = ref([])

async function loadModelConfigs() {
  try {
    const res = await fetch('/api/models')
    if (res.ok) {
      modelConfigs.value = await res.json()
    }
  } catch (e) {
    console.error('加载模型配置失败:', e)
  }
}

async function loadFloorData() {
  isLoading.value = true
  try {
    floorData.value = await api.getFloor(props.floorId)
    machines.value = floorData.value.machines || []
    areas.value = floorData.value.areas || []
    tracks.value = floorData.value.tracks || []
    vehicles.value = floorData.value.vehicles || []
  } catch (e) {
    console.error('加载楼层数据失败:', e)
  }
  isLoading.value = false
}

// 直接创建区域（不依赖鼠标画框）
function quickAddArea() {
  const name = newArea.value.name || `${newArea.value.area_type}_${Date.now().toString().slice(-4)}`
  handleAddArea({
    name,
    area_type: newArea.value.area_type,
    x_pos: 30,
    y_pos: 30,
    width: 15,
    height: 15,
    color: newArea.value.color || areaTypeColors[newArea.value.area_type] || '#1e3a5f',
  })
  newArea.value.name = ''
}

// 切换区域类型时自动套用该类型默认颜色（用户可再用颜色选择器覆盖）
watch(() => newArea.value.area_type, (t) => {
  newArea.value.color = areaTypeColors[t] || '#1e3a5f'
})

// 选中区域变化时，把名称/颜色/尺寸/坐标同步到编辑草稿框
watch(selectedArea, (a) => {
  if (a) {
    editAreaName.value = a.name || ''
    editAreaColor.value = a.color || '#1e3a5f'
    editAreaX.value = +Number(a.x_pos ?? 0).toFixed(2)
    editAreaY.value = +Number(a.y_pos ?? 0).toFixed(2)
    editAreaW.value = +Number(a.width ?? 10).toFixed(2)
    editAreaH.value = +Number(a.height ?? 10).toFixed(2)
  }
}, { immediate: true })

// 保存选中区域的名称/颜色/尺寸/坐标到后端（D-#1 支持手动输入尺寸）
async function saveAreaProps() {
  const a = selectedArea.value
  if (!a) return
  const newName = (editAreaName.value || '').trim() || a.name
  const newColor = editAreaColor.value || a.color
  const nx = clampPct(+editAreaX.value || 0, 0, 100)
  const ny = clampPct(+editAreaY.value || 0, 0, 100)
  const nw = clampPct(+editAreaW.value || 1, 0.5, 100)
  const nh = clampPct(+editAreaH.value || 1, 0.5, 100)
  // 边界限制：x+w 与 y+h 不能超过 100
  const newX = Math.min(nx, 100 - nw)
  const newY = Math.min(ny, 100 - nh)
  // 无变更直接返回
  if (
    newName === a.name && newColor === a.color
    && Math.abs(newX - a.x_pos) < 0.01
    && Math.abs(newY - a.y_pos) < 0.01
    && Math.abs(nw - a.width) < 0.01
    && Math.abs(nh - a.height) < 0.01
  ) {
    showToast('无变更', 'info')
    return
  }
  savingArea.value = true
  try {
    await api.updateFloorArea(props.floorId, a.id, {
      name: newName, color: newColor,
      x_pos: newX, y_pos: newY, width: nw, height: nh,
    })
    // 同步本地对象，避免整页刷新
    a.name = newName
    a.color = newColor
    a.x_pos = newX; a.y_pos = newY; a.width = nw; a.height = nh
    editAreaName.value = newName
    editAreaColor.value = newColor
    editAreaX.value = +newX.toFixed(2); editAreaY.value = +newY.toFixed(2)
    editAreaW.value = +nw.toFixed(2); editAreaH.value = +nh.toFixed(2)
    showToast('区域已保存', 'success')
  } catch (err) {
    console.error('[FloorPlan] 区域保存失败:', err)
    showToast('保存失败: ' + errMsg(err, err.message || ''), 'error')
    // 回滚草稿框
    editAreaName.value = a.name
    editAreaColor.value = a.color
    editAreaX.value = +(a.x_pos ?? 0).toFixed(2)
    editAreaY.value = +(a.y_pos ?? 0).toFixed(2)
    editAreaW.value = +(a.width ?? 10).toFixed(2)
    editAreaH.value = +(a.height ?? 10).toFixed(2)
  } finally {
    savingArea.value = false
  }
}

function selectMachine(m) {
  selectedMachine.value = m
  if (!editMode.value) {
    emit('select-machine', m)
  }
}

// === 双击机台 → 编辑外链跳转配置（仅管理员） ===
const showExternalLinkModal = ref(false)
const editingLinkMachine = ref(null)
const externalLinkForm = ref({ external_url: '', use_external_url: 0 })
const savingExternalLink = ref(false)
let machineClickTimer = null

function canEditModel() {
  return authStore.hasPermission && authStore.hasPermission('model_edit')
}

function onMachineClick(m, e) {
  if (e) e.stopPropagation()
  // 管理员 + 编辑模式：延迟单击，给双击编辑机会
  if (canEditModel() && editMode.value) {
    if (machineClickTimer) clearTimeout(machineClickTimer)
    machineClickTimer = setTimeout(() => {
      selectMachine(m)
      machineClickTimer = null
    }, 300)
  } else {
    // 非编辑模式或非管理员：直接导航
    selectMachine(m)
  }
}
function onMachineDblClick(m, e) {
  if (e) e.stopPropagation()
  if (machineClickTimer) { clearTimeout(machineClickTimer); machineClickTimer = null }
  // 只有编辑模式 + 管理员才能弹编辑框
  if (!editMode.value) return
  if (!canEditModel()) {
    showToast('仅管理员可编辑机台外链配置', 'warn')
    return
  }
  openExternalLinkEditor(m)
}
function openExternalLinkEditor(m) {
  // 从最新 machines 数组中查找，确保数据是最新的
  const latest = machines.value.find(x => x.id === m.id) || m
  editingLinkMachine.value = latest
  externalLinkForm.value = {
    external_url: latest.external_url || '',
    use_external_url: latest.use_external_url ? 1 : 0,
  }
  showExternalLinkModal.value = true
}
async function saveExternalLink() {
  const m = editingLinkMachine.value
  if (!m) return
  const rawUrl = (externalLinkForm.value.external_url || '').trim()
  // 自动补全协议前缀（www.baidu.com → https://www.baidu.com）
  const url = rawUrl && !/^https?:\/\//i.test(rawUrl) ? 'https://' + rawUrl : rawUrl
  if (externalLinkForm.value.use_external_url && !url) {
    showToast('启用跳转网站时必须填写 URL', 'error')
    return
  }
  savingExternalLink.value = true
  try {
    const updated = await api.updateMachineExternalLink(m.id, {
      external_url: url,
      use_external_url: externalLinkForm.value.use_external_url ? 1 : 0,
    })
    // 精确更新本地数据
    const idx = machines.value.findIndex(x => x.id === m.id)
    if (idx >= 0) {
      machines.value[idx].external_url = updated.external_url
      machines.value[idx].use_external_url = updated.use_external_url
    }
    m.external_url = updated.external_url
    m.use_external_url = updated.use_external_url
    showExternalLinkModal.value = false
    showToast('外链配置已保存', 'success')
  } catch (e) {
    showToast('保存失败: ' + errMsg(e, e.message || ''), 'error')
  } finally {
    savingExternalLink.value = false
  }
}

// 获取百分比坐标（基于内层画布，支持缩放）
function getPercent(e) {
  const el = canvasInnerRef.value || e.currentTarget
  const rect = el.getBoundingClientRect()
  const x = ((e.clientX - rect.left) / rect.width) * 100
  const y = ((e.clientY - rect.top) / rect.height) * 100
  return { x: Math.max(0, Math.min(100, x)), y: Math.max(0, Math.min(100, y)) }
}

// === 多选辅助 ===
function multiKey(e) {
  // Ctrl/Meta(⌘) 或 Shift 视为多选修饰键
  return e.ctrlKey || e.metaKey || e.shiftKey
}
function isMultiSelected(type, id) {
  return multiSelection.value.has(`${type}:${id}`)
}
function clearMultiSelection() {
  multiSelection.value = new Set()
}
// 把单个机台/区域加入多选（不替换）
function addToMultiSelection(type, id) {
  const s = new Set(multiSelection.value)
  s.add(`${type}:${id}`)
  multiSelection.value = s
}
// 框选命中的机台/区域加入多选
function computeBoxSelection(box) {
  if (!box) return
  const x1 = Math.min(box.startX, box.x)
  const x2 = Math.max(box.startX, box.x)
  const y1 = Math.min(box.startY, box.y)
  const y2 = Math.max(box.startY, box.y)
  const s = new Set(multiSelection.value)
  // 机台点中心在框内即选中
  machines.value.forEach((m) => {
    if (m.floor_x >= x1 && m.floor_x <= x2 && m.floor_y >= y1 && m.floor_y <= y2) {
      s.add(`machine:${m.id}`)
    }
  })
  // 区域中心在框内或与框相交即选中
  areas.value.forEach((a) => {
    const ax2 = a.x_pos + a.width
    const ay2 = a.y_pos + a.height
    if (a.x_pos < x2 && ax2 > x1 && a.y_pos < y2 && ay2 > y1) {
      s.add(`area:${a.id}`)
    }
  })
  multiSelection.value = s
}

// === D-#2: 批量复制 ===
const batchCloning = ref(false)
async function batchCloneSelected(offset = { x: 3, y: 3 }) {
  if (multiSelection.value.size === 0) return
  batchCloning.value = true
  try {
    const areaIds = []; const machineIds = []
    for (const k of multiSelection.value) {
      const [t, id] = k.split(':', 2)
      if (t === 'area') areaIds.push(+id)
      else if (t === 'machine') machineIds.push(id)
    }
    let createdAreas = [], createdMachines = []
    if (areaIds.length) {
      const r = await api.cloneFloorAreas(props.floorId, areaIds, offset)
      createdAreas = r.items || []
    }
    if (machineIds.length) {
      const r = await api.cloneFloorMachines(props.floorId, machineIds, offset)
      createdMachines = r.items || []
    }
    showToast(`已复制 ${createdAreas.length + createdMachines.length} 个对象`, 'success')
    // 把复制结果对应加入多选（替换原多选集）
    const ns = new Set()
    createdAreas.forEach(a => ns.add(`area:${a.id}`))
    createdMachines.forEach(m => ns.add(`machine:${m.id}`))
    multiSelection.value = ns
    await loadFloorData()
  } catch (e) {
    showToast('批量复制失败: ' + errMsg(e, e.message || ''), 'error')
  } finally {
    batchCloning.value = false
  }
}

// === D-#3: 图层重排（支持单选+多选集合）===
const reordering = ref(false)
function reorderTargets(action) {
  // 优先级：多选集合 > 单选区域 > 单选机台
  const list = []
  for (const k of multiSelection.value) {
    const [t, id] = k.split(':', 2)
    list.push({ t, id: t === 'area' ? +id : id })
  }
  if (!list.length && selectedArea.value) {
    list.push({ t: 'area', id: selectedArea.value.id })
  }
  if (!list.length && selectedMachine.value) {
    list.push({ t: 'machine', id: selectedMachine.value.id })
  }
  return list
}
async function reorderSelected(action) {
  const list = reorderTargets(action)
  if (!list.length) return
  reordering.value = true
  try {
    // 批量时，top/down 需要从前向后保持顺序；bottom/up 从后向前
    let order = list
    if (action === 'top' || action === 'down') order = [...list]
    if (action === 'bottom' || action === 'up') order = [...list].reverse()
    for (const it of order) {
      if (it.t === 'area') {
        await api.reorderFloorArea(props.floorId, it.id, action)
      } else {
        await api.reorderFloorMachine(props.floorId, it.id, action)
      }
    }
    showToast(`图层${{top:'置顶',bottom:'置底',up:'上移一层',down:'下移一层'}[action]}完成`, 'success')
    await loadFloorData()
  } catch (e) {
    showToast('图层操作失败: ' + errMsg(e, e.message || ''), 'error')
  } finally {
    reordering.value = false
  }
}

function handleMouseDown(e) {
  if (!editMode.value) return

  // 如果点击的是删除按钮，不触发画框/拖拽
  if (e.target.closest('.area-delete')) return

  const pos = getPercent(e)
  mousePos.value = pos

  if (editTool.value === 'machine') {
    // 点击放置机台
    handleAddMachine(pos)
  } else if (editTool.value === 'area') {
    // 开始画框
    drawingArea.value = { startX: pos.x, startY: pos.y, x: pos.x, y: pos.y, w: 0, h: 0 }
    document.addEventListener('mousemove', docMouseMove)
    document.addEventListener('mouseup', docMouseUp)
  } else if (editTool.value === 'track') {
    // 点击添加轨迹点
    drawingTrack.value.push([pos.x, pos.y])
  } else if (editTool.value === 'vehicle') {
    // 点击放置天车（需要先选轨迹）
    handleAddVehicle(pos)
  } else if (editTool.value === 'select') {
    // 优先：点击区域 resize 手柄
    const handleEl = e.target.closest('.resize-handle')
    if (handleEl) {
      const aid = parseInt(handleEl.dataset.aid)
      const h = handleEl.dataset.handle
      const a = areas.value.find(x => x.id === aid)
      if (a) {
        selectedArea.value = a
        selectedMachine.value = null
        if (!multiKey(e)) clearMultiSelection()
        dragMode.value = `resize-${h}`
        resizeHandle.value = h
        dragInfo.value = { area: a, startX: pos.x, startY: pos.y, origX: a.x_pos, origY: a.y_pos, origW: a.width, origH: a.height }
        document.addEventListener('mousemove', docMouseMove)
        document.addEventListener('mouseup', docMouseUp)
      }
      return
    }

    // 检查是否点击了机台（拖拽）
    const machineEl = e.target.closest('.machine-marker')
    if (machineEl) {
      const mid = machineEl.dataset.mid
      const m = machines.value.find(x => x.id === mid)
      if (m) {
        // 多选修饰键：toggle 加入多选
        if (multiKey(e)) {
          if (isMultiSelected('machine', m.id)) {
            const s = new Set(multiSelection.value)
            s.delete(`machine:${m.id}`)
            multiSelection.value = s
          } else {
            addToMultiSelection('machine', m.id)
          }
          selectedMachine.value = m
          selectedArea.value = null
          return
        }
        // 普通点击：若该机台已在多选中，则开始多选移动；否则单选
        if (isMultiSelected('machine', m.id) && multiSelection.value.size > 1) {
          // 开始多选移动
          selectedMachine.value = m
          selectedArea.value = null
          dragMode.value = 'multi-move'
          // 记录所有选中项的起始坐标
          const starts = {}
          multiSelection.value.forEach((key) => {
            const [t, id] = key.split(':')
            if (t === 'machine') {
              const mm = machines.value.find(x => x.id === id)
              if (mm) starts[key] = { x: mm.floor_x, y: mm.floor_y }
            } else if (t === 'area') {
              const aa = areas.value.find(x => x.id === parseInt(id))
              if (aa) starts[key] = { x: aa.x_pos, y: aa.y_pos }
            }
          })
          multiMoveStart.value = { startX: pos.x, startY: pos.y, starts }
          document.addEventListener('mousemove', docMouseMove)
          document.addEventListener('mouseup', docMouseUp)
        } else {
          // 单选 + 拖拽
          clearMultiSelection()
          selectedMachine.value = m
          selectedArea.value = null
          dragMode.value = 'move'
          dragInfo.value = { machine: m, offsetX: pos.x - m.floor_x, offsetY: pos.y - m.floor_y }
          document.addEventListener('mousemove', docMouseMove)
          document.addEventListener('mouseup', docMouseUp)
        }
      }
      return
    }

    // 检查是否点击了区域（拖拽）
    const areaEl = e.target.closest('.floor-area')
    if (areaEl) {
      const aid = parseInt(areaEl.dataset.aid)
      const a = areas.value.find(x => x.id === aid)
      if (a) {
        if (multiKey(e)) {
          if (isMultiSelected('area', a.id)) {
            const s = new Set(multiSelection.value)
            s.delete(`area:${a.id}`)
            multiSelection.value = s
          } else {
            addToMultiSelection('area', a.id)
          }
          selectedArea.value = a
          selectedMachine.value = null
          return
        }
        if (isMultiSelected('area', a.id) && multiSelection.value.size > 1) {
          selectedArea.value = a
          selectedMachine.value = null
          dragMode.value = 'multi-move'
          const starts = {}
          multiSelection.value.forEach((key) => {
            const [t, id] = key.split(':')
            if (t === 'machine') {
              const mm = machines.value.find(x => x.id === id)
              if (mm) starts[key] = { x: mm.floor_x, y: mm.floor_y }
            } else if (t === 'area') {
              const aa = areas.value.find(x => x.id === parseInt(id))
              if (aa) starts[key] = { x: aa.x_pos, y: aa.y_pos }
            }
          })
          multiMoveStart.value = { startX: pos.x, startY: pos.y, starts }
          document.addEventListener('mousemove', docMouseMove)
          document.addEventListener('mouseup', docMouseUp)
        } else {
          clearMultiSelection()
          selectedArea.value = a
          selectedMachine.value = null
          dragMode.value = 'move'
          dragInfo.value = { area: a, offsetX: pos.x - a.x_pos, offsetY: pos.y - a.y_pos }
          document.addEventListener('mousemove', docMouseMove)
          document.addEventListener('mouseup', docMouseUp)
        }
      }
      return
    }

    // 点空白处：开始框选（select 工具 + 无多选修饰键时清空多选）
    if (!multiKey(e)) clearMultiSelection()
    // 同时取消单选
    selectedMachine.value = null
    selectedArea.value = null
    dragMode.value = 'box-select'
    boxSelect.value = { startX: pos.x, startY: pos.y, x: pos.x, y: pos.y }
    document.addEventListener('mousemove', docMouseMove)
    document.addEventListener('mouseup', docMouseUp)
  }
}

// document 级别的鼠标移动处理（画框/拖拽/多选/resize）
function docMouseMove(e) {
  if (!editMode.value) return
  // 用内层画布的 rect 计算百分比坐标（支持缩放）
  const canvas = canvasInnerRef.value || document.querySelector('.fp-canvas-inner') || document.querySelector('.fp-canvas')
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const x = ((e.clientX - rect.left) / rect.width) * 100
  const y = ((e.clientY - rect.top) / rect.height) * 100
  const pos = { x: Math.max(0, Math.min(100, x)), y: Math.max(0, Math.min(100, y)) }
  mousePos.value = pos

  if (drawingArea.value) {
    const d = drawingArea.value
    drawingArea.value = {
      startX: d.startX,
      startY: d.startY,
      x: Math.min(d.startX, pos.x),
      y: Math.min(d.startY, pos.y),
      w: Math.abs(pos.x - d.startX),
      h: Math.abs(pos.y - d.startY),
    }
    return
  }

  // 框选矩形
  if (dragMode.value === 'box-select' && boxSelect.value) {
    boxSelect.value = { ...boxSelect.value, x: pos.x, y: pos.y }
    return
  }

  // 多选批量移动
  if (dragMode.value === 'multi-move' && multiMoveStart.value) {
    const dx = pos.x - multiMoveStart.value.startX
    const dy = pos.y - multiMoveStart.value.startY
    multiSelection.value.forEach((key) => {
      const [t, id] = key.split(':')
      const st = multiMoveStart.value.starts[key]
      if (!st) return
      const nx = Math.max(0, Math.min(100, st.x + dx))
      const ny = Math.max(0, Math.min(100, st.y + dy))
      if (t === 'machine') {
        const mm = machines.value.find(z => z.id === id)
        if (mm) { mm.floor_x = nx; mm.floor_y = ny }
      } else if (t === 'area') {
        const aa = areas.value.find(z => z.id === parseInt(id))
        if (aa) { aa.x_pos = nx; aa.y_pos = ny }
      }
    })
    return
  }

  // 区域 resize
  if (dragMode.value && dragMode.value.startsWith('resize-') && dragInfo.value) {
    const a = dragInfo.value.area
    const h = resizeHandle.value
    let { origX, origY, origW, origH } = dragInfo.value
    let newX = origX, newY = origY, newW = origW, newH = origH
    const dx = pos.x - dragInfo.value.startX
    const dy = pos.y - dragInfo.value.startY
    if (h.includes('l')) {
      newX = origX + dx
      newW = origW - dx
    }
    if (h.includes('r')) {
      newW = origW + dx
    }
    if (h.includes('t')) {
      newY = origY + dy
      newH = origH - dy
    }
    if (h.includes('b')) {
      newH = origH + dy
    }
    // 最小尺寸 2%
    const MIN = 2
    if (newW < MIN) {
      if (h.includes('l')) newX = origX + origW - MIN
      newW = MIN
    }
    if (newH < MIN) {
      if (h.includes('t')) newY = origY + origH - MIN
      newH = MIN
    }
    // 边界限制 0~100
    newX = Math.max(0, Math.min(100 - newW, newX))
    newY = Math.max(0, Math.min(100 - newH, newY))
    a.x_pos = newX
    a.y_pos = newY
    a.width = newW
    a.height = newH
    return
  }

  // 单选拖拽
  if (dragInfo.value) {
    const newX = pos.x - dragInfo.value.offsetX
    const newY = pos.y - dragInfo.value.offsetY
    const clampedX = Math.max(0, Math.min(100, newX))
    const clampedY = Math.max(0, Math.min(100, newY))
    if (dragInfo.value.machine) {
      dragInfo.value.machine.floor_x = clampedX
      dragInfo.value.machine.floor_y = clampedY
    } else if (dragInfo.value.area) {
      dragInfo.value.area.x_pos = clampedX
      dragInfo.value.area.y_pos = clampedY
    }
  }
}

// document 级别的鼠标松开处理
function docMouseUp(e) {
  document.removeEventListener('mousemove', docMouseMove)
  document.removeEventListener('mouseup', docMouseUp)

  if (!editMode.value) {
    dragMode.value = null
    boxSelect.value = null
    multiMoveStart.value = null
    resizeHandle.value = null
    dragInfo.value = null
    return
  }

  // 画区域完成
  if (drawingArea.value && editTool.value === 'area') {
    const d = drawingArea.value
    const w = d.w < 3 ? 8 : d.w
    const h = d.h < 3 ? 8 : d.h
    const name = newArea.value.name || `${newArea.value.area_type}_${Date.now().toString().slice(-4)}`
    handleAddArea({
      name,
      area_type: newArea.value.area_type,
      x_pos: d.x,
      y_pos: d.y,
      width: w,
      height: h,
      color: newArea.value.color || areaTypeColors[newArea.value.area_type] || '#1e3a5f',
    })
    newArea.value.name = ''
    drawingArea.value = null
    dragMode.value = null
    return
  }

  // 框选完成 → 计算命中并加入多选
  if (dragMode.value === 'box-select' && boxSelect.value) {
    const b = boxSelect.value
    // 只有拖拽距离足够才算框选，否则视为单击空白（已清空多选）
    if (Math.abs(b.x - b.startX) > 1 || Math.abs(b.y - b.startY) > 1) {
      computeBoxSelection(b)
    }
    boxSelect.value = null
    dragMode.value = null
    return
  }

  // 多选批量移动完成 → 保存所有选中项位置
  if (dragMode.value === 'multi-move' && multiMoveStart.value) {
    multiSelection.value.forEach((key) => {
      const [t, id] = key.split(':')
      if (t === 'machine') {
        const mm = machines.value.find(z => z.id === id)
        if (mm) {
          api.updateMachinePosition(props.floorId, mm.id, { x: mm.floor_x, y: mm.floor_y })
        }
      } else if (t === 'area') {
        const aa = areas.value.find(z => z.id === parseInt(id))
        if (aa) {
          api.updateFloorArea(props.floorId, aa.id, {
            x_pos: aa.x_pos, y_pos: aa.y_pos, width: aa.width, height: aa.height,
          })
        }
      }
    })
    multiMoveStart.value = null
    dragMode.value = null
    return
  }

  // resize 完成 → 保存区域尺寸
  if (dragMode.value && dragMode.value.startsWith('resize-') && dragInfo.value) {
    const a = dragInfo.value.area
    api.updateFloorArea(props.floorId, a.id, {
      x_pos: a.x_pos, y_pos: a.y_pos, width: a.width, height: a.height,
    })
    resizeHandle.value = null
    dragInfo.value = null
    dragMode.value = null
    return
  }

  // 单选拖拽完成
  if (dragInfo.value) {
    if (dragInfo.value.machine) {
      api.updateMachinePosition(props.floorId, dragInfo.value.machine.id, {
        x: dragInfo.value.machine.floor_x,
        y: dragInfo.value.machine.floor_y,
      })
    } else if (dragInfo.value.area) {
      // 保存区域位置 — 用更新接口
      api.updateFloorArea(props.floorId, dragInfo.value.area.id, {
        x_pos: dragInfo.value.area.x_pos,
        y_pos: dragInfo.value.area.y_pos,
        width: dragInfo.value.area.width,
        height: dragInfo.value.area.height,
      })
    }
    dragInfo.value = null
  }
  dragMode.value = null
}

function handleAddMachine(pos) {
  if (!newMachine.value.id) {
    showToast('请先输入机台ID', 'error')
    return
  }
  if (!newMachine.value.model) {
    showToast('请选择模型', 'error')
    return
  }
  api.addFloorMachine(props.floorId, {
    id: newMachine.value.id,
    name: newMachine.value.name || newMachine.value.id,
    model: newMachine.value.model,
    process_type: newMachine.value.process_type,
    line: newMachine.value.line,
    floor_x: pos.x,
    floor_y: pos.y,
  }).then(() => {
    loadFloorData()
    newMachine.value.id = ''
    newMachine.value.name = ''
    showToast('机台添加成功', 'success')
  }).catch(err => {
    console.error('[FloorPlan] 机台添加失败:', err)
    showToast('添加失败: ' + errMsg(err, err.message || ''), 'error')
  })
}

function handleAddArea(areaData) {
  console.log('[FloorPlan] 创建区域:', areaData)
  api.addFloorArea(props.floorId, areaData).then((res) => {
    console.log('[FloorPlan] 区域创建成功:', res)
    loadFloorData()
    showToast('区域创建成功', 'success')
  }).catch(err => {
    console.error('[FloorPlan] 区域创建失败:', err)
    showToast('添加区域失败: ' + errMsg(err, err.message || ''), 'error')
  })
}

// Toast 提示
const toast = ref({ show: false, msg: '', type: 'info' })
let toastTimer = null
function showToast(msg, type = 'info') {
  toast.value = { show: true, msg, type }
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toast.value.show = false
  }, 2500)
}
const showDeleteConfirm = ref(false)
const pendingDelete = ref({ type: '', item: null })

function confirmDeleteArea(area) {
  pendingDelete.value = { type: 'area', item: area }
  showDeleteConfirm.value = true
}

function confirmDeleteMachine(m) {
  pendingDelete.value = { type: 'machine', item: m }
  showDeleteConfirm.value = true
}

// 选中机台变化时同步名称草稿
watch(selectedMachine, (m) => {
  if (m) {
    editMachineName.value = m.name || m.id || ''
  }
}, { immediate: true })

// 保存机台名称到后端
async function saveMachineName() {
  const m = selectedMachine.value
  if (!m) return
  const newName = (editMachineName.value || '').trim()
  if (!newName) {
    showToast('名称不能为空', 'error')
    return
  }
  if (newName === m.name) {
    showToast('无变更', 'info')
    return
  }
  savingMachine.value = true
  try {
    await api.updateFloorMachine(props.floorId, m.id, { name: newName })
    m.name = newName
    editMachineName.value = newName
    showToast('机台名称已保存', 'success')
  } catch (err) {
    console.error('[FloorPlan] 机台改名失败:', err)
    showToast('改名失败: ' + errMsg(err, err.message || ''), 'error')
    editMachineName.value = m.name || m.id || ''
  } finally {
    savingMachine.value = false
  }
}

function doDelete() {
  if (!pendingDelete.value.item) return
  const { type, item } = pendingDelete.value
  if (type === 'area') {
    api.deleteFloorArea(props.floorId, item.id).then(() => {
      loadFloorData()
    })
  } else if (type === 'machine') {
    api.deleteFloorMachine(props.floorId, item.id).then(() => {
      loadFloorData()
      selectedMachine.value = null
    })
  } else if (type === 'track') {
    api.deleteTrack(props.floorId, item.id).then(() => {
      loadFloorData()
    })
  } else if (type === 'vehicle') {
    api.deleteVehicle(props.floorId, item.id).then(() => {
      loadFloorData()
    })
  }
  showDeleteConfirm.value = false
  pendingDelete.value = { type: '', item: null }
}

function cancelDelete() {
  showDeleteConfirm.value = false
  pendingDelete.value = { type: '', item: null }
}

// ========== 轨迹操作 ==========

function saveTrack() {
  if (drawingTrack.value.length < 2) {
    showToast('至少需要2个轨迹点', 'error')
    return
  }
  const name = newTrack.value.name || `轨迹_${Date.now().toString().slice(-4)}`
  api.addTrack(props.floorId, {
    name,
    points: drawingTrack.value,
    color: newTrack.value.color,
    speed: newTrack.value.speed,
  }).then(() => {
    loadFloorData()
    drawingTrack.value = []
    newTrack.value.name = ''
    showToast('轨迹保存成功', 'success')
  }).catch(err => {
    showToast('轨迹保存失败: ' + errMsg(err, err.message || ''), 'error')
  })
}

function undoTrackPoint() {
  drawingTrack.value.pop()
}

function clearTrackDrawing() {
  drawingTrack.value = []
}

function confirmDeleteTrack(track) {
  pendingDelete.value = { type: 'track', item: track }
  showDeleteConfirm.value = true
}

// ========== 天车操作 ==========

function handleAddVehicle(pos) {
  if (!newVehicle.value.id) {
    showToast('请先输入天车ID', 'error')
    return
  }
  api.addVehicle(props.floorId, {
    id: newVehicle.value.id,
    name: newVehicle.value.name || newVehicle.value.id,
    track_id: newVehicle.value.track_id,
    speed: 1.0,
  }).then(() => {
    loadFloorData()
    newVehicle.value.id = ''
    newVehicle.value.name = ''
    showToast('天车添加成功', 'success')
  }).catch(err => {
    showToast('天车添加失败: ' + errMsg(err, err.message || ''), 'error')
  })
}

// 直接添加天车（不需要点击地图）
function handleAddVehicleDirect() {
  // 智能生成下一个可用的ID
  const existingIds = vehicles.value.map(v => v.id)
  let autoId = newVehicle.value.id
  if (!autoId) {
    let maxNum = 0
    existingIds.forEach(id => {
      const match = id.match(/OHT-(\d+)/)
      if (match) maxNum = Math.max(maxNum, parseInt(match[1]))
    })
    autoId = `OHT-${(maxNum + 1).toString().padStart(2, '0')}`
  }
  
  // 检查ID是否已存在
  if (existingIds.includes(autoId)) {
    showToast(`天车ID "${autoId}" 已存在，请更换`, 'error')
    return
  }
  if (!newVehicle.value.track_id) {
    showToast('请选择要绑定的轨迹', 'error')
    return
  }
  api.addVehicle(props.floorId, {
    id: autoId,
    name: newVehicle.value.name || autoId,
    track_id: newVehicle.value.track_id,
    speed: 1.0,
  }).then(() => {
    loadFloorData()
    newVehicle.value.id = ''
    newVehicle.value.name = ''
    showToast(`天车 "${autoId}" 添加成功，绑定轨迹`, 'success')
  }).catch(err => {
    showToast('天车添加失败: ' + errMsg(err, err.message || ''), 'error')
  })
}

function confirmDeleteVehicle(v) {
  pendingDelete.value = { type: 'vehicle', item: v }
  showDeleteConfirm.value = true
}

let vehicleAnimFrame = null
const vehicleProgress = reactive({})

function updateVehiclePositions() {
  const dt = 16 / 1000
  vehicles.value.forEach(v => {
    if (v.track_id) {
      if (vehicleProgress[v.id] === undefined) {
        vehicleProgress[v.id] = v.progress || 0
      }
      vehicleProgress[v.id] += dt * (v.speed || 1) * 0.05
      if (vehicleProgress[v.id] >= 1) vehicleProgress[v.id] = 0
    }
  })
  vehicleAnimFrame = requestAnimationFrame(updateVehiclePositions)
}

// 天车在轨迹上的实时位置（基于progress计算）
function vehiclePos(v) {
  const track = tracks.value.find(t => t.id == v.track_id)
  if (!track || !track.points || track.points.length === 0) return null
  const pts = track.points
  const progress = vehicleProgress[v.id] !== undefined ? vehicleProgress[v.id] : (v.progress || 0)
  const totalSegs = pts.length - 1
  if (totalSegs < 1) return { x: pts[0][0], y: pts[0][1] }
  const segProgress = progress * totalSegs
  const segIdx = Math.floor(segProgress)
  const segFrac = segProgress - segIdx
  const clampedIdx = Math.min(segIdx, totalSegs - 1)
  return {
    x: pts[clampedIdx][0] + (pts[clampedIdx + 1][0] - pts[clampedIdx][0]) * segFrac,
    y: pts[clampedIdx][1] + (pts[clampedIdx + 1][1] - pts[clampedIdx][1]) * segFrac,
  }
}

// 轨迹SVG路径
function trackPath(points) {
  if (!points || points.length === 0) return ''
  return points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p[0]} ${p[1]}`).join(' ')
}

function trackDrawingPath() {
  return trackPath(drawingTrack.value)
}

function savePosition() {
  if (selectedMachine.value && editMode.value) {
    api.updateMachinePosition(
      props.floorId,
      selectedMachine.value.id,
      { x: mousePos.value.x, y: mousePos.value.y }
    ).then(() => {
      selectedMachine.value.floor_x = mousePos.value.x
      selectedMachine.value.floor_y = mousePos.value.y
    })
  }
}

function exportFloorPlan() {
  api.exportFloorPlan(props.floorId).then(data => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `floor-${props.floorId}-plan.json`
    a.click()
    URL.revokeObjectURL(url)
  })
}

function importFloorPlan(e) {
  const file = e.target.files[0]
  if (!file) return
  
  const reader = new FileReader()
  reader.onload = (ev) => {
    try {
      const data = JSON.parse(ev.target.result)
      api.importFloorPlan({ floor_id: props.floorId, ...data }).then(() => {
        loadFloorData()
        showToast('导入成功', 'success')
      })
    } catch (err) {
      showToast('导入失败：JSON格式错误', 'error')
    }
  }
  reader.readAsText(file)
}

const drawingPreview = computed(() => {
  if (!drawingArea.value || drawingArea.value.w < 1) return null
  return {
    left: drawingArea.value.x + '%',
    top: drawingArea.value.y + '%',
    width: drawingArea.value.w + '%',
    height: drawingArea.value.h + '%',
  }
})

// 框选矩形预览
const boxSelectPreview = computed(() => {
  if (!boxSelect.value) return null
  const b = boxSelect.value
  const x = Math.min(b.startX, b.x)
  const y = Math.min(b.startY, b.y)
  const w = Math.abs(b.x - b.startX)
  const h = Math.abs(b.y - b.startY)
  if (w < 0.5 && h < 0.5) return null
  return {
    left: x + '%',
    top: y + '%',
    width: w + '%',
    height: h + '%',
  }
})

// 多选数量
const multiSelectCount = computed(() => multiSelection.value.size)

// 批量删除所有多选项
async function batchDeleteMultiSelection() {
  if (multiSelection.value.size === 0) return
  if (!confirm(`确认删除选中的 ${multiSelection.value.size} 个对象（机台仅从平面图移除）？`)) return
  const keys = Array.from(multiSelection.value)
  for (const key of keys) {
    const [t, id] = key.split(':')
    try {
      if (t === 'machine') {
        await api.deleteFloorMachine(props.floorId, id)
      } else if (t === 'area') {
        await api.deleteFloorArea(props.floorId, parseInt(id))
      }
    } catch (err) {
      console.error('[FloorPlan] 批量删除单项失败:', key, err)
    }
  }
  clearMultiSelection()
  selectedMachine.value = null
  selectedArea.value = null
  showToast('批量删除完成', 'success')
  await loadFloorData()
}

watch(() => props.floorId, () => {
  loadFloorData()
})

watch(editMode, (val) => {
  if (!val) {
    editTool.value = 'select'
    drawingArea.value = null
    dragInfo.value = null
    dragMode.value = null
    boxSelect.value = null
    multiMoveStart.value = null
    resizeHandle.value = null
    clearMultiSelection()
  }
})

// 权限被收回时强制退出编辑模式
watch(() => authStore.hasPermission('floor_edit'), (allowed) => {
  if (!allowed && editMode.value) {
    editMode.value = false
  }
}, { immediate: true })

onMounted(() => {
  loadFloorData().then(() => {
    updateVehiclePositions()
  })
  loadModelConfigs()
})

onUnmounted(() => {
  document.removeEventListener('mousemove', docMouseMove)
  document.removeEventListener('mouseup', docMouseUp)
  if (vehicleAnimFrame) cancelAnimationFrame(vehicleAnimFrame)
})
</script>

<template>
  <div class="floor-plan">
    <div class="fp-header">
      <div class="fp-title">
        <span class="fp-icon">🏢</span>
        {{ floorData?.name || '楼层平面图' }}
        <span class="fp-desc">{{ floorData?.description }}</span>
      </div>
      <div class="fp-actions">
        <div class="zoom-controls">
          <button class="action-btn zoom-btn" @click="zoomOut" title="缩小">−</button>
          <span class="zoom-level">{{ Math.round(zoom * 100) }}%</span>
          <button class="action-btn zoom-btn" @click="zoomIn" title="放大">+</button>
          <button class="action-btn" @click="zoomReset" title="重置缩放">1:1</button>
        </div>
        <label v-if="authStore.hasPermission('floor_edit')" class="action-btn import-btn">
          📥 导入
          <input type="file" accept=".json" @change="importFloorPlan" />
        </label>
        <button class="action-btn" @click="exportFloorPlan">📤 导出</button>
        <button
          v-if="authStore.hasPermission('floor_edit')"
          class="action-btn"
          :class="{ active: editMode }"
          @click="editMode = !editMode"
        >
          ✏️ {{ editMode ? '完成编辑' : '编辑模式' }}
        </button>
      </div>
    </div>
    
    <!-- 编辑工具栏 -->
    <div v-if="editMode" class="edit-toolbar">
      <div class="tool-group">
        <span class="tool-label">工具:</span>
        <button class="tool-btn" :class="{ active: editTool === 'select' }" @click="editTool = 'select'">
          🖱 选择/拖拽
        </button>
        <button class="tool-btn" :class="{ active: editTool === 'machine' }" @click="editTool = 'machine'">
          ➕ 添加机台
        </button>
        <button class="tool-btn" :class="{ active: editTool === 'area' }" @click="editTool = 'area'">
          □ 画区域
        </button>
        <button class="tool-btn" :class="{ active: editTool === 'track' }" @click="editTool = 'track'">
          🛤 画轨迹
        </button>
        <button class="tool-btn" :class="{ active: editTool === 'vehicle' }" @click="editTool = 'vehicle'">
          🚁 添加天车
        </button>
      </div>

      <!-- 多选信息条（D-#2 批量复制 + D-#3 图层操作） -->
      <div v-if="multiSelectCount > 0" class="multi-info">
        <span class="mi-count">已选 {{ multiSelectCount }} 项</span>
        <span class="mi-hint">拖拽任一选中项批量移动 | Ctrl/Shift 单击增减</span>
        <button class="tool-btn" :disabled="batchCloning" @click="batchCloneSelected({x:3,y:3})">⎘ 批量复制 (+3,+3)</button>
        <button class="tool-btn" :disabled="batchCloning" @click="batchCloneSelected({x:6,y:6})">⎘ 复制 (+6,+6)</button>
        <button class="tool-btn" :disabled="reordering" @click="reorderSelected('bottom')">⬇ 置底</button>
        <button class="tool-btn" :disabled="reordering" @click="reorderSelected('down')">↧ 下移</button>
        <button class="tool-btn" :disabled="reordering" @click="reorderSelected('up')">↥ 上移</button>
        <button class="tool-btn" :disabled="reordering" @click="reorderSelected('top')">⬆ 置顶</button>
        <button class="tool-btn" @click="clearMultiSelection">取消选择</button>
        <button class="tool-btn danger" @click="batchDeleteMultiSelection">🗑 批量删除</button>
      </div>
      
      <div v-if="editTool === 'machine'" class="tool-form">
        <input v-model="newMachine.id" placeholder="机台ID" class="tool-input" />
        <input v-model="newMachine.name" placeholder="名称(可选)" class="tool-input" />
        <select v-model="newMachine.model" class="tool-input">
          <option value="">-- 选择模型 --</option>
          <option v-for="m in modelConfigs" :key="m.model_id" :value="m.model_id">{{ m.model_name }} ({{ m.model_id }})</option>
        </select>
        <select v-model="newMachine.process_type" class="tool-input">
          <option v-for="t in processTypes" :key="t" :value="t">{{ t }}</option>
        </select>
        <select v-model="newMachine.line" class="tool-input">
          <option :value="1">Line 1</option>
          <option :value="2">Line 2</option>
        </select>
        <span class="tool-hint">点击地图放置机台</span>
      </div>
      
      <div v-if="editTool === 'area'" class="tool-form">
        <input v-model="newArea.name" placeholder="区域名称(可选)" class="tool-input" />
        <select v-model="newArea.area_type" class="tool-input">
          <option value="equipment">设备区</option>
          <option value="walkway">过道(T1/T2)</option>
          <option value="stk">STK传输区</option>
          <option value="pump">PUMP区</option>
          <option value="elevator">电梯</option>
          <option value="exit">逃生门</option>
        </select>
        <input v-model="newArea.color" type="color" class="tool-input-color" :title="newArea.color" />
        <button class="tool-btn primary" @click="quickAddArea">+ 直接创建</button>
        <span class="tool-hint">或 在地图上拖拽画框</span>
      </div>
      
      <!-- 画轨迹工具表单 -->
      <div v-if="editTool === 'track'" class="tool-form">
        <input v-model="newTrack.name" placeholder="轨迹名称(可选)" class="tool-input" />
        <input v-model="newTrack.color" type="color" class="tool-input-color" />
        <span class="tool-hint">点击地图添加轨迹点 ({{ drawingTrack.length }}点)</span>
        <button class="tool-btn" @click="undoTrackPoint" :disabled="drawingTrack.length === 0">↩ 撤销</button>
        <button class="tool-btn" @click="clearTrackDrawing" :disabled="drawingTrack.length === 0">清空</button>
        <button class="tool-btn primary" @click="saveTrack" :disabled="drawingTrack.length < 2">💾 保存轨迹</button>
      </div>
      
      <!-- 添加天车表单 -->
      <div v-if="editTool === 'vehicle'" class="tool-form">
        <input v-model="newVehicle.id" placeholder="天车ID(如OHT-01)" class="tool-input" />
        <input v-model="newVehicle.name" placeholder="名称(可选)" class="tool-input" />
        <select v-model="newVehicle.track_id" class="tool-input">
          <option :value="null">不绑定轨迹</option>
          <option v-for="t in tracks" :key="t.id" :value="t.id">{{ t.name }} (ID:{{ t.id }})</option>
        </select>
        <span v-if="tracks.length === 0" class="tool-hint" style="color:#f59e0b">请先画轨迹！</span>
        <button class="tool-btn primary" @click="handleAddVehicleDirect">+ 添加天车</button>
      </div>
      
      <div v-if="editTool === 'select' && selectedMachine" class="tool-info area-edit-info">
        <span class="ae-label">机台:</span>
        <span class="ae-mid">{{ selectedMachine.id }}</span>
        <input
          v-model="editMachineName"
          placeholder="机台名称"
          class="tool-input ae-name"
          @keyup.enter="saveMachineName"
        />
        <button
          class="tool-btn primary"
          :disabled="savingMachine"
          @click="saveMachineName"
        >
          {{ savingMachine ? '保存中…' : '💾 改名' }}
        </button>
        <button class="tool-btn" :disabled="batchCloning" @click="(()=>{ addToMultiSelection('machine', selectedMachine.id); batchCloneSelected({x:3,y:3}); })">
          ⎘ 复制
        </button>
        <button class="tool-btn" :disabled="reordering" @click="reorderSelected('bottom')">⬇置底</button>
        <button class="tool-btn" :disabled="reordering" @click="reorderSelected('down')">↧</button>
        <button class="tool-btn" :disabled="reordering" @click="reorderSelected('up')">↥</button>
        <button class="tool-btn" :disabled="reordering" @click="reorderSelected('top')">⬆置顶</button>
        <button class="tool-btn danger" @click="confirmDeleteMachine(selectedMachine)">🗑 删除</button>
      </div>
      
      <!-- 选中区域编辑信息（D-#1：手动输入长宽/位置 + D-#3：图层操作） -->
      <div v-if="editTool === 'select' && selectedArea" class="tool-info area-edit-info area-edit-info-d">
        <div class="ae-row">
          <span class="ae-label">选中区域:</span>
          <input
            v-model="editAreaName"
            placeholder="区域名称"
            class="tool-input ae-name"
            @keyup.enter="saveAreaProps"
          />
          <input
            v-model="editAreaColor"
            type="color"
            class="tool-input-color"
            :title="editAreaColor"
          />
          <button class="tool-btn primary" :disabled="savingArea" @click="saveAreaProps">
            {{ savingArea ? '保存中…' : '💾 保存' }}
          </button>
          <button class="tool-btn danger" @click="confirmDeleteArea(selectedArea)">🗑 删除</button>
        </div>
        <div class="ae-row ae-row-grid">
          <label class="ae-sub">X (%)</label>
          <input v-model.number="editAreaX" type="number" step="0.1" min="0" max="100" class="tool-input ae-wh" />
          <label class="ae-sub">Y (%)</label>
          <input v-model.number="editAreaY" type="number" step="0.1" min="0" max="100" class="tool-input ae-wh" />
          <label class="ae-sub">宽 (%)</label>
          <input v-model.number="editAreaW" type="number" step="0.1" min="0.5" max="100" class="tool-input ae-wh" />
          <label class="ae-sub">高 (%)</label>
          <input v-model.number="editAreaH" type="number" step="0.1" min="0.5" max="100" class="tool-input ae-wh" />
          <label class="ae-sub">宽 (m)</label>
          <input :value="editAreaWM" type="number" step="0.1" class="tool-input ae-wh"
            @change="(e)=>{ const w=+e.target.value||0; applyAreaMeters(w, editAreaHM) }" />
          <label class="ae-sub">高 (m)</label>
          <input :value="editAreaHM" type="number" step="0.1" class="tool-input ae-wh"
            @change="(e)=>{ const h=+e.target.value||0; applyAreaMeters(editAreaWM, h) }" />
        </div>
        <div class="ae-row ae-layer-row">
          <button class="tool-btn" :disabled="reordering" @click="reorderSelected('bottom')">⬇ 置底</button>
          <button class="tool-btn" :disabled="reordering" @click="reorderSelected('down')">↧ 下移</button>
          <button class="tool-btn" :disabled="reordering" @click="reorderSelected('up')">↥ 上移</button>
          <button class="tool-btn" :disabled="reordering" @click="reorderSelected('top')">⬆ 置顶</button>
        </div>
      </div>
      
      <!-- 天车列表（编辑模式下可见，方便删除） -->
      <div v-if="editMode && vehicles.length > 0" class="vehicle-list">
        <div class="vl-title">🚁 天车列表 ({{ vehicles.length }})</div>
        <div class="vl-items">
          <div v-for="v in vehicles" :key="v.id" class="vl-item" @mouseenter="hoverVehicle = v.id" @mouseleave="hoverVehicle = null">
            <span class="vl-name">{{ v.name || v.id }}</span>
            <span class="vl-track">
              {{ tracks.find(t => t.id == v.track_id)?.name || '无轨迹' }}
            </span>
            <button class="vl-del" @click.stop="confirmDeleteVehicle(v)" title="删除">✕</button>
          </div>
        </div>
      </div>
    </div>
    
    <div
      class="fp-canvas"
      @mousedown="handleMouseDown"
      @wheel="onWheel"
      :class="{ 'cursor-cross': editTool === 'machine' || editTool === 'area' || editTool === 'track' || editTool === 'vehicle', 'cursor-grab': editTool === 'select' && editMode }"
    >
     <div ref="canvasInnerRef" class="fp-canvas-inner" :style="{ width: (zoom * 100) + '%', height: (zoom * 100) + '%' }">
      <div class="canvas-grid">
        <div v-for="i in 20" :key="'h'+i" class="grid-line horizontal" :style="{ top: (i * 5) + '%' }"></div>
        <div v-for="i in 20" :key="'v'+i" class="grid-line vertical" :style="{ left: (i * 5) + '%' }"></div>
      </div>
      
      <!-- 区域 -->
      <div
        v-for="area in areas"
        :key="area.id"
        class="floor-area"
        :data-aid="area.id"
        :class="{
          'area-editable': editMode,
          'area-selected': selectedArea?.id === area.id,
          'area-multi': isMultiSelected('area', area.id),
        }"
        :style="{
          left: area.x_pos + '%',
          top: area.y_pos + '%',
          width: area.width + '%',
          height: area.height + '%',
          background: area.color + '60',
          borderColor: area.color,
        }"
      >
        <div class="area-name">
          <span class="area-icon">{{ areaTypeIcons[area.area_type] || '📦' }}</span>
          {{ area.name }}
        </div>
        <div v-if="editMode" class="area-delete" @click.stop="confirmDeleteArea(area)">✕</div>
        <!-- resize 手柄：仅 select 工具 + 区域被选中时显示 -->
        <template v-if="editMode && editTool === 'select' && (selectedArea?.id === area.id || isMultiSelected('area', area.id))">
          <div class="resize-handle handle-tl" :data-aid="area.id" data-handle="tl"></div>
          <div class="resize-handle handle-tr" :data-aid="area.id" data-handle="tr"></div>
          <div class="resize-handle handle-bl" :data-aid="area.id" data-handle="bl"></div>
          <div class="resize-handle handle-br" :data-aid="area.id" data-handle="br"></div>
          <div class="resize-handle handle-t" :data-aid="area.id" data-handle="t"></div>
          <div class="resize-handle handle-r" :data-aid="area.id" data-handle="r"></div>
          <div class="resize-handle handle-b" :data-aid="area.id" data-handle="b"></div>
          <div class="resize-handle handle-l" :data-aid="area.id" data-handle="l"></div>
        </template>
      </div>
      
      <!-- 画框预览 -->
      <div v-if="drawingPreview" class="drawing-preview" :style="drawingPreview"></div>

      <!-- 框选矩形预览 -->
      <div v-if="boxSelectPreview" class="box-select-preview" :style="boxSelectPreview"></div>
      
      <!-- 机台标记 -->
      <div
        v-for="m in machines"
        :key="m.id"
        class="machine-marker"
        :data-mid="m.id"
        :class="{
          selected: selectedMachine?.id === m.id,
          'edit-movable': editMode,
          'machine-stk': m.process_type === 'STK',
          'machine-multi': isMultiSelected('machine', m.id),
        }"
        :style="{
          left: m.floor_x + '%',
          top: m.floor_y + '%',
        }"
        :title="m.use_external_url ? `外链：${m.external_url}` : (canEditModel() ? '单击进入，双击编辑外链' : '')"
        @click="onMachineClick(m, $event)"
        @dblclick="onMachineDblClick(m, $event)"
      >
        <span v-if="m.use_external_url" class="ext-link-badge" :title="`跳转网站：${m.external_url}`">↗</span>
        <div 
          v-if="m.process_type === 'STK'"
          class="marker-stk"
          :style="{ background: stateColors[m.state] || stateColors.idle }"
        ></div>
        <div 
          v-else
          class="marker-dot" 
          :style="{ background: stateColors[m.state] || stateColors.idle }"
        ></div>
        <div class="marker-id">{{ m.id }}</div>
        <div v-if="m.process_type !== 'ETCH' && m.process_type !== 'STK'" class="marker-type">{{ m.process_type }}</div>
        <div 
          v-if="m.alarm_count > 0" 
          class="marker-alarm"
        >
          {{ m.alarm_count }}
        </div>
      </div>
      
      <!-- 轨迹SVG层 -->
      <svg class="track-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
        <!-- 已保存的轨迹 -->
        <path 
          v-for="t in tracks" 
          :key="'track-' + t.id"
          :d="trackPath(t.points)"
          :stroke="t.color"
          stroke-width="0.8"
          fill="none"
          stroke-dasharray="2,1"
          vector-effect="non-scaling-stroke"
          :class="{ 'track-selected': editMode && selectedArea?.id === t.id }"
        />
        <!-- 轨迹端点 -->
        <template v-for="t in tracks" :key="'tp-' + t.id">
          <circle 
            v-for="(p, i) in t.points" 
            :key="'tp-' + t.id + '-' + i"
            :cx="p[0]" :cy="p[1]" r="0.6"
            :fill="t.color"
            vector-effect="non-scaling-stroke"
          />
        </template>
        <!-- 正在绘制的轨迹 -->
        <path 
          v-if="drawingTrack.length > 0"
          :d="trackDrawingPath()"
          :stroke="newTrack.color"
          stroke-width="1"
          fill="none"
          stroke-dasharray="1.5,1"
          vector-effect="non-scaling-stroke"
        />
        <!-- 绘制中的点 -->
        <circle 
          v-for="(p, i) in drawingTrack" 
          :key="'dp-' + i"
          :cx="p[0]" :cy="p[1]" r="0.8"
          :fill="newTrack.color"
          :stroke="'#fff'"
          stroke-width="0.3"
          vector-effect="non-scaling-stroke"
        />
      </svg>
      
      <!-- 轨迹标签和删除按钮 -->
      <div 
        v-for="t in tracks" 
        :key="'tl-' + t.id"
        class="track-label"
        :style="{
          left: (t.points && t.points[0] ? t.points[0][0] : 0) + '%',
          top: (t.points && t.points[0] ? t.points[0][1] : 0) + '%',
        }"
      >
        <span class="track-name" :style="{ color: t.color }">🛤 {{ t.name }}</span>
        <span v-if="editMode" class="track-del" @click.stop="confirmDeleteTrack(t)">✕</span>
      </div>
      
      <!-- 天车标记 -->
      <div 
        v-for="v in vehicles" 
        :key="'v-' + v.id"
        class="vehicle-marker"
        :class="{ 'vehicle-hover': hoverVehicle === v.id }"
        :style="vehiclePos(v) ? { left: vehiclePos(v).x + '%', top: vehiclePos(v).y + '%' } : { display: 'none' }"
      >
        <div class="vehicle-icon" :class="{ moving: v.state === 'moving' }">🚁</div>
        <div class="vehicle-id">{{ v.id }}</div>
        <div v-if="v.lot_id" class="vehicle-lot">{{ v.lot_id }}</div>
        <div v-if="editMode" class="vehicle-del" @click.stop="confirmDeleteVehicle(v)">✕</div>
      </div>
      
      <!-- 编辑提示 -->
      <div v-if="editMode" class="edit-hint">
        <span v-if="editTool === 'select'">
          🖱 拖拽机台/区域调整位置 | 空白处拖拽框选 | 选中区域拖角调整大小 | Ctrl/Shift 单击多选
        </span>
        <span v-if="editTool === 'machine'">
          ➕ 点击地图放置机台: X={{ mousePos.x.toFixed(1) }} Y={{ mousePos.y.toFixed(1) }}
        </span>
        <span v-if="editTool === 'area'">
          □ 拖拽画框创建区域: X={{ mousePos.x.toFixed(1) }} Y={{ mousePos.y.toFixed(1) }}
        </span>
        <span v-if="editTool === 'track'">
          🛤 点击添加轨迹点: {{ drawingTrack.length }}点 | X={{ mousePos.x.toFixed(1) }} Y={{ mousePos.y.toFixed(1) }}
        </span>
        <span v-if="editTool === 'vehicle'">
          🚁 点击放置天车: X={{ mousePos.x.toFixed(1) }} Y={{ mousePos.y.toFixed(1) }}
        </span>
      </div>
    </div>

    <!-- 双击机台：编辑外链跳转配置（仅管理员） -->
    <div v-if="showExternalLinkModal" class="ext-link-overlay" @click.self="showExternalLinkModal = false">
      <div class="ext-link-modal">
        <div class="ext-link-modal-header">
          <h3>编辑机台跳转 — {{ editingLinkMachine?.id }}</h3>
          <button class="ext-link-close" @click="showExternalLinkModal = false">×</button>
        </div>
        <div class="ext-link-modal-body">
          <div class="ext-link-row">
            <label class="ext-link-radio">
              <input type="radio" :value="0" v-model.number="externalLinkForm.use_external_url" />
              <span>使用原路线（进入机台详情页）</span>
            </label>
            <label class="ext-link-radio">
              <input type="radio" :value="1" v-model.number="externalLinkForm.use_external_url" />
              <span>使用跳转网站（iframe 嵌入）</span>
            </label>
          </div>
          <div class="ext-link-field">
            <label>跳转网站 URL</label>
            <input
              type="text"
              v-model.trim="externalLinkForm.external_url"
              placeholder="https://your-site.com/path"
              :disabled="!externalLinkForm.use_external_url"
              @keyup.enter="saveExternalLink"
            />
            <div class="ext-link-hint">⚠️ 目标站点需允许被 iframe 嵌入（X-Frame-Options / CSP frame-ancestors）</div>
          </div>
        </div>
        <div class="ext-link-modal-actions">
          <button class="ext-link-save" :disabled="savingExternalLink" @click="saveExternalLink">
            {{ savingExternalLink ? '保存中…' : '保存' }}
          </button>
          <button class="ext-link-cancel" @click="showExternalLinkModal = false">取消</button>
        </div>
      </div>
    </div>

    <!-- Toast 提示 -->
    <div v-if="toast.show" class="toast" :class="toast.type">
      {{ toast.msg }}
    </div>
    
    <!-- 删除确认弹窗 -->
    <div v-if="showDeleteConfirm" class="delete-modal-mask" @click="cancelDelete">
      <div class="delete-modal" @click.stop>
        <div class="modal-title">确认删除</div>
        <div class="modal-body">
          <template v-if="pendingDelete.type === 'area'">
            确定要删除区域 <strong>"{{ pendingDelete.item?.name }}"</strong> 吗？
          </template>
          <template v-if="pendingDelete.type === 'machine'">
            确定要从楼层移除机台 <strong>"{{ pendingDelete.item?.id }}"</strong> 吗？
            <div class="modal-tip">仅移除楼层位置，机台数据保留</div>
          </template>
          <template v-if="pendingDelete.type === 'track'">
            确定要删除轨迹 <strong>"{{ pendingDelete.item?.name }}"</strong> 吗？
          </template>
          <template v-if="pendingDelete.type === 'vehicle'">
            确定要删除天车 <strong>"{{ pendingDelete.item?.id }}"</strong> 吗？
          </template>
        </div>
        <div class="modal-actions">
          <button class="modal-btn cancel" @click="cancelDelete">取消</button>
          <button class="modal-btn confirm" @click="doDelete">确认删除</button>
        </div>
      </div>
    </div>
     </div><!-- /.fp-canvas-inner -->

    <div class="fp-legend">
      <div class="legend-title">图例说明</div>
      <div class="legend-items">
        <div class="legend-item">
          <span class="legend-dot" style="background:#10b981"></span> 运行
        </div>
        <div class="legend-item">
          <span class="legend-dot" style="background:#f59e0b"></span> 空闲
        </div>
        <div class="legend-item">
          <span class="legend-dot" style="background:#ef4444"></span> 故障
        </div>
        <div class="legend-item">
          <span class="legend-dot" style="background:#3b82f6"></span> 维护
        </div>
        <div class="legend-item">
          <span class="legend-rect" style="background:#1a4a3a"></span> STK传输
        </div>
        <div class="legend-item">
          <span class="legend-rect" style="background:#3a3a3a"></span> T1/T2过道
        </div>
      </div>
      <div class="legend-info">
        机台: {{ machines.length }} | 区域: {{ areas.length }} | 轨迹: {{ tracks.length }} | 天车: {{ vehicles.length }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.floor-plan {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}

.fp-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: var(--panel-2);
}

.fp-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--accent);
  display: flex;
  align-items: center;
  gap: 8px;
}

.fp-icon { font-size: 18px; }

.fp-desc {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 400;
  margin-left: 8px;
}

.fp-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.zoom-controls {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-right: 4px;
}
.zoom-btn {
  width: 26px;
  height: 26px;
  padding: 0 !important;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 700;
}
.zoom-level {
  font-size: 11px;
  color: var(--text-dim);
  min-width: 36px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.action-btn {
  padding: 5px 10px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-dim);
  border-radius: 6px;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s;
}

.action-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.action-btn.active {
  background: rgba(0, 212, 255, 0.12);
  color: var(--accent);
  border-color: var(--accent);
}

.import-btn {
  position: relative;
  overflow: hidden;
}

.import-btn input {
  position: absolute;
  opacity: 0;
  cursor: pointer;
  width: 100%;
  height: 100%;
  left: 0;
  top: 0;
}

/* 编辑工具栏 */
.edit-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--border);
  background: rgba(0, 212, 255, 0.05);
  flex-wrap: wrap;
}

.tool-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tool-label {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 600;
}

.tool-btn {
  padding: 4px 10px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-dim);
  border-radius: 5px;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s;
}

.tool-btn:hover { border-color: var(--accent); color: var(--accent); }
.tool-btn.active { background: rgba(0,212,255,0.15); color: var(--accent); border-color: var(--accent); }
.tool-btn.primary { background: rgba(0,212,255,0.2); color: var(--accent); border-color: var(--accent); font-weight: 600; }
.tool-btn.primary:hover { background: rgba(0,212,255,0.3); }
.tool-btn.danger { color: var(--red); border-color: var(--red); }
.tool-btn.danger:hover { background: rgba(239,68,68,0.15); }

.tool-form {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.tool-input {
  padding: 4px 8px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  border-radius: 4px;
  font-size: 11px;
  width: 90px;
}

.tool-input:focus {
  outline: none;
  border-color: var(--accent);
}

.tool-hint {
  font-size: 10px;
  color: var(--accent);
  font-style: italic;
}

.tool-info {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--accent);
}

/* 选中区域编辑表单 */
.area-edit-info {
  padding: 6px 8px;
  background: rgba(0, 212, 255, 0.06);
  border: 1px solid rgba(0, 212, 255, 0.25);
  border-radius: 6px;
}

.ae-label {
  font-size: 11px;
  color: var(--accent);
  font-weight: 600;
  white-space: nowrap;
}

.ae-name {
  width: 120px;
}

.ae-mid {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 11px;
  color: #94a3b8;
  white-space: nowrap;
}

/* D 批：区域属性扩展行 */
.area-edit-info-d {
  display: block;
  max-width: 560px;
}
.area-edit-info-d .ae-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  padding: 3px 0;
}
.area-edit-info-d .ae-row + .ae-row {
  border-top: 1px dashed rgba(0, 212, 255, 0.15);
  margin-top: 3px;
}
.area-edit-info-d .ae-row-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px 8px;
  align-items: center;
}
.area-edit-info-d .ae-row-grid .ae-sub,
.area-edit-info-d .ae-row-grid .tool-input {
  width: 100%;
}
.area-edit-info-d .ae-sub {
  font-size: 10px;
  color: #94a3b8;
  text-align: right;
}
.area-edit-info-d .ae-wh {
  font-family: 'Consolas', 'Monaco', monospace;
}
.area-edit-info-d .ae-layer-row {
  justify-content: flex-end;
}

/* 画布 */
.fp-canvas {
  flex: 1;
  position: relative;
  background: #0a1120;
  overflow: auto;
  user-select: none;
}

.fp-canvas-inner {
  position: relative;
  flex-shrink: 0;
  min-width: 100%;
  min-height: 100%;
}

.cursor-cross { cursor: crosshair; }
.cursor-grab { cursor: grab; }

.canvas-grid {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.grid-line {
  position: absolute;
  background: rgba(26, 40, 68, 0.4);
}

.grid-line.horizontal { width: 100%; height: 1px; }
.grid-line.vertical { width: 1px; height: 100%; }

.floor-area {
  position: absolute;
  border: 1px solid;
  border-radius: 4px;
  cursor: default;
  transition: all 0.15s;
}

.area-editable {
  cursor: pointer;
}

.area-editable:hover {
  filter: brightness(1.3);
}

.area-selected {
  border-width: 2px !important;
  border-color: var(--accent) !important;
  box-shadow: 0 0 12px rgba(0, 212, 255, 0.4);
  z-index: 5;
}

.area-name {
  font-size: 9px;
  color: rgba(255,255,255,0.8);
  padding: 3px 6px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.area-icon { font-size: 10px; }

.area-delete {
  position: absolute;
  top: 2px;
  right: 4px;
  color: var(--red);
  cursor: pointer;
  font-size: 12px;
  font-weight: bold;
  opacity: 0.6;
}

.area-delete:hover { opacity: 1; }

/* 画框预览 */
.drawing-preview {
  position: absolute;
  border: 2px dashed var(--accent);
  background: rgba(0, 212, 255, 0.1);
  pointer-events: none;
  border-radius: 4px;
}

/* 框选矩形预览 */
.box-select-preview {
  position: absolute;
  border: 1px dashed rgba(0, 212, 255, 0.8);
  background: rgba(0, 212, 255, 0.08);
  pointer-events: none;
  border-radius: 2px;
  z-index: 18;
}

/* 多选高亮 */
.floor-area.area-multi {
  border-color: #a855f7 !important;
  box-shadow: 0 0 0 2px rgba(168, 85, 247, 0.5), 0 0 12px rgba(168, 85, 247, 0.3);
  z-index: 6;
}
.machine-marker.machine-multi {
  z-index: 18;
}
.machine-marker.machine-multi .marker-dot,
.machine-marker.machine-multi .marker-stk {
  box-shadow: 0 0 0 2px #a855f7, 0 0 10px rgba(168, 85, 247, 0.6);
}

/* 区域 resize 手柄 */
.resize-handle {
  position: absolute;
  width: 10px;
  height: 10px;
  background: var(--accent);
  border: 1.5px solid #fff;
  border-radius: 2px;
  z-index: 30;
  box-sizing: border-box;
}
.resize-handle.handle-tl { top: -5px; left: -5px; cursor: nwse-resize; }
.resize-handle.handle-tr { top: -5px; right: -5px; cursor: nesw-resize; }
.resize-handle.handle-bl { bottom: -5px; left: -5px; cursor: nesw-resize; }
.resize-handle.handle-br { bottom: -5px; right: -5px; cursor: nwse-resize; }
.resize-handle.handle-t  { top: -5px; left: 50%; transform: translateX(-50%); cursor: ns-resize; width: 14px; height: 8px; }
.resize-handle.handle-r  { right: -5px; top: 50%; transform: translateY(-50%); cursor: ew-resize; width: 8px; height: 14px; }
.resize-handle.handle-b  { bottom: -5px; left: 50%; transform: translateX(-50%); cursor: ns-resize; width: 14px; height: 8px; }
.resize-handle.handle-l  { left: -5px; top: 50%; transform: translateY(-50%); cursor: ew-resize; width: 8px; height: 14px; }

/* 多选信息条 */
.multi-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  background: rgba(168, 85, 247, 0.1);
  border: 1px solid rgba(168, 85, 247, 0.4);
  border-radius: 6px;
  font-size: 11px;
}
.multi-info .mi-count {
  color: #a855f7;
  font-weight: 700;
}
.multi-info .mi-hint {
  color: var(--text-dim);
  font-size: 10px;
}

/* 轨迹SVG层 */
.track-svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 8;
}

.track-svg path {
  opacity: 0.8;
}

.track-svg .track-selected {
  stroke-width: 1.5;
  opacity: 1;
}

/* 轨迹标签 */
.track-label {
  position: absolute;
  transform: translate(4px, -100%);
  z-index: 12;
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 4px;
}

.track-name {
  font-size: 9px;
  font-weight: 700;
  text-shadow: 0 1px 3px rgba(0,0,0,0.9);
  white-space: nowrap;
}

.track-del {
  color: var(--red);
  cursor: pointer;
  font-size: 11px;
  font-weight: bold;
  opacity: 0.6;
}

.track-del:hover { opacity: 1; }

/* 天车标记 */
.vehicle-marker {
  position: absolute;
  transform: translate(-50%, -50%);
  z-index: 15;
  cursor: pointer;
  pointer-events: auto;
}

.vehicle-icon {
  font-size: 18px;
  text-align: center;
  filter: drop-shadow(0 0 4px rgba(0, 212, 255, 0.6));
}

.vehicle-icon.moving {
  animation: vehiclePulse 0.8s ease-in-out infinite;
}

@keyframes vehiclePulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.15); }
}

.vehicle-id {
  font-size: 8px;
  font-weight: 700;
  color: #fff;
  text-shadow: 0 1px 3px rgba(0,0,0,0.9);
  text-align: center;
}

.vehicle-lot {
  font-size: 7px;
  color: var(--accent);
  text-align: center;
}

.vehicle-del {
  position: absolute;
  top: -4px;
  right: -8px;
  color: var(--red);
  cursor: pointer;
  font-size: 10px;
  font-weight: bold;
  opacity: 0.6;
}

.vehicle-del:hover { opacity: 1; }

.vehicle-marker.vehicle-hover .vehicle-icon {
  font-size: 24px;
  filter: drop-shadow(0 0 8px rgba(0, 212, 255, 1));
}

.vehicle-marker.vehicle-hover .vehicle-id {
  font-size: 10px;
  color: #00d4ff;
}

/* 天车列表 */
.vehicle-list {
  margin-top: 12px;
  padding: 10px;
  background: rgba(15, 23, 42, 0.9);
  border: 1px solid rgba(0, 212, 255, 0.2);
  border-radius: 6px;
  max-height: 180px;
  overflow-y: auto;
}

.vl-title {
  font-size: 12px;
  font-weight: 600;
  color: #00d4ff;
  margin-bottom: 8px;
}

.vl-items {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.vl-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  background: rgba(0, 212, 255, 0.08);
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
  transition: background 0.2s;
}

.vl-item:hover {
  background: rgba(0, 212, 255, 0.15);
}

.vl-name {
  flex: 1;
  color: #e2e8f0;
  font-weight: 500;
}

.vl-track {
  font-size: 10px;
  color: #94a3b8;
  background: rgba(0,0,0,0.3);
  padding: 1px 5px;
  border-radius: 3px;
}

.vl-del {
  background: none;
  border: none;
  color: #ef4444;
  cursor: pointer;
  font-size: 12px;
  padding: 2px 4px;
  opacity: 0.6;
}

.vl-del:hover { opacity: 1; }

/* 颜色选择器 */
.tool-input-color {
  width: 30px;
  height: 26px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  cursor: pointer;
  padding: 2px;
}

/* 机台标记 */
.machine-marker {
  position: absolute;
  transform: translate(-50%, -50%);
  cursor: pointer;
  transition: transform 0.1s;
  z-index: 10;
  /* 固定可点击区域 + 透明背景确保空白处也能点击，双击编辑不失效 */
  width: 48px;
  height: 36px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  padding-top: 2px;
  background: transparent;  /* 允许空白处捕获点击事件 */
  border-radius: 4px;
}
/* 机台内部元素不拦截事件，全部冒泡到外层 .machine-marker 统一处理（保证双击/单击稳定） */
.machine-marker > * { pointer-events: none; }

.machine-marker:hover {
  transform: translate(-50%, -50%) scale(1.3);
}

.machine-marker.selected {
  z-index: 20;
}

.machine-marker.selected .marker-dot,
.machine-marker.selected .marker-stk {
  box-shadow: 0 0 12px var(--accent), 0 0 4px #fff;
}

.machine-marker.edit-movable {
  cursor: move;
}

.marker-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.3);
  box-shadow: 0 0 6px currentColor;
  margin: 0 auto;
}

.marker-stk {
  width: 24px;
  height: 10px;
  border-radius: 2px;
  border: 2px solid rgba(255,255,255,0.3);
  box-shadow: 0 0 6px currentColor;
  margin: 0 auto;
}

.marker-id {
  font-size: 8px;
  font-weight: 700;
  color: #fff;
  white-space: nowrap;
  text-shadow: 0 1px 3px rgba(0,0,0,0.9);
  margin-top: 2px;
  text-align: center;
}

.marker-type {
  font-size: 7px;
  color: var(--accent);
  text-align: center;
}

.marker-alarm {
  position: absolute;
  top: -6px;
  right: -6px;
  background: var(--red);
  color: #fff;
  font-size: 8px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 8px;
}

.edit-hint {
  position: absolute;
  bottom: 8px;
  left: 8px;
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent);
  padding: 5px 10px;
  border-radius: 6px;
  font-size: 11px;
  border: 1px solid var(--accent);
  pointer-events: none;
}

.fp-legend {
  position: sticky;
  bottom: 0;
  z-index: 5;
  padding: 8px 14px;
  border-top: 1px solid var(--border);
  background: var(--panel-2);
}

.legend-title {
  font-size: 10px;
  font-weight: 700;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.8px;
  margin-bottom: 6px;
}

.legend-items {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.legend-item {
  font-size: 11px;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: 6px;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.legend-rect {
  width: 14px;
  height: 6px;
  border-radius: 2px;
}

.legend-info {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 4px;
}

/* Toast 提示 */
/* 外链跳转角标 */
.ext-link-badge {
  position: absolute;
  top: -2px;
  right: -2px;
  font-size: 11px;
  line-height: 1;
  color: #38bdf8;
  text-shadow: 0 0 2px #000;
  pointer-events: none;
}

/* 外链编辑模态框 */
.ext-link-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}
.ext-link-modal {
  width: 460px;
  max-width: 92vw;
  background: #0f1b2d;
  border: 1px solid #1e3a5f;
  border-radius: 8px;
  box-shadow: 0 10px 40px rgba(0,0,0,0.5);
  color: #e5e7eb;
  font-size: 13px;
}
.ext-link-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #1e3a5f;
}
.ext-link-modal-header h3 { margin: 0; font-size: 15px; }
.ext-link-close {
  background: transparent;
  border: none;
  color: #9ca3af;
  font-size: 20px;
  cursor: pointer;
  line-height: 1;
}
.ext-link-close:hover { color: #ef4444; }
.ext-link-modal-body { padding: 16px; display: flex; flex-direction: column; gap: 14px; }
.ext-link-row { display: flex; flex-direction: column; gap: 8px; }
.ext-link-radio { display: flex; align-items: center; gap: 8px; cursor: pointer; }
.ext-link-radio input { accent-color: #06b6d4; }
.ext-link-field { display: flex; flex-direction: column; gap: 4px; }
.ext-link-field label { font-size: 12px; color: #9ca3af; }
.ext-link-field input {
  padding: 6px 8px;
  background: #0b1220;
  border: 1px solid #1e3a5f;
  border-radius: 4px;
  color: #e5e7eb;
  font-size: 13px;
}
.ext-link-field input:disabled { opacity: 0.4; }
.ext-link-hint { font-size: 11px; color: #f59e0b; margin-top: 2px; }
.ext-link-modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid #1e3a5f;
}
.ext-link-save, .ext-link-cancel {
  padding: 6px 16px;
  border-radius: 4px;
  border: 1px solid #1e3a5f;
  cursor: pointer;
  font-size: 13px;
}
.ext-link-save { background: #06b6d4; color: #001018; border-color: #06b6d4; }
.ext-link-save:disabled { opacity: 0.5; cursor: not-allowed; }
.ext-link-cancel { background: transparent; color: #9ca3af; }

.toast {
  position: absolute;
  top: 60px;
  left: 50%;
  transform: translateX(-50%);
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  z-index: 200;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
  animation: toastIn 0.2s ease-out;
}

.toast.info {
  background: #1e293b;
  color: #94a3b8;
  border: 1px solid #334155;
}

.toast.success {
  background: #064e3b;
  color: #6ee7b7;
  border: 1px solid #065f46;
}

.toast.error {
  background: #7f1d1d;
  color: #fca5a5;
  border: 1px solid #991b1b;
}

@keyframes toastIn {
  from { opacity: 0; transform: translateX(-50%) translateY(-10px); }
  to { opacity: 1; transform: translateX(-50%) translateY(0); }
}

/* 删除确认弹窗 */
.delete-modal-mask {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  backdrop-filter: blur(2px);
}

.delete-modal {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  min-width: 300px;
  max-width: 90%;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
}

.modal-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--red);
  margin-bottom: 12px;
}

.modal-body {
  font-size: 13px;
  color: var(--text);
  margin-bottom: 18px;
  line-height: 1.6;
}

.modal-body strong {
  color: var(--accent);
}

.modal-tip {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 6px;
}

.modal-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

.modal-btn {
  padding: 8px 18px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid var(--border);
  transition: all 0.15s;
}

.modal-btn.cancel {
  background: var(--bg);
  color: var(--text-dim);
}

.modal-btn.cancel:hover {
  border-color: var(--text-dim);
  color: var(--text);
}

.modal-btn.confirm {
  background: var(--red);
  color: #fff;
  border-color: var(--red);
}

.modal-btn.confirm:hover {
  filter: brightness(1.2);
}
</style>
