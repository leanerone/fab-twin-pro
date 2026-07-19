<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useAnimationConfig } from '../composables/useAnimationConfig.js'

// === 统一动画配置（M1 配置层）===
// 加载 /configs/machine-animations/podopener.json，2D/3D 共用
const animConfig = useAnimationConfig('podopener')
const animConfigReady = ref(false)
// 配置 phase key → 2D 视图阶段 key 的映射（PACKING）
const PACKING_KEY_MAP_2D = {
  'POD_PLACE': 'ATTACH_POD_PLACE',
  'POD_UP': 'ATTACH_POD_UP',
  'POD_DOWN': 'ATTACH_POD_DOWN',
  'POD_REACH_STAGE': 'ATTACH_POD_REACH_STAGE',
  'CST_PLACE': 'ATTACH_CST_PLACE',
  'POD_REACH_POS': 'ATTACH_POD_REACH_POS',
  'POD_REMOVE': 'ATTACH_POD_REMOVE',
  'POD_LOCK': 'POD_LOCK',
  'READ_TAG': 'READ_TAG',
  'BATCH_CONFIRM': 'BATCH_START',
  'UI_CONFIRM': 'UI_CONFIRM',
  'UI_DOUBLECHECK': 'UI_DOUBLECHECK',
  'WRITE_TAG': 'WRITE_TAG',
  'POD_UNLOCK': 'POD_UNLOCK',
}
const UNPACKING_KEY_MAP_2D = {
  'POD_PLACE': 'DETACH_POD_PLACE',
  'POD_UP': 'DETACH_POD_UP',
  'POD_DOWN': 'DETACH_POD_DOWN',
  'POD_REACH_STAGE': 'DETACH_POD_REACH_STAGE',
  'CST_REMOVE': 'DETACH_CST_REMOVE',
  'POD_REACH_POS': 'DETACH_POD_REACH_POS',
  'POD_REMOVE': 'DETACH_POD_REMOVE',
  'POD_LOCK': 'POD_LOCK',
  'READ_TAG': 'READ_TAG',
  'BATCH_CONFIRM': 'BATCH_START',
  'UI_CONFIRM': 'DETACH_CST_REMOVE',
  'UI_DOUBLECHECK': 'DETACH_POD_REACH_POS',
  'WRITE_TAG': 'WRITE_TAG',
  'POD_UNLOCK': 'POD_UNLOCK',
}

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
const svgRef = ref(null)

const PHASE_DURATION = 1600

// === 阶段定义：默认硬编码作为 fallback，配置加载后覆盖 ===
let ATTACH_FLOW = [
  { key: 'ATTACH_POD_PLACE', label: '空POD放置', duration: PHASE_DURATION },
  { key: 'POD_LOCK', label: 'POD锁定', duration: PHASE_DURATION * 0.6 },
  { key: 'READ_TAG', label: '扫描标签', duration: PHASE_DURATION * 1.2 },
  { key: 'BATCH_START', label: '信号确认', duration: PHASE_DURATION * 0.8 },
  { key: 'ATTACH_POD_UP', label: 'POD上升', duration: PHASE_DURATION * 1.4 },
  { key: 'ATTACH_POD_REACH_STAGE', label: 'POD到顶', duration: PHASE_DURATION * 0.4 },
  { key: 'ATTACH_CST_PLACE', label: '放入晶舟', duration: PHASE_DURATION * 1.2 },
  { key: 'UI_CONFIRM', label: 'UI确认', duration: PHASE_DURATION * 0.5 },
  { key: 'ATTACH_POD_DOWN', label: 'POD下降', duration: PHASE_DURATION * 1.4 },
  { key: 'ATTACH_POD_REACH_POS', label: 'POD到底', duration: PHASE_DURATION * 0.4 },
  { key: 'UI_DOUBLECHECK', label: '二次确认', duration: PHASE_DURATION * 0.5 },
  { key: 'WRITE_TAG', label: '写入标签', duration: PHASE_DURATION * 1 },
  { key: 'POD_UNLOCK', label: 'POD解锁', duration: PHASE_DURATION * 0.6 },
  { key: 'ATTACH_POD_REMOVE', label: '满POD移走', duration: PHASE_DURATION },
  { key: 'IDLE_ATTACH', label: '待机', duration: PHASE_DURATION * 0.6 },
]

let DETACH_FLOW = [
  { key: 'DETACH_POD_PLACE', label: '满POD放置', duration: PHASE_DURATION },
  { key: 'POD_LOCK', label: 'POD锁定', duration: PHASE_DURATION * 0.6 },
  { key: 'READ_TAG', label: '扫描标签', duration: PHASE_DURATION * 1.2 },
  { key: 'BATCH_START', label: '信号确认', duration: PHASE_DURATION * 0.8 },
  { key: 'DETACH_POD_UP', label: 'POD上升', duration: PHASE_DURATION * 1.4 },
  { key: 'DETACH_POD_REACH_STAGE', label: 'POD到顶', duration: PHASE_DURATION * 0.4 },
  { key: 'DETACH_CST_REMOVE', label: '移走晶舟', duration: PHASE_DURATION * 1.2 },
  { key: 'DETACH_POD_DOWN', label: 'POD下降', duration: PHASE_DURATION * 1.4 },
  { key: 'DETACH_POD_REACH_POS', label: 'POD到底', duration: PHASE_DURATION * 0.4 },
  { key: 'WRITE_TAG', label: '写入标签', duration: PHASE_DURATION * 1 },
  { key: 'POD_UNLOCK', label: 'POD解锁', duration: PHASE_DURATION * 0.6 },
  { key: 'DETACH_POD_REMOVE', label: '空POD移走', duration: PHASE_DURATION },
  { key: 'IDLE_DETACH', label: '待机', duration: PHASE_DURATION * 0.6 },
]

/**
 * 从统一配置构建本组件使用的阶段/事件映射格式
 */
function applyConfigToPhases() {
  const cfg = animConfig.config.value
  if (!cfg) return
  const packingPhases = cfg.flows?.PACKING?.phases || []
  const unpackingPhases = cfg.flows?.UNPACKING?.phases || []
  const packingEvtMap = cfg.flows?.PACKING?.event_to_phase || {}
  const unpackingEvtMap = cfg.flows?.UNPACKING?.event_to_phase || {}

  if (packingPhases.length) {
    ATTACH_FLOW = packingPhases.map(p => ({
      key: PACKING_KEY_MAP_2D[p.key] || p.key,
      label: p.label,
      duration: p.duration_ms,
      _configKey: p.key,
    }))
    // 追加 IDLE 阶段
    ATTACH_FLOW.push({ key: 'IDLE_ATTACH', label: '待机', duration: PHASE_DURATION * 0.6 })
    EVENT_TO_ATTACH_PHASE = {}
    for (const [evt, def] of Object.entries(packingEvtMap)) {
      const phaseKey = PACKING_KEY_MAP_2D[def.phase] || def.phase
      EVENT_TO_ATTACH_PHASE[evt] = phaseKey
    }
  }
  if (unpackingPhases.length) {
    DETACH_FLOW = unpackingPhases.map(p => ({
      key: UNPACKING_KEY_MAP_2D[p.key] || p.key,
      label: p.label,
      duration: p.duration_ms,
      _configKey: p.key,
    }))
    DETACH_FLOW.push({ key: 'IDLE_DETACH', label: '待机', duration: PHASE_DURATION * 0.6 })
    EVENT_TO_DETACH_PHASE = {}
    for (const [evt, def] of Object.entries(unpackingEvtMap)) {
      const phaseKey = UNPACKING_KEY_MAP_2D[def.phase] || def.phase
      EVENT_TO_DETACH_PHASE[evt] = phaseKey
    }
  }
  animConfigReady.value = true
  console.log('[VPO2D] 统一配置已加载', {
    attach: ATTACH_FLOW.length, detach: DETACH_FLOW.length,
    attachEvt: Object.keys(EVENT_TO_ATTACH_PHASE).length,
    detachEvt: Object.keys(EVENT_TO_DETACH_PHASE).length,
  })
}

let animationFrameId = null
let startTime = 0
let currentCycleType = 'attach'
let currentPhaseIndex = 0
let phaseStartTime = 0

const currentPhaseLabel = ref('待机')
const cycleTypeLabel = ref('ATTACH')

let EVENT_TO_ATTACH_PHASE = {
  'POD_PLACED': 'ATTACH_POD_PLACE',
  'COMPLETED_PORT_LOCK': 'POD_LOCK',
  'READ_BATTERY': 'READ_TAG',
  'READ_TAG': 'READ_TAG',
  'BATCH_INFO_FROM_ECUI': 'BATCH_START',
  'OPEN_POD': 'ATTACH_POD_UP',
  'REACH_STAGE': 'ATTACH_POD_REACH_STAGE',
  'UI_CONFIRM': 'UI_CONFIRM',
  'CLOSE_POD': 'ATTACH_POD_DOWN',
  'ACK_UI_DOUBLECHECK': 'UI_DOUBLECHECK',
  'REACH_POS': 'ATTACH_POD_REACH_POS',
  'WRITE_TAG': 'WRITE_TAG',
  'COMPLETED_PORT_UNLOCK': 'POD_UNLOCK',
  'POD_REMOVED': 'ATTACH_POD_REMOVE',
}

let EVENT_TO_DETACH_PHASE = {
  'POD_PLACED': 'DETACH_POD_PLACE',
  'COMPLETED_PORT_LOCK': 'POD_LOCK',
  'READ_BATTERY': 'READ_TAG',
  'READ_TAG': 'READ_TAG',
  'BATCH_INFO_FROM_ECUI': 'BATCH_START',
  'OPEN_POD': 'DETACH_POD_UP',
  'REACH_STAGE': 'DETACH_POD_REACH_STAGE',
  'UI_CONFIRM': 'DETACH_CST_REMOVE',
  'CLOSE_POD': 'DETACH_POD_DOWN',
  'ACK_UI_DOUBLECHECK': 'DETACH_POD_REACH_POS',
  'REACH_POS': 'DETACH_POD_REACH_POS',
  'WRITE_TAG': 'WRITE_TAG',
  'COMPLETED_PORT_UNLOCK': 'POD_UNLOCK',
  'POD_REMOVED': 'DETACH_POD_REMOVE',
}

function easeInOut(t) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2
}

function mechanicalEase(t) {
  if (t <= 0) return 0
  if (t >= 1) return 1
  return easeInOut(t)
}

function lerp(from, to, t) {
  return from + (to - from) * t
}

function getCurrentFlow() {
  return currentCycleType === 'attach' ? ATTACH_FLOW : DETACH_FLOW
}

function createSvgElement(tag, attrs = {}) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag)
  Object.entries(attrs).forEach(([key, value]) => {
    el.setAttribute(key, String(value))
  })
  return el
}

function draw2DBase() {
  if (!svgRef.value) return
  const svg = svgRef.value
  svg.innerHTML = ''
  svg.setAttribute('viewBox', '0 0 1000 1000')

  const defs = createSvgElement('defs')

  const darkGrad = createSvgElement('linearGradient', {
    id: 'darkGradient',
    x1: '0', x2: '0', y1: '0', y2: '1',
  })
  darkGrad.appendChild(createSvgElement('stop', { offset: '0%', 'stop-color': '#2b333d' }))
  darkGrad.appendChild(createSvgElement('stop', { offset: '100%', 'stop-color': '#111827' }))
  defs.appendChild(darkGrad)

  const softShadow = createSvgElement('filter', {
    id: 'softShadow', x: '-20%', y: '-20%', width: '140%', height: '140%',
  })
  softShadow.appendChild(createSvgElement('feDropShadow', {
    dx: '0', dy: '16', stdDeviation: '12',
    'flood-color': '#0f172a', 'flood-opacity': '0.16',
  }))
  defs.appendChild(softShadow)

  const gridPattern = createSvgElement('pattern', {
    id: 'gridPattern', width: '50', height: '50', patternUnits: 'userSpaceOnUse',
  })
  gridPattern.appendChild(createSvgElement('path', {
    d: 'M 50 0 L 0 0 0 50', fill: 'none', class: 'grid-line',
  }))
  defs.appendChild(gridPattern)

  svg.appendChild(defs)

  svg.appendChild(createSvgElement('rect', { width: '1000', height: '1000', fill: '#f8fafc' }))
  svg.appendChild(createSvgElement('rect', { width: '1000', height: '1000', fill: 'url(#gridPattern)', opacity: '0.55' }))

  svg.appendChild(createSvgElement('ellipse', {
    cx: '506', cy: '906', rx: '386', ry: '52', fill: '#cbd5e1', opacity: '0.45',
  }))

  const titleText = createSvgElement('text', { x: '56', y: '72', class: 'machine-label' })
  titleText.textContent = 'PODOPENER FRONT VIEW'
  svg.appendChild(titleText)

  const subtitleText = createSvgElement('text', { x: '56', y: '98', fill: '#64748b', 'font-size': '13' })
  subtitleText.textContent = 'POD 穿脱循环演示'
  svg.appendChild(subtitleText)

  const mainGroup = createSvgElement('g', { filter: 'url(#softShadow)' })

  mainGroup.appendChild(createSvgElement('rect', {
    x: '285', y: '810', width: '430', height: '80', rx: '10',
    fill: '#5d636a', stroke: '#374151', 'stroke-width': '2',
  }))

  mainGroup.appendChild(createSvgElement('rect', {
    x: '388', y: '694', width: '224', height: '88', rx: '14',
    fill: '#1f2937', stroke: '#111827', 'stroke-width': '2',
  }))

  mainGroup.appendChild(createSvgElement('rect', {
    x: '320', y: '240', width: '45', height: '570', rx: '8',
    fill: '#7a8289', stroke: '#334155', 'stroke-width': '2',
  }))
  mainGroup.appendChild(createSvgElement('rect', {
    x: '635', y: '240', width: '45', height: '570', rx: '8',
    fill: '#7a8289', stroke: '#334155', 'stroke-width': '2',
  }))

  mainGroup.appendChild(createSvgElement('rect', {
    x: '365', y: '278', width: '270', height: '470', rx: '10',
    fill: '#e5ebf1', stroke: '#475569', 'stroke-width': '2',
  }))

  mainGroup.appendChild(createSvgElement('rect', {
    x: '310', y: '228', width: '380', height: '32', rx: '7',
    fill: 'url(#darkGradient)', stroke: '#111827', 'stroke-width': '2',
  }))

  mainGroup.appendChild(createSvgElement('rect', {
    x: '466', y: '66', width: '68', height: '14', rx: '4',
    fill: '#1f2937', stroke: '#111827', 'stroke-width': '1',
  }))

  mainGroup.appendChild(createSvgElement('rect', {
    x: '470', y: '300', width: '6', height: '440',
    fill: '#a8b1ba', stroke: '#64748b', 'stroke-width': '1',
  }))
  mainGroup.appendChild(createSvgElement('rect', {
    x: '524', y: '300', width: '6', height: '440',
    fill: '#a8b1ba', stroke: '#64748b', 'stroke-width': '1',
  }))

  for (let i = 0; i < 16; i++) {
    mainGroup.appendChild(createSvgElement('line', {
      x1: '421', y1: String(304 + 24 * i),
      x2: '579', y2: String(304 + 24 * i),
      stroke: '#7c8793', 'stroke-width': '1',
    }))
  }

  mainGroup.appendChild(createSvgElement('rect', {
    x: '374', y: '742', width: '252', height: '42', rx: '10',
    fill: 'rgba(15,23,42,0.92)', stroke: '#0f172a', 'stroke-width': '1',
  }))

  svg.appendChild(mainGroup)

  const commGroup = createSvgElement('g')
  commGroup.appendChild(createSvgElement('rect', {
    x: '384', y: '790', width: '164', height: '36', rx: '6',
    fill: 'none', stroke: '#475569', 'stroke-width': '2',
  }))
  for (let i = 0; i < 2; i++) {
    for (let j = 0; j < 12; j++) {
      commGroup.appendChild(createSvgElement('circle', {
        cx: String(399 + 12 * j), cy: String(801 + 12 * i), r: '3', class: 'port-pin',
      }))
    }
  }
  svg.appendChild(commGroup)

  const commLabel = createSvgElement('text', { x: '382', y: '846', fill: '#64748b', 'font-size': '12' })
  commLabel.textContent = 'COMM / SERVICE PORTS'
  svg.appendChild(commLabel)

  const controlGroup = createSvgElement('g', { filter: 'url(#softShadow)' })
  controlGroup.appendChild(createSvgElement('rect', {
    x: '130', y: '790', width: '165', height: '70', rx: '10',
    fill: '#111827', stroke: '#0b1020', 'stroke-width': '1.2',
  }))
  controlGroup.appendChild(createSvgElement('circle', {
    cx: '214', cy: '824', r: '18',
    fill: '#f59e0b', stroke: '#7c2d12', 'stroke-width': '1.5',
  }))
  controlGroup.appendChild(createSvgElement('line', {
    x1: '295', y1: '824', x2: '390', y2: '788',
    stroke: '#94a3b8', 'stroke-width': '2',
  }))
  svg.appendChild(controlGroup)

  const frontViewText = createSvgElement('text', {
    x: '748', y: '96', fill: '#0f172a', 'font-size': '16', 'font-weight': '700',
  })
  frontViewText.textContent = 'FRONT VIEW'
  svg.appendChild(frontViewText)

  const opLabel = createSvgElement('text', { x: '92', y: '880', fill: '#0f172a', 'font-size': '12' })
  opLabel.textContent = 'OPERATOR CONTROL BOX'
  svg.appendChild(opLabel)

  const podLayer = createSvgElement('g', { id: 'pod2dLayer' })
  const waferPortLayer = createSvgElement('g', { id: 'waferPort2dLayer' })
  const cassetteLayer = createSvgElement('g', { id: 'cassette2dLayer' })
  const effectLayer = createSvgElement('g', { id: 'effect2dLayer' })

  svg.appendChild(cassetteLayer)
  svg.appendChild(waferPortLayer)
  svg.appendChild(podLayer)
  svg.appendChild(effectLayer)

  const mountPoints = [[320, 240], [680, 240], [320, 890], [680, 890], [347, 812], [652, 812]]
  mountPoints.forEach(([x, y]) => {
    svg.appendChild(createSvgElement('circle', {
      cx: String(x), cy: String(y), r: '8',
      fill: '#f8fafc', stroke: '#334155', 'stroke-width': '2',
    }))
    svg.appendChild(createSvgElement('circle', {
      cx: String(x), cy: String(y), r: '3', fill: '#334155',
    }))
  })
}

function drawCassette(parent, x, y, w, h) {
  parent.appendChild(createSvgElement('rect', {
    x: String(x), y: String(y), width: String(w), height: String(h),
    fill: '#e5e7eb', stroke: '#4b5563', 'stroke-width': '1.2',
  }))

  const padX = 8
  const padY = 6
  const slots = 9
  const step = (h - padY * 2) / (slots - 1)

  for (let i = 0; i < slots; i++) {
    parent.appendChild(createSvgElement('ellipse', {
      cx: String(x + w / 2),
      cy: String(y + padY + i * step),
      rx: String((w - padX * 2) / 2),
      ry: String(Math.max(2.6, step * 0.28)),
      fill: '#6aa0d6',
      stroke: '#3d6f99',
      'stroke-width': '0.9',
    }))
  }
}

function computeAnimationState(now) {
  const flow = getCurrentFlow()
  const phase = flow[currentPhaseIndex]
  const phaseElapsed = now - phaseStartTime
  const phaseProgress = Math.min(1, phaseElapsed / phase.duration)
  const eased = mechanicalEase(phaseProgress)

  const state = {
    cycleType: currentCycleType,
    phaseKey: phase.key,
    phaseProgress: phaseProgress,
    easedProgress: eased,
    carrierY: 730,
    podCoverY: 730 - 210,
    podVisible: true,
    podBaseVisible: true,
    podCoverVisible: true,
    podOffsetX: 0,
    podOffsetY: 0,
    cassetteVisible: false,
    cassetteOffsetY: 0,
    cassetteOffsetX: 0,
    latchLocked: false,
    scanActive: false,
    scanProgress: 0,
    signalActive: false,
    carryWaferWithPod: true,
  }

  if (currentCycleType === 'attach') {
    state.carryWaferWithPod = false
    switch (phase.key) {
      case 'ATTACH_POD_PLACE':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.podOffsetX = lerp(-400, 0, eased)
        state.podOffsetY = lerp(200, 0, eased)
        state.cassetteVisible = false
        state.latchLocked = false
        break
      case 'POD_LOCK':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.latchLocked = true
        state.cassetteVisible = false
        break
      case 'READ_TAG':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.latchLocked = true
        state.scanActive = true
        state.scanProgress = eased
        state.cassetteVisible = false
        break
      case 'BATCH_START':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.latchLocked = true
        state.signalActive = true
        state.cassetteVisible = false
        break
      case 'ATTACH_POD_UP':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.carrierY = lerp(730, 300, eased)
        state.podCoverY = lerp(730 - 210, 300 - 210, eased)
        state.latchLocked = true
        state.cassetteVisible = false
        break
      case 'ATTACH_POD_REACH_STAGE':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.carrierY = 300
        state.podCoverY = 300 - 210
        state.latchLocked = true
        state.cassetteVisible = false
        break
      case 'ATTACH_CST_PLACE':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.carrierY = 300
        state.podCoverY = 300 - 210
        state.latchLocked = true
        state.cassetteVisible = true
        state.cassetteOffsetY = lerp(300, 0, eased)
        break
      case 'UI_CONFIRM':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.carrierY = 300
        state.podCoverY = 300 - 210
        state.latchLocked = true
        state.cassetteVisible = true
        state.signalActive = true
        break
      case 'ATTACH_POD_DOWN':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.carrierY = lerp(300, 730, eased)
        state.podCoverY = lerp(300 - 210, 730 - 210, eased)
        state.latchLocked = true
        state.cassetteVisible = true
        break
      case 'ATTACH_POD_REACH_POS':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.carrierY = 730
        state.podCoverY = 730 - 210
        state.latchLocked = true
        state.cassetteVisible = true
        break
      case 'UI_DOUBLECHECK':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.carrierY = 730
        state.podCoverY = 730 - 210
        state.latchLocked = true
        state.cassetteVisible = true
        state.signalActive = true
        break
      case 'WRITE_TAG':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.carrierY = 730
        state.podCoverY = 730 - 210
        state.latchLocked = true
        state.scanActive = true
        state.scanProgress = eased
        state.cassetteVisible = true
        break
      case 'POD_UNLOCK':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.carrierY = 730
        state.podCoverY = 730 - 210
        state.latchLocked = false
        state.cassetteVisible = true
        break
      case 'ATTACH_POD_REMOVE':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.podOffsetX = lerp(0, 400, eased)
        state.podOffsetY = lerp(0, 200, eased)
        state.cassetteVisible = true
        state.latchLocked = false
        state.carryWaferWithPod = true
        break
      case 'IDLE_ATTACH':
        state.podVisible = false
        state.podCoverVisible = false
        state.podBaseVisible = false
        state.cassetteVisible = false
        state.latchLocked = false
        break
    }
  } else {
    state.carryWaferWithPod = true
    switch (phase.key) {
      case 'DETACH_POD_PLACE':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.podOffsetX = lerp(400, 0, eased)
        state.podOffsetY = lerp(200, 0, eased)
        state.cassetteVisible = true
        state.latchLocked = false
        state.carryWaferWithPod = true
        break
      case 'POD_LOCK':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.latchLocked = true
        state.cassetteVisible = false
        state.carryWaferWithPod = true
        break
      case 'READ_TAG':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.latchLocked = true
        state.scanActive = true
        state.scanProgress = eased
        state.cassetteVisible = false
        state.carryWaferWithPod = true
        break
      case 'BATCH_START':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.latchLocked = true
        state.signalActive = true
        state.cassetteVisible = false
        state.carryWaferWithPod = true
        break
      case 'DETACH_POD_UP':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.carrierY = lerp(730, 300, eased)
        state.podCoverY = lerp(730 - 210, 300 - 210, eased)
        state.latchLocked = true
        state.cassetteVisible = true
        state.cassetteOffsetY = 0
        state.carryWaferWithPod = false
        break
      case 'DETACH_POD_REACH_STAGE':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.carrierY = 300
        state.podCoverY = 300 - 210
        state.latchLocked = true
        state.cassetteVisible = true
        state.carryWaferWithPod = false
        break
      case 'DETACH_CST_REMOVE':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.carrierY = 300
        state.podCoverY = 300 - 210
        state.latchLocked = true
        state.cassetteVisible = true
        state.cassetteOffsetY = lerp(0, 300, eased)
        state.carryWaferWithPod = false
        break
      case 'DETACH_POD_DOWN':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.carrierY = lerp(300, 730, eased)
        state.podCoverY = lerp(300 - 210, 730 - 210, eased)
        state.latchLocked = true
        state.cassetteVisible = false
        break
      case 'DETACH_POD_REACH_POS':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.carrierY = 730
        state.podCoverY = 730 - 210
        state.latchLocked = true
        state.cassetteVisible = false
        break
      case 'WRITE_TAG':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.carrierY = 730
        state.podCoverY = 730 - 210
        state.latchLocked = true
        state.scanActive = true
        state.scanProgress = eased
        state.cassetteVisible = false
        break
      case 'POD_UNLOCK':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.carrierY = 730
        state.podCoverY = 730 - 210
        state.latchLocked = false
        state.cassetteVisible = false
        break
      case 'DETACH_POD_REMOVE':
        state.podVisible = true
        state.podCoverVisible = true
        state.podBaseVisible = true
        state.podOffsetX = lerp(0, -400, eased)
        state.podOffsetY = lerp(0, 200, eased)
        state.cassetteVisible = false
        state.latchLocked = false
        break
      case 'IDLE_DETACH':
        state.podVisible = false
        state.podCoverVisible = false
        state.podBaseVisible = false
        state.cassetteVisible = false
        state.latchLocked = false
        break
    }
  }

  return state
}

function drawAnimation(state, now) {
  const podLayer = document.getElementById('pod2dLayer')
  const waferPortLayer = document.getElementById('waferPort2dLayer')
  const cassetteLayer = document.getElementById('cassette2dLayer')
  const effectLayer = document.getElementById('effect2dLayer')

  if (!podLayer || !waferPortLayer || !cassetteLayer || !effectLayer) return

  podLayer.innerHTML = ''
  waferPortLayer.innerHTML = ''
  cassetteLayer.innerHTML = ''
  effectLayer.innerHTML = ''

  const ns = 'http://www.w3.org/2000/svg'
  const centerX = 506
  const carrierY = state.carrierY
  const podOffsetX = state.podOffsetX
  const podOffsetY = state.podOffsetY

  const latchColor = state.latchLocked ? '#dc2626' : '#16a34a'
  const latchPositions = [
    { x: 348, y: 650, dx: -12 },
    { x: 348, y: 718, dx: -12 },
    { x: 664, y: 650, dx: 12 },
    { x: 664, y: 718, dx: 12 },
  ]
  latchPositions.forEach((pos) => {
    waferPortLayer.appendChild(createSvgElement('rect', {
      x: String(pos.x), y: String(pos.y), width: '14', height: '28', rx: '4',
      fill: latchColor, stroke: '#1f2937', 'stroke-width': '1',
    }))
    if (!state.latchLocked) {
      waferPortLayer.appendChild(createSvgElement('line', {
        x1: String(pos.x + 7), y1: String(pos.y + 14),
        x2: String(pos.x + 7 + pos.dx), y2: String(pos.y + 8),
        stroke: latchColor, 'stroke-width': '4', 'stroke-linecap': 'round',
      }))
    }
  })

  if (state.cassetteVisible && !state.carryWaferWithPod) {
    const cassX = 366
    const cassY = 648 + state.cassetteOffsetY
    const cassW = 268
    const cassH = 94
    drawCassette(cassetteLayer, cassX, cassY, cassW, cassH)
    const label = createSvgElement('text', {
      x: '642', y: String(cassY + 58),
      fill: '#0f172a', 'font-size': '13', 'font-weight': '700',
    })
    label.textContent = 'CASSETTE x25'
    cassetteLayer.appendChild(label)
  }

  if (state.podVisible) {
    const shellX = 344 + podOffsetX
    const shellY = state.podCoverY + podOffsetY
    const shellCenterX = centerX + podOffsetX

    podLayer.appendChild(createSvgElement('ellipse', {
      cx: shellCenterX,
      cy: carrierY + 30 + podOffsetY,
      rx: '108', ry: '20',
      fill: 'rgba(15, 23, 42, 0.12)',
    }))

    if (state.podBaseVisible) {
      podLayer.appendChild(createSvgElement('rect', {
        x: String(312 + podOffsetX),
        y: String(carrierY + podOffsetY),
        width: '376', height: '34',
        fill: '#111827',
        stroke: '#0b1020',
        'stroke-width': '1.3',
      }))

      podLayer.appendChild(createSvgElement('rect', {
        x: String(438 + podOffsetX),
        y: String(carrierY - 8 + podOffsetY),
        width: '124', height: '62', rx: '12',
        fill: '#d7dde3',
        stroke: '#6b7280',
        'stroke-width': '1.2',
      }))

      podLayer.appendChild(createSvgElement('rect', {
        x: String(452 + podOffsetX),
        y: String(carrierY + 6 + podOffsetY),
        width: '96', height: '34', rx: '8',
        fill: '#f3f4f6',
        stroke: '#9ca3af',
        'stroke-width': '1',
      }))

      podLayer.appendChild(createSvgElement('rect', {
        x: String(468 + podOffsetX),
        y: String(carrierY + 34 + podOffsetY),
        width: '10', height: '80',
        fill: '#adb5bd',
        stroke: '#64748b',
        'stroke-width': '1',
      }))
      podLayer.appendChild(createSvgElement('rect', {
        x: String(522 + podOffsetX),
        y: String(carrierY + 34 + podOffsetY),
        width: '10', height: '80',
        fill: '#adb5bd',
        stroke: '#64748b',
        'stroke-width': '1',
      }))

      podLayer.appendChild(createSvgElement('rect', {
        x: String(374 + podOffsetX),
        y: String(carrierY + 10 + podOffsetY),
        width: '252', height: '46', rx: '10',
        fill: 'rgba(100,116,139,0.18)',
        stroke: 'rgba(71,85,105,0.55)',
        'stroke-width': '0.9',
      }))

      const liftLabel = createSvgElement('text', {
        x: String(562 + podOffsetX),
        y: String(carrierY + 54 + podOffsetY),
        fill: '#0f172a', 'font-size': '13', 'font-weight': '700',
      })
      liftLabel.textContent = 'LIFT CARRIER'
      podLayer.appendChild(liftLabel)
    }

    if (state.podCoverVisible) {
      podLayer.appendChild(createSvgElement('rect', {
        x: String(shellX),
        y: String(shellY),
        width: '312', height: '190', rx: '12',
        fill: 'rgba(214,226,235,0.45)',
        stroke: '#6b7280',
        'stroke-width': '1.4',
      }))

      podLayer.appendChild(createSvgElement('rect', {
        x: String(392 + podOffsetX),
        y: String(carrierY - 170 + podOffsetY),
        width: '216', height: '132', rx: '10',
        fill: 'rgba(236,244,251,0.5)',
        stroke: '#9ca3af',
        'stroke-width': '1.1',
      }))

      podLayer.appendChild(createSvgElement('rect', {
        x: String(456 + podOffsetX),
        y: String(carrierY - 130 + podOffsetY),
        width: '88', height: '84', rx: '8',
        fill: 'rgba(248,251,254,0.55)',
        stroke: '#a8b3bd',
        'stroke-width': '1',
      }))

      if (state.carryWaferWithPod && state.cassetteVisible) {
        const cassInPodX = 366 + podOffsetX
        const cassInPodY = carrierY - 92 + podOffsetY
        drawCassette(podLayer, cassInPodX, cassInPodY, 268, 70)
      }

      if (state.scanActive) {
        const scanY = carrierY - 126 + podOffsetY + 70 * state.scanProgress
        podLayer.appendChild(createSvgElement('line', {
          x1: String(456 + podOffsetX),
          y1: String(scanY),
          x2: String(544 + podOffsetX),
          y2: String(scanY),
          stroke: '#ef4444',
          'stroke-width': '3',
          'stroke-linecap': 'round',
        }))

        effectLayer.appendChild(createSvgElement('polygon', {
          points: `${506 + podOffsetX},${carrierY - 86 + podOffsetY} ${640},${carrierY - 120 + podOffsetY} ${640},${carrierY - 50 + podOffsetY}`,
          fill: 'rgba(239, 68, 68, 0.15)',
        }))
        effectLayer.appendChild(createSvgElement('line', {
          x1: String(506 + podOffsetX),
          y1: String(carrierY - 86 + podOffsetY),
          x2: '640',
          y2: String(carrierY - 85 + podOffsetY),
          stroke: 'rgba(248, 113, 113, 0.8)',
          'stroke-width': '3',
          'stroke-linecap': 'round',
        }))
      }

      if (state.signalActive) {
        const wavePoints = []
        const waveTime = now / 180
        for (let i = 0; i <= 12; i++) {
          const px = 452 + podOffsetX + i * 8
          const py = carrierY - 92 + podOffsetY + Math.sin(i * 0.9 - waveTime) * 6
          wavePoints.push(`${px},${py}`)
        }
        podLayer.appendChild(createSvgElement('polyline', {
          points: wavePoints.join(' '),
          fill: 'none',
          stroke: '#ef4444',
          'stroke-width': '2.5',
          'stroke-linecap': 'round',
          'stroke-linejoin': 'round',
        }))

        for (let r = 0; r < 3; r++) {
          const radius = 20 + r * 15 + ((now / 15) % 15)
          const alpha = 0.3 - r * 0.08
          effectLayer.appendChild(createSvgElement('circle', {
            cx: String(506 + podOffsetX),
            cy: String(carrierY - 100 + podOffsetY),
            r: String(radius),
            fill: 'none',
            stroke: `rgba(34, 197, 94, ${alpha})`,
            'stroke-width': '2',
          }))
        }
      }

      const podLabel = createSvgElement('text', {
        x: String(shellCenterX),
        y: String(carrierY - 102 + podOffsetY),
        'text-anchor': 'middle',
        'font-size': '15',
        'font-weight': '800',
        fill: '#0f172a',
      })
      podLabel.textContent = 'POD'
      podLayer.appendChild(podLabel)

      podLayer.appendChild(createSvgElement('rect', {
        x: String(466 + podOffsetX),
        y: String(shellY - 20),
        width: '80', height: '18', rx: '4',
        fill: '#6b7280',
        stroke: '#4b5563',
        'stroke-width': '1',
      }))
    }

    if (podOffsetX !== 0 || podOffsetY !== 0) {
      const leftHandBaseX = 280 + podOffsetX
      const rightHandBaseX = 720 + podOffsetX
      const handBaseY = carrierY - 60 + podOffsetY
      const leftDir = -1
      const rightDir = 1

      function drawCartoonHand(baseX, baseY, dir) {
        const g = createSvgElement('g', {})
        const palmRx = 32
        const palmRy = 26
        g.appendChild(createSvgElement('ellipse', {
          cx: String(baseX + dir * 28), cy: String(baseY),
          rx: String(palmRx), ry: String(palmRy),
          fill: 'rgba(255, 245, 230, 0.92)', stroke: '#c49a6c', 'stroke-width': '2.2',
        }))
        const fingerW = 10
        const fingerH = 28
        for (let i = 0; i < 3; i++) {
          const fx = baseX + dir * (10 + i * 14)
          const fy = baseY - 30 - i * 4
          g.appendChild(createSvgElement('ellipse', {
            cx: String(fx), cy: String(fy),
            rx: String(fingerW / 2), ry: String(fingerH / 2),
            fill: 'rgba(255, 245, 230, 0.92)', stroke: '#c49a6c', 'stroke-width': '1.8',
          }))
        }
        const tx = baseX + dir * 8
        const ty = baseY - 10
        g.appendChild(createSvgElement('ellipse', {
          cx: String(tx), cy: String(ty),
          rx: '7', ry: '16',
          fill: 'rgba(255, 245, 230, 0.92)', stroke: '#c49a6c', 'stroke-width': '1.8',
          transform: `rotate(${dir * 35}, ${tx}, ${ty})`,
        }))
        const cuffW = 36
        const cuffH = 14
        g.appendChild(createSvgElement('rect', {
          x: String(baseX + dir * 44 - cuffW / 2),
          y: String(baseY - cuffH / 2),
          width: String(cuffW), height: String(cuffH), rx: '4',
          fill: '#5c8ad6', stroke: '#3a609e', 'stroke-width': '1.5',
        }))
        return g
      }

      effectLayer.appendChild(drawCartoonHand(leftHandBaseX, handBaseY, leftDir))
      effectLayer.appendChild(drawCartoonHand(rightHandBaseX, handBaseY, rightDir))
    }
  }
}

function animate(now) {
  // 暂停时停止动画循环
  if (props.paused) {
    animationFrameId = null
    return
  }

  if (!startTime) {
    startTime = now
    phaseStartTime = now
  }

  const flow = getCurrentFlow()
  const phase = flow[currentPhaseIndex]
  const phaseElapsed = now - phaseStartTime

  if (phaseElapsed >= phase.duration) {
    // 实时模式：阶段完成后停止动画，等待下一个事件
    if (props.mode === 'realtime') {
      currentPhaseIndex++
      if (currentPhaseIndex >= flow.length) {
        currentPhaseIndex = 0
        currentCycleType = currentCycleType === 'attach' ? 'detach' : 'attach'
        cycleTypeLabel.value = currentCycleType === 'attach' ? 'ATTACH' : 'DETACH'
      }
      const newFlow = getCurrentFlow()
      currentPhaseLabel.value = newFlow[currentPhaseIndex].label
      // 绘制最后一帧然后停止
      const state = computeAnimationState(phaseStartTime + phase.duration)
      drawAnimation(state, phaseStartTime + phase.duration)
      animationFrameId = null
      return
    }

    // 回放模式：自动推进到下一个阶段
    currentPhaseIndex++
    phaseStartTime = now

    if (currentPhaseIndex >= flow.length) {
      currentPhaseIndex = 0
      currentCycleType = currentCycleType === 'attach' ? 'detach' : 'attach'
      cycleTypeLabel.value = currentCycleType === 'attach' ? 'ATTACH' : 'DETACH'
    }

    const newFlow = getCurrentFlow()
    currentPhaseLabel.value = newFlow[currentPhaseIndex].label
  }

  const state = computeAnimationState(now)
  drawAnimation(state, now)

  animationFrameId = requestAnimationFrame(animate)
}

onMounted(async () => {
  await nextTick()
  // 加载统一动画配置（M1 配置层）
  await animConfig.loadConfig()
  applyConfigToPhases()
  draw2DBase()
  currentPhaseLabel.value = '待机'
  cycleTypeLabel.value = 'IDLE'
  // 初始不自动播放，先画一帧待机状态
  if (svgRef.value) {
    const idleState = computeAnimationState(performance.now())
    drawAnimation(idleState, performance.now())
  }
  // 等待新事件驱动，不在加载时立即触发
})

// 监听事件，驱动动画
let lastProcessedTs = ''
// mode切换时重置lastProcessedTs，避免历史事件触发动画
// 实时模式下，events由MachineDetail保证只包含新事件
watch(() => props.mode, () => {
  lastProcessedTs = ''
  // 停止当前动画
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId)
    animationFrameId = null
  }
  currentPhaseLabel.value = '待机'
  cycleTypeLabel.value = 'IDLE'
})

watch(() => props.events, (evs) => {
  if (evs && evs.length) {
    // displayEvents 是倒序的，最新的在 index 0
    const latest = evs[0]
    const latestTs = latest?.timestamp || latest?.event_ts_utc || ''
    // 实时模式下，如果lastProcessedTs为空（初始状态），且事件时间比当前时间早很多，说明是历史数据，不触发动画
    if (props.mode === 'realtime' && lastProcessedTs === '') {
      const eventTime = new Date(latestTs.replace(/Z$/, '')).getTime()
      const now = Date.now()
      // 如果事件时间早于5分钟前，认为是历史数据，不触发动画
      if (now - eventTime > 5 * 60 * 1000) {
        console.log('[VPO2D] 实时模式下跳过历史事件，时间差=', (now - eventTime) / 1000, '秒')
        lastProcessedTs = latestTs
        return
      }
    }
    if (latestTs === lastProcessedTs) return
    handleEventsUpdate(evs)
  }
}, { deep: true })

// 监听暂停状态
watch(() => props.paused, (isPaused) => {
  if (isPaused) {
    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId)
      animationFrameId = null
    }
  } else {
    // 实时模式下不自动启动循环，由事件驱动
    // 回放模式下且非待机状态时恢复动画
    if (props.mode === 'playback' && animationFrameId == null && currentPhaseLabel.value !== '待机') {
      animationFrameId = requestAnimationFrame(animate)
    }
  }
})

function triggerEventPhase(code) {
  if (EVENT_TO_ATTACH_PHASE.hasOwnProperty(code)) {
    const phaseKey = EVENT_TO_ATTACH_PHASE[code]
    setCycleType('attach')
    jumpToPhase(phaseKey)
    console.log('[VPO2D] 事件匹配(穿入):', code, '->', phaseKey)
    return true
  }
  if (EVENT_TO_DETACH_PHASE.hasOwnProperty(code)) {
    const phaseKey = EVENT_TO_DETACH_PHASE[code]
    setCycleType('detach')
    jumpToPhase(phaseKey)
    console.log('[VPO2D] 事件匹配(脱出):', code, '->', phaseKey)
    return true
  }
  console.log('[VPO2D] 事件未匹配到动画阶段:', code)
  return false
}

function handleEventsUpdate(evs) {
  if (!Array.isArray(evs) || !evs.length) return
  const latest = evs[0]
  const ts = latest?.timestamp || latest?.event_ts_utc || ''
  if (ts === lastProcessedTs) return
  lastProcessedTs = ts
  const code = (latest?.event_code || latest?.event_name || '').toUpperCase()
  console.log('[VPO2D] 处理事件 code=', code, 'mode=', props.mode, 'paused=', props.paused)

  if (/ALARM|ABORT|ERROR/.test(code)) {
    cycleTypeLabel.value = 'ALARM'
    currentPhaseLabel.value = '报警'
    return
  }

  const triggered = triggerEventPhase(code)
  if (!triggered) return

  if (props.paused) {
    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId)
      animationFrameId = null
    }
    const state = computeAnimationState(performance.now())
    drawAnimation(state, performance.now())
    return
  }

  if (animationFrameId == null) {
    phaseStartTime = performance.now()
    animationFrameId = requestAnimationFrame(animate)
  }
}

function setCycleType(type) {
  if (currentCycleType !== type) {
    currentCycleType = type
    cycleTypeLabel.value = type === 'attach' ? 'ATTACH' : 'DETACH'
  }
}

function jumpToPhase(phaseKey) {
  const flow = getCurrentFlow()
  const idx = flow.findIndex(p => p.key === phaseKey)
  if (idx >= 0) {
    currentPhaseIndex = idx
    phaseStartTime = performance.now()
    currentPhaseLabel.value = flow[idx].label
  }
}

onUnmounted(() => {
  if (animationFrameId) {
    cancelAnimationFrame(animationFrameId)
  }
})
</script>

<template>
  <div ref="containerRef" class="vpo-viewer">
    <svg ref="svgRef" class="vpo-svg" viewBox="0 0 1000 1000" role="img" aria-label="PODOPENER 2D 视图"></svg>

    <div class="vpo-status-bar">
      <div class="status-item">
        <span class="status-label">循环模式:</span>
        <span class="status-value cycle-label">{{ cycleTypeLabel }}</span>
      </div>
      <div class="status-item">
        <span class="status-label">当前阶段:</span>
        <span class="status-value phase-label">{{ currentPhaseLabel }}</span>
      </div>
    </div>

    <div class="vpo-legend">
      <div class="legend-item"><span class="dot" style="background:#ef4444"></span><span>锁定</span></div>
      <div class="legend-item"><span class="dot" style="background:#22c55e"></span><span>解锁</span></div>
      <div class="legend-item"><span class="dot" style="background:#3b82f6"></span><span>晶圆</span></div>
      <div class="legend-item"><span class="dot" style="background:#f59e0b"></span><span>扫描/信号</span></div>
    </div>
  </div>
</template>

<style scoped>
.vpo-viewer {
  position: relative;
  width: 100%;
  height: 100%;
  background: linear-gradient(180deg, #f8fafc 0%, #edf2f7 100%);
  border-radius: 8px;
  overflow: hidden;
}

.vpo-svg {
  width: 100%;
  height: 100%;
  display: block;
}

.vpo-status-bar {
  position: absolute;
  top: 56px;
  right: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: rgba(13, 20, 36, 0.85);
  backdrop-filter: blur(6px);
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid #1e2d44;
  font-size: 12px;
  z-index: 5;
  min-width: 180px;
}

.status-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.status-label {
  color: #94a3b8;
  font-size: 11px;
}

.status-value {
  color: #e5e7eb;
  font-weight: 600;
  font-size: 12px;
}

.cycle-label {
  color: #22c55e;
  font-weight: 700;
  letter-spacing: 1px;
}

.phase-label {
  color: #f59e0b;
}

.vpo-legend {
  position: absolute;
  right: 12px;
  top: 120px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  background: rgba(13, 20, 36, 0.9);
  backdrop-filter: blur(8px);
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid #1e2d44;
  font-size: 11px;
  color: #94a3b8;
  z-index: 5;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.grid-line {
  stroke: #dbe5ef;
  stroke-width: 1;
}

.machine-outline {
  fill: none;
  stroke: #334155;
  stroke-width: 2;
  stroke-dasharray: 8 7;
  opacity: 0.42;
}

.machine-label {
  fill: #334155;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0;
}

.port-pin {
  fill: #f8fafc;
  stroke: #334155;
  stroke-width: 1;
}
</style>
