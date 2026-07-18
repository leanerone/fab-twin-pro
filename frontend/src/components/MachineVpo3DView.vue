<script setup>
import { ref, onMounted, onUnmounted, watch, computed, nextTick } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { useEventActionMapping } from '../composables/useEventActionMapping.js'

const props = defineProps({
  machine: { type: Object, default: () => null },
  modelConfig: { type: Object, default: null },
  currentState: { type: String, default: 'idle' },
  metrics: { type: Object, default: () => ({}) },
  runState: { type: Object, default: null },
  events: { type: Array, default: () => [] },
  paused: { type: Boolean, default: false },
  mode: { type: String, default: 'realtime' },  // realtime / playback
})

const containerRef = ref(null)

let scene, camera, renderer, controls
let machineGroup = null
let latchGroup = null
let podShellGroup = null
let cassetteGroup = null
let scanLine = null
let signalGroup = null
let leftHandGroup = null
let rightHandGroup = null
let animId = null
let resizeHandler = null
let autoLoopTimer = null

const MODEL_SCALE = 0.005
const DEFAULT_MODEL_URL = '/models/vpo-2200-3d.json'

const POD_BOTTOM_Z_BASE = 148 * MODEL_SCALE
const POD_TOP_Z = 680 * MODEL_SCALE
const POD_SHELL_HEIGHT = 300 * MODEL_SCALE
const POD_BASE_Y = -36 * MODEL_SCALE
const POD_ENTRY_Y = -436 * MODEL_SCALE
const POD_ENTRY_Z_OFFSET = 200 * MODEL_SCALE
const WAFER_COUNT = 25

const geometryCache = new Map()
const materialCache = new Map()
const modelTemplateCache = new Map()

function getCachedGeometry(key, factory) {
  if (!geometryCache.has(key)) geometryCache.set(key, factory())
  return geometryCache.get(key)
}

function getCachedMaterial(key, factory) {
  if (!materialCache.has(key)) materialCache.set(key, factory())
  return materialCache.get(key)
}

const stateColors = {
  idle: '#9CA3AF',
  running: '#22C55E',
  hold: '#F59E0B',
  alarm: '#EF4444',
  maintenance: '#3B82F6',
}

const {
  podProgress,
  podDirection,
  waferLocation,
  chamberState,
  alarmInfo,
  podLocked,
  scanActive,
  signalActive,
  processEvent,
  processEvents,
} = useEventActionMapping(props)

const modelUrl = computed(() => {
  const cfg = props.modelConfig
  return cfg?.views_config?.view_3d?.model_source || DEFAULT_MODEL_URL
})

const cameraConfig = computed(() => {
  const cfg = props.modelConfig?.views_config?.view_3d?.default_camera
  return cfg || { position: [4, -6, 3], target: [0, 0, 2] }
})

const currentColor = computed(() => {
  const s = chamberState.value || props.currentState || 'idle'
  return stateColors[s] || stateColors.idle
})

const currentPhase = ref('IDLE')
const phaseProgress = ref(0)
const autoLoopRunning = ref(false)
const currentFlowType = ref('attach')

function toThreeCoords(x, y, z) {
  return new THREE.Vector3(
    (x || 0) * MODEL_SCALE,
    (z || 0) * MODEL_SCALE,
    -(y || 0) * MODEL_SCALE,
  )
}

function toThreeRotation(rx, ry, rz) {
  return new THREE.Euler(
    (rx || 0) * Math.PI / 180,
    (rz || 0) * Math.PI / 180,
    -(ry || 0) * Math.PI / 180,
  )
}

function parseColor(color) {
  return new THREE.Color(color || '#aaaaaa')
}

function createBoxPart(part) {
  const size = part.size || [100, 100, 100]
  const geoKey = `box:${size[0]},${size[1]},${size[2]}`
  const geo = getCachedGeometry(geoKey, () => new THREE.BoxGeometry(size[0] * MODEL_SCALE, size[2] * MODEL_SCALE, size[1] * MODEL_SCALE))
  const colorKey = part.color || '#aaaaaa'
  const mat = getCachedMaterial(colorKey, () => new THREE.MeshStandardMaterial({
    color: parseColor(part.color),
    metalness: 0.5,
    roughness: 0.4,
  }))
  const mesh = new THREE.Mesh(geo, mat)
  const pos = toThreeCoords(...(part.position || [0, 0, 0]))
  mesh.position.copy(pos)
  const rot = toThreeRotation(...(part.rotation_deg || [0, 0, 0]))
  mesh.rotation.copy(rot)
  mesh.castShadow = true
  mesh.receiveShadow = true
  mesh.userData.partId = part.id
  return mesh
}

function createCylinderPart(part) {
  const size = part.size || [50, 50, 100]
  const geoKey = `cyl:${size[0]},${size[1]},${size[2]}`
  const geo = getCachedGeometry(geoKey, () => new THREE.CylinderGeometry(
    size[0] * MODEL_SCALE,
    size[1] * MODEL_SCALE,
    size[2] * MODEL_SCALE,
    24,
  ))
  const colorKey = part.color || '#aaaaaa'
  const mat = getCachedMaterial(colorKey, () => new THREE.MeshStandardMaterial({
    color: parseColor(part.color),
    metalness: 0.5,
    roughness: 0.4,
  }))
  const mesh = new THREE.Mesh(geo, mat)
  const pos = toThreeCoords(...(part.position || [0, 0, 0]))
  mesh.position.copy(pos)
  const rot = toThreeRotation(...(part.rotation_deg || [0, 0, 0]))
  mesh.rotation.copy(rot)
  mesh.castShadow = true
  mesh.receiveShadow = true
  mesh.userData.partId = part.id
  return mesh
}

async function loadModelJson(url) {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`加载模型失败: ${url}`)
  return res.json()
}

function buildMachineFromJson(model) {
  const modelId = model.model_id || model.modelId || 'vpo-default'
  if (modelTemplateCache.has(modelId)) {
    return modelTemplateCache.get(modelId).clone(true)
  }

  const group = new THREE.Group()
  const parts = model.parts || []
  parts.forEach(part => {
    let mesh
    if (part.type === 'box') mesh = createBoxPart(part)
    else if (part.type === 'cylinder') mesh = createCylinderPart(part)
    else mesh = createBoxPart(part)
    group.add(mesh)
  })

  modelTemplateCache.set(modelId, group.clone(true))
  return group
}

function createPodShellGroup() {
  const group = new THREE.Group()
  group.userData.isPodShell = true

  const baseMat = new THREE.MeshStandardMaterial({
    color: 0x2d3748,
    transparent: true,
    opacity: 0.88,
    metalness: 0.3,
    roughness: 0.5,
  })

  const bodyMat = new THREE.MeshStandardMaterial({
    color: 0x10b981,
    transparent: true,
    opacity: 0.45,
    metalness: 0.1,
    roughness: 0.2,
    side: THREE.DoubleSide,
  })

  const handleMat = new THREE.MeshStandardMaterial({
    color: 0x047857,
    transparent: true,
    opacity: 0.8,
    metalness: 0.2,
    roughness: 0.4,
  })

  const tagMat = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    metalness: 0.1,
    roughness: 0.3,
  })

  const baseGeo = new THREE.BoxGeometry(300 * MODEL_SCALE, 16 * MODEL_SCALE, 240 * MODEL_SCALE)
  const base = new THREE.Mesh(baseGeo, baseMat)
  base.position.y = 8 * MODEL_SCALE
  base.castShadow = true
  base.receiveShadow = true
  base.userData.partName = 'pod_base'
  group.add(base)

  const bodyGeo = new THREE.BoxGeometry(300 * MODEL_SCALE, POD_SHELL_HEIGHT, 240 * MODEL_SCALE)
  const body = new THREE.Mesh(bodyGeo, bodyMat)
  body.position.y = 16 * MODEL_SCALE + POD_SHELL_HEIGHT / 2
  body.castShadow = true
  body.receiveShadow = true
  body.userData.partName = 'pod_body'
  group.add(body)

  const handleGeo = new THREE.BoxGeometry(100 * MODEL_SCALE, 16 * MODEL_SCALE, 30 * MODEL_SCALE)
  const handle = new THREE.Mesh(handleGeo, handleMat)
  handle.position.y = 16 * MODEL_SCALE + POD_SHELL_HEIGHT + 8 * MODEL_SCALE
  handle.castShadow = true
  handle.userData.partName = 'pod_handle'
  group.add(handle)

  const tagGeo = new THREE.BoxGeometry(80 * MODEL_SCALE, 40 * MODEL_SCALE, 8 * MODEL_SCALE)
  const tag = new THREE.Mesh(tagGeo, tagMat)
  tag.position.set(0, 56 * MODEL_SCALE, 116 * MODEL_SCALE)
  tag.castShadow = true
  tag.userData.partName = 'pod_tag'
  group.add(tag)

  return group
}

function createCassetteGroup() {
  const group = new THREE.Group()
  group.userData.isCassette = true

  const frameMat = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    metalness: 0.05,
    roughness: 0.4,
  })

  const slotMat = new THREE.MeshStandardMaterial({
    color: 0x94a3b8,
    metalness: 0.1,
    roughness: 0.5,
    transparent: true,
    opacity: 0.7,
  })

  const waferMat = new THREE.MeshStandardMaterial({
    color: 0x6b7280,
    metalness: 0.2,
    roughness: 0.6,
  })

  const waferEdgeMat = new THREE.MeshStandardMaterial({
    color: 0x4b5563,
    metalness: 0.3,
    roughness: 0.5,
  })

  const barcodeBorderMat = new THREE.MeshStandardMaterial({
    color: 0x000000,
    metalness: 0.0,
    roughness: 1.0,
  })

  const cassetteBaseGeo = new THREE.BoxGeometry(238 * MODEL_SCALE, 10 * MODEL_SCALE, 124 * MODEL_SCALE)
  const cassetteBase = new THREE.Mesh(cassetteBaseGeo, frameMat)
  cassetteBase.position.set(0, 5 * MODEL_SCALE, 0)
  cassetteBase.castShadow = true
  cassetteBase.receiveShadow = true
  group.add(cassetteBase)

  const cassetteBackGeo = new THREE.BoxGeometry(238 * MODEL_SCALE, 254 * MODEL_SCALE, 12 * MODEL_SCALE)
  const cassetteBack = new THREE.Mesh(cassetteBackGeo, frameMat)
  cassetteBack.position.set(0, 127 * MODEL_SCALE, 56 * MODEL_SCALE)
  cassetteBack.castShadow = true
  cassetteBack.receiveShadow = true
  group.add(cassetteBack)

  const cassetteLeftGeo = new THREE.BoxGeometry(12 * MODEL_SCALE, 254 * MODEL_SCALE, 124 * MODEL_SCALE)
  const cassetteLeft = new THREE.Mesh(cassetteLeftGeo, frameMat)
  cassetteLeft.position.set(-113 * MODEL_SCALE, 127 * MODEL_SCALE, 0)
  cassetteLeft.castShadow = true
  cassetteLeft.receiveShadow = true
  group.add(cassetteLeft)

  const cassetteRightGeo = new THREE.BoxGeometry(12 * MODEL_SCALE, 254 * MODEL_SCALE, 124 * MODEL_SCALE)
  const cassetteRight = new THREE.Mesh(cassetteRightGeo, frameMat)
  cassetteRight.position.set(113 * MODEL_SCALE, 127 * MODEL_SCALE, 0)
  cassetteRight.castShadow = true
  cassetteRight.receiveShadow = true
  group.add(cassetteRight)

  const cassetteTopGeo = new THREE.BoxGeometry(238 * MODEL_SCALE, 10 * MODEL_SCALE, 124 * MODEL_SCALE)
  const cassetteTop = new THREE.Mesh(cassetteTopGeo, frameMat)
  cassetteTop.position.set(0, 249 * MODEL_SCALE, 0)
  cassetteTop.castShadow = true
  cassetteTop.receiveShadow = true
  group.add(cassetteTop)

  const frontLipGeo = new THREE.BoxGeometry(238 * MODEL_SCALE, 8 * MODEL_SCALE, 42 * MODEL_SCALE)
  const frontLip = new THREE.Mesh(frontLipGeo, frameMat)
  frontLip.position.set(0, 20 * MODEL_SCALE, -52 * MODEL_SCALE)
  frontLip.castShadow = true
  frontLip.receiveShadow = true
  group.add(frontLip)

  const borderTopGeo = new THREE.BoxGeometry(118 * MODEL_SCALE, 2.4 * MODEL_SCALE, 2 * MODEL_SCALE)
  const borderTop = new THREE.Mesh(borderTopGeo, barcodeBorderMat)
  borderTop.position.set(0, 28 * MODEL_SCALE, -57 * MODEL_SCALE)
  group.add(borderTop)

  const borderBottomGeo = new THREE.BoxGeometry(118 * MODEL_SCALE, 2.4 * MODEL_SCALE, 2 * MODEL_SCALE)
  const borderBottom = new THREE.Mesh(borderBottomGeo, barcodeBorderMat)
  borderBottom.position.set(0, -4 * MODEL_SCALE, -57 * MODEL_SCALE)
  group.add(borderBottom)

  const borderLeftGeo = new THREE.BoxGeometry(2 * MODEL_SCALE, 34 * MODEL_SCALE, 2 * MODEL_SCALE)
  const borderLeft = new THREE.Mesh(borderLeftGeo, barcodeBorderMat)
  borderLeft.position.set(-58 * MODEL_SCALE, 12 * MODEL_SCALE, -57 * MODEL_SCALE)
  group.add(borderLeft)

  const borderRightGeo = new THREE.BoxGeometry(2 * MODEL_SCALE, 34 * MODEL_SCALE, 2 * MODEL_SCALE)
  const borderRight = new THREE.Mesh(borderRightGeo, barcodeBorderMat)
  borderRight.position.set(58 * MODEL_SCALE, 12 * MODEL_SCALE, -57 * MODEL_SCALE)
  group.add(borderRight)

  const barPositions = [-48, -40, -34, -29, -22, -16, -10, -5, 2, 8, 13, 18, 24, 31, 37, 44]
  const barWidths = [2, 4, 2, 3, 5, 2, 4, 2, 6, 3, 2, 5, 2, 4, 3, 2]
  for (let i = 0; i < barPositions.length; i++) {
    const barGeo = new THREE.BoxGeometry(barWidths[i] * MODEL_SCALE, 24 * MODEL_SCALE, 2.5 * MODEL_SCALE)
    const bar = new THREE.Mesh(barGeo, barcodeBorderMat)
    bar.position.set(barPositions[i] * MODEL_SCALE, 12 * MODEL_SCALE, -57 * MODEL_SCALE)
    group.add(bar)
  }

  const slotStartY = 20 * MODEL_SCALE
  const slotEndY = 220 * MODEL_SCALE
  const slotSpacing = (slotEndY - slotStartY) / (WAFER_COUNT - 1)

  for (let i = 0; i < WAFER_COUNT; i++) {
    const slotY = slotStartY + i * slotSpacing

    const slotLeftGeo = new THREE.BoxGeometry(6 * MODEL_SCALE, 2 * MODEL_SCALE, 74 * MODEL_SCALE)
    const slotLeft = new THREE.Mesh(slotLeftGeo, slotMat)
    slotLeft.position.set(-98 * MODEL_SCALE, slotY, 10 * MODEL_SCALE)
    group.add(slotLeft)

    const slotRightGeo = new THREE.BoxGeometry(6 * MODEL_SCALE, 2 * MODEL_SCALE, 74 * MODEL_SCALE)
    const slotRight = new THREE.Mesh(slotRightGeo, slotMat)
    slotRight.position.set(98 * MODEL_SCALE, slotY, 10 * MODEL_SCALE)
    group.add(slotRight)
  }

  for (let i = 0; i < WAFER_COUNT; i++) {
    const waferY = slotStartY + i * slotSpacing
    const waferZOffset = -14 + (i % 3) * 2

    const waferGroup = new THREE.Group()

    const waferGeo = new THREE.CylinderGeometry(107 * MODEL_SCALE, 107 * MODEL_SCALE, 4 * MODEL_SCALE, 48)
    const wafer = new THREE.Mesh(waferGeo, waferMat)
    wafer.rotation.x = Math.PI / 2
    wafer.castShadow = true
    wafer.receiveShadow = true
    waferGroup.add(wafer)

    const edgeGeo = new THREE.TorusGeometry(107 * MODEL_SCALE, 1.5 * MODEL_SCALE, 8, 48)
    const edge = new THREE.Mesh(edgeGeo, waferEdgeMat)
    edge.rotation.x = Math.PI / 2
    waferGroup.add(edge)

    waferGroup.position.set(0, waferY, waferZOffset * MODEL_SCALE)
    waferGroup.userData.waferIndex = i
    group.add(waferGroup)
  }

  return group
}

function createLatchGroup() {
  const group = new THREE.Group()
  group.userData.isLatchGroup = true

  const latchMat = new THREE.MeshStandardMaterial({
    color: 0xef4444,
    metalness: 0.5,
    roughness: 0.4,
  })

  const positions = [
    { x: -156, y: -96, z: 163, side: 'left' },
    { x: -156, y: 24, z: 163, side: 'left' },
    { x: 156, y: -96, z: 163, side: 'right' },
    { x: 156, y: 24, z: 163, side: 'right' },
  ]

  positions.forEach((pos, idx) => {
    const latchGeo = new THREE.BoxGeometry(12 * MODEL_SCALE, 30 * MODEL_SCALE, 24 * MODEL_SCALE)
    const latch = new THREE.Mesh(latchGeo, latchMat.clone())
    latch.position.set(
      pos.x * MODEL_SCALE,
      pos.z * MODEL_SCALE,
      -pos.y * MODEL_SCALE
    )
    latch.userData.isLatch = true
    latch.userData.side = pos.side
    latch.userData.latchIndex = idx
    group.add(latch)
  })

  return group
}

function createScanLine() {
  const group = new THREE.Group()
  group.userData.isScanLine = true

  const scanMat = new THREE.MeshStandardMaterial({
    color: 0xef4444,
    emissive: 0xef4444,
    emissiveIntensity: 0.8,
    transparent: true,
    opacity: 0.9,
  })

  const scanGeo = new THREE.BoxGeometry(84 * MODEL_SCALE, 2 * MODEL_SCALE, 2 * MODEL_SCALE)
  const line = new THREE.Mesh(scanGeo, scanMat)
  line.position.set(0, 0, 0)
  group.add(line)

  group.visible = false
  return group
}

function createHandModel(isLeft = true) {
  const group = new THREE.Group()
  group.userData.isHandModel = true
  group.userData.isLeft = isLeft
  const dir = isLeft ? 1 : -1

  const skinMat = new THREE.MeshStandardMaterial({
    color: 0xeac09a,
    roughness: 0.65,
    metalness: 0.0,
  })
  const darkSkinMat = new THREE.MeshStandardMaterial({
    color: 0xd4a574,
    roughness: 0.7,
    metalness: 0.0,
  })

  const palmGeo = new THREE.BoxGeometry(55 * MODEL_SCALE, 14 * MODEL_SCALE, 48 * MODEL_SCALE)
  const palm = new THREE.Mesh(palmGeo, skinMat)
  palm.position.set(0, 0, 0)
  group.add(palm)

  const palmTopGeo = new THREE.BoxGeometry(50 * MODEL_SCALE, 4 * MODEL_SCALE, 42 * MODEL_SCALE)
  const palmTop = new THREE.Mesh(palmTopGeo, darkSkinMat)
  palmTop.position.set(0, 9 * MODEL_SCALE, 0)
  group.add(palmTop)

  for (let i = 0; i < 4; i++) {
    const fx = (-15 + i * 10) * MODEL_SCALE
    const fGeo = new THREE.CapsuleGeometry(4.5 * MODEL_SCALE, 38 * MODEL_SCALE, 4, 8)
    const finger = new THREE.Mesh(fGeo, skinMat)
    finger.position.set(fx, 32 * MODEL_SCALE, dir * 2 * MODEL_SCALE)
    finger.rotation.x = dir * 0.08 * (i - 1.5)
    group.add(finger)

    const fTipGeo = new THREE.SphereGeometry(5 * MODEL_SCALE, 8, 8)
    const fTip = new THREE.Mesh(fTipGeo, darkSkinMat)
    fTip.position.set(fx, 52 * MODEL_SCALE, dir * 2 * MODEL_SCALE)
    group.add(fTip)
  }

  const thumbGeo = new THREE.CapsuleGeometry(5.5 * MODEL_SCALE, 28 * MODEL_SCALE, 4, 8)
  const thumb = new THREE.Mesh(thumbGeo, skinMat)
  thumb.position.set(dir * 28 * MODEL_SCALE, 12 * MODEL_SCALE, 0)
  thumb.rotation.z = dir * Math.PI / 3.5
  thumb.rotation.y = dir * 0.3
  group.add(thumb)

  const wristGeo = new THREE.CylinderGeometry(16 * MODEL_SCALE, 18 * MODEL_SCALE, 22 * MODEL_SCALE, 12)
  const wrist = new THREE.Mesh(wristGeo, darkSkinMat)
  wrist.position.set(0, -18 * MODEL_SCALE, 0)
  group.add(wrist)

  group.visible = false
  return group
}

function createSignalGroup() {
  const group = new THREE.Group()
  group.userData.isSignalGroup = true

  const signalMat = new THREE.MeshStandardMaterial({
    color: 0xef4444,
    emissive: 0xef4444,
    emissiveIntensity: 0.6,
    transparent: true,
    opacity: 0.8,
  })

  const count = 16
  const totalWidth = 70 * MODEL_SCALE
  const spacing = totalWidth / count

  for (let i = 0; i <= count; i++) {
    const barGeo = new THREE.BoxGeometry(spacing + 0.5 * MODEL_SCALE, 2 * MODEL_SCALE, 2 * MODEL_SCALE)
    const bar = new THREE.Mesh(barGeo, signalMat.clone())
    bar.position.x = -totalWidth / 2 + i * spacing
    bar.userData.signalIndex = i
    group.add(bar)
  }

  group.visible = false
  return group
}

function updateLatchState(locked) {
  if (!latchGroup) return

  const color = locked ? new THREE.Color(0xef4444) : new THREE.Color(0x10b981)
  const angle = locked ? 0 : 35 * Math.PI / 180

  latchGroup.children.forEach(child => {
    if (child.userData.isLatch) {
      child.material.color.copy(color)
      child.material.emissive = new THREE.Color(0x000000)
      if (child.userData.side === 'left') {
        child.rotation.y = -angle
      } else {
        child.rotation.y = angle
      }
    }
  })
}

function updateScanAnimation(time) {
  if (!scanLine) return

  if (scanActive.value) {
    scanLine.visible = true
    const scanProgress = (time / 1000) % 1
    const scanY = 20 * MODEL_SCALE - 40 * MODEL_SCALE * scanProgress

    if (podShellGroup) {
      const tagPos = new THREE.Vector3(0, 56 * MODEL_SCALE, 116 * MODEL_SCALE)
      podShellGroup.localToWorld(tagPos)
      scanLine.position.copy(tagPos)
      scanLine.position.y += scanY
      scanLine.position.z += 4 * MODEL_SCALE
    }
  } else {
    scanLine.visible = false
  }
}

function updateSignalAnimation(time) {
  if (!signalGroup) return

  if (signalActive.value) {
    signalGroup.visible = true
    const t = time / 150

    if (podShellGroup) {
      const tagPos = new THREE.Vector3(0, 56 * MODEL_SCALE, 116 * MODEL_SCALE)
      podShellGroup.localToWorld(tagPos)
      signalGroup.position.copy(tagPos)
      signalGroup.position.y -= 10 * MODEL_SCALE
    }

    signalGroup.children.forEach((bar, idx) => {
      if (bar.userData.signalIndex !== undefined) {
        const x = -35 + idx * (70 / 16)
        const offset = 6 * Math.sin(0.15 * x - t)
        bar.position.z = offset * MODEL_SCALE
        const scale = 0.5 + 0.5 * Math.abs(Math.sin(0.15 * x - t + Math.PI / 4))
        bar.scale.y = scale
        bar.material.opacity = 0.4 + 0.4 * scale
      }
    })
  } else {
    signalGroup.visible = false
  }
}

const ATTACH_PHASES = [
  { name: 'ATTACH_POD_PLACE', duration: 2500, desc: '空POD放置' },
  { name: 'POD_LOCK', duration: 1200, desc: '锁定' },
  { name: 'READ_TAG', duration: 2000, desc: '扫描' },
  { name: 'POD_UP', duration: 3000, desc: 'POD上升' },
  { name: 'POD_DOWN', duration: 3000, desc: 'POD下降罩住' },
  { name: 'WRITE_TAG', duration: 1200, desc: '写入Tag' },
  { name: 'POD_UNLOCK', duration: 1200, desc: '解锁' },
  { name: 'ATTACH_POD_REMOVE', duration: 2500, desc: '满POD移走' },
]

const DETACH_PHASES = [
  { name: 'DETACH_POD_PLACE', duration: 2500, desc: '满POD放置' },
  { name: 'POD_LOCK', duration: 1200, desc: '锁定' },
  { name: 'READ_TAG', duration: 2000, desc: '扫描' },
  { name: 'DETACH_POD_UP', duration: 3000, desc: 'POD上升' },
  { name: 'DETACH_POD_DOWN', duration: 3000, desc: '空POD下降' },
  { name: 'WRITE_TAG', duration: 1200, desc: '写入Tag' },
  { name: 'POD_UNLOCK', duration: 1200, desc: '解锁' },
  { name: 'DETACH_POD_REMOVE', duration: 2500, desc: '空POD移走' },
]

// 事件代码 -> 动画阶段映射 (PACKING穿入流程)
const EVENT_TO_ATTACH_PHASE = {
  'POD_PLACED': 0,
  'COMPLETED_PORT_LOCK': 1,
  'READ_BATTERY': 2,
  'READ_TAG': 2,
  'BATCH_INFO_FROM_ECUI': 2,
  'OPEN_POD': 3,
  'REACH_STAGE': 3,
  'UI_CONFIRM': 4,
  'CLOSE_POD': 4,
  'ACK_UI_DOUBLECHECK': 4,
  'REACH_POS': 5,
  'WRITE_TAG': 5,
  'COMPLETED_PORT_UNLOCK': 6,
  'POD_REMOVED': 7,
}

// 事件代码 -> 动画阶段映射 (UNPACKING脱出流程)
const EVENT_TO_DETACH_PHASE = {
  'UI_CONFIRM': 0,
  'CLOSE_POD': 1,
  'REACH_POS': 2,
  'WRITE_TAG': 5,
  'COMPLETED_PORT_UNLOCK': 6,
  'POD_REMOVED': 7,
}

let currentPhaseIndex = 0
let phaseStartTime = 0
let lastFrameTime = 0

function easeInOut(t) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2
}

function mechanicalEase(t) {
  if (t <= 0) return 0
  if (t >= 1) return 1
  return easeInOut(t)
}

function lerp(a, b, t) {
  return a + (b - a) * t
}

function updatePodAnimation(time) {
  if (!autoLoopRunning.value) return
  // 暂停时停止动画推进
  if (props.paused) {
    autoLoopRunning.value = false
    return
  }

  const deltaTime = time - lastFrameTime
  lastFrameTime = time

  const phases = currentFlowType.value === 'attach' ? ATTACH_PHASES : DETACH_PHASES
  const phase = phases[currentPhaseIndex]
  const elapsed = time - phaseStartTime
  const progress = Math.min(1, elapsed / phase.duration)
  const easedProgress = mechanicalEase(progress)

  phaseProgress.value = easedProgress
  currentPhase.value = phase.name

  updateVisualsByPhase(phase.name, easedProgress)

  if (progress >= 1) {
    // 实时模式：阶段完成后停止动画，等待下一个事件
    if (props.mode === 'realtime') {
      autoLoopRunning.value = false
      return
    }
    // 回放模式：自动推进到下一个阶段
    currentPhaseIndex++
    phaseStartTime = time

    if (currentPhaseIndex >= phases.length) {
      currentPhaseIndex = 0
      currentFlowType.value = currentFlowType.value === 'attach' ? 'detach' : 'attach'
      phaseStartTime = time
    }
  }
}

function updateVisualsByPhase(phaseName, progress) {
  if (!podShellGroup || !cassetteGroup) return

  let podBottomZ = POD_BOTTOM_Z_BASE
  let podVisible = true
  let cassetteVisible = true
  let opPodY = 0
  let opPodZ = 0
  let latchLocked = false
  let scanOn = false
  let signalOn = false
  let scanProgress = 0

  const entryY = -400 * MODEL_SCALE
  const entryZ = 200 * MODEL_SCALE

  switch (phaseName) {
    case 'ATTACH_POD_PLACE':
      podVisible = true
      cassetteVisible = false
      podBottomZ = POD_BOTTOM_Z_BASE
      if (progress < 0.5) {
        const p = progress / 0.5
        opPodY = lerp(entryY, 0, p)
        opPodZ = entryZ
      } else {
        const p = (progress - 0.5) / 0.5
        opPodY = 0
        opPodZ = lerp(entryZ, 0, p)
      }
      latchLocked = false
      break

    case 'POD_LOCK':
      podVisible = true
      cassetteVisible = false
      podBottomZ = POD_BOTTOM_Z_BASE
      opPodY = 0
      opPodZ = 0
      latchLocked = progress > 0.5
      break

    case 'READ_TAG':
      podVisible = true
      cassetteVisible = false
      podBottomZ = POD_BOTTOM_Z_BASE
      opPodY = 0
      opPodZ = 0
      latchLocked = true
      scanOn = true
      scanProgress = progress
      signalOn = progress > 0.3
      break

    case 'POD_UP':
      podVisible = true
      cassetteVisible = true
      podBottomZ = lerp(POD_BOTTOM_Z_BASE, POD_TOP_Z, progress)
      opPodY = 0
      opPodZ = 0
      latchLocked = true
      break

    case 'POD_DOWN':
      podVisible = true
      cassetteVisible = true
      podBottomZ = lerp(POD_TOP_Z, POD_BOTTOM_Z_BASE, progress)
      opPodY = 0
      opPodZ = 0
      latchLocked = true
      break

    case 'WRITE_TAG':
      podVisible = true
      cassetteVisible = true
      podBottomZ = POD_BOTTOM_Z_BASE
      opPodY = 0
      opPodZ = 0
      latchLocked = true
      scanOn = true
      scanProgress = progress
      signalOn = progress > 0.3
      break

    case 'POD_UNLOCK':
      podVisible = true
      cassetteVisible = true
      podBottomZ = POD_BOTTOM_Z_BASE
      opPodY = 0
      opPodZ = 0
      latchLocked = progress < 0.5
      break

    case 'ATTACH_POD_REMOVE':
      podVisible = true
      cassetteVisible = true
      podBottomZ = POD_BOTTOM_Z_BASE
      if (progress < 0.5) {
        const p = progress / 0.5
        opPodY = 0
        opPodZ = lerp(0, entryZ, p)
      } else {
        const p = (progress - 0.5) / 0.5
        opPodY = lerp(0, entryY, p)
        opPodZ = entryZ
      }
      latchLocked = false
      break

    case 'DETACH_POD_PLACE':
      podVisible = true
      cassetteVisible = true
      podBottomZ = POD_BOTTOM_Z_BASE
      if (progress < 0.5) {
        const p = progress / 0.5
        opPodY = lerp(entryY, 0, p)
        opPodZ = entryZ
      } else {
        const p = (progress - 0.5) / 0.5
        opPodY = 0
        opPodZ = lerp(entryZ, 0, p)
      }
      latchLocked = false
      break

    case 'DETACH_POD_UP':
      podVisible = true
      cassetteVisible = true
      podBottomZ = lerp(POD_BOTTOM_Z_BASE, POD_TOP_Z, progress)
      opPodY = 0
      opPodZ = 0
      latchLocked = true
      break

    case 'DETACH_POD_DOWN':
      podVisible = true
      cassetteVisible = false
      podBottomZ = lerp(POD_TOP_Z, POD_BOTTOM_Z_BASE, progress)
      opPodY = 0
      opPodZ = 0
      latchLocked = true
      break

    case 'DETACH_POD_REMOVE':
      podVisible = true
      cassetteVisible = false
      podBottomZ = POD_BOTTOM_Z_BASE
      if (progress < 0.5) {
        const p = progress / 0.5
        opPodY = 0
        opPodZ = lerp(0, entryZ, p)
      } else {
        const p = (progress - 0.5) / 0.5
        opPodY = lerp(0, entryY, p)
        opPodZ = entryZ
      }
      latchLocked = false
      break

    default:
      podVisible = false
      cassetteVisible = false
      break
  }

  podShellGroup.visible = podVisible
  cassetteGroup.visible = cassetteVisible

  const baseYRaw = -36
  const threeX = 0 + opPodY
  const threeY = podBottomZ + opPodZ
  const threeZ = -(baseYRaw * MODEL_SCALE) - opPodY

  podShellGroup.position.set(threeX, threeY, threeZ)

  const cassetteInPod = phaseName === 'ATTACH_POD_REMOVE' || phaseName === 'DETACH_POD_PLACE'
  if (cassetteInPod) {
    cassetteGroup.position.set(threeX, POD_BOTTOM_Z_BASE + 9 * MODEL_SCALE + opPodZ, threeZ)
  } else {
    cassetteGroup.position.set(0, POD_BOTTOM_Z_BASE + 9 * MODEL_SCALE, -(baseYRaw * MODEL_SCALE))
  }

  updateLatchState(latchLocked)

  scanActive.value = scanOn
  signalActive.value = signalOn

  if (scanLine && scanOn) {
    scanLine.visible = true
    scanLine.position.y = threeY + 56 * MODEL_SCALE + 20 * MODEL_SCALE - 40 * MODEL_SCALE * scanProgress
    scanLine.position.x = threeX
    scanLine.position.z = threeZ + 116 * MODEL_SCALE
  } else if (scanLine) {
    scanLine.visible = false
  }

  const podMoving = opPodY !== 0 || opPodZ !== 0
  if (leftHandGroup) {
    leftHandGroup.visible = podMoving
    if (podMoving) {
      leftHandGroup.position.set(
        threeX - 200 * MODEL_SCALE,
        POD_BOTTOM_Z_BASE + 140 * MODEL_SCALE + opPodZ,
        threeZ
      )
      leftHandGroup.rotation.y = -Math.PI / 2
    }
  }
  if (rightHandGroup) {
    rightHandGroup.visible = podMoving
    if (podMoving) {
      rightHandGroup.position.set(
        threeX + 200 * MODEL_SCALE,
        POD_BOTTOM_Z_BASE + 140 * MODEL_SCALE + opPodZ,
        threeZ
      )
      rightHandGroup.rotation.y = Math.PI / 2
    }
  }
}

function startAutoLoop() {
  if (autoLoopRunning.value) return
  autoLoopRunning.value = true
  currentFlowType.value = 'attach'
  currentPhaseIndex = 0
  phaseStartTime = performance.now()
  lastFrameTime = performance.now()
}

function stopAutoLoop() {
  autoLoopRunning.value = false
  currentPhase.value = 'IDLE'
  phaseProgress.value = 0
}

function triggerAttach() {
  stopAutoLoop()
  currentFlowType.value = 'attach'
  currentPhaseIndex = 0
  phaseStartTime = performance.now()
  lastFrameTime = performance.now()
  autoLoopRunning.value = true
}

function triggerDetach() {
  stopAutoLoop()
  currentFlowType.value = 'detach'
  currentPhaseIndex = 0
  phaseStartTime = performance.now()
  lastFrameTime = performance.now()
  autoLoopRunning.value = true
}

// 跳转到指定阶段并播放（实时模式用）
function jumpToPhase(flowType, phaseIndex) {
  stopAutoLoop()
  currentFlowType.value = flowType
  currentPhaseIndex = phaseIndex
  phaseStartTime = performance.now()
  lastFrameTime = performance.now()
  autoLoopRunning.value = true
  console.log('[VPO3D] 跳转到阶段:', flowType, phaseIndex, 
    flowType === 'attach' ? ATTACH_PHASES[phaseIndex]?.name : DETACH_PHASES[phaseIndex]?.name)
}

// 根据事件代码触发对应阶段动画
function triggerEventPhase(code) {
  // 先尝试穿入流程映射
  if (EVENT_TO_ATTACH_PHASE.hasOwnProperty(code)) {
    const phaseIndex = EVENT_TO_ATTACH_PHASE[code]
    jumpToPhase('attach', phaseIndex)
    return true
  }
  // 再尝试脱出流程映射
  if (EVENT_TO_DETACH_PHASE.hasOwnProperty(code)) {
    const phaseIndex = EVENT_TO_DETACH_PHASE[code]
    jumpToPhase('detach', phaseIndex)
    return true
  }
  return false
}

function initScene() {
  if (!containerRef.value) return

  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x2d3436)

  camera = new THREE.PerspectiveCamera(45, containerRef.value.clientWidth / containerRef.value.clientHeight, 0.1, 100)

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false })
  renderer.setSize(containerRef.value.clientWidth, containerRef.value.clientHeight)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  containerRef.value.appendChild(renderer.domElement)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.05

  const ambient = new THREE.AmbientLight(0xffffff, 0.8)
  scene.add(ambient)

  const mainLight = new THREE.DirectionalLight(0xffffff, 1.5)
  mainLight.position.set(5, 8, 5)
  mainLight.castShadow = true
  mainLight.shadow.mapSize.set(2048, 2048)
  mainLight.shadow.bias = -0.0001
  scene.add(mainLight)

  const fillLight = new THREE.DirectionalLight(0xffffff, 0.6)
  fillLight.position.set(-5, 4, -5)
  scene.add(fillLight)

  const groundGeometry = new THREE.PlaneGeometry(2000 * MODEL_SCALE, 2000 * MODEL_SCALE)
  const groundMaterial = new THREE.MeshStandardMaterial({
    color: 0x1a1a2e,
    roughness: 0.8,
    metalness: 0.1,
  })
  const ground = new THREE.Mesh(groundGeometry, groundMaterial)
  ground.rotation.x = -Math.PI / 2
  ground.position.y = -10 * MODEL_SCALE
  ground.receiveShadow = true
  scene.add(ground)

  const gridHelper = new THREE.GridHelper(1500 * MODEL_SCALE, 50, 0x4a4a6a, 0x2a2a4a)
  gridHelper.position.y = -9 * MODEL_SCALE
  scene.add(gridHelper)
}

async function loadAndBuildMachine() {
  if (!scene) return

  if (machineGroup) {
    scene.remove(machineGroup)
    machineGroup = null
  }

  try {
    const model = await loadModelJson(modelUrl.value)
    machineGroup = buildMachineFromJson(model)
    scene.add(machineGroup)

    latchGroup = createLatchGroup()
    machineGroup.add(latchGroup)

    podShellGroup = createPodShellGroup()
    podShellGroup.position.y = POD_BOTTOM_Z_BASE
    scene.add(podShellGroup)

    cassetteGroup = createCassetteGroup()
    cassetteGroup.position.y = POD_BOTTOM_Z_BASE + 9 * MODEL_SCALE
    cassetteGroup.visible = false
    scene.add(cassetteGroup)

    scanLine = createScanLine()
    scene.add(scanLine)

    signalGroup = createSignalGroup()
    scene.add(signalGroup)

    leftHandGroup = createHandModel(true)
    leftHandGroup.visible = false
    scene.add(leftHandGroup)

    rightHandGroup = createHandModel(false)
    rightHandGroup.visible = false
    scene.add(rightHandGroup)

    updateLatchState(false)
  } catch (e) {
    console.error('[MachineVpo3DView] 加载3D模型失败:', e)
  }
}

function setupCamera() {
  camera.position.set(-6, 5, 10)
  controls.target.set(0, 2, 0)
  controls.update()
}

function animate(time) {
  animId = requestAnimationFrame(animate)

  updatePodAnimation(time)
  updateScanAnimation(time)
  updateSignalAnimation(time)

  controls.update()
  renderer.render(scene, camera)
}

function onResize() {
  if (!containerRef.value || !camera || !renderer) return
  const w = containerRef.value.clientWidth
  const h = containerRef.value.clientHeight
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  renderer.setSize(w, h)
}

watch(() => props.events, (evts) => {
  if (!evts || evts.length === 0) return
  processEvents(evts)
}, { deep: true })

watch(() => props.currentState, (state) => {
  chamberState.value = (state || 'idle').toLowerCase()
})

// 监听事件，驱动动画
let lastEventTs = ''
// mode切换时重置lastEventTs，避免历史事件触发动画
// 实时模式下，events由MachineDetail保证只包含新事件
watch(() => props.mode, () => {
  lastEventTs = ''
  // 停止当前动画
  stopAutoLoop()
  currentPhase.value = 'IDLE'
})

watch(() => props.events, (evs) => {
  if (!Array.isArray(evs) || evs.length === 0) return
  // displayEvents 是倒序的，最新的在 index 0
  const latest = evs[0]
  const latestTs = latest?.timestamp || latest?.event_ts_utc || ''
  console.log('[VPO3D] events变化, mode=', props.mode, 'latestTs=', latestTs, 'lastEventTs=', lastEventTs, 'paused=', props.paused)
  if (latestTs === lastEventTs) return
  // 实时模式下，如果lastEventTs为空（初始状态），且事件时间比当前时间早很多，说明是历史数据，不触发动画
  if (props.mode === 'realtime' && lastEventTs === '') {
    const eventTime = new Date(latestTs.replace(/Z$/, '')).getTime()
    const now = Date.now()
    // 如果事件时间早于5分钟前，认为是历史数据，不触发动画
    if (now - eventTime > 5 * 60 * 1000) {
      console.log('[VPO3D] 实时模式下跳过历史事件，时间差=', (now - eventTime) / 1000, '秒')
      lastEventTs = latestTs
      return
    }
  }
  lastEventTs = latestTs
  const code = (latest?.event_code || latest?.event_name || '').toUpperCase()
  console.log('[VPO3D] 处理事件 code=', code, 'event_code=', latest?.event_code, 'event_name=', latest?.event_name)
  // 实时模式和回放模式都使用事件-阶段映射
  const triggered = triggerEventPhase(code)
  if (!triggered) {
    console.log('[VPO3D] 事件未匹配到动画阶段:', code)
  }
  // 暂停状态下，跳转到阶段后停止动画，只显示静态画面
  if (props.paused) {
    if (triggered) {
      stopAutoLoop()
      // 手动更新一帧画面
      const phases = currentFlowType.value === 'attach' ? ATTACH_PHASES : DETACH_PHASES
      const phase = phases[currentPhaseIndex]
      if (phase) {
        updateVisualsByPhase(phase.name, 0)
      }
    }
    return
  }
  // 回放模式下，确保自动循环播放已启动
  if (props.mode === 'playback' && triggered) {
    if (!autoLoopRunning.value) {
      autoLoopRunning.value = true
    }
  }
  // 扫描/读取标签效果
  if (/SCAN|READ_TAG|READ_BATTERY/.test(code)) {
    scanActive.value = true
    setTimeout(() => { scanActive.value = false }, 1500)
  }
  // 写入标签效果
  if (/WRITE_TAG/.test(code)) {
    signalActive.value = true
    setTimeout(() => { signalActive.value = false }, 2000)
  }
  // 告警
  if (/ALARM|ABORT|ERROR/.test(code)) {
    chamberState.value = 'alarm'
  }
  // 端口锁定
  if (/LOCK|COMPLETED_PORT_LOCK/.test(code) && !/UNLOCK/.test(code)) {
    // 锁定状态由 processEvent 处理
  }
  // 解锁/完成
  if (/UNLOCK|COMPLETED_PORT_UNLOCK|COMPLETE|END|FINISH/.test(code)) {
    chamberState.value = 'running'
  }
  // 打开/关闭POD盖
  if (/OPEN_POD/.test(code)) {
    // 盖子打开动画由 processEvent 处理
  }
}, { deep: true })

// 监听暂停状态
watch(() => props.paused, (isPaused) => {
  if (isPaused) {
    stopAutoLoop()
  } else if (props.mode === 'playback') {
    // 回放模式下恢复动画
    // 实时模式下由事件驱动，不自动启动
  }
})

onMounted(async () => {
  await nextTick()
  initScene()
  await loadAndBuildMachine()
  setupCamera()
  lastFrameTime = performance.now()
  animate(performance.now())
  resizeHandler = () => onResize()
  window.addEventListener('resize', resizeHandler)
  onResize()
  // 不再自动播放，动画由 props.events 驱动
})

onUnmounted(() => {
  stopAutoLoop()
  if (animId) cancelAnimationFrame(animId)
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  if (renderer) {
    renderer.dispose()
    if (containerRef.value && renderer.domElement && renderer.domElement.parentNode === containerRef.value) {
      containerRef.value.removeChild(renderer.domElement)
    }
  }
  if (machineGroup && scene) scene.remove(machineGroup)
  if (podShellGroup && scene) scene.remove(podShellGroup)
  if (cassetteGroup && scene) scene.remove(cassetteGroup)
  if (scanLine && scene) scene.remove(scanLine)
  if (signalGroup && scene) scene.remove(signalGroup)
  if (leftHandGroup && scene) scene.remove(leftHandGroup)
  if (rightHandGroup && scene) scene.remove(rightHandGroup)
})

defineExpose({ triggerAttach, triggerDetach, startAutoLoop, stopAutoLoop })
</script>

<template>
  <div ref="containerRef" class="vpo3d-viewer">


    <div class="vpo3d-status">
      <div class="status-indicator" :style="{ background: currentColor }"></div>
      <span class="status-text">{{ chamberState || currentState }}</span>
      <span class="phase-text">{{ currentPhase }}</span>
      <span class="pod-progress">进度: {{ Math.round(phaseProgress * 100) }}%</span>
      <span v-if="podLocked" class="lock-indicator">锁定</span>
      <span v-if="scanActive" class="scan-indicator">扫描</span>
      <span v-if="signalActive" class="signal-indicator">信号</span>
    </div>

    <div class="vpo3d-label">PODOPENER-1 3D View</div>
  </div>
</template>

<style scoped>
.vpo3d-viewer {
  position: relative;
  width: 100%;
  height: 100%;
  background: #2d3436;
  border-radius: 8px;
  overflow: hidden;
}

.vpo3d-status {
  position: absolute;
  top: 56px;
  right: 14px;
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(13, 20, 36, 0.9);
  backdrop-filter: blur(8px);
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 12px;
  color: #94a3b8;
  z-index: 10;
  flex-wrap: wrap;
  max-width: calc(100% - 28px);
}

.status-indicator {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.status-text {
  color: #e5e7eb;
  font-weight: 600;
}

.phase-text {
  color: #a78bfa;
  font-weight: 500;
}

.pod-progress {
  color: #3b82f6;
}

.lock-indicator {
  color: #ef4444;
}

.scan-indicator {
  color: #f59e0b;
  animation: pulse 1s infinite;
}

.signal-indicator {
  color: #22c55e;
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.vpo3d-label {
  position: absolute;
  top: 14px;
  left: 14px;
  font-size: 14px;
  font-weight: 700;
  color: #e5e7eb;
  z-index: 10;
}
</style>
