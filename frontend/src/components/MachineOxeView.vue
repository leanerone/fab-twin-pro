<script setup>
import { ref, reactive, watch, onMounted, onUnmounted } from 'vue'

// ==================== Props 契约（与 PODOPENER 一致）====================
const props = defineProps({
  machine: { type: Object, default: () => ({}) },
  modelConfig: { type: Object, default: () => ({}) },
  currentState: { type: String, default: 'idle' },
  metrics: { type: Object, default: () => ({}) },
  events: { type: Array, default: () => [] },  // 倒序，最新在 index 0
  paused: { type: Boolean, default: false },
  mode: { type: String, default: 'realtime' },  // 'realtime' / 'playback'
  speed: { type: Number, default: 1 },  // 回放倍速：0.5 / 1 / 2 / 4 / 8 / 16
  currentLotId: { type: String, default: '' },
})

// ==================== 回放倍速：缩放所有动画时长，与事件推进速度保持同步 ====================
function scaleDuration(ms) {
  if (props.mode !== 'playback') return ms
  const s = Math.max(0.25, Number(props.speed) || 1)
  // 最低 30ms，避免极快倍速下动画肉眼完全不可见
  return Math.max(30, Math.round(ms / s))
}

// ==================== Canvas 引用 ====================
const canvasRef = ref(null)
const containerRef = ref(null)
let canvas = null
let ctx = null
let rafId = null

// ==================== HTML 浮层响应式状态（替代 oxe.html 的 document.getElementById 操作）====================
const machineStateText = ref('Idle')
const kpiLot = ref('-')
const kpiRecipe = ref('-')
const kpiEvent = ref('-')
const kpiStateText = ref('Idle')
const kpiStateClass = ref('status-idle')
const timelineEntries = ref([])

// ==================== 从 oxe.html 迁移的 UNITS 坐标定义 ====================
const UNITS = {
  CHAMBER_A: { id: 'CHAMBER_A', name: 'CHAMBER_A', x: -208, y: -220, w: 120, d: 100, h: 0, color: '#a8b7cc' },
  CHAMBER_B: { id: 'CHAMBER_B', name: 'CHAMBER_B', x: -32, y: -220, w: 120, d: 100, h: 0, color: '#a8b7cc' },
  CHAMBER_C: { id: 'CHAMBER_C', name: 'CHAMBER_C', x: 60, y: -48, w: 120, d: 96, h: 0, color: '#a8b7cc' },
  PORT1: { id: 'PORT1', name: 'PORT1', x: -208, y: 120, w: 120, d: 88, h: 0, color: '#8ea0b8' },
  PORT2: { id: 'PORT2', name: 'PORT2', x: -32, y: 120, w: 120, d: 88, h: 0, color: '#8ea0b8' },
  SMIF1: { id: 'SMIF1', name: 'SMIF1', x: -208, y: 208, w: 120, d: 68, h: 0, color: '#6b7280' },
  SMIF2: { id: 'SMIF2', name: 'SMIF2', x: -32, y: 208, w: 120, d: 68, h: 0, color: '#6b7280' },
  PA: { id: 'PA', name: 'PA', x: -300, y: -48, w: 120, d: 96, h: 0, color: '#8b7bd1' },
  ARM: { id: 'ARM', name: 'ARM', x: -180, y: -120, w: 240, d: 240, h: 0, color: '#cfd8e6' },
}

// ==================== 从 oxe.html 迁移的 activeState（改为 reactive）====================
const activeState = reactive({
  chamberCount: 3,
  events: [],
  activeUnitId: 'SMIF1',
  machineState: 'Idle',
  timerId: null,
  index: 0,
  doorProgress: 0,
  portDoorProgress: { PORT1: 0, PORT2: 0 },
  portVisuals: {
    PORT1: { podPlaced: false, podLocked: false, podLift: 0, podPlaceProgress: 0, podCarryProgress: 0, cassetteAt: 'SMIF1', podSmif: 'SMIF1', cassettePos: null, cassetteSlots: new Array(25).fill(true) },
    PORT2: { podPlaced: false, podLocked: false, podLift: 0, podPlaceProgress: 0, podCarryProgress: 0, cassetteAt: 'SMIF2', podSmif: 'SMIF2', cassettePos: null, cassetteSlots: new Array(25).fill(true) },
  },
  chamberStates: { CHAMBER_A: 'idle', CHAMBER_B: 'idle', CHAMBER_C: 'idle' },
  mappingActive: false,
  mappingPortId: 'PORT1',
  mappingPhase: 0,
  movingWafer: null,
  movingWaferLabel: '',
  waferAtPA: false,
  waferInChamber: { CHAMBER_A: false, CHAMBER_B: false, CHAMBER_C: false },
  chamberWaferLabel: { CHAMBER_A: '', CHAMBER_B: '', CHAMBER_C: '' },
  chamberEpoch: { CHAMBER_A: 0, CHAMBER_B: 0, CHAMBER_C: 0 },
  waferMap: { PORT1: new Array(25).fill(0), PORT2: new Array(25).fill(0) },
  armTarget: null,
  lotStatus: {
    PORT1: { lot: 'NULL', status: 'IDLE' },
    PORT2: { lot: 'NULL', status: 'IDLE' },
  },
  alarmLeft: [],
  alarmRight: [],
  alarmExpandedLeft: false,
  alarmExpandedRight: false,
  liveMode: false,
  liveToolId: '',
  liveSessionId: '',
  rafLoopStarted: false,
  lastEventPortId: 'PORT1',
  lastPollRawId: 0,
})

// 运行中的动画取消函数，便于暂停时停止
const activeAnimationCancels = new Set()

// ==================== 工具函数 ====================
function shadeColor(hex, percent) {
  const n = parseInt(hex.slice(1), 16)
  let r = (n >> 16) & 255
  let g = (n >> 8) & 255
  let b = n & 255
  const p = percent / 100
  r = Math.max(0, Math.min(255, Math.round(r + (255 - r) * p)))
  g = Math.max(0, Math.min(255, Math.round(g + (255 - g) * p)))
  b = Math.max(0, Math.min(255, Math.round(b + (255 - b) * p)))
  const s = (r << 16) | (g << 8) | b
  return '#' + s.toString(16).padStart(6, '0')
}

function project(x, y, z) {
  const cx = canvas.clientWidth * 0.5
  const cy = canvas.clientHeight * 0.46
  return { x: cx + x, y: cy + y - (z || 0) * 0.03 }
}

function lerpPoint(a, b, t) {
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t }
}

function statusTextClass(statusText) {
  const s = String(statusText || '').toLowerCase()
  if (s.indexOf('alarm') >= 0) return 'status-alarm-text'
  if (s.indexOf('idle') >= 0) return 'status-idle-text'
  if (s.indexOf('processing') >= 0 || s.indexOf('unloading') >= 0 || s.indexOf('success') >= 0 || s.indexOf('mapping') >= 0 || s.indexOf('pod') >= 0) return 'status-running-text'
  return 'status-info-text'
}

// oxe.html 原本操作 #lotStatusPanel DOM，Vue 中状态由 Canvas 绘制，此函数保留为空以兼容调用
function updateLotPanel() { /* no-op: lot 状态已由 Canvas drawWaferMapPanel 绘制 */ }

function emptyWaferMap() {
  return new Array(25).fill(0)
}

function parseWaferMapString(value) {
  const raw = String(value || '').trim().replace(/[^0123]/g, '')
  if (!raw) return null
  const arr = emptyWaferMap()
  for (let i = 0; i < 25 && i < raw.length; i += 1) {
    const ch = raw.charAt(i)
    if (ch === '1') arr[i] = 1
    else if (ch === '2') arr[i] = 2
    else if (ch === '3') arr[i] = 3
    else arr[i] = 0
  }
  return arr
}

function getWaferMappingValue(ev) {
  if (!ev || typeof ev !== 'object') return ''
  return (ev.EVENT_VALUE || ev.event_value || ev.EVENTVALUE || ev.eventvalue || ev.EventValue || ev.mapping_value || ev.MAPPING_VALUE || ev.alarm_text || ev.ALARM_TEXT || ev.ALTX || '')
}

function applyMappingToPort(portId, ev) {
  const normalizedPort = normalizePortId(portId || ev.port_id || ev.PORT_ID || ev.portid || ev.PORTID || ev.port || ev.PORT)
  const parsed = parseWaferMapString(getWaferMappingValue(ev))
  if (parsed) {
    activeState.waferMap[normalizedPort] = parsed
    getPortVisual(normalizedPort).cassetteSlots = parsed.map(function (v) { return Number(v || 0) > 0 })
    return
  }
  // 修复：mapping_value 为空时 fallback：按 cassetteSlots 推断或默认全部填充为灰色(1)，
  // 避免 Wafer Map 面板一直是空白。
  const portVisual = getPortVisual(normalizedPort)
  const fallback = new Array(25).fill(0)
  const slotsFromVisual = (portVisual && Array.isArray(portVisual.cassetteSlots)) ? portVisual.cassetteSlots : null
  let hasAny = false
  for (let i = 0; i < 25; i += 1) {
    const hasSlot = slotsFromVisual ? !!slotsFromVisual[i] : true
    fallback[i] = hasSlot ? 1 : 0
    if (hasSlot) hasAny = true
  }
  if (hasAny) {
    activeState.waferMap[normalizedPort] = fallback
  }
}

function markWaferAsCompleted(portId, slot) {
  const normalizedPort = normalizePortId(portId)
  const idx = Number(slot) - 1
  if (idx < 0 || idx >= 25) return
  activeState.waferMap[normalizedPort][idx] = 3
}

function markWaferAsRunning(portId, slot) {
  const normalizedPort = normalizePortId(portId)
  const idx = Number(slot) - 1
  if (idx < 0 || idx >= 25) return
  activeState.waferMap[normalizedPort][idx] = 2
}

function normalizePortId(portVal) {
  const s = String(portVal || '').trim().toUpperCase()
  if (s === '2' || s === 'PORT2' || s === 'CM2' || s === 'SMIF2' || s === 'SMIF-2') return 'PORT2'
  if (s === '1' || s === 'PORT1' || s === 'CM1' || s === 'SMIF1' || s === 'SMIF-1') return 'PORT1'
  return 'PORT1'
}

function tryNormalizePortId(portVal) {
  const s = String(portVal || '').trim().toUpperCase()
  if (!s || s === 'NULL' || s === 'N/A' || s === 'NONE') return null
  if (s === '2' || s === 'PORT2' || s === 'CM2' || s === 'SMIF2' || s === 'SMIF-2') return 'PORT2'
  if (s === '1' || s === 'PORT1' || s === 'CM1' || s === 'SMIF1' || s === 'SMIF-1') return 'PORT1'
  return null
}

function normalizeChamberId(chamberId) {
  const s = String(chamberId || '').trim().toUpperCase()
  if (s === 'A' || s === 'CHAMBER_A' || s === 'PMA') return 'CHAMBER_A'
  if (s === 'B' || s === 'CHAMBER_B' || s === 'PMB') return 'CHAMBER_B'
  if (s === 'C' || s === 'CHAMBER_C' || s === 'PMC') return 'CHAMBER_C'
  return 'CHAMBER_A'
}

function resolvePortFromChamber(chamberId) {
  const raw = String(chamberId || '').trim().toUpperCase()
  if (!raw || raw === 'NULL') return null
  if (raw === 'A' || raw === 'CHAMBER_A' || raw === 'PMA') return 'PORT1'
  if (raw === 'B' || raw === 'CHAMBER_B' || raw === 'PMB') return 'PORT2'
  if (raw === 'C' || raw === 'CHAMBER_C' || raw === 'PMC') return 'PORT1'
  const chamber = normalizeChamberId(chamberId)
  if (chamber === 'CHAMBER_A') return 'PORT1'
  if (chamber === 'CHAMBER_B') return 'PORT2'
  return null
}

function resolveEventPortId(ev, fallbackPortId) {
  if (ev) {
    const directPort = tryNormalizePortId(ev.port_id || ev.PORT_ID || ev.portid || ev.PORTID || ev.port || ev.PORT || ev.cm || ev.CM)
    if (directPort) return directPort
    const smifPort = tryNormalizePortId(ev.smif_id || ev.SMIF_ID || ev.smif || ev.SMIF)
    if (smifPort) return smifPort
    const chamberPort = resolvePortFromChamber(ev.chamber_id || ev.CHAMBER_ID || ev.chamber || ev.CHAMBER)
    if (chamberPort) return chamberPort
  }
  const fallback = tryNormalizePortId(fallbackPortId)
  if (fallback) return fallback
  return normalizePortId(fallbackPortId || activeState.lastEventPortId || activeState.mappingPortId || 'PORT1')
}

function portFromEvent(portVal) {
  return resolveEventPortId({ port_id: portVal })
}

function chamberLabel(chamberId) {
  return normalizeChamberId(chamberId)
}

function getActiveLotPorts() {
  const ports = []
  ;['PORT1', 'PORT2'].forEach(function (portId) {
    const info = activeState.lotStatus[portId] || { lot: 'NULL', status: 'IDLE' }
    const lot = String(info.lot || '').toUpperCase()
    const status = String(info.status || '').toUpperCase()
    if (lot && lot !== 'NULL' && status !== 'IDLE') ports.push(portId)
  })
  return ports
}

function getPortVisual(portId) {
  return activeState.portVisuals[normalizePortId(portId)]
}

function smifFromPort(portId) {
  return normalizePortId(portId) === 'PORT2' ? 'SMIF2' : 'SMIF1'
}

function displayUnitLabel(unitId) {
  if (unitId === 'CHAMBER_A' || unitId === 'CHAMBER_B' || unitId === 'CHAMBER_C') return unitId
  return unitId
}

// ==================== 从 oxe.html 迁移的绘制函数 ====================
function drawPoly(points, fill, stroke, width) {
  ctx.beginPath()
  ctx.moveTo(points[0].x, points[0].y)
  for (let i = 1; i < points.length; i += 1) ctx.lineTo(points[i].x, points[i].y)
  ctx.closePath()
  if (fill) { ctx.fillStyle = fill; ctx.fill() }
  if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = width || 1.2; ctx.stroke() }
}

function getTopFace(unit, zOffset) {
  const h = zOffset || 0
  return {
    t1: project(unit.x, unit.y, h),
    t2: project(unit.x + unit.w, unit.y, h),
    t3: project(unit.x + unit.w, unit.y + unit.d, h),
    t4: project(unit.x, unit.y + unit.d, h),
  }
}

function getUnitBaseColor(unit) {
  if (unit.id === 'ARM') return '#cbd5e1'
  if (unit.id === 'CHAMBER_A' || unit.id === 'CHAMBER_B' || unit.id === 'CHAMBER_C') {
    const state = activeState.chamberStates[unit.id] || 'idle'
    if (state === 'running') return '#16a34a'
    if (state === 'alarm') return '#dc2626'
    if (state === 'unloading') return '#ca8a04'
    return '#94a3b8'
  }
  return unit.color
}

function drawPrism(unit, active) {
  const x = unit.x, y = unit.y, w = unit.w, d = unit.d
  const base = getUnitBaseColor(unit)
  const cTop = active ? shadeColor(base, 18) : shadeColor(base, 8)
  const p1 = project(x, y, 0)
  const p2 = project(x + w, y, 0)
  const p3 = project(x + w, y + d, 0)
  const p4 = project(x, y + d, 0)
  drawPoly([p1, p2, p3, p4], cTop, '#334155', 1.2)
  const centerLabel = project(x + w * 0.5, y + d * 0.5, 0)
  ctx.fillStyle = '#eef5fb'
  ctx.font = 'bold 10px Segoe UI'
  ctx.textAlign = 'center'
  if (unit.id !== 'ARM') ctx.fillText(displayUnitLabel(unit.id), centerLabel.x, centerLabel.y + 4)
}

function getVisibleUnits() {
  let arr = [UNITS.PA, UNITS.CHAMBER_A, UNITS.CHAMBER_B, UNITS.CHAMBER_C, UNITS.ARM, UNITS.PORT1, UNITS.PORT2, UNITS.SMIF1, UNITS.SMIF2]
  if (activeState.chamberCount === 2) {
    arr = [UNITS.PA, UNITS.CHAMBER_A, UNITS.CHAMBER_B, UNITS.ARM, UNITS.PORT1, UNITS.PORT2, UNITS.SMIF1, UNITS.SMIF2]
  }
  return arr
}

function getUnitCenter(unitId) {
  const u = UNITS[unitId] || UNITS.SMIF1
  return { x: u.x + u.w * 0.5, y: u.y + u.d * 0.5, z: u.h + 3 }
}

function drawGroundGrid() {
  ctx.strokeStyle = 'rgba(100, 116, 139, 0.14)'
  ctx.lineWidth = 1
  for (let i = -300; i <= 300; i += 30) {
    const p1 = project(i, -240, 0)
    const p2 = project(i, 260, 0)
    ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke()
  }
  for (let i = -240; i <= 260; i += 30) {
    const q1 = project(-300, i, 0)
    const q2 = project(300, i, 0)
    ctx.beginPath(); ctx.moveTo(q1.x, q1.y); ctx.lineTo(q2.x, q2.y); ctx.stroke()
  }
}

function drawArmZonePillar() {
  const arm = UNITS.ARM
  const cx = arm.x + arm.w * 0.5
  const cy = arm.y + arm.d * 0.5
  const rxSmall = arm.w * 0.26
  const rySmall = arm.d * 0.26
  const rxLarge = arm.w * 0.5
  const ryLarge = arm.d * 0.5
  const poly = [
    project(cx - rxSmall, cy - ryLarge, 0), project(cx + rxSmall, cy - ryLarge, 0),
    project(cx + rxLarge, cy - rySmall, 0), project(cx + rxLarge, cy + rySmall, 0),
    project(cx + rxSmall, cy + ryLarge, 0), project(cx - rxSmall, cy + ryLarge, 0),
    project(cx - rxLarge, cy + rySmall, 0), project(cx - rxLarge, cy - rySmall, 0),
  ]
  drawPoly(poly, 'rgba(203, 213, 225, 0.86)', '#334155', 1.8)
  const hub = project(cx, cy, 0)
  ctx.beginPath(); ctx.arc(hub.x, hub.y, 12, 0, Math.PI * 2)
  ctx.strokeStyle = '#64748b'; ctx.lineWidth = 4; ctx.stroke()
  ctx.beginPath(); ctx.arc(hub.x, hub.y, 5, 0, Math.PI * 2)
  ctx.fillStyle = '#f8fafc'; ctx.fill()
  const label = project(cx + arm.w * 0.16, cy + arm.d * 0.18, 0)
  ctx.fillStyle = '#dbeafe'
  ctx.font = 'bold 14px Segoe UI'
  ctx.textAlign = 'center'
  ctx.fillText('ARM', label.x, label.y + 4)
}

function drawPortDoor(unit) {
  const open = Math.max(0, Math.min(1, activeState.portDoorProgress[unit.id] || 0))
  const doorW = unit.w * 0.36
  const doorHClosed = unit.d * 0.072
  const topY = unit.y + unit.d - doorHClosed
  const bottomY = topY + doorHClosed
  const leftClosed = unit.x + (unit.w - doorW) * 0.5
  const slideLeft = unit.w * 0.44
  const left = leftClosed - open * slideLeft
  const right = left + doorW
  const topL = project(left, topY, 0)
  const topR = project(right, topY, 0)
  const botR = project(right, bottomY, 0)
  const botL = project(left, bottomY, 0)
  const fillR = Math.round(192 + (2 - 192) * open)
  const fillG = Math.round(198 + (6 - 198) * open)
  const fillB = Math.round(208 + (23 - 208) * open)
  const fillA = 0.95 + (0.10 - 0.95) * open
  const strokeR = Math.round(120 + (15 - 120) * open)
  const strokeG = Math.round(130 + (23 - 130) * open)
  const strokeB = Math.round(145 + (42 - 145) * open)
  const strokeA = 0.88 + (0.65 - 0.88) * open
  drawPoly([topL, topR, botR, botL],
    'rgba(' + fillR + ', ' + fillG + ', ' + fillB + ', ' + fillA.toFixed(2) + ')',
    'rgba(' + strokeR + ', ' + strokeG + ', ' + strokeB + ', ' + strokeA.toFixed(2) + ')', 1.2)
}

function drawPortDoors() {
  drawPortDoor(UNITS.PORT1)
  drawPortDoor(UNITS.PORT2)
}

function drawWaferMarker(center, color, label) {
  const p = project(center.x, center.y, center.z)
  ctx.save()
  ctx.translate(p.x, p.y)
  ctx.scale(1.45, 0.9)
  ctx.beginPath()
  ctx.arc(0, 0, 9.5, 0, Math.PI * 2)
  ctx.fillStyle = color || '#fde68a'
  ctx.fill()
  ctx.strokeStyle = '#92400e'
  ctx.lineWidth = 1
  ctx.stroke()
  ctx.restore()
  if (label) {
    ctx.fillStyle = '#0f172a'
    ctx.font = 'bold 10px Segoe UI'
    ctx.textAlign = 'center'
    ctx.fillText(label, p.x, p.y + 3)
  }
}

function drawPlacedWafers() {
  if (activeState.waferAtPA) {
    const pa = getUnitCenter('PA')
    drawWaferMarker({ x: pa.x, y: pa.y, z: pa.z + 7 }, '#fef3c7')
  }
  Object.keys(activeState.waferInChamber).forEach(function (key) {
    if (activeState.waferInChamber[key]) {
      const c = getUnitCenter(key)
      const lbl = activeState.chamberWaferLabel[key] || ''
      drawWaferMarker({ x: c.x, y: c.y, z: c.z + 8 }, '#fde68a', lbl)
    }
  })
}

function drawPodShell(center) {
  const p = project(center.x, center.y, center.z + 2)
  const w = 48
  const h = 58
  ctx.fillStyle = 'rgba(31, 41, 55, 0.26)'
  ctx.strokeStyle = 'rgba(15, 23, 42, 0.72)'
  ctx.lineWidth = 1.2
  ctx.beginPath()
  ctx.moveTo(p.x - w / 2, p.y + h / 2 - 8)
  ctx.lineTo(p.x - w / 2, p.y - h / 2 + 10)
  ctx.quadraticCurveTo(p.x - w / 2 + 3, p.y - h / 2, p.x - w / 2 + 12, p.y - h / 2)
  ctx.lineTo(p.x + w / 2 - 12, p.y - h / 2)
  ctx.quadraticCurveTo(p.x + w / 2 - 3, p.y - h / 2, p.x + w / 2, p.y - h / 2 + 10)
  ctx.lineTo(p.x + w / 2, p.y + h / 2 - 8)
  ctx.quadraticCurveTo(p.x + w / 2 - 2, p.y + h / 2, p.x + w / 2 - 10, p.y + h / 2)
  ctx.lineTo(p.x - w / 2 + 10, p.y + h / 2)
  ctx.quadraticCurveTo(p.x - w / 2 + 2, p.y + h / 2, p.x - w / 2, p.y + h / 2 - 8)
  ctx.closePath()
  ctx.fill()
  ctx.stroke()
  ctx.fillStyle = 'rgba(96, 165, 250, 0.22)'
  ctx.fillRect(p.x - 13, p.y + 7, 26, 10)
}

function drawCassetteCarrier(center) {
  const p = project(center.x, center.y, center.z + 2)
  const w = 34
  const h = 48
  ctx.fillStyle = 'rgba(255,255,255,0.88)'
  ctx.strokeStyle = '#cbd5e1'
  ctx.lineWidth = 1
  ctx.fillRect(p.x - w / 2, p.y - h / 2, w, h)
  ctx.strokeRect(p.x - w / 2, p.y - h / 2, w, h)
  ctx.fillStyle = 'rgba(148, 163, 184, 0.28)'
  ctx.fillRect(p.x - w / 2 + 2, p.y - h / 2 + 2, 5, h - 4)
  ctx.fillRect(p.x + w / 2 - 7, p.y - h / 2 + 2, 5, h - 4)
}

function drawPodLockMarks(center, offset) {
  const p = project(center.x, center.y, center.z + offset)
  const s = 5
  const dx = 19
  const dy = 13
  ctx.fillStyle = '#ef4444'
  ctx.fillRect(p.x - dx, p.y + dy - s, s, s)
  ctx.fillRect(p.x + dx - s, p.y + dy - s, s, s)
}

function hasAnyWaferInMap(portId) {
  const map = activeState.waferMap[normalizePortId(portId)] || []
  for (let i = 0; i < map.length; i += 1) {
    if (Number(map[i] || 0) > 0) return true
  }
  return false
}

function getCassetteDisplayCenterForPort(portId) {
  const normalizedPort = normalizePortId(portId)
  const visual = getPortVisual(normalizedPort)
  if (visual.cassettePos) return visual.cassettePos
  if (visual.cassetteAt === 'PORT1' || visual.cassetteAt === 'PORT2') {
    const p = UNITS[visual.cassetteAt]
    return { x: p.x + p.w * 0.5, y: p.y + p.d * 0.64, z: 8 }
  }
  return getUnitCenter(visual.cassetteAt || smifFromPort(normalizedPort))
}

function getCassetteSlotsForPort(portId, fallbackSlots) {
  const normalizedPort = normalizePortId(portId)
  const map = activeState.waferMap[normalizedPort] || []
  if (hasAnyWaferInMap(normalizedPort)) {
    return map.map(function (v) { return Number(v || 0) > 0 })
  }
  return fallbackSlots || new Array(25).fill(false)
}

function getSlotCoord(slotNumber, center) {
  const total = 25
  const idx = Math.max(1, Math.min(total, Number(slotNumber || 1))) - 1
  const startY = center.y + 22
  const pitch = 1.75
  return { x: center.x, y: startY - idx * pitch, z: center.z + 5 }
}

function drawCassetteSlots(center, slots) {
  const slotBox = project(center.x, center.y, center.z + 3)
  const w = 30
  const h = 46
  ctx.fillStyle = 'rgba(226, 232, 240, 0.92)'
  ctx.fillRect(slotBox.x - w / 2, slotBox.y - h / 2, w, h)
  ctx.strokeStyle = '#ffffff'
  ctx.lineWidth = 1
  ctx.strokeRect(slotBox.x - w / 2, slotBox.y - h / 2, w, h)
  for (let i = 1; i <= 25; i += 1) {
    const slotY = slotBox.y + h / 2 - 2 - ((i - 1) * ((h - 6) / 24))
    const present = slots && slots[i - 1]
    ctx.fillStyle = present ? '#fef08a' : '#cbd5e1'
    ctx.fillRect(slotBox.x - 11, slotY - 0.8, 22, 1.6)
  }
}

function drawMovingWafer() {
  if (!activeState.movingWafer) return
  const p = project(activeState.movingWafer.x, activeState.movingWafer.y, activeState.movingWafer.z)
  ctx.save()
  ctx.translate(p.x, p.y)
  ctx.scale(1.45, 0.9)
  ctx.beginPath()
  ctx.arc(0, 0, 9.5, 0, Math.PI * 2)
  ctx.fillStyle = '#fde68a'
  ctx.fill()
  ctx.strokeStyle = '#a16207'
  ctx.lineWidth = 1.1
  ctx.stroke()
  ctx.restore()
  if (activeState.movingWaferLabel) {
    ctx.fillStyle = '#0f172a'
    ctx.font = 'bold 11px Segoe UI'
    ctx.textAlign = 'center'
    ctx.fillText(activeState.movingWaferLabel, p.x, p.y - 13)
  }
}

function drawHandsForPod(center, podPlaceProgress, podCarryProgress) {
  let handProgress = 0
  if (podPlaceProgress < 1) handProgress = Math.max(handProgress, 1 - podPlaceProgress)
  handProgress = Math.max(handProgress, podCarryProgress)
  if (handProgress <= 0.001) return
  const p = project(center.x, center.y, center.z + 2)
  ctx.fillStyle = 'rgba(240, 205, 170, 0.95)'
  ctx.fillRect(p.x - 34, p.y - 6, 12, 22)
  ctx.fillRect(p.x + 22, p.y - 6, 12, 22)
}

function drawRobotArm() {
  const arm = UNITS.ARM
  const center = getUnitCenter('ARM')
  const hub = project(center.x, center.y, 0)
  const target3d = activeState.armTarget || { x: center.x - 8, y: center.y - 12, z: center.z + 8 }
  const target = project(target3d.x, target3d.y, target3d.z)
  const vx = target.x - hub.x
  const vy = target.y - hub.y
  const distance = Math.sqrt(vx * vx + vy * vy)
  const len = Math.min(220, Math.max(24, distance))
  const ux = distance > 0 ? vx / distance : 1
  const uy = distance > 0 ? vy / distance : 0
  const ex = hub.x + ux * len
  const ey = hub.y + uy * len
  const px = -uy
  const py = ux
  ctx.strokeStyle = '#475569'; ctx.lineWidth = 12; ctx.lineCap = 'round'
  ctx.beginPath(); ctx.moveTo(hub.x, hub.y); ctx.lineTo(hub.x + ux * len * 0.55, hub.y + uy * len * 0.55); ctx.stroke()
  ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 8
  ctx.beginPath(); ctx.moveTo(hub.x + ux * len * 0.55, hub.y + uy * len * 0.55); ctx.lineTo(ex, ey); ctx.stroke()
  ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 5
  ctx.beginPath()
  ctx.moveTo(ex, ey); ctx.lineTo(ex + px * 9 - ux * 2, ey + py * 9 - uy * 2)
  ctx.moveTo(ex, ey); ctx.lineTo(ex - px * 9 - ux * 2, ey - py * 9 - uy * 2)
  ctx.stroke()
  ctx.fillStyle = '#64748b'
  ctx.beginPath(); ctx.arc(hub.x, hub.y, 13, 0, Math.PI * 2); ctx.fill()
  ctx.fillStyle = '#e2e8f0'
  ctx.beginPath(); ctx.arc(hub.x, hub.y, 6, 0, Math.PI * 2); ctx.fill()
  ctx.strokeStyle = 'rgba(239, 68, 68, 0.9)'
  ctx.lineWidth = 2
  drawArmZonePillar()
}

function drawPodAndCassetteForPort(portId) {
  const normalizedPort = normalizePortId(portId)
  const visual = getPortVisual(normalizedPort)
  const lotInfo = activeState.lotStatus[normalizedPort] || { lot: 'NULL', status: 'IDLE' }
  const lot = String(lotInfo.lot || '').toUpperCase()
  const status = String(lotInfo.status || '').toUpperCase()
  const lotActive = lot && lot !== 'NULL' && status !== 'IDLE'
  if (!visual.podPlaced && !lotActive) return
  const smifUnitId = visual.podSmif || smifFromPort(normalizedPort)
  const smifCenter = getUnitCenter(smifUnitId)
  const placingOffset = (1 - visual.podPlaceProgress) * 170
  const shellCenter = {
    x: smifCenter.x - placingOffset - visual.podCarryProgress * 170,
    y: smifCenter.y - placingOffset * 0.2 - visual.podCarryProgress * 36,
    z: smifCenter.z + 7 + visual.podLift + (1 - visual.podPlaceProgress) * 4 + visual.podCarryProgress * 6,
  }
  drawPodShell(shellCenter)
  drawHandsForPod(shellCenter, visual.podPlaceProgress, visual.podCarryProgress)
  if (visual.podLocked && visual.podCarryProgress < 0.98) drawPodLockMarks(shellCenter, 0)
  let cassetteCenter
  if (visual.podCarryProgress > 0.001 || visual.podPlaceProgress < 0.999) {
    cassetteCenter = { x: shellCenter.x, y: shellCenter.y, z: shellCenter.z - 2 }
  } else {
    cassetteCenter = getCassetteDisplayCenterForPort(normalizedPort)
  }
  drawCassetteCarrier({ x: cassetteCenter.x, y: cassetteCenter.y, z: cassetteCenter.z + 2 })
  drawCassetteSlots({ x: cassetteCenter.x, y: cassetteCenter.y, z: cassetteCenter.z + 2 }, getCassetteSlotsForPort(normalizedPort, visual.cassetteSlots))
}

function drawPodAndCassette() {
  drawPodAndCassetteForPort('PORT1')
  drawPodAndCassetteForPort('PORT2')
}

function drawMappingScan() {
  if (!activeState.mappingActive) return
  const scanPort = activeState.mappingPortId || 'PORT1'
  const unit = UNITS[scanPort] || UNITS.PORT1
  const mapVisual = getPortVisual(scanPort)
  if (mapVisual.cassetteAt !== scanPort && !mapVisual.cassettePos) return
  const face = getTopFace(unit, 9)
  activeState.mappingPhase += 0.018
  if (activeState.mappingPhase > 2) activeState.mappingPhase = 0
  const t = activeState.mappingPhase <= 1 ? activeState.mappingPhase : (2 - activeState.mappingPhase)
  const a = lerpPoint(face.t1, face.t4, t)
  const b = lerpPoint(face.t2, face.t3, t)
  ctx.strokeStyle = '#ef4444'
  ctx.lineWidth = 2
  ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke()
}

function drawWaferMapPanel(portId, side) {
  const map = activeState.waferMap[portId] || emptyWaferMap()
  const canvasW = canvas.clientWidth
  const panelW = 155
  const panelH = 330
  const x = side === 'right' ? (canvasW - panelW - 10) : 10
  const y = 74
  const lotInfo = activeState.lotStatus[portId] || { lot: '-', status: 'Idle' }
  ctx.fillStyle = 'rgba(250, 252, 255, 0.95)'
  ctx.strokeStyle = '#94a3b8'
  ctx.lineWidth = 1
  ctx.fillRect(x, 10, panelW, 58)
  ctx.strokeRect(x, 10, panelW, 58)
  ctx.fillStyle = '#0f172a'
  ctx.font = 'bold 11px Segoe UI'
  ctx.textAlign = 'left'
  ctx.fillText(portId + ' LOT:' + lotInfo.lot, x + 8, 28)
  ctx.fillText('Status:', x + 8, 46)
  ctx.fillStyle = (lotInfo.status.indexOf('running') >= 0 || lotInfo.status.indexOf('processing') >= 0) ? '#16a34a' : '#0f172a'
  ctx.fillText(lotInfo.status, x + 60, 46)
  ctx.fillStyle = 'rgba(250, 252, 255, 0.92)'
  ctx.strokeStyle = '#94a3b8'
  ctx.lineWidth = 1
  ctx.fillRect(x, y, panelW, panelH)
  ctx.strokeRect(x, y, panelW, panelH)
  ctx.fillStyle = '#0f172a'
  ctx.font = 'bold 11px Segoe UI'
  ctx.textAlign = 'left'
  ctx.fillText(portId + ' WAFER MAP', x + 8, y + 14)
  const top = y + 24
  const rowH = 11.5
  for (let i = 25; i >= 1; i -= 1) {
    const row = 25 - i
    const cy = top + row * rowH
    const status = map[i - 1] || 0
    ctx.fillStyle = '#0f172a'
    ctx.font = '10px Segoe UI'
    ctx.textAlign = 'right'
    const txt = i < 10 ? '0' + i : String(i)
    ctx.fillText(txt, x + 22, cy + 4)
    if (status > 0) {
      ctx.beginPath()
      ctx.ellipse(x + 88, cy + 1, 46, 4.2, 0, 0, Math.PI * 2)
      ctx.fillStyle = status === 1 ? '#9ca3af' : (status === 2 ? '#22c55e' : '#fde047')
      ctx.fill()
      ctx.strokeStyle = '#334155'
      ctx.lineWidth = 0.8
      ctx.stroke()
    }
  }
  const alarmList = (side === 'right') ? activeState.alarmRight : activeState.alarmLeft
  const isExpanded = (side === 'right') ? activeState.alarmExpandedRight : activeState.alarmExpandedLeft
  if (alarmList && alarmList.length > 0) {
    const alarmBoxH = isExpanded ? Math.min(60, 14 + alarmList.length * 14) : 18
    ctx.fillStyle = 'rgba(254, 226, 226, 0.95)'
    ctx.strokeStyle = '#dc2626'
    ctx.lineWidth = 1
    ctx.fillRect(x, y + panelH + 4, panelW, alarmBoxH)
    ctx.strokeRect(x, y + panelH + 4, panelW, alarmBoxH)
    ctx.fillStyle = '#991b1b'
    ctx.font = '9px Segoe UI'
    ctx.textAlign = 'left'
    ctx.fillText('⚠ ALARM (' + alarmList.length + ') ▼', x + 4, y + panelH + 14)
    if (isExpanded) {
      for (let ai = 0; ai < alarmList.length && ai < 3; ai++) {
        const entry = alarmList[ai]
        ctx.fillText('[' + entry.time + '] ' + entry.text.slice(0, 16), x + 4, y + panelH + 28 + ai * 14)
      }
      if (alarmList.length > 3) {
        ctx.fillText('... 共 ' + alarmList.length + ' 条', x + 4, y + panelH + 28 + 3 * 14 - 2)
      }
    }
  }
}

// ==================== render / frameLoop ====================
function render() {
  if (!ctx || !canvas) return
  ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight)
  drawGroundGrid()
  const units = getVisibleUnits()
  units.forEach(function (u) { drawPrism(u, activeState.activeUnitId === u.id) })
  drawRobotArm()
  drawPodAndCassette()
  drawPortDoors()
  drawMappingScan()
  drawPlacedWafers()
  drawMovingWafer()
  drawWaferMapPanel('PORT1', 'left')
  drawWaferMapPanel('PORT2', 'right')
}

function frameLoop() {
  render()
  rafId = requestAnimationFrame(frameLoop)
}

// ==================== KPI / Timeline（替代 oxe.html 的 DOM 操作）====================
function setStateText(state) {
  const value = state || 'Idle'
  kpiStateText.value = value
  kpiStateClass.value = 'status-' + value.toLowerCase()
  machineStateText.value = value
}

function appendTimeline(ev) {
  const t = formatEventTime(ev)
  const eventName = getEffectiveEventName(ev)
  const extraPort = resolveEventPortId(ev, null)
  const extra = extraPort ? ' / ' + extraPort : (ev.chamber_id ? ' / ' + chamberLabel(ev.chamber_id) : '')
  timelineEntries.value.push({ time: t, name: eventName, extra })
  if (timelineEntries.value.length > 200) {
    timelineEntries.value.splice(0, timelineEntries.value.length - 200)
  }
}

// ==================== 事件归一化 ====================
function normalizeIncomingEvent(ev) {
  if (!ev || typeof ev !== 'object') return ev
  const normalized = ev
  let rawType = String(normalized.event_type || normalized.EVENT_TYPE || '').trim().toUpperCase()
  if (rawType === 'ENDMAPPING') rawType = 'WAFER_MAPPING'
  if (rawType) normalized.event_type = rawType
  const semanticNameForNormalize = String((normalized && (normalized.event_name || normalized.status)) || '').trim()
  let effectiveForNormalize = ((rawType === 'VFEI' || rawType === 'VFEO' || rawType === 'HOST' || rawType === '') && semanticNameForNormalize) ? semanticNameForNormalize : (rawType || semanticNameForNormalize)
  if (String(effectiveForNormalize || '').trim().toUpperCase() === 'ENDMAPPING') effectiveForNormalize = 'WAFER_MAPPING'
  effectiveForNormalize = String(effectiveForNormalize || '').trim().toUpperCase()
  if (rawType === 'WAFER_MAPPING' || effectiveForNormalize === 'WAFER_MAPPING') {
    if (!normalized.EVENTVALUE && !normalized.eventvalue && !normalized.EVENT_VALUE && !normalized.event_value) {
      const waferMapRaw = getWaferMappingValue(normalized)
      if (waferMapRaw) normalized.EVENTVALUE = String(waferMapRaw)
    }
  }
  if (!normalized.event_ts_utc) {
    normalized.event_ts_utc = normalized.EVENT_TS_UTC || normalized.event_time_utc || normalized.EVENT_TIME_UTC || normalized.timestamp || normalized.TIMESTAMP || normalized.event_time || normalized.EVENT_TIME || normalized.ts || normalized.TS || normalized.received_ts_utc || normalized.RECEIVED_TS_UTC || ''
  }
  return normalized
}

function getEffectiveEventName(ev) {
  if (!ev || typeof ev !== 'object') return ''
  const rawType = String(ev.event_type || ev.EVENT_TYPE || '').trim().toUpperCase()
  const semanticName = String((ev && (ev.event_name || ev.status)) || '').trim()
  let result
  if ((rawType === 'VFEI' || rawType === 'VFEO' || rawType === 'HOST' || rawType === '') && semanticName) {
    result = semanticName
  } else {
    result = rawType || semanticName
  }
  if (String(result || '').trim().toUpperCase() === 'ENDMAPPING') result = 'WAFER_MAPPING'
  return result.toUpperCase()
}

// ==================== 从 oxe.html 迁移的动画函数 ====================
function animateValue(from, to, durationMs, onUpdate, onDone) {
  let start = 0
  let cancelled = false
  let rafId = null
  function tick(ts) {
    if (cancelled) return
    if (!start) start = ts
    const t = Math.min(1, (ts - start) / durationMs)
    onUpdate(from + (to - from) * t)
    if (t < 1) {
      rafId = requestAnimationFrame(tick)
    } else {
      activeAnimationCancels.delete(cancel)
      if (onDone) onDone()
    }
  }
  function cancel() {
    cancelled = true
    if (rafId) cancelAnimationFrame(rafId)
    activeAnimationCancels.delete(cancel)
  }
  rafId = requestAnimationFrame(tick)
  activeAnimationCancels.add(cancel)
  return cancel
}

function animateCassetteTransfer(portId, fromUnit, toUnit, durationMs, onDone) {
  const visual = getPortVisual(portId)
  const from = getUnitCenter(fromUnit)
  const to = getUnitCenter(toUnit)
  visual.cassetteAt = 'MOVING'
  animateValue(0, 1, durationMs, function (t) {
    visual.cassettePos = {
      x: from.x + (to.x - from.x) * t,
      y: from.y + (to.y - from.y) * t,
      z: from.z + 2 + Math.sin(t * Math.PI) * 6,
    }
  }, function () {
    visual.cassettePos = null
    visual.cassetteAt = toUnit
    if (onDone) onDone()
  })
}

function setCassetteSlotsFromMapping(mappedSlots) {
  const slots = new Array(25)
  for (let i = 0; i < 25; i += 1) slots[i] = false
  if (Array.isArray(mappedSlots) && mappedSlots.length > 0) {
    mappedSlots.forEach(function (slot) {
      const idx = Number(slot) - 1
      if (idx >= 0 && idx < 25) slots[idx] = true
    })
  }
  const mappingPort = normalizePortId(activeState.mappingPortId || 'PORT1')
  getPortVisual(mappingPort).cassetteSlots = slots
}

function setChamberState(chamberId, state) {
  const key = normalizeChamberId(chamberId)
  if (!key || !activeState.chamberStates[key]) return
  activeState.chamberStates[key] = state
}

function bumpChamberEpoch(chamberId) {
  const key = normalizeChamberId(chamberId)
  activeState.chamberEpoch[key] = (activeState.chamberEpoch[key] || 0) + 1
  return activeState.chamberEpoch[key]
}

function applyLotStatusByEvent(ev) {
  const eventName = getEffectiveEventName(ev)
  let cmKey = resolveEventPortId(ev, activeState.lastEventPortId)
  if (eventName === 'STARTMAPPING_RIGHT') cmKey = 'PORT2'
  if (eventName === 'POD_PLACED') activeState.lotStatus[cmKey].status = 'POD_PLACED'
  else if (eventName === 'LOCK_PORT_COMPLETED') activeState.lotStatus[cmKey].status = 'CHECK RCMS'
  else if (eventName === 'MVIN') activeState.lotStatus[cmKey].status = 'loading lot'
  else if (eventName === 'LOAD_CYCLE_STARTED') activeState.lotStatus[cmKey].status = 'LOAD_START'
  else if (eventName === 'LOAD_CYCLE_COMPLETED') activeState.lotStatus[cmKey].status = 'LOAD_OK'
  else if (eventName === 'STARTMAPPING_LEFT' || eventName === 'STARTMAPPING_RIGHT') activeState.lotStatus[cmKey].status = 'StartMapping'
  else if (eventName === 'WAFER_MAPPING' || eventName === 'ENDMAPPING') activeState.lotStatus[cmKey].status = 'EndMapping'
  else if (eventName === 'START') activeState.lotStatus[cmKey].status = 'PP-SELECT OK'
  else if (eventName === 'PS') activeState.lotStatus[cmKey].status = 'Processing'
  else if (eventName === 'PE') activeState.lotStatus[cmKey].status = 'Processing end'
  else if (eventName === 'DOOR_OPEN') activeState.lotStatus[cmKey].status = 'DOOR_OPEN'
  else if (eventName === 'UNLOAD_CYCLE_COMPLETED') activeState.lotStatus[cmKey].status = 'UNLOAD_OK'
  else if (eventName === 'MVOU') activeState.lotStatus[cmKey].status = '出站成功'
  else if (eventName === 'POD_REMOVED') { activeState.lotStatus[cmKey].lot = 'NULL'; activeState.lotStatus[cmKey].status = 'IDLE' }
  else if (eventName === 'BATCH_INFO_FROM_ECUI') {
    activeState.lotStatus[cmKey].lot = ev.lot_id || ev.LOT_ID || ev.lot || 'NULL'
    activeState.lotStatus[cmKey].status = 'BATCH_INFO'
  }
  updateLotPanel()
}

function animateWaferPath(points, durationMs, onDone) {
  activeState.movingWafer = { x: points[0].x, y: points[0].y, z: points[0].z }
  const segments = points.length - 1
  animateValue(0, segments, durationMs, function (value) {
    const idx = Math.min(segments - 1, Math.floor(value))
    const localT = value - idx
    const from = points[idx]
    const to = points[idx + 1]
    activeState.movingWafer = {
      x: from.x + (to.x - from.x) * localT,
      y: from.y + (to.y - from.y) * localT,
      z: from.z + (to.z - from.z) * localT,
    }
    activeState.armTarget = { x: activeState.movingWafer.x, y: activeState.movingWafer.y, z: activeState.movingWafer.z + 2 }
  }, function () {
    activeState.movingWafer = null
    activeState.armTarget = null
    if (onDone) onDone()
  })
}

function getArmHome3D() {
  const center = getUnitCenter('ARM')
  return { x: center.x - 8, y: center.y - 12, z: center.z + 8 }
}

function animateArmTo(target3d, durationMs, carryWafer, onDone) {
  const home = getArmHome3D()
  const from = activeState.armTarget || home
  animateValue(0, 1, durationMs, function (t) {
    activeState.armTarget = {
      x: from.x + (target3d.x - from.x) * t,
      y: from.y + (target3d.y - from.y) * t,
      z: from.z + (target3d.z - from.z) * t,
    }
    if (carryWafer && activeState.movingWafer) {
      activeState.movingWafer = { x: activeState.armTarget.x, y: activeState.armTarget.y, z: activeState.armTarget.z }
    }
  }, function () {
    if (onDone) onDone()
  })
}

function handleWaferLoaded(ev) {
  const slot = Number(ev.slot || ev.wafer_id || ev.slot_id || 1)
  const eventPort = resolveEventPortId(ev, activeState.lastEventPortId)
  const portNo = eventPort === 'PORT2' ? '2' : '1'
  const waferTag = portNo + '-' + slot
  activeState.movingWaferLabel = waferTag
  const cassetteCenter = getCassetteDisplayCenterForPort(eventPort)
  const start = getSlotCoord(slot, cassetteCenter)
  const arm = getArmHome3D()
  const pa = getUnitCenter('PA')
  const chamberRaw = ev.chamber_id
  const chamberId = (chamberRaw && String(chamberRaw).trim().toUpperCase() !== 'NULL') ? normalizeChamberId(chamberRaw) : (eventPort === 'PORT2' ? 'CHAMBER_B' : 'CHAMBER_A')
  const loadEpoch = bumpChamberEpoch(chamberId)
  const chamber = getUnitCenter(chamberId)
  activeState.activeUnitId = chamberId
  activeState.chamberWaferLabel[chamberId] = ''
  animateArmTo({ x: start.x, y: start.y, z: start.z + 8 }, scaleDuration(1000), false, function () {
    if (slot >= 1 && slot <= 25) getPortVisual(eventPort).cassetteSlots[slot - 1] = false
    activeState.waferAtPA = false
    activeState.waferInChamber[chamberId] = false
    activeState.movingWafer = { x: start.x, y: start.y, z: start.z + 8 }
    animateArmTo({ x: arm.x, y: arm.y, z: arm.z }, scaleDuration(1000), true, function () {
      animateArmTo({ x: pa.x, y: pa.y, z: pa.z + 10 }, scaleDuration(1000), true, function () {
        activeState.movingWafer = null
        activeState.movingWaferLabel = ''
        activeState.waferAtPA = true
        animateValue(0, 1, scaleDuration(320), function () {}, function () {
          activeState.movingWafer = { x: pa.x, y: pa.y, z: pa.z + 10 }
          activeState.waferAtPA = false
          animateArmTo({ x: arm.x, y: arm.y, z: arm.z }, scaleDuration(900), true, function () {
            animateArmTo({ x: chamber.x, y: chamber.y, z: chamber.z + 9 }, scaleDuration(1000), true, function () {
              if (activeState.chamberEpoch[chamberId] !== loadEpoch || activeState.chamberStates[chamberId] === 'idle') {
                activeState.movingWafer = null
                activeState.movingWaferLabel = ''
                activeState.waferAtPA = false
                return
              }
              activeState.movingWafer = null
              activeState.movingWaferLabel = ''
              activeState.waferInChamber[chamberId] = true
              activeState.chamberWaferLabel[chamberId] = waferTag
              animateArmTo(getArmHome3D(), scaleDuration(800), false)
            })
          })
        })
      })
    })
  })
}

function handleWaferUnloaded(ev) {
  const slot = Number(ev.slot || ev.wafer_id || ev.slot_id || 1)
  const eventPort = resolveEventPortId(ev, activeState.lastEventPortId)
  const portNo = eventPort === 'PORT2' ? '2' : '1'
  const waferTag = portNo + '-' + slot
  activeState.movingWaferLabel = waferTag
  const cassetteCenter = getCassetteDisplayCenterForPort(eventPort)
  const target = getSlotCoord(slot, cassetteCenter)
  const chamberRaw = ev.chamber_id
  const chamberId = (chamberRaw && String(chamberRaw).trim().toUpperCase() !== 'NULL') ? normalizeChamberId(chamberRaw) : (eventPort === 'PORT2' ? 'CHAMBER_B' : 'CHAMBER_A')
  bumpChamberEpoch(chamberId)
  activeState.chamberWaferLabel[chamberId] = ''
  const chamber = getUnitCenter(chamberId)
  const arm = getArmHome3D()
  activeState.activeUnitId = eventPort
  animateArmTo({ x: chamber.x, y: chamber.y, z: chamber.z + 9 }, scaleDuration(1000), false, function () {
    activeState.waferInChamber[chamberId] = false
    activeState.movingWafer = { x: chamber.x, y: chamber.y, z: chamber.z + 9 }
    animateArmTo({ x: arm.x, y: arm.y, z: arm.z }, scaleDuration(1000), true, function () {
      animateArmTo({ x: target.x, y: target.y, z: target.z + 8 }, scaleDuration(1200), true, function () {
        activeState.movingWafer = null
        activeState.movingWaferLabel = ''
        if (slot >= 1 && slot <= 25) getPortVisual(eventPort).cassetteSlots[slot - 1] = true
        animateArmTo(getArmHome3D(), scaleDuration(800), false)
      })
    })
  })
}

// ==================== applyEvent（完整迁移 20+ 种事件类型）====================
function applyEvent(ev) {
  ev = normalizeIncomingEvent(ev)
  const eventName = getEffectiveEventName(ev)
  activeState.machineState = ev.machine_state || activeState.machineState
  const eventPort = resolveEventPortId(ev, activeState.lastEventPortId)
  activeState.lastEventPortId = eventPort
  activeState.activeUnitId = eventPort === 'PORT2' ? 'SMIF2' : 'SMIF1'
  kpiLot.value = ev.lot_id || '-'
  kpiRecipe.value = ev.recipe || '-'
  kpiEvent.value = eventName || ev.event_type
  setStateText(activeState.machineState)
  appendTimeline(ev)
  applyLotStatusByEvent(ev)

  if (eventName === 'POD_PLACED') {
    const podVisual = getPortVisual(eventPort)
    podVisual.podPlaced = true
    podVisual.podPlaceProgress = 0
    podVisual.podCarryProgress = 0
    podVisual.podLocked = false
    podVisual.podLift = 0
    podVisual.podSmif = smifFromPort(eventPort)
    podVisual.cassetteAt = podVisual.podSmif
    podVisual.cassettePos = null
    activeState.mappingActive = false
    activeState.mappingPortId = eventPort
    // 修复：POD_PLACED 时立即初始化 Wafer Map 为全灰色(1)，否则 Wafer Map 面板会一直空
    // （等 WAFER_MAPPING 事件才画的话，回放中经常缺失 mapping_value，就看不到晶圆）
    podVisual.cassetteSlots = new Array(25).fill(true)
    activeState.waferMap[eventPort] = new Array(25).fill(1)
    animateValue(0, 1, scaleDuration(1000), function (v) { podVisual.podPlaceProgress = v })
  } else if (eventName === 'UNLOCK_PORT_COMPLETED') {
    getPortVisual(eventPort).podLocked = false
    activeState.activeUnitId = eventPort === 'PORT2' ? 'SMIF2' : 'SMIF1'
  } else if (eventName === 'LOCK_PORT_COMPLETED') {
    getPortVisual(eventPort).podLocked = true
  } else if (eventName === 'MVIN') {
    const mvinVisual = getPortVisual(eventPort)
    animateValue(mvinVisual.podLift, 34, scaleDuration(900), function (v) { mvinVisual.podLift = v })
  } else if (eventName === 'DOOR_OPEN') {
    animateValue(activeState.portDoorProgress[eventPort] || 0, 1, scaleDuration(700), function (v) { activeState.portDoorProgress[eventPort] = v })
  } else if (eventName === 'LOAD_CYCLE_STARTED') {
    const loadSmif = smifFromPort(eventPort)
    animateCassetteTransfer(eventPort, loadSmif, eventPort, scaleDuration(1500))
  } else if (eventName === 'LOAD_CYCLE_COMPLETED') {
    const doneVisual = getPortVisual(eventPort)
    doneVisual.cassetteAt = eventPort
    doneVisual.cassettePos = null
  } else if (eventName === 'DOOR_CLOSE') {
    animateValue(activeState.portDoorProgress[eventPort] || 0, 0, scaleDuration(700), function (v) { activeState.portDoorProgress[eventPort] = v })
  } else if (eventName === 'STARTMAPPING_LEFT' || eventName === 'STARTMAPPING_RIGHT') {
    activeState.mappingActive = true
    activeState.mappingPortId = eventName === 'STARTMAPPING_RIGHT' ? 'PORT2' : eventPort
  } else if (eventName === 'WAFER_MAPPING' || eventName === 'ENDMAPPING') {
    const mappingPort = resolveEventPortId({
      port_id: ev.port_id || ev.PORT_ID || ev.portid || ev.PORTID || ev.port || ev.PORT,
      smif_id: ev.smif_id || ev.SMIF_ID,
      chamber_id: ev.chamber_id || ev.CHAMBER_ID,
    }, eventPort)
    activeState.mappingActive = false
    activeState.mappingPortId = mappingPort
    activeState.mappingPhase = 0
    applyMappingToPort(mappingPort, ev)
    if (Array.isArray(ev.mapped_slots) && ev.mapped_slots.length > 0) setCassetteSlotsFromMapping(ev.mapped_slots)
  } else if (eventName === 'ALARM' || eventName === 'EC_ALARM_REPORT' || eventName === 'ALARM_REPORT') {
    setChamberState(normalizeChamberId(ev.chamber_id), 'alarm')
    activeState.activeUnitId = normalizeChamberId(ev.chamber_id)
    const alarmPort = eventPort
    const alarmChamber = normalizeChamberId(ev.chamber_id)
    const alarmLot = ev.lot_id || ev.lot || ''
    const alarmText = (ev.alarm_text || ev.ALTX || ev.alarm_id || ev.ALID || 'ALARM') + (ev.chamber_id ? ' @ ' + ev.chamber_id : '')
    const alarmTime = formatEventTime(ev)
    const alarmEntry = { time: alarmTime, text: alarmText }
    if (alarmPort === 'PORT2' || alarmChamber === 'CHAMBER_B' || alarmLot === activeState.lotStatus.PORT2.lot) {
      activeState.alarmRight.push(alarmEntry)
      activeState.alarmExpandedRight = true
    } else {
      activeState.alarmLeft.push(alarmEntry)
      activeState.alarmExpandedLeft = true
    }
  } else if (eventName === 'PE') {
    let peChamber = ev.chamber_id
    if (!peChamber) {
      const pePort = eventPort
      peChamber = (pePort === 'PORT2') ? 'CHAMBER_B' : 'CHAMBER_A'
    }
    bumpChamberEpoch(peChamber)
    activeState.waferInChamber[normalizeChamberId(peChamber)] = false
    activeState.waferAtPA = false
    setChamberState(peChamber, 'idle')
  } else if (eventName === 'READYTOUNLOAD') {
    const rtuChamber = normalizeChamberId(ev.chamber_id)
    if (activeState.chamberStates[rtuChamber] !== 'idle') setChamberState(rtuChamber, 'unloading')
  } else if (eventName === 'WAFERLOADED') {
    const wlRaw = ev.chamber_id
    const wlChamber = (wlRaw && String(wlRaw).trim().toUpperCase() !== 'NULL') ? normalizeChamberId(wlRaw) : (eventPort === 'PORT2' ? 'CHAMBER_B' : 'CHAMBER_A')
    setChamberState(wlChamber, 'running')
    activeState.activeUnitId = wlChamber
    handleWaferLoaded(ev)
    markWaferAsRunning(eventPort, ev.slot || ev.wafer_id || ev.slot_id)
  } else if (eventName === 'WAFERUNLOADED') {
    const wuRaw = ev.chamber_id
    const wuChamber = (wuRaw && String(wuRaw).trim().toUpperCase() !== 'NULL') ? normalizeChamberId(wuRaw) : (eventPort === 'PORT2' ? 'CHAMBER_B' : 'CHAMBER_A')
    setChamberState(wuChamber, 'idle')
    handleWaferUnloaded(ev)
    markWaferAsCompleted(eventPort, ev.slot || ev.wafer_id || ev.slot_id)
  } else if (eventName === 'UNLOAD_CYCLE_COMPLETED') {
    const unloadSmif = smifFromPort(eventPort)
    const unloadVisual = getPortVisual(eventPort)
    const unloadChamber = eventPort === 'PORT2' ? 'CHAMBER_B' : 'CHAMBER_A'
    animateCassetteTransfer(eventPort, eventPort, unloadSmif, scaleDuration(1500), function () {
      animateValue(unloadVisual.podLift, 0, scaleDuration(800), function (v) { unloadVisual.podLift = v })
      bumpChamberEpoch(unloadChamber)
      activeState.waferInChamber[unloadChamber] = false
      activeState.waferAtPA = false
      setChamberState(unloadChamber, 'idle')
    })
  } else if (eventName === 'POD_REMOVED') {
    const removedVisual = getPortVisual(eventPort)
    const removedChamber = eventPort === 'PORT2' ? 'CHAMBER_B' : 'CHAMBER_A'
    activeState.waferMap[eventPort] = emptyWaferMap()
    activeState.activeUnitId = eventPort === 'PORT2' ? 'SMIF2' : 'SMIF1'
    animateValue(0, 1, scaleDuration(1000), function (v) { removedVisual.podCarryProgress = v }, function () {
      removedVisual.podPlaced = false
      removedVisual.podLocked = false
      removedVisual.podPlaceProgress = 0
      removedVisual.podCarryProgress = 0
      removedVisual.podLift = 0
      removedVisual.podSmif = smifFromPort(eventPort)
      removedVisual.cassetteAt = removedVisual.podSmif
      removedVisual.cassettePos = null
      removedVisual.cassetteSlots = new Array(25).fill(false)
      bumpChamberEpoch(removedChamber)
      activeState.waferInChamber[removedChamber] = false
      activeState.waferAtPA = false
      if (eventPort === 'PORT2') {
        activeState.alarmRight = []
        activeState.alarmExpandedRight = false
      } else {
        activeState.alarmLeft = []
        activeState.alarmExpandedLeft = false
      }
    })
  } else if (eventName === 'FDC_CLEARCONTEXT') {
    const clearChamber = eventPort === 'PORT2' ? 'CHAMBER_B' : 'CHAMBER_A'
    bumpChamberEpoch(clearChamber)
    activeState.waferInChamber[clearChamber] = false
    activeState.waferAtPA = false
    setChamberState(clearChamber, 'idle')
  } else if (eventName === 'SENSOR') {
    let sensorDesc = ev.description || ev.sensor_name || '传感器数据'
    if (ev.sensor_value != null) sensorDesc += ' = ' + ev.sensor_value
    kpiEvent.value = 'SENSOR: ' + sensorDesc
  } else if (eventName === 'STATE') {
    const stateVal = String(ev.state || ev.machine_state || '').toUpperCase()
    if (stateVal === 'RUNNING' || stateVal === 'PROCESS') {
      const stChamber = ev.chamber_id ? normalizeChamberId(ev.chamber_id) : (eventPort === 'PORT2' ? 'CHAMBER_B' : 'CHAMBER_A')
      setChamberState(stChamber, 'running')
      activeState.activeUnitId = stChamber
    } else if (stateVal === 'IDLE' || stateVal === 'READY') {
      const idleChamber = ev.chamber_id ? normalizeChamberId(ev.chamber_id) : (eventPort === 'PORT2' ? 'CHAMBER_B' : 'CHAMBER_A')
      if (activeState.chamberStates[idleChamber] === 'running') setChamberState(idleChamber, 'idle')
    } else if (stateVal === 'HOLD' || stateVal === 'PAUSE') {
      const holdChamber = ev.chamber_id ? normalizeChamberId(ev.chamber_id) : (eventPort === 'PORT2' ? 'CHAMBER_B' : 'CHAMBER_A')
      setChamberState(holdChamber, 'hold')
    }
  } else if (eventName === 'TRANSFER') {
    const transferChamber = ev.chamber_id ? normalizeChamberId(ev.chamber_id) : (eventPort === 'PORT2' ? 'CHAMBER_B' : 'CHAMBER_A')
    if (ev.transfer_stage === 'PICK' || ev.action === 'PICK') {
      setChamberState(transferChamber, 'loading')
    } else if (ev.transfer_stage === 'PLACE' || ev.action === 'PLACE') {
      setChamberState(transferChamber, 'running')
      activeState.waferInChamber[transferChamber] = true
    }
  }
}

// ==================== 停止所有动画（暂停时调用）====================
function stopAllAnimations() {
  if (activeState.timerId) {
    clearTimeout(activeState.timerId)
    activeState.timerId = null
  }
  // 取消所有进行中的 requestAnimationFrame 动画
  const cancels = Array.from(activeAnimationCancels)
  activeAnimationCancels.clear()
  cancels.forEach(function (fn) { try { fn() } catch (e) {} })
}

// ==================== Bootstrap（按最近 POD_PLACED 重建状态）====================
function getEventTsMs(ev) {
  const normalized = normalizeIncomingEvent(ev) || {}
  const ts = normalized.event_ts_utc || normalized.EVENT_TS_UTC || normalized.timestamp || normalized.TIMESTAMP || normalized.event_time || normalized.EVENT_TIME || normalized.ts || normalized.TS
  if (!ts) return 0
  const ms = Date.parse(String(ts))
  return isNaN(ms) ? 0 : ms
}

function isPodPlacedEventName(eventName) {
  const s = String(eventName || '').toUpperCase()
  return s === 'POD_PLACED' || s === 'POD_PLACE'
}

function isPodRemovedEventName(eventName) {
  const s = String(eventName || '').toUpperCase()
  return s === 'POD_REMOVED' || s === 'POD_REMOVE'
}

function cloneEventAsType(ev, eventType) {
  const copy = {}
  for (const k in ev) {
    if (Object.prototype.hasOwnProperty.call(ev, k)) copy[k] = ev[k]
  }
  copy.event_type = eventType
  return copy
}

function findPortBootstrapContext(events, portId) {
  const normalizedPort = normalizePortId(portId)
  const smifId = smifFromPort(normalizedPort)
  const portEvents = events.filter(function (ev) {
    return resolveEventPortId(ev, null) === normalizedPort
  }).sort(function (a, b) { return getEventTsMs(a) - getEventTsMs(b) })
  let latestPodPlaced = null
  for (let i = portEvents.length - 1; i >= 0; i -= 1) {
    if (isPodPlacedEventName(getEffectiveEventName(portEvents[i]))) { latestPodPlaced = portEvents[i]; break }
  }
  if (!latestPodPlaced) {
    return { portId: normalizedPort, active: false, baseTs: 0, podPlacedEvent: null, latestEvent: null, batchEvent: null, mappingEvent: null, unloadedSlots: [] }
  }
  const baseTs = getEventTsMs(latestPodPlaced)
  const afterPlaced = portEvents.filter(function (ev) { return getEventTsMs(ev) > baseTs })
  let latestPodRemoved = null
  for (let i = afterPlaced.length - 1; i >= 0; i -= 1) {
    const evName = getEffectiveEventName(afterPlaced[i])
    const evSmif = String(afterPlaced[i].smif_id || afterPlaced[i].SMIF_ID || '').toUpperCase()
    const evPort = resolveEventPortId(afterPlaced[i], null)
    if (isPodRemovedEventName(evName) && (evPort === normalizedPort || evSmif === smifId)) { latestPodRemoved = afterPlaced[i]; break }
  }
  if (latestPodRemoved) {
    return { portId: normalizedPort, active: false, baseTs: baseTs, podPlacedEvent: latestPodPlaced, latestEvent: null, batchEvent: null, mappingEvent: null, unloadedSlots: [] }
  }
  let batchEvent = null
  let mappingEvent = null
  let latestEvent = null
  const unloadedSet = {}
  for (let i = 0; i < afterPlaced.length; i += 1) {
    const item = afterPlaced[i]
    const itemName = getEffectiveEventName(item)
    latestEvent = item
    if (itemName === 'BATCH_INFO_FROM_ECUI') batchEvent = item
    if (itemName === 'WAFER_MAPPING') mappingEvent = item
    if (itemName === 'WAFERUNLOADED') {
      const slot = Number(item.slot || item.wafer_id || item.slot_id || 0)
      if (slot >= 1 && slot <= 25) unloadedSet[slot] = true
    }
  }
  const unloadedSlots = Object.keys(unloadedSet).map(function (s) { return Number(s) }).sort(function (a, b) { return a - b })
  return { portId: normalizedPort, active: true, baseTs: baseTs, podPlacedEvent: latestPodPlaced, latestEvent: latestEvent, batchEvent: batchEvent, mappingEvent: mappingEvent, unloadedSlots: unloadedSlots }
}

function buildBootstrapReplayEvents(context) {
  if (!context || !context.active || !context.podPlacedEvent) return []
  const events = []
  const latestEventName = context.latestEvent ? getEffectiveEventName(context.latestEvent) : ''
  const shouldReplayPodPlaced = !latestEventName || latestEventName === 'POD_PLACED'
  const replaySet8 = { LOCK_PORT_COMPLETED: true, MVIN: true, DOOR_OPEN: true, DOOR_CLOSE: true, BATCH_INFO_FROM_ECUI: true }
  const replaySet9 = { STARTMAPPING_LEFT: true, PS: true, WAFERLOADED: true, WAFERUNLOADED: true, PE: true, READYTOUNLOAD: true, MVOU: true }
  if (shouldReplayPodPlaced) events.push(cloneEventAsType(context.podPlacedEvent, 'POD_PLACED'))
  if (!context.batchEvent) {
    if (!events.length) events.push(cloneEventAsType(context.podPlacedEvent, 'POD_PLACED'))
    return events
  }
  events.push(cloneEventAsType(context.batchEvent, 'BATCH_INFO_FROM_ECUI'))
  if (context.mappingEvent) events.push(cloneEventAsType(context.mappingEvent, 'WAFER_MAPPING'))
  if (latestEventName === 'UNLOAD_CYCLE_COMPLETED') events.push(cloneEventAsType(context.latestEvent, 'UNLOAD_CYCLE_COMPLETED'))
  else if (latestEventName === 'LOAD_CYCLE_STARTED') events.push(cloneEventAsType(context.latestEvent, 'LOAD_CYCLE_STARTED'))
  else if (latestEventName === 'WAFER_MAPPING') events.push(cloneEventAsType(context.latestEvent, 'LOAD_CYCLE_COMPLETED'))
  else if (latestEventName === 'LOAD_CYCLE_COMPLETED') events.push(cloneEventAsType(context.latestEvent, 'LOAD_CYCLE_COMPLETED'))
  else if (replaySet8[latestEventName]) events.push(cloneEventAsType(context.latestEvent, latestEventName))
  else if (replaySet9[latestEventName]) {
    events.push(cloneEventAsType(context.latestEvent, 'LOAD_CYCLE_COMPLETED'))
    events.push(cloneEventAsType(context.latestEvent, latestEventName))
  }
  return events
}

function primeBootstrapPortVisual(context) {
  if (!context || !context.portId) return
  const portId = normalizePortId(context.portId)
  const visual = getPortVisual(portId)
  visual.podPlaced = !!context.active
  visual.podPlaceProgress = context.active ? 1 : 0
  visual.podCarryProgress = 0
  visual.podLift = 0
  visual.podSmif = smifFromPort(portId)
  visual.cassettePos = null
  if (!context.active) {
    visual.podLocked = false
    visual.cassetteAt = visual.podSmif
  }
}

function applyBootstrapForPort(context) {
  const portId = context.portId
  primeBootstrapPortVisual(context)
  if (!context.active) {
    activeState.lotStatus[portId] = { lot: 'NULL', status: 'IDLE' }
    return
  }
  const replayEvents = buildBootstrapReplayEvents(context)
  replayEvents.forEach(function (ev) { applyEvent(ev) })
  if (!context.batchEvent) return
  context.unloadedSlots.forEach(function (slot) { markWaferAsCompleted(portId, slot) })
}

function bootstrapFromLatestPodPlaced(toolId) {
  if (!toolId) return Promise.resolve()
  return fetch('/api/oxe/history-events?tool_id=' + encodeURIComponent(toolId) + '&limit=2000', { cache: 'no-store' })
    .then(function (res) { if (!res.ok) throw new Error('history load failed'); return res.json() })
    .then(function (payload) {
      const events = payload && Array.isArray(payload.events) ? payload.events.map(normalizeIncomingEvent) : []
      if (!events.length) return
      activeState.events = events
      const p1Context = findPortBootstrapContext(events, 'PORT1')
      const p2Context = findPortBootstrapContext(events, 'PORT2')
      applyBootstrapForPort(p1Context)
      applyBootstrapForPort(p2Context)
    }).catch(function () {})
}

// ==================== 工具：时间格式化 / 解析 ====================
function formatEventTime(ev) {
  const normalized = normalizeIncomingEvent(ev) || {}
  const ts = normalized.event_ts_utc || normalized.EVENT_TS_UTC || normalized.timestamp || normalized.TIMESTAMP || normalized.event_time || normalized.EVENT_TIME || normalized.ts || normalized.TS
  if (ts) {
    const s = String(ts)
    if (s.length >= 19 && s.indexOf('T') > 0) return s.slice(11, 19)
    return s.slice(0, 8)
  }
  return '--:--:--'
}

function parseTs(ts) {
  if (!ts) return 0
  // 兼容带 Z 的 ISO 时间戳
  const ms = Date.parse(String(ts))
  return isNaN(ms) ? 0 : ms
}

// ==================== 回放支持（照搬 PODOPENER 模式）====================
let lastEventTs = ''
let lastEventTsMs = 0

watch(() => props.events, (evs) => {
  if (!Array.isArray(evs) || evs.length === 0) return

  // displayEvents 是倒序的，最新在 index 0
  // 需要找出所有比 lastEventTs 更新的事件，按时间正序逐条 applyEvent
  const newEvents = []
  for (const ev of evs) {
    const ts = ev?.timestamp || ev?.event_ts_utc || ''
    if (!ts) continue
    const tsMs = parseTs(ts)
    if (tsMs <= 0) continue

    // 实时模式首次进入：过滤5分钟前的历史事件
    if (props.mode === 'realtime' && lastEventTsMs === 0) {
      if (Date.now() - tsMs > 5 * 60 * 1000) continue
    }

    // 只处理比上次更新的事件
    if (tsMs > lastEventTsMs) {
      newEvents.push({ ev, ts, tsMs })
    }
  }

  if (newEvents.length === 0) return

  // 按时间正序排序（旧→新），逐条 applyEvent 重建状态
  newEvents.sort((a, b) => a.tsMs - b.tsMs)

  for (const item of newEvents) {
    applyEvent(item.ev)
  }

  // 更新去重游标为最新事件的时间
  const lastItem = newEvents[newEvents.length - 1]
  lastEventTs = lastItem.ts
  lastEventTsMs = lastItem.tsMs
}, { deep: true })

watch(() => props.paused, (isPaused) => {
  if (isPaused) {
    stopAllAnimations()
  }
})

watch(() => props.mode, (newMode) => {
  lastEventTs = ''
  lastEventTsMs = 0
  if (newMode === 'playback') {
    stopLivePolling()
  } else {
    startLivePolling()
  }
})

// ==================== 实时模式（1秒轮询 /api/oxe/latest-event）====================
let livePollTimer = null

function startLivePolling() {
  stopLivePolling()
  const toolId = props.machine?.id
  if (!toolId) return

  activeState.liveMode = true
  activeState.lastPollRawId = 0
  // 先 bootstrap 重建状态，再启动 1 秒轮询
  bootstrapFromLatestPodPlaced(toolId).finally(function () {
    if (!activeState.liveMode) return
    livePollTimer = setInterval(function () {
      if (!activeState.liveMode) {
        clearInterval(livePollTimer)
        livePollTimer = null
        return
      }
      fetch('/api/oxe/latest-event?tool_id=' + encodeURIComponent(toolId), { cache: 'no-store' })
        .then(function (res) { if (!res.ok) return null; return res.json() })
        .then(function (data) {
          if (!data || data.error) return
          const rawId = Number(data.raw_id || 0)
          if (rawId && rawId > activeState.lastPollRawId) {
            activeState.lastPollRawId = rawId
            const normalized = normalizeIncomingEvent(data)
            if (normalized && (normalized.event_type || normalized.event_name)) {
              applyEvent(normalized)
            }
          }
        }).catch(function () {})
    }, 1000)
  })
}

function stopLivePolling() {
  activeState.liveMode = false
  if (livePollTimer) {
    clearInterval(livePollTimer)
    livePollTimer = null
  }
}

// ==================== Canvas 尺寸适配 ====================
function resizeCanvas() {
  if (!canvas || !containerRef.value) return
  const ratio = window.devicePixelRatio || 1
  const rect = containerRef.value.getBoundingClientRect()
  canvas.width = Math.round(rect.width * ratio)
  canvas.height = Math.round(rect.height * ratio)
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0)
  render()
}

// ==================== Canvas 点击：切换告警面板展开/收起 ====================
function onCanvasClick(ev) {
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const cx = ev.clientX - rect.left
  const cy = ev.clientY - rect.top
  const panelW = 155
  const panelH = 330
  const leftX = 10
  const rightX = canvas.clientWidth - panelW - 10
  const alarmY = 74 + panelH + 4
  if (cx >= leftX && cx <= leftX + panelW && cy >= alarmY && cy <= alarmY + 60) {
    if (activeState.alarmLeft && activeState.alarmLeft.length > 0) activeState.alarmExpandedLeft = !activeState.alarmExpandedLeft
  }
  if (cx >= rightX && cx <= rightX + panelW && cy >= alarmY && cy <= alarmY + 60) {
    if (activeState.alarmRight && activeState.alarmRight.length > 0) activeState.alarmExpandedRight = !activeState.alarmExpandedRight
  }
}

// ==================== 生命周期 ====================
onMounted(() => {
  canvas = canvasRef.value
  if (!canvas) return
  ctx = canvas.getContext('2d')
  resizeCanvas()
  window.addEventListener('resize', resizeCanvas)
  canvas.addEventListener('click', onCanvasClick)

  // 启动渲染循环
  frameLoop()

  // 实时模式启动轮询
  if (props.mode === 'realtime') {
    startLivePolling()
  }
})

onUnmounted(() => {
  if (rafId) cancelAnimationFrame(rafId)
  stopLivePolling()
  stopAllAnimations()
  window.removeEventListener('resize', resizeCanvas)
  if (canvas) canvas.removeEventListener('click', onCanvasClick)
})
</script>

<template>
  <div ref="containerRef" class="oxe-viewer">
    <canvas ref="canvasRef" class="oxe-canvas" />

    <!-- 顶部居中 KPI / 状态浮层 -->
    <div class="oxe-kpi-panel">
      <div class="kpi-row kpi-machine-row">
        <span class="kpi-label">机台</span>
        <strong class="kpi-val kpi-machine-name">{{ props.machine?.id || '-' }}</strong>
      </div>
      <div class="kpi-row">
        <span class="kpi-label">LOT</span>
        <strong class="kpi-val">{{ kpiLot }}</strong>
      </div>
      <div class="kpi-row">
        <span class="kpi-label">Recipe</span>
        <strong class="kpi-val">{{ kpiRecipe }}</strong>
      </div>
      <div class="kpi-row">
        <span class="kpi-label">当前 Event</span>
        <strong class="kpi-val">{{ kpiEvent }}</strong>
      </div>
      <div class="kpi-row">
        <span class="kpi-label">状态</span>
        <strong class="kpi-val" :class="kpiStateClass">{{ kpiStateText }}</strong>
      </div>
    </div>

    <!-- 事件时间轴浮层 -->
    <div class="oxe-timeline-panel">
      <div class="timeline-head">事件进程</div>
      <div class="timeline-body">
        <div v-for="(row, idx) in timelineEntries.slice().reverse()" :key="idx" class="event-row">
          <span class="event-time">{{ row.time }}</span>
          <span class="event-name"><strong>{{ row.name }}</strong><em>{{ row.extra }}</em></span>
        </div>
      </div>
    </div>

    <!-- 图例 -->
    <div class="oxe-legend">
      <span class="legend-item"><span class="dot" style="background:#16a34a"></span>Running</span>
      <span class="legend-item"><span class="dot" style="background:#ca8a04"></span>Hold</span>
      <span class="legend-item"><span class="dot" style="background:#dc2626"></span>Alarm</span>
      <span class="legend-item"><span class="dot" style="background:#94a3b8"></span>Idle</span>
      <span class="legend-item"><span class="dot" style="background:#ef4444"></span>LOCK 角标</span>
    </div>
  </div>
</template>

<style scoped>
.oxe-viewer {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 320px;
  background: linear-gradient(180deg, #f4f8fc 0%, #e5eef6 100%);
  overflow: hidden;
}
.oxe-canvas {
  width: 100%;
  height: 100%;
  display: block;
}
.oxe-kpi-panel {
  position: absolute;
  top: 10px;
  left: 50%;
  transform: translateX(-50%);
  min-width: 150px;
  padding: 8px 10px;
  border: 1px solid #c7d3e0;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(4px);
  z-index: 3;
  display: grid;
  gap: 4px;
  font-size: 12px;
}
.kpi-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.kpi-label {
  color: #607089;
}
.kpi-val {
  color: #0f172a;
  font-size: 13px;
}
.kpi-machine-row {
  padding-bottom: 4px;
  margin-bottom: 4px;
  border-bottom: 1px solid #e2e8f0;
}
.kpi-machine-name {
  font-size: 15px;
  font-weight: 800;
  color: #0e7490;
}
.status-running-text { color: #16a34a; }
.status-alarm-text { color: #dc2626; }
.status-idle-text { color: #64748b; }
.status-info-text { color: #0e7490; }
.oxe-timeline-panel {
  position: absolute;
  left: 10px;
  bottom: 10px;
  width: 220px;
  max-height: 220px;
  border: 1px solid #c7d3e0;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.12);
  backdrop-filter: blur(4px);
  z-index: 3;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.timeline-head {
  padding: 6px 10px;
  border-bottom: 1px solid #e2e8f0;
  font-size: 12px;
  font-weight: 600;
  color: #0f172a;
  background: rgba(246, 249, 252, 0.9);
}
.timeline-body {
  padding: 4px 10px;
  overflow: auto;
  font-size: 11px;
}
.event-row {
  display: grid;
  grid-template-columns: 56px 1fr;
  gap: 6px;
  padding: 3px 0;
  border-bottom: 1px solid #edf2f7;
}
.event-time {
  color: #607089;
  font-family: ui-monospace, "Cascadia Mono", monospace;
}
.event-name em {
  display: inline;
  margin-left: 4px;
  color: #607089;
  font-style: normal;
}
.oxe-legend {
  position: absolute;
  right: 10px;
  bottom: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-width: 260px;
  z-index: 3;
}
.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 7px;
  border-radius: 999px;
  border: 1px solid #c7d3e0;
  background: rgba(255, 255, 255, 0.92);
  color: #607089;
  font-size: 11px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
</style>
