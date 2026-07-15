<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { TransformControls } from 'three/addons/controls/TransformControls.js'
import { useModelStore } from '../stores/model'

const modelStore = useModelStore()

// 简易提示
function showToast(msg, type = 'info') {
  const el = document.createElement('div')
  el.textContent = msg
  const colors = {
    info: '#3b82f6',
    success: '#10b981',
    warning: '#f59e0b',
    error: '#ef4444',
  }
  el.style.cssText = `
    position: fixed; top: 20px; left: 50%; transform: translateX(-50%);
    background: ${colors[type] || colors.info}; color: #fff; padding: 8px 16px;
    border-radius: 4px; font-size: 13px; z-index: 99999; opacity: 0;
    transition: opacity 0.2s, top 0.2s;
  `
  document.body.appendChild(el)
  requestAnimationFrame(() => {
    el.style.opacity = '1'
    el.style.top = '30px'
  })
  setTimeout(() => {
    el.style.opacity = '0'
    el.style.top = '20px'
    setTimeout(() => el.remove(), 200)
  }, 2000)
}

// ======================== 部件初始数据 ========================
const initialPartsData = [
  { id: 'efem', name: 'EFEM前端模块', type: 'box', position: [-2, 1.9, 0], size: [1.5, 2.8, 3.5], color: 0x2a3a5a },
  { id: 'lp1', name: 'Load Port 1', type: 'box', position: [-2.85, 1.8, -0.8], size: [0.2, 1.2, 1.3], color: 0x0f1828 },
  { id: 'lp2', name: 'Load Port 2', type: 'box', position: [-2.85, 1.8, 0.8], size: [0.2, 1.2, 1.3], color: 0x0f1828 },
  { id: 'efemRobot', name: 'EFEM机械臂', type: 'robot', position: [-2, 0, 0], color: 0x8a95aa },
  { id: 'aligner', name: '对准器', type: 'cylinder', position: [-1.5, 1.5, 0], size: [0.3, 0.8], color: 0x475569 },
  { id: 'vtm', name: 'VTM真空传输', type: 'cylinder', position: [0, 1.6, 0], size: [1.3, 2.2], color: 0x2a3a5a },
  { id: 'vtmRobot', name: 'VTM机械臂', type: 'robot', position: [0, 0.5, 0], color: 0x8a95aa },
  { id: 'pm1', name: '工艺腔 PM-1', type: 'chamber', position: [2.2, 1.8, 0], color: 0x3a4a6a },
  { id: 'pm2', name: '工艺腔 PM-2', type: 'chamber', position: [0, 1.8, 2.2], color: 0x3a4a6a },
  { id: 'pm3', name: '工艺腔 PM-3', type: 'chamber', position: [-2.2, 1.8, 0], color: 0x3a4a6a },
  { id: 'pm4', name: '工艺腔 PM-4', type: 'chamber', position: [0, 1.8, -2.2], color: 0x3a4a6a },
]

// 深拷贝并补充默认字段
function makeParts(data) {
  return data.map(p => ({
    ...p,
    rotation: [0, 0, 0],
    scale: [1, 1, 1],
    eventConfig: {
      stateEvent: 'run',
      actionType: 'rotate',
      rotateAngle: 90,
      moveTarget: [0, 2, 0],
      colorTarget: 0x00ff00,
      visibleTarget: false,
      duration: 1.0,
      easing: 'easeInOut',
    },
    keyframes: [],
  }))
}

const parts = ref(makeParts(initialPartsData))
const selectedId = ref(null)
const transformMode = ref('translate')
const previewing = ref(false)

// ======================== 型号管理 ========================
const currentModelId = ref('TEL-DRM-UNIT')
const showNewModelDialog = ref(false)
const newModelForm = ref({ model_id: '', model_name: '', view_mode: 'threejs', vendor: '', process_type: 'ETCH' })
const rightTab = ref('part')
const eventActionList = ref([])
const selectedEventIdx = ref(-1)

const selectedEventAction = computed(() =>
  selectedEventIdx.value >= 0 ? eventActionList.value[selectedEventIdx.value] : null
)

function addEventAction() {
  eventActionList.value.push({
    event_name: '新事件',
    event_code: '',
    trigger_type: 'state',
    trigger_params: {},
    action_sequence: [],
    rollback_sequence: [],
  })
  selectedEventIdx.value = eventActionList.value.length - 1
}

function removeEventAction(idx) {
  eventActionList.value.splice(idx, 1)
  if (selectedEventIdx.value >= eventActionList.value.length) {
    selectedEventIdx.value = eventActionList.value.length - 1
  }
}

function addActionStep() {
  if (!selectedEventAction.value) return
  selectedEventAction.value.action_sequence.push({
    part_id: parts.value[0]?.id || '',
    action_type: 'rotate',
    duration: 1.0,
    easing: 'easeInOut',
    params: {},
  })
}

function removeActionStep(idx) {
  if (!selectedEventAction.value) return
  selectedEventAction.value.action_sequence.splice(idx, 1)
}

const currentModelConfig = computed(() => modelStore.getModelById(currentModelId.value))

const viewModeLabel = computed(() => {
  const vm = currentModelConfig.value?.view_mode || 'threejs'
  const map = { threejs: '3D模型', isometric: '2.5D等角', svg: '2D SVG', hybrid: '2D/3D混合' }
  return map[vm] || vm
})

async function loadModels() {
  await modelStore.loadModels()
  if (modelStore.models.length > 0 && !currentModelId.value) {
    currentModelId.value = modelStore.models[0].model_id
  }
}

function switchModel(modelId) {
  currentModelId.value = modelId
  const cfg = modelStore.getModelById(modelId)
  if (cfg?.parts_config?.length) {
    parts.value = cfg.parts_config.map(p => ({
      id: p.part_id,
      name: p.part_name,
      type: p.view_3d?.type || 'box',
      position: p.view_3d?.position || [0, 0, 0],
      size: p.view_3d?.size || [1, 1, 1],
      color: parseInt((p.view_3d?.color || '#4a5568').replace('#', ''), 16),
      rotation: [0, 0, 0],
      scale: [1, 1, 1],
      eventConfig: {
        stateEvent: 'run',
        actionType: 'rotate',
        rotateAngle: 90,
        moveTarget: [0, 2, 0],
        colorTarget: 0x00ff00,
        visibleTarget: false,
        duration: 1.0,
        easing: 'easeInOut',
      },
      keyframes: [],
    }))
  }
  showToast(`已切换到型号：${cfg?.model_name || modelId}`, 'info')
}

async function createNewModel() {
  if (!newModelForm.value.model_id) {
    showToast('请输入型号ID', 'warning')
    return
  }
  try {
    await modelStore.createModel({
      model_id: newModelForm.value.model_id,
      model_name: newModelForm.value.model_name || newModelForm.value.model_id,
      vendor: newModelForm.value.vendor,
      process_type: newModelForm.value.process_type,
      view_mode: newModelForm.value.view_mode,
      views_config: { view_3d: { type: 'threejs', model_source: 'procedural' } },
      parts_config: [],
      state_mapping: [],
      hotspots_config: [],
    })
    currentModelId.value = newModelForm.value.model_id
    showNewModelDialog.value = false
    newModelForm.value = { model_id: '', model_name: '', view_mode: 'threejs', vendor: '', process_type: 'ETCH' }
    showToast('型号创建成功', 'success')
  } catch (e) {
    showToast('创建失败: ' + e.message, 'error')
  }
}

async function duplicateCurrentModel() {
  const newId = prompt('请输入新型号ID:', currentModelId.value + '-COPY')
  if (!newId) return
  try {
    await modelStore.duplicateModel(currentModelId.value, {
      new_model_id: newId,
      new_model_name: currentModelConfig.value?.model_name + ' (副本)',
    })
    currentModelId.value = newId
    showToast('复制成功', 'success')
  } catch (e) {
    showToast('复制失败: ' + e.message, 'error')
  }
}

async function deleteCurrentModel() {
  if (modelStore.models.length <= 1) {
    showToast('至少保留一个型号', 'warning')
    return
  }
  try {
    const ok = confirm(`确定删除型号 ${currentModelId.value}？此操作不可恢复。`)
    if (!ok) return
    await modelStore.deleteModel(currentModelId.value)
    currentModelId.value = modelStore.models[0]?.model_id || ''
    showToast('已删除', 'success')
  } catch { /* 用户取消 */ }
}

// ======================== 选项常量 ========================
const stateEventOptions = [
  { value: 'run', label: '运行中 (run)' },
  { value: 'idle', label: '空闲 (idle)' },
  { value: 'error', label: '故障 (error)' },
  { value: 'maint', label: '维护 (maint)' },
  { value: 'setup', label: '准备中 (setup)' },
]
const actionTypeOptions = [
  { value: 'rotate', label: '旋转' },
  { value: 'move', label: '移动' },
  { value: 'color', label: '变色' },
  { value: 'visibility', label: '显示/隐藏' },
]
const easingOptions = [
  { value: 'linear', label: '线性' },
  { value: 'easeIn', label: '渐入' },
  { value: 'easeOut', label: '渐出' },
  { value: 'easeInOut', label: '渐入渐出' },
]
const easings = {
  linear: (t) => t,
  easeIn: (t) => t * t,
  easeOut: (t) => 1 - (1 - t) * (1 - t),
  easeInOut: (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2),
}

// ======================== Three.js 变量 ========================
let scene, camera, renderer, orbitControls, transformControls
let raycaster, pointer
let boxHelper = null
let highlightedId = null
let animId = null
let resizeObserver = null
const partObjects = new Map() // id -> Object3D
const canvasRef = ref(null)
const fileInputRef = ref(null)

// 动画预览
const activePreviews = new Map() // partId -> { keyframes, startTime, duration }
const activeEventTests = new Map() // partId -> { config, startTime, duration, startState }

// 同步标志位，防止反馈循环
let syncingFromMesh = false

// ======================== 计算属性 ========================
const selectedPart = computed(() =>
  parts.value.find((p) => p.id === selectedId.value) || null
)

// ======================== 颜色工具 ========================
function numToHexStr(num) {
  return '#' + (num || 0).toString(16).padStart(6, '0')
}
function hexStrToNum(str) {
  return parseInt(str.replace('#', ''), 16)
}

// ======================== 几何体创建 ========================
function createPartObject(part) {
  let obj
  const mat = new THREE.MeshStandardMaterial({
    color: part.color,
    metalness: 0.6,
    roughness: 0.3,
  })

  switch (part.type) {
    case 'box': {
      const [w, h, d] = part.size || [1, 1, 1]
      obj = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat)
      break
    }
    case 'cylinder': {
      const [r, h] = part.size || [0.5, 1]
      obj = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 24), mat)
      break
    }
    case 'robot': {
      obj = new THREE.Group()
      const base = new THREE.Mesh(
        new THREE.CylinderGeometry(0.2, 0.25, 0.3, 12),
        new THREE.MeshStandardMaterial({ color: part.color, metalness: 0.7, roughness: 0.3 })
      )
      base.position.y = 0.8
      obj.add(base)
      const arm = new THREE.Mesh(
        new THREE.BoxGeometry(0.08, 1.2, 0.08),
        new THREE.MeshStandardMaterial({ color: 0xb0bccc, metalness: 0.85, roughness: 0.2 })
      )
      arm.position.y = 1.5
      obj.add(arm)
      const hand = new THREE.Mesh(
        new THREE.BoxGeometry(0.6, 0.05, 0.25),
        new THREE.MeshStandardMaterial({ color: 0xb0bccc, metalness: 0.85, roughness: 0.2 })
      )
      hand.position.y = 2.1
      obj.add(hand)
      break
    }
    case 'chamber': {
      obj = new THREE.Group()
      const body = new THREE.Mesh(
        new THREE.CylinderGeometry(0.8, 0.9, 1.5, 24),
        mat
      )
      obj.add(body)
      const lid = new THREE.Mesh(
        new THREE.CylinderGeometry(0.95, 0.95, 0.25, 24),
        new THREE.MeshStandardMaterial({ color: part.color, metalness: 0.6, roughness: 0.35 })
      )
      lid.position.y = 0.875
      obj.add(lid)
      const rf = new THREE.Mesh(
        new THREE.BoxGeometry(0.4, 0.5, 0.4),
        new THREE.MeshStandardMaterial({ color: 0x2a3a5a, metalness: 0.6, roughness: 0.4 })
      )
      rf.position.y = 1.275
      obj.add(rf)
      break
    }
    default: {
      obj = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), mat)
    }
  }

  // 应用变换
  obj.position.set(...part.position)
  obj.rotation.set(
    THREE.MathUtils.degToRad(part.rotation[0]),
    THREE.MathUtils.degToRad(part.rotation[1]),
    THREE.MathUtils.degToRad(part.rotation[2])
  )
  obj.scale.set(...part.scale)

  // 标记所有子对象 partId（用于射线拾取）
  obj.traverse((child) => {
    child.userData.partId = part.id
  })

  obj.castShadow = true
  obj.receiveShadow = true
  return obj
}

// ======================== 场景初始化 ========================
function initScene() {
  const canvas = canvasRef.value
  if (!canvas) return
  const w = canvas.clientWidth || 800
  const h = canvas.clientHeight || 600

  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x1a2438)
  scene.fog = new THREE.Fog(0x1a2438, 15, 40)

  camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 100)
  camera.position.set(7, 5, 8)

  renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
  renderer.setSize(w, h)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap

  // 轨道控制器
  orbitControls = new OrbitControls(camera, canvas)
  orbitControls.enableDamping = true
  orbitControls.dampingFactor = 0.08
  orbitControls.minDistance = 4
  orbitControls.maxDistance = 25
  orbitControls.maxPolarAngle = Math.PI / 2.1
  orbitControls.target.set(0, 1.8, 0)

  // 变换控制器
  transformControls = new TransformControls(camera, canvas)
  transformControls.setMode('translate')
  transformControls.setSize(0.8)
  // r158+ 需要通过 getHelper() 添加到场景
  if (typeof transformControls.getHelper === 'function') {
    scene.add(transformControls.getHelper())
  } else {
    scene.add(transformControls)
  }
  transformControls.addEventListener('dragging-changed', (event) => {
    orbitControls.enabled = !event.value
  })
  transformControls.addEventListener('objectChange', () => {
    if (selectedId.value) {
      syncMeshToPart(selectedId.value)
    }
  })

  // ===== 灯光（足够亮）=====
  // 环境光
  scene.add(new THREE.AmbientLight(0xa0b0d0, 1.2))
  // 主方向光
  const keyLight = new THREE.DirectionalLight(0xffffff, 1.8)
  keyLight.position.set(8, 14, 6)
  keyLight.castShadow = true
  keyLight.shadow.mapSize.set(2048, 2048)
  keyLight.shadow.camera.left = -10
  keyLight.shadow.camera.right = 10
  keyLight.shadow.camera.top = 10
  keyLight.shadow.camera.bottom = -10
  keyLight.shadow.camera.near = 1
  keyLight.shadow.camera.far = 40
  scene.add(keyLight)
  // 补光 - 左侧
  const fillLight1 = new THREE.DirectionalLight(0xb0c4de, 1.0)
  fillLight1.position.set(-8, 8, 4)
  scene.add(fillLight1)
  // 补光 - 右后
  const fillLight2 = new THREE.DirectionalLight(0xffffff, 0.8)
  fillLight2.position.set(0, 6, -10)
  scene.add(fillLight2)
  // 点光源 - 青色
  const pointCyan = new THREE.PointLight(0x00d4ff, 1.2, 25)
  pointCyan.position.set(-5, 5, 5)
  scene.add(pointCyan)
  // 点光源 - 暖色
  const pointWarm = new THREE.PointLight(0xffaa44, 0.8, 20)
  pointWarm.position.set(5, 4, -3)
  scene.add(pointWarm)
  // 半球光
  scene.add(new THREE.HemisphereLight(0x88aacc, 0x222233, 0.6))

  // ===== 地板 =====
  const floorGeo = new THREE.PlaneGeometry(40, 40)
  const floorMat = new THREE.MeshStandardMaterial({
    color: 0x0d1828,
    metalness: 0.1,
    roughness: 0.85,
  })
  const floor = new THREE.Mesh(floorGeo, floorMat)
  floor.rotation.x = -Math.PI / 2
  floor.receiveShadow = true
  scene.add(floor)
  // 网格
  const grid = new THREE.GridHelper(40, 40, 0x2a3a5a, 0x152238)
  grid.position.y = 0.01
  scene.add(grid)

  // ===== 构建所有部件 =====
  parts.value.forEach((part) => {
    const obj = createPartObject(part)
    scene.add(obj)
    partObjects.set(part.id, obj)
  })

  // 射线拾取
  raycaster = new THREE.Raycaster()
  pointer = new THREE.Vector2()

  // 点击选择
  let pointerDownPos = { x: 0, y: 0 }
  let pointerDownTime = 0
  canvas.addEventListener('pointerdown', (e) => {
    pointerDownPos = { x: e.clientX, y: e.clientY }
    pointerDownTime = Date.now()
  })
  canvas.addEventListener('pointerup', (e) => {
    const dx = e.clientX - pointerDownPos.x
    const dy = e.clientY - pointerDownPos.y
    const dist = Math.sqrt(dx * dx + dy * dy)
    const dt = Date.now() - pointerDownTime
    if (dt < 400 && dist < 5) {
      handleCanvasClick(e)
    }
  })

  // 尺寸观察
  resizeObserver = new ResizeObserver(() => onResize())
  resizeObserver.observe(canvas.parentElement)

  animate()
}

// ======================== 点击拾取 ========================
function handleCanvasClick(e) {
  if (!renderer || !camera) return
  const rect = renderer.domElement.getBoundingClientRect()
  pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
  pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(pointer, camera)

  const meshes = []
  partObjects.forEach((obj) => {
    obj.traverse((child) => {
      if (child.isMesh) meshes.push(child)
    })
  })
  const intersects = raycaster.intersectObjects(meshes, false)
  if (intersects.length > 0) {
    const partId = intersects[0].object.userData.partId
    if (partId) {
      selectPart(partId)
    }
  }
}

// ======================== 选择 & 高亮 ========================
function selectPart(id) {
  selectedId.value = id
}

function highlightPart(id) {
  // 恢复之前的高亮
  restoreEmissive()
  if (boxHelper) {
    scene.remove(boxHelper)
    if (boxHelper.dispose) boxHelper.dispose()
    boxHelper = null
  }

  highlightedId = id
  if (!id) return

  const obj = partObjects.get(id)
  if (!obj) return

  // 添加发光边框（BoxHelper）
  boxHelper = new THREE.BoxHelper(obj, 0x00d4ff)
  scene.add(boxHelper)

  // 提升 emissive
  obj.traverse((child) => {
    if (child.isMesh && child.material && child.material.emissive) {
      if (child.userData.origEmissive === undefined) {
        child.userData.origEmissive = child.material.emissive.getHex()
        child.userData.origEmissiveIntensity = child.material.emissiveIntensity || 0
      }
      child.material.emissive.setHex(0x00d4ff)
      child.material.emissiveIntensity = 0.35
    }
  })
}

function restoreEmissive() {
  if (!highlightedId) return
  const obj = partObjects.get(highlightedId)
  if (obj) {
    obj.traverse((child) => {
      if (child.isMesh && child.material && child.material.emissive) {
        if (child.userData.origEmissive !== undefined) {
          child.material.emissive.setHex(child.userData.origEmissive)
          child.material.emissiveIntensity = child.userData.origEmissiveIntensity
        }
      }
    })
  }
  highlightedId = null
}

// ======================== 数据 <-> 网格 同步 ========================
function applyPartToMesh(id) {
  const part = parts.value.find((p) => p.id === id)
  const obj = partObjects.get(id)
  if (!part || !obj) return
  obj.position.set(...part.position)
  obj.rotation.set(
    THREE.MathUtils.degToRad(part.rotation[0]),
    THREE.MathUtils.degToRad(part.rotation[1]),
    THREE.MathUtils.degToRad(part.rotation[2])
  )
  obj.scale.set(...part.scale)
  if (boxHelper) boxHelper.update()
}

function syncMeshToPart(id) {
  const part = parts.value.find((p) => p.id === id)
  const obj = partObjects.get(id)
  if (!part || !obj) return
  syncingFromMesh = true
  part.position[0] = +obj.position.x.toFixed(3)
  part.position[1] = +obj.position.y.toFixed(3)
  part.position[2] = +obj.position.z.toFixed(3)
  part.rotation[0] = +THREE.MathUtils.radToDeg(obj.rotation.x).toFixed(1)
  part.rotation[1] = +THREE.MathUtils.radToDeg(obj.rotation.y).toFixed(1)
  part.rotation[2] = +THREE.MathUtils.radToDeg(obj.rotation.z).toFixed(1)
  part.scale[0] = +obj.scale.x.toFixed(2)
  part.scale[1] = +obj.scale.y.toFixed(2)
  part.scale[2] = +obj.scale.z.toFixed(2)
  nextTick(() => {
    syncingFromMesh = false
  })
}

// ======================== 属性编辑事件 ========================
function onTransformInput() {
  if (syncingFromMesh || !selectedId.value) return
  applyPartToMesh(selectedId.value)
}

function onColorInput(event) {
  const part = selectedPart.value
  if (!part) return
  part.color = hexStrToNum(event.target.value)
  // 重建对象以应用新颜色
  rebuildPart(part.id)
}

function rebuildPart(id) {
  const part = parts.value.find((p) => p.id === id)
  if (!part) return
  const oldObj = partObjects.get(id)
  if (oldObj) {
    // 保留当前变换
    part.position = [+oldObj.position.x.toFixed(3), +oldObj.position.y.toFixed(3), +oldObj.position.z.toFixed(3)]
    part.rotation = [
      +THREE.MathUtils.radToDeg(oldObj.rotation.x).toFixed(1),
      +THREE.MathUtils.radToDeg(oldObj.rotation.y).toFixed(1),
      +THREE.MathUtils.radToDeg(oldObj.rotation.z).toFixed(1),
    ]
    part.scale = [+oldObj.scale.x.toFixed(2), +oldObj.scale.y.toFixed(2), +oldObj.scale.z.toFixed(2)]
    scene.remove(oldObj)
    oldObj.traverse((child) => {
      if (child.geometry) child.geometry.dispose()
      if (child.material) child.material.dispose()
    })
    partObjects.delete(id)
  }
  const newObj = createPartObject(part)
  scene.add(newObj)
  partObjects.set(id, newObj)
  if (selectedId.value === id) {
    transformControls.attach(newObj)
    highlightPart(id)
  }
}

// ======================== 变换模式切换 ========================
function setTransformMode(mode) {
  transformMode.value = mode
  if (transformControls) {
    transformControls.setMode(mode)
  }
}

// ======================== 关键帧管理 ========================
function addKeyframe() {
  const part = selectedPart.value
  if (!part) return
  const lastTime = part.keyframes.length > 0
    ? Math.max(...part.keyframes.map((k) => k.time))
    : -1
  part.keyframes.push({
    time: +(lastTime + 1).toFixed(2),
    position: [...part.position],
    rotation: [...part.rotation],
    easing: 'easeInOut',
  })
}

function captureKeyframe() {
  // 捕获当前网格状态作为关键帧
  const part = selectedPart.value
  if (!part) return
  const obj = partObjects.get(part.id)
  if (!obj) return
  syncMeshToPart(part.id)
  addKeyframe()
}

function deleteKeyframe(idx) {
  const part = selectedPart.value
  if (!part) return
  part.keyframes.splice(idx, 1)
}

function onKeyframeInput() {
  // 关键帧编辑后无需操作网格（预览时才应用）
}

// ======================== 动画预览 ========================
function previewKeyframes(partId) {
  const part = parts.value.find((p) => p.id === partId)
  if (!part || !part.keyframes || part.keyframes.length < 2) return
  const obj = partObjects.get(partId)
  if (!obj) return

  const kfs = [...part.keyframes].sort((a, b) => a.time - b.time)
  const duration = kfs[kfs.length - 1].time * 1000

  activePreviews.set(partId, {
    keyframes: kfs,
    startTime: performance.now(),
    duration,
  })

  if (!previewing.value) {
    previewing.value = true
    if (transformControls) transformControls.detach()
  }
}

function previewSelectedAnimation() {
  if (!selectedId.value) return
  previewKeyframes(selectedId.value)
}

function previewAllAnimations() {
  parts.value.forEach((part) => {
    if (part.keyframes && part.keyframes.length >= 2) {
      previewKeyframes(part.id)
    }
  })
}

function updateKeyframePreviews() {
  const now = performance.now()
  const finished = []

  activePreviews.forEach((anim, partId) => {
    const elapsed = (now - anim.startTime) / 1000
    const obj = partObjects.get(partId)
    if (!obj) {
      finished.push(partId)
      return
    }

    const totalSec = anim.duration / 1000
    if (elapsed >= totalSec) {
      const last = anim.keyframes[anim.keyframes.length - 1]
      if (last.position) obj.position.set(...last.position)
      if (last.rotation) {
        obj.rotation.set(
          THREE.MathUtils.degToRad(last.rotation[0]),
          THREE.MathUtils.degToRad(last.rotation[1]),
          THREE.MathUtils.degToRad(last.rotation[2])
        )
      }
      finished.push(partId)
      return
    }

    // 找到当前段
    let i = 0
    while (i < anim.keyframes.length - 1 && anim.keyframes[i + 1].time <= elapsed) {
      i++
    }
    const k1 = anim.keyframes[i]
    const k2 = anim.keyframes[i + 1] || k1
    const segDur = k2.time - k1.time
    const t = segDur > 0 ? (elapsed - k1.time) / segDur : 0
    const clampedT = Math.min(1, Math.max(0, t))
    const eased = easings[k2.easing || 'linear'](clampedT)

    if (k1.position && k2.position) {
      obj.position.x = THREE.MathUtils.lerp(k1.position[0], k2.position[0], eased)
      obj.position.y = THREE.MathUtils.lerp(k1.position[1], k2.position[1], eased)
      obj.position.z = THREE.MathUtils.lerp(k1.position[2], k2.position[2], eased)
    }
    if (k1.rotation && k2.rotation) {
      obj.rotation.x = THREE.MathUtils.degToRad(
        THREE.MathUtils.lerp(k1.rotation[0], k2.rotation[0], eased)
      )
      obj.rotation.y = THREE.MathUtils.degToRad(
        THREE.MathUtils.lerp(k1.rotation[1], k2.rotation[1], eased)
      )
      obj.rotation.z = THREE.MathUtils.degToRad(
        THREE.MathUtils.lerp(k1.rotation[2], k2.rotation[2], eased)
      )
    }
  })

  finished.forEach((id) => {
    activePreviews.delete(id)
    syncMeshToPart(id)
  })

  if (activePreviews.size === 0 && activeEventTests.size === 0 && previewing.value) {
    previewing.value = false
    if (selectedId.value && partObjects.has(selectedId.value) && transformControls) {
      transformControls.attach(partObjects.get(selectedId.value))
    }
  }
}

// ======================== 事件动作测试 ========================
function testEventAction() {
  const part = selectedPart.value
  if (!part) return
  const cfg = part.eventConfig
  const obj = partObjects.get(part.id)
  if (!obj || previewing.value) return

  const duration = (cfg.duration || 1) * 1000
  activeEventTests.set(part.id, {
    config: cfg,
    startTime: performance.now(),
    duration,
    startPos: obj.position.clone(),
    startRotY: obj.rotation.y,
    startColor: new THREE.Color(part.color),
    targetColor: new THREE.Color(cfg.colorTarget || 0x00ff00),
    partId: part.id,
  })

  if (!previewing.value) {
    previewing.value = true
    if (transformControls) transformControls.detach()
  }
}

function updateEventTests() {
  const now = performance.now()
  const finished = []

  activeEventTests.forEach((anim, partId) => {
    const elapsed = now - anim.startTime
    const t = Math.min(elapsed / anim.duration, 1)
    const eased = easings[anim.config.easing || 'linear'](t)
    const obj = partObjects.get(partId)
    if (!obj) {
      finished.push(partId)
      return
    }
    const cfg = anim.config

    switch (cfg.actionType) {
      case 'rotate':
        obj.rotation.y = anim.startRotY + THREE.MathUtils.degToRad(cfg.rotateAngle || 0) * eased
        break
      case 'move':
        if (Array.isArray(cfg.moveTarget)) {
          obj.position.x = THREE.MathUtils.lerp(anim.startPos.x, cfg.moveTarget[0], eased)
          obj.position.y = THREE.MathUtils.lerp(anim.startPos.y, cfg.moveTarget[1], eased)
          obj.position.z = THREE.MathUtils.lerp(anim.startPos.z, cfg.moveTarget[2], eased)
        }
        break
      case 'color':
        obj.traverse((child) => {
          if (child.isMesh && child.material && child.material.color) {
            child.material.color.lerpColors(anim.startColor, anim.targetColor, eased)
          }
        })
        break
      case 'visibility':
        obj.visible = cfg.visibleTarget ? eased > 0.3 : eased < 0.7
        break
    }

    if (t >= 1) {
      finished.push(partId)
    }
  })

  finished.forEach((id) => {
    activeEventTests.delete(id)
    syncMeshToPart(id)
    // 恢复可见性
    const obj = partObjects.get(id)
    if (obj) obj.visible = true
  })

  if (activePreviews.size === 0 && activeEventTests.size === 0 && previewing.value) {
    previewing.value = false
    if (selectedId.value && partObjects.has(selectedId.value) && transformControls) {
      transformControls.attach(partObjects.get(selectedId.value))
    }
  }
}

// ======================== 保存 / 加载 / 重置 ========================
function saveConfig() {
  const config = {
    version: '1.0',
    parts: parts.value.map((p) => ({
      id: p.id,
      name: p.name,
      type: p.type,
      position: p.position,
      rotation: p.rotation,
      scale: p.scale,
      size: p.size,
      color: p.color,
      eventConfig: p.eventConfig,
      keyframes: p.keyframes,
    })),
  }
  const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'model-editor-config.json'
  a.click()
  URL.revokeObjectURL(url)
}

function triggerLoad() {
  fileInputRef.value?.click()
}

function loadConfig(event) {
  const file = event.target.files[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const config = JSON.parse(e.target.result)
      if (!config.parts || !Array.isArray(config.parts)) {
        alert('配置文件格式错误：缺少 parts 数组')
        return
      }
      // 清除旧对象
      partObjects.forEach((obj) => {
        scene.remove(obj)
        obj.traverse((child) => {
          if (child.geometry) child.geometry.dispose()
          if (child.material) child.material.dispose()
        })
      })
      partObjects.clear()
      if (boxHelper) {
        scene.remove(boxHelper)
        boxHelper = null
      }
      // 加载新数据
      parts.value = config.parts.map((p) => ({
        ...p,
        rotation: p.rotation || [0, 0, 0],
        scale: p.scale || [1, 1, 1],
        eventConfig: p.eventConfig || {
          stateEvent: 'run',
          actionType: 'rotate',
          rotateAngle: 90,
          moveTarget: [0, 2, 0],
          colorTarget: 0x00ff00,
          visibleTarget: false,
          duration: 1.0,
          easing: 'easeInOut',
        },
        keyframes: p.keyframes || [],
      }))
      // 重建对象
      parts.value.forEach((part) => {
        const obj = createPartObject(part)
        scene.add(obj)
        partObjects.set(part.id, obj)
      })
      selectedId.value = null
    } catch (err) {
      alert('加载配置失败：' + err.message)
    }
  }
  reader.readAsText(file)
  event.target.value = '' // 允许重新选择同一文件
}

function resetPositions() {
  const defaults = makeParts(initialPartsData)
  parts.value.forEach((part) => {
    const def = defaults.find((d) => d.id === part.id)
    if (def) {
      part.position = [...def.position]
      part.rotation = [...def.rotation]
      part.scale = [...def.scale]
      part.color = def.color
    }
  })
  // 重建所有对象
  partObjects.forEach((obj, id) => {
    scene.remove(obj)
    obj.traverse((child) => {
      if (child.geometry) child.geometry.dispose()
      if (child.material) child.material.dispose()
    })
  })
  partObjects.clear()
  if (boxHelper) {
    scene.remove(boxHelper)
    boxHelper = null
  }
  parts.value.forEach((part) => {
    const obj = createPartObject(part)
    scene.add(obj)
    partObjects.set(part.id, obj)
  })
  if (selectedId.value && transformControls) {
    transformControls.attach(partObjects.get(selectedId.value))
    highlightPart(selectedId.value)
  }
}

// ======================== 渲染循环 ========================
function onResize() {
  if (!renderer || !canvasRef.value) return
  const canvas = canvasRef.value
  const w = canvas.clientWidth || 1
  const h = canvas.clientHeight || 1
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  renderer.setSize(w, h)
}

function animate() {
  animId = requestAnimationFrame(animate)
  if (!orbitControls) return
  orbitControls.update()

  // 更新预览动画
  if (activePreviews.size > 0) updateKeyframePreviews()
  if (activeEventTests.size > 0) updateEventTests()

  // 更新高亮边框
  if (boxHelper) boxHelper.update()

  renderer.render(scene, camera)
}

// ======================== 监听选中变化 ========================
watch(selectedId, (newId) => {
  if (newId && partObjects.has(newId) && transformControls) {
    transformControls.attach(partObjects.get(newId))
    highlightPart(newId)
  } else {
    if (transformControls) transformControls.detach()
    highlightPart(null)
  }
})

// ======================== 生命周期 ========================
onMounted(() => {
  nextTick(() => {
    loadModels()
    setTimeout(() => initScene(), 50)
  })
})

onUnmounted(() => {
  if (animId) cancelAnimationFrame(animId)
  if (resizeObserver) resizeObserver.disconnect()
  if (transformControls) transformControls.dispose()
  if (orbitControls) orbitControls.dispose()
  if (renderer) renderer.dispose()
  partObjects.forEach((obj) => {
    obj.traverse((child) => {
      if (child.geometry) child.geometry.dispose()
      if (child.material) child.material.dispose()
    })
  })
  partObjects.clear()
})
</script>

<template>
  <div class="model-editor">
    <!-- ===== 左侧面板：型号管理 + 部件列表 ===== -->
    <aside class="left-panel">
      <!-- 型号选择器 -->
      <div class="panel-section">
        <div class="panel-header">
          <span class="header-icon">⚙</span>
          机台型号
        </div>
        <div class="model-selector">
          <select
            class="model-select"
            :value="currentModelId"
            @change="switchModel($event.target.value)"
          >
            <option v-for="m in modelStore.models" :key="m.model_id" :value="m.model_id">
              {{ m.model_name }} ({{ m.model_id }})
            </option>
          </select>
          <div class="model-actions">
            <button class="mini-btn" @click="showNewModelDialog = true" title="新建型号">+ 新建</button>
            <button class="mini-btn" @click="duplicateCurrentModel" title="复制型号">复制</button>
            <button class="mini-btn danger" @click="deleteCurrentModel" title="删除型号">删</button>
          </div>
        </div>
        <div class="model-info" v-if="currentModelConfig">
          <div class="model-info-row">
            <span class="info-label">视图模式</span>
            <span class="info-tag">{{ viewModeLabel }}</span>
          </div>
          <div class="model-info-row">
            <span class="info-label">部件数</span>
            <span class="info-value">{{ parts.length }}</span>
          </div>
        </div>
      </div>

      <div class="panel-divider"></div>

      <div class="panel-header">
        <span class="header-icon">◆</span>
        部件列表
      </div>
      <div class="parts-list">
        <div
          v-for="part in parts"
          :key="part.id"
          class="part-item"
          :class="{ selected: part.id === selectedId }"
          @click="selectPart(part.id)"
        >
          <div class="part-item-header">
            <span class="part-color-dot" :style="{ background: numToHexStr(part.color) }"></span>
            <span class="part-name">{{ part.name }}</span>
          </div>
          <div class="part-info">
            <span class="info-label">位置</span>
            <span class="info-value">{{ part.position.map((v) => v.toFixed(2)).join(', ') }}</span>
          </div>
          <div class="part-info">
            <span class="info-label">旋转</span>
            <span class="info-value">{{ part.rotation.map((v) => v.toFixed(0) + '°').join(' ') }}</span>
          </div>
        </div>
      </div>
    </aside>

    <!-- ===== 中央 3D 视图 ===== -->
    <main class="center-view">
      <div class="view-toolbar">
        <div class="toolbar-group">
          <button
            class="tool-btn"
            :class="{ active: transformMode === 'translate' }"
            @click="setTransformMode('translate')"
          >移动</button>
          <button
            class="tool-btn"
            :class="{ active: transformMode === 'rotate' }"
            @click="setTransformMode('rotate')"
          >旋转</button>
          <button
            class="tool-btn"
            :class="{ active: transformMode === 'scale' }"
            @click="setTransformMode('scale')"
          >缩放</button>
        </div>
        <div class="toolbar-hint" v-if="selectedId">
          已选中：{{ selectedPart?.name }}
        </div>
        <div class="toolbar-hint" v-else>
          点击左侧列表或3D视图中的部件进行选择
        </div>
      </div>
      <canvas ref="canvasRef" class="editor-canvas"></canvas>
    </main>

    <!-- ===== 右侧面板：属性编辑器 ===== -->
    <aside class="right-panel">
      <!-- Tab 切换 -->
      <div class="right-tabs">
        <button
          class="right-tab"
          :class="{ active: rightTab === 'part' }"
          @click="rightTab = 'part'"
        >部件属性</button>
        <button
          class="right-tab"
          :class="{ active: rightTab === 'event' }"
          @click="rightTab = 'event'"
        >事件动作</button>
      </div>

      <!-- ===== 部件属性 Tab ===== -->
      <div v-show="rightTab === 'part'" class="tab-content">
      <template v-if="selectedPart">
        <!-- 变换属性 -->
        <div class="panel-section">
          <div class="panel-header">
            <span class="header-icon">◆</span>
            变换属性
          </div>
          <div class="prop-group">
            <div class="prop-group-title">位置</div>
            <div class="prop-row">
              <label>X</label>
              <input
                type="number"
                step="0.1"
                class="prop-input"
                :value="selectedPart.position[0].toFixed(3)"
                @input="selectedPart.position[0] = parseFloat($event.target.value) || 0; onTransformInput()"
              />
              <label>Y</label>
              <input
                type="number"
                step="0.1"
                class="prop-input"
                :value="selectedPart.position[1].toFixed(3)"
                @input="selectedPart.position[1] = parseFloat($event.target.value) || 0; onTransformInput()"
              />
              <label>Z</label>
              <input
                type="number"
                step="0.1"
                class="prop-input"
                :value="selectedPart.position[2].toFixed(3)"
                @input="selectedPart.position[2] = parseFloat($event.target.value) || 0; onTransformInput()"
              />
            </div>
          </div>
          <div class="prop-group">
            <div class="prop-group-title">旋转 (°)</div>
            <div class="prop-row">
              <label>X</label>
              <input
                type="number"
                step="1"
                class="prop-input"
                :value="selectedPart.rotation[0].toFixed(1)"
                @input="selectedPart.rotation[0] = parseFloat($event.target.value) || 0; onTransformInput()"
              />
              <label>Y</label>
              <input
                type="number"
                step="1"
                class="prop-input"
                :value="selectedPart.rotation[1].toFixed(1)"
                @input="selectedPart.rotation[1] = parseFloat($event.target.value) || 0; onTransformInput()"
              />
              <label>Z</label>
              <input
                type="number"
                step="1"
                class="prop-input"
                :value="selectedPart.rotation[2].toFixed(1)"
                @input="selectedPart.rotation[2] = parseFloat($event.target.value) || 0; onTransformInput()"
              />
            </div>
          </div>
          <div class="prop-group">
            <div class="prop-group-title">缩放</div>
            <div class="prop-row">
              <label>X</label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                class="prop-input"
                :value="selectedPart.scale[0].toFixed(2)"
                @input="selectedPart.scale[0] = parseFloat($event.target.value) || 0.1; onTransformInput()"
              />
              <label>Y</label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                class="prop-input"
                :value="selectedPart.scale[1].toFixed(2)"
                @input="selectedPart.scale[1] = parseFloat($event.target.value) || 0.1; onTransformInput()"
              />
              <label>Z</label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                class="prop-input"
                :value="selectedPart.scale[2].toFixed(2)"
                @input="selectedPart.scale[2] = parseFloat($event.target.value) || 0.1; onTransformInput()"
              />
            </div>
          </div>
          <div class="prop-group">
            <div class="prop-group-title">颜色</div>
            <div class="prop-row color-row">
              <input
                type="color"
                class="color-input"
                :value="numToHexStr(selectedPart.color)"
                @input="onColorInput"
              />
              <span class="color-hex">{{ numToHexStr(selectedPart.color) }}</span>
            </div>
          </div>
        </div>

        <!-- 事件匹配配置 -->
        <div class="panel-section">
          <div class="panel-header">
            <span class="header-icon">◆</span>
            事件匹配配置
          </div>
          <div class="prop-group">
            <div class="prop-group-title">绑定状态事件</div>
            <select class="prop-select" v-model="selectedPart.eventConfig.stateEvent">
              <option v-for="opt in stateEventOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
          <div class="prop-group">
            <div class="prop-group-title">动作类型</div>
            <select class="prop-select" v-model="selectedPart.eventConfig.actionType">
              <option v-for="opt in actionTypeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
          <!-- 旋转参数 -->
          <div class="prop-group" v-if="selectedPart.eventConfig.actionType === 'rotate'">
            <div class="prop-group-title">旋转角度 (°)</div>
            <input
              type="number"
              step="1"
              class="prop-input full"
              v-model.number="selectedPart.eventConfig.rotateAngle"
            />
          </div>
          <!-- 移动参数 -->
          <div class="prop-group" v-if="selectedPart.eventConfig.actionType === 'move'">
            <div class="prop-group-title">目标位置</div>
            <div class="prop-row">
              <label>X</label>
              <input
                type="number"
                step="0.1"
                class="prop-input"
                v-model.number="selectedPart.eventConfig.moveTarget[0]"
              />
              <label>Y</label>
              <input
                type="number"
                step="0.1"
                class="prop-input"
                v-model.number="selectedPart.eventConfig.moveTarget[1]"
              />
              <label>Z</label>
              <input
                type="number"
                step="0.1"
                class="prop-input"
                v-model.number="selectedPart.eventConfig.moveTarget[2]"
              />
            </div>
          </div>
          <!-- 变色参数 -->
          <div class="prop-group" v-if="selectedPart.eventConfig.actionType === 'color'">
            <div class="prop-group-title">目标颜色</div>
            <div class="prop-row color-row">
              <input
                type="color"
                class="color-input"
                :value="numToHexStr(selectedPart.eventConfig.colorTarget)"
                @input="selectedPart.eventConfig.colorTarget = hexStrToNum($event.target.value)"
              />
              <span class="color-hex">{{ numToHexStr(selectedPart.eventConfig.colorTarget) }}</span>
            </div>
          </div>
          <!-- 可见性参数 -->
          <div class="prop-group" v-if="selectedPart.eventConfig.actionType === 'visibility'">
            <div class="prop-group-title">目标状态</div>
            <select class="prop-select" v-model="selectedPart.eventConfig.visibleTarget">
              <option :value="true">隐藏</option>
              <option :value="false">显示</option>
            </select>
          </div>
          <div class="prop-group">
            <div class="prop-group-title">持续时间 (秒)</div>
            <input
              type="number"
              step="0.1"
              min="0.1"
              class="prop-input full"
              v-model.number="selectedPart.eventConfig.duration"
            />
          </div>
          <div class="prop-group">
            <div class="prop-group-title">缓动方式</div>
            <select class="prop-select" v-model="selectedPart.eventConfig.easing">
              <option v-for="opt in easingOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
          <button class="action-btn" @click="testEventAction" :disabled="previewing">
            测试事件动作
          </button>
        </div>

        <!-- 轨迹编辑 -->
        <div class="panel-section">
          <div class="panel-header">
            <span class="header-icon">◆</span>
            轨迹编辑
            <span class="kf-count">({{ selectedPart.keyframes.length }})</span>
          </div>
          <div class="kf-actions">
            <button class="action-btn sm" @click="captureKeyframe">捕获当前</button>
            <button class="action-btn sm" @click="addKeyframe">添加关键帧</button>
          </div>
          <div class="kf-list" v-if="selectedPart.keyframes.length > 0">
            <div
              v-for="(kf, idx) in selectedPart.keyframes"
              :key="idx"
              class="kf-item"
            >
              <div class="kf-item-header">
                <span class="kf-index">#{{ idx + 1 }}</span>
                <div class="kf-time">
                  <label>时间</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    class="prop-input sm"
                    v-model.number="kf.time"
                    @input="onKeyframeInput"
                  />
                </div>
                <button class="kf-delete" @click="deleteKeyframe(idx)">删除</button>
              </div>
              <div class="kf-row">
                <span class="kf-label">位置</span>
                <input type="number" step="0.1" class="prop-input xs" v-model.number="kf.position[0]" @input="onKeyframeInput" />
                <input type="number" step="0.1" class="prop-input xs" v-model.number="kf.position[1]" @input="onKeyframeInput" />
                <input type="number" step="0.1" class="prop-input xs" v-model.number="kf.position[2]" @input="onKeyframeInput" />
              </div>
              <div class="kf-row">
                <span class="kf-label">旋转°</span>
                <input type="number" step="1" class="prop-input xs" v-model.number="kf.rotation[0]" @input="onKeyframeInput" />
                <input type="number" step="1" class="prop-input xs" v-model.number="kf.rotation[1]" @input="onKeyframeInput" />
                <input type="number" step="1" class="prop-input xs" v-model.number="kf.rotation[2]" @input="onKeyframeInput" />
              </div>
              <div class="kf-row">
                <span class="kf-label">缓动</span>
                <select class="prop-select xs" v-model="kf.easing">
                  <option v-for="opt in easingOptions" :key="opt.value" :value="opt.value">
                    {{ opt.label }}
                  </option>
                </select>
              </div>
            </div>
          </div>
          <div class="kf-empty" v-else>
            暂无关键帧，点击「捕获当前」或「添加关键帧」
          </div>
          <button
            class="action-btn"
            @click="previewSelectedAnimation"
            :disabled="previewing || selectedPart.keyframes.length < 2"
          >
            预览动画
          </button>
        </div>
      </template>
      <div v-else class="empty-hint">
        <div class="empty-icon">⬡</div>
        <div>请从左侧列表或3D视图中选择一个部件</div>
      </div>
      </div>

      <!-- ===== 事件动作配置 Tab ===== -->
      <div v-show="rightTab === 'event'" class="tab-content">
        <div class="panel-section">
          <div class="panel-header">
            <span class="header-icon">⚡</span>
            事件动作映射
            <button class="mini-btn right" @click="addEventAction">+ 新增</button>
          </div>
          <div class="event-list">
            <div
              v-for="(ea, idx) in eventActionList"
              :key="idx"
              class="event-item"
              :class="{ active: selectedEventIdx === idx }"
              @click="selectedEventIdx = idx"
            >
              <div class="event-item-header">
                <span class="event-name">{{ ea.event_name || '未命名事件' }}</span>
                <button class="icon-btn" @click.stop="removeEventAction(idx)">×</button>
              </div>
              <div class="event-item-meta">
                <span class="meta-tag">{{ ea.event_code || '-' }}</span>
                <span class="meta-tag">{{ ea.action_sequence?.length || 0 }}个动作</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="selectedEventAction" class="panel-section">
          <div class="panel-header">
            <span class="header-icon">▶</span>
            事件详情
          </div>
          <div class="prop-group">
            <div class="prop-row">
              <label>事件名称</label>
              <input type="text" class="prop-input full" v-model="selectedEventAction.event_name" />
            </div>
            <div class="prop-row">
              <label>事件代码</label>
              <input type="text" class="prop-input full" v-model="selectedEventAction.event_code" placeholder="如: wafer_load_start" />
            </div>
            <div class="prop-row">
              <label>触发条件</label>
              <select class="prop-select full" v-model="selectedEventAction.trigger_type">
                <option value="state">状态变化</option>
                <option value="event">事件触发</option>
                <option value="timer">定时触发</option>
              </select>
            </div>
          </div>
        </div>

        <div v-if="selectedEventAction" class="panel-section">
          <div class="panel-header">
            <span class="header-icon">♦</span>
            动作序列
            <button class="mini-btn right" @click="addActionStep">+ 动作</button>
          </div>
          <div class="action-steps">
            <div
              v-for="(step, sIdx) in selectedEventAction.action_sequence"
              :key="sIdx"
              class="action-step"
            >
              <div class="step-header">
                <span class="step-index">{{ sIdx + 1 }}</span>
                <select class="prop-select sm" v-model="step.part_id">
                  <option value="">-- 选择部件 --</option>
                  <option v-for="p in parts" :key="p.id" :value="p.id">{{ p.name }}</option>
                </select>
                <button class="icon-btn" @click="removeActionStep(sIdx)">×</button>
              </div>
              <div class="step-body">
                <div class="prop-row">
                  <label>动作</label>
                  <select class="prop-select" v-model="step.action_type">
                    <option value="rotate">旋转</option>
                    <option value="move">移动</option>
                    <option value="color">变色</option>
                    <option value="visibility">显示/隐藏</option>
                    <option value="keyframes">关键帧</option>
                  </select>
                </div>
                <div class="prop-row">
                  <label>时长(s)</label>
                  <input type="number" step="0.1" class="prop-input xs" v-model.number="step.duration" />
                </div>
                <div class="prop-row">
                  <label>缓动</label>
                  <select class="prop-select" v-model="step.easing">
                    <option v-for="opt in easingOptions" :key="opt.value" :value="opt.value">
                      {{ opt.label }}
                    </option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-if="!selectedEventAction" class="empty-hint">
          <div class="empty-icon">⚡</div>
          <div>选择或新增一个事件动作映射</div>
        </div>
      </div>
    </aside>

    <!-- ===== 底部工具栏 ===== -->
    <footer class="bottom-toolbar">
      <button class="tool-bar-btn save" @click="saveConfig">保存配置</button>
      <button class="tool-bar-btn load" @click="triggerLoad">加载配置</button>
      <button class="tool-bar-btn reset" @click="resetPositions">重置位置</button>
      <button class="tool-bar-btn preview" @click="previewAllAnimations" :disabled="previewing">
        预览全部动画
      </button>
      <span class="toolbar-status" v-if="previewing">动画播放中...</span>
      <input
        ref="fileInputRef"
        type="file"
        accept=".json"
        style="display: none"
        @change="loadConfig"
      />
    </footer>

    <!-- 新建型号对话框 -->
    <div v-if="showNewModelDialog" class="dialog-overlay" @click.self="showNewModelDialog = false">
      <div class="dialog">
        <div class="dialog-header">新建机台型号</div>
        <div class="dialog-body">
          <div class="form-item">
            <label>型号ID *</label>
            <input v-model="newModelForm.model_id" type="text" placeholder="如: OXE-300, VPO-2200" />
          </div>
          <div class="form-item">
            <label>型号名称</label>
            <input v-model="newModelForm.model_name" type="text" placeholder="如: OXE刻蚀机" />
          </div>
          <div class="form-item">
            <label>厂商</label>
            <input v-model="newModelForm.vendor" type="text" placeholder="TEL / AMAT / Lam..." />
          </div>
          <div class="form-item">
            <label>工艺类型</label>
            <select v-model="newModelForm.process_type">
              <option value="ETCH">刻蚀 ETCH</option>
              <option value="OXIDE">氧化 OXIDE</option>
              <option value="CMP">化学机械抛光 CMP</option>
              <option value="PVD">物理气相沉积 PVD</option>
              <option value="CVD">化学气相沉积 CVD</option>
              <option value="LITHO">光刻 LITHO</option>
              <option value="WAT">晶圆测试 WAT</option>
            </select>
          </div>
          <div class="form-item">
            <label>默认视图模式</label>
            <select v-model="newModelForm.view_mode">
              <option value="threejs">3D模型 (Three.js)</option>
              <option value="isometric">2.5D等角视图</option>
              <option value="svg">2D SVG视图</option>
              <option value="hybrid">2D/3D混合</option>
            </select>
          </div>
        </div>
        <div class="dialog-footer">
          <button class="btn" @click="showNewModelDialog = false">取消</button>
          <button class="btn primary" @click="createNewModel">创建</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.model-editor {
  display: grid;
  grid-template-columns: 260px 1fr 340px;
  grid-template-rows: 1fr 52px;
  height: 100vh;
  background: #0a1120;
  color: #e5e7eb;
  font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
  font-size: 13px;
  overflow: hidden;
}

/* ===== 左侧面板 ===== */
.left-panel {
  grid-row: 1;
  grid-column: 1;
  background: #0d1526;
  border-right: 1px solid #1e2d44;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  padding: 12px 16px;
  font-size: 14px;
  font-weight: 600;
  color: #00d4ff;
  border-bottom: 1px solid #1e2d44;
  background: #0f1a2e;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.header-icon {
  font-size: 10px;
  color: #00d4ff;
}

.parts-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.part-item {
  padding: 10px 12px;
  margin-bottom: 4px;
  border-radius: 6px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.15s;
  background: #111a2e;
}
.part-item:hover {
  border-color: #2a4060;
  background: #142035;
}
.part-item.selected {
  border-color: #00d4ff;
  background: #0a2030;
  box-shadow: 0 0 8px rgba(0, 212, 255, 0.2);
}

.part-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.part-color-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 1px solid #334466;
  flex-shrink: 0;
}
.part-name {
  font-weight: 500;
  color: #d5dce8;
}

.part-info {
  display: flex;
  gap: 6px;
  font-size: 11px;
  line-height: 1.5;
}
.info-label {
  color: #5a6a85;
  width: 28px;
  flex-shrink: 0;
}
.info-value {
  color: #8090a8;
  font-family: 'Consolas', monospace;
}

/* ===== 中央 3D 视图 ===== */
.center-view {
  grid-row: 1;
  grid-column: 2;
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.view-toolbar {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(13, 21, 38, 0.85);
  border: 1px solid #1e2d44;
  border-radius: 8px;
  padding: 6px 10px;
  backdrop-filter: blur(6px);
}
.toolbar-group {
  display: flex;
  gap: 4px;
}
.tool-btn {
  padding: 4px 12px;
  background: #1a2640;
  border: 1px solid #2a3854;
  border-radius: 4px;
  color: #9ca3af;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.15s;
}
.tool-btn:hover {
  background: #233454;
  color: #d5dce8;
}
.tool-btn.active {
  background: #00d4ff;
  color: #0a1120;
  border-color: #00d4ff;
  font-weight: 600;
}
.toolbar-hint {
  font-size: 12px;
  color: #6b7a94;
}

.editor-canvas {
  width: 100%;
  height: 100%;
  display: block;
  cursor: default;
}

/* ===== 右侧面板 ===== */
.right-panel {
  grid-row: 1;
  grid-column: 3;
  background: #0d1526;
  border-left: 1px solid #1e2d44;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.panel-section {
  border-bottom: 1px solid #1e2d44;
}
.panel-section .panel-header {
  position: sticky;
  top: 0;
  z-index: 1;
}

.prop-group {
  padding: 8px 16px;
}
.prop-group-title {
  font-size: 11px;
  color: #5a6a85;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.prop-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.prop-row label {
  font-size: 11px;
  color: #6b7a94;
  width: 14px;
  text-align: center;
  flex-shrink: 0;
}
.prop-row.color-row {
  gap: 10px;
}

.prop-input {
  flex: 1;
  min-width: 0;
  background: #0a1120;
  border: 1px solid #1e2d44;
  border-radius: 4px;
  color: #e5e7eb;
  padding: 4px 6px;
  font-size: 12px;
  font-family: 'Consolas', monospace;
  width: 100%;
}
.prop-input:focus {
  outline: none;
  border-color: #00d4ff;
  box-shadow: 0 0 0 1px rgba(0, 212, 255, 0.3);
}
.prop-input.full {
  flex: 1;
}
.prop-input.sm {
  padding: 3px 4px;
  font-size: 11px;
  width: 60px;
  flex: 0 0 60px;
}
.prop-input.xs {
  padding: 3px 4px;
  font-size: 11px;
  width: 0;
  flex: 1;
  min-width: 0;
}

.prop-select {
  flex: 1;
  background: #0a1120;
  border: 1px solid #1e2d44;
  border-radius: 4px;
  color: #e5e7eb;
  padding: 5px 8px;
  font-size: 12px;
  cursor: pointer;
  width: 100%;
}
.prop-select:focus {
  outline: none;
  border-color: #00d4ff;
}
.prop-select.xs {
  padding: 3px 4px;
  font-size: 11px;
  flex: 1;
}

.color-input {
  width: 36px;
  height: 28px;
  border: 1px solid #1e2d44;
  border-radius: 4px;
  cursor: pointer;
  background: transparent;
  padding: 2px;
  flex-shrink: 0;
}
.color-hex {
  font-family: 'Consolas', monospace;
  font-size: 12px;
  color: #8090a8;
}

.action-btn {
  display: block;
  margin: 8px 16px 12px;
  padding: 7px 12px;
  background: #0a2030;
  border: 1px solid #00d4ff;
  border-radius: 4px;
  color: #00d4ff;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition: all 0.15s;
  width: calc(100% - 32px);
}
.action-btn:hover:not(:disabled) {
  background: #00d4ff;
  color: #0a1120;
}
.action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.action-btn.sm {
  width: auto;
  margin: 0;
  padding: 4px 10px;
  font-size: 11px;
}

.kf-count {
  color: #5a6a85;
  font-weight: 400;
  margin-left: 4px;
}

.kf-actions {
  display: flex;
  gap: 8px;
  padding: 8px 16px;
}

.kf-list {
  padding: 0 16px 8px;
  max-height: 400px;
  overflow-y: auto;
}

.kf-item {
  background: #0a1120;
  border: 1px solid #1a2640;
  border-radius: 4px;
  padding: 8px;
  margin-bottom: 6px;
}
.kf-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.kf-index {
  font-size: 11px;
  color: #00d4ff;
  font-weight: 600;
  flex-shrink: 0;
}
.kf-time {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
}
.kf-time label {
  font-size: 10px;
  color: #5a6a85;
}
.kf-delete {
  padding: 2px 8px;
  background: transparent;
  border: 1px solid #ef4444;
  border-radius: 3px;
  color: #ef4444;
  cursor: pointer;
  font-size: 11px;
  transition: all 0.15s;
}
.kf-delete:hover {
  background: #ef4444;
  color: #fff;
}

.kf-row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
}
.kf-label {
  font-size: 10px;
  color: #5a6a85;
  width: 36px;
  flex-shrink: 0;
}

.kf-empty {
  padding: 16px;
  text-align: center;
  color: #5a6a85;
  font-size: 12px;
}

.empty-hint {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: #5a6a85;
  font-size: 13px;
}
.empty-icon {
  font-size: 48px;
  color: #1e2d44;
}

/* ===== 底部工具栏 ===== */
.bottom-toolbar {
  grid-row: 2;
  grid-column: 1 / -1;
  background: #0f1a2e;
  border-top: 1px solid #1e2d44;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
}

.tool-bar-btn {
  padding: 6px 18px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s;
  border: 1px solid;
}
.tool-bar-btn.save {
  background: #0a2030;
  border-color: #00d4ff;
  color: #00d4ff;
}
.tool-bar-btn.save:hover {
  background: #00d4ff;
  color: #0a1120;
}
.tool-bar-btn.load {
  background: #0a2030;
  border-color: #10b981;
  color: #10b981;
}
.tool-bar-btn.load:hover {
  background: #10b981;
  color: #0a1120;
}
.tool-bar-btn.reset {
  background: #0a2030;
  border-color: #f59e0b;
  color: #f59e0b;
}
.tool-bar-btn.reset:hover {
  background: #f59e0b;
  color: #0a1120;
}
.tool-bar-btn.preview {
  background: #0a2030;
  border-color: #8b5cf6;
  color: #8b5cf6;
}
.tool-bar-btn.preview:hover:not(:disabled) {
  background: #8b5cf6;
  color: #0a1120;
}
.tool-bar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.toolbar-status {
  color: #f59e0b;
  font-size: 12px;
  margin-left: auto;
}

/* ===== 滚动条样式 ===== */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: #0a1120;
}
::-webkit-scrollbar-thumb {
  background: #1e2d44;
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: #2a4060;
}

/* ===== 响应式 ===== */
@media (max-width: 1200px) {
  .model-editor {
    grid-template-columns: 220px 1fr 300px;
  }
}
@media (max-width: 900px) {
  .model-editor {
    grid-template-columns: 200px 1fr 280px;
  }
}

/* ===== 型号管理 ===== */
.panel-section {
  padding: 0 12px;
}
.panel-divider {
  height: 1px;
  background: #1e2d44;
  margin: 8px 0;
}
.model-selector {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.model-select {
  width: 100%;
  background: #0a1120;
  border: 1px solid #1e2d44;
  border-radius: 4px;
  color: #e5e7eb;
  padding: 6px 8px;
  font-size: 12px;
}
.model-actions {
  display: flex;
  gap: 4px;
}
.mini-btn {
  flex: 1;
  padding: 4px 6px;
  background: #1e2d44;
  border: 1px solid #2a4060;
  border-radius: 3px;
  color: #94a3b8;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s;
}
.mini-btn:hover {
  background: #2a4060;
  color: #e5e7eb;
}
.mini-btn.danger:hover {
  background: #ef4444;
  border-color: #ef4444;
  color: #fff;
}
.model-info {
  margin-top: 10px;
  background: #0a1120;
  border: 1px solid #1e2d44;
  border-radius: 4px;
  padding: 6px 8px;
}
.model-info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  padding: 2px 0;
}
.info-tag {
  background: #0a2030;
  color: #38bdf8;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
}

/* ===== 对话框 ===== */
.dialog-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}
.dialog {
  background: #0f1a2e;
  border: 1px solid #1e2d44;
  border-radius: 8px;
  width: 420px;
  max-width: 90vw;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}
.dialog-header {
  padding: 14px 20px;
  font-size: 15px;
  font-weight: 600;
  color: #e5e7eb;
  border-bottom: 1px solid #1e2d44;
}
.dialog-body {
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.dialog-footer {
  padding: 12px 20px;
  border-top: 1px solid #1e2d44;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.form-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.form-item label {
  font-size: 12px;
  color: #94a3b8;
}
.form-item input,
.form-item select {
  background: #0a1120;
  border: 1px solid #1e2d44;
  border-radius: 4px;
  color: #e5e7eb;
  padding: 6px 10px;
  font-size: 13px;
}
.form-item input:focus,
.form-item select:focus {
  outline: none;
  border-color: #3b82f6;
}
.btn {
  padding: 6px 16px;
  background: #1e2d44;
  border: 1px solid #2a4060;
  border-radius: 4px;
  color: #e5e7eb;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.btn:hover {
  background: #2a4060;
}
.btn.primary {
  background: #3b82f6;
  border-color: #3b82f6;
}
.btn.primary:hover {
  background: #2563eb;
}

/* ===== 右侧Tab ===== */
.right-tabs {
  display: flex;
  border-bottom: 1px solid #1e2d44;
  background: #0f1a2e;
}
.right-tab {
  flex: 1;
  padding: 10px 0;
  background: transparent;
  border: none;
  color: #64748b;
  font-size: 13px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
}
.right-tab:hover {
  color: #94a3b8;
}
.right-tab.active {
  color: #3b82f6;
  border-bottom-color: #3b82f6;
}
.tab-content {
  flex: 1;
  overflow-y: auto;
  padding-bottom: 12px;
}
.panel-header .right {
  margin-left: auto;
}
.panel-header .mini-btn {
  padding: 2px 8px;
  font-size: 11px;
}

/* ===== 事件列表 ===== */
.event-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 200px;
  overflow-y: auto;
}
.event-item {
  background: #0a1120;
  border: 1px solid #1e2d44;
  border-radius: 4px;
  padding: 8px 10px;
  cursor: pointer;
  transition: all 0.15s;
}
.event-item:hover {
  border-color: #2a4060;
}
.event-item.active {
  border-color: #3b82f6;
  background: #0a1628;
}
.event-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.event-name {
  font-size: 12px;
  font-weight: 500;
  color: #e5e7eb;
}
.icon-btn {
  background: transparent;
  border: none;
  color: #64748b;
  font-size: 16px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}
.icon-btn:hover {
  color: #ef4444;
}
.event-item-meta {
  display: flex;
  gap: 6px;
}
.meta-tag {
  background: #0f1a2e;
  color: #64748b;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
}

/* ===== 动作步骤 ===== */
.action-steps {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 350px;
  overflow-y: auto;
}
.action-step {
  background: #0a1120;
  border: 1px solid #1e2d44;
  border-radius: 4px;
  overflow: hidden;
}
.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: #0f1a2e;
  border-bottom: 1px solid #1e2d44;
}
.step-index {
  background: #3b82f6;
  color: #fff;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}
.step-body {
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
</style>
