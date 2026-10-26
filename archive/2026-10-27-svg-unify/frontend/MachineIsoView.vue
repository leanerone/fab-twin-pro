<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'

// Props: 支持暂停控制
const props = defineProps({
  paused: { type: Boolean, default: false },
  metrics: { type: Object, default: () => ({}) },
  runState: { type: String, default: 'idle' },
  events: { type: Array, default: () => [] },
  mode: { type: String, default: 'realtime' },
})

const containerRef = ref(null)
const canvasRef = ref(null)
const width = ref(800)
const height = ref(600)

let ctx = null
let rafId = null
let animTime = 0

const UNITS = {
  CHAMBER_A: { id: 'CHAMBER_A', x: -208, y: -220, w: 120, d: 100, color: '#3a4a5e' },
  CHAMBER_B: { id: 'CHAMBER_B', x: -32, y: -220, w: 120, d: 100, color: '#3a4a5e' },
  CHAMBER_C: { id: 'CHAMBER_C', x: 60, y: -48, w: 120, d: 96, color: '#3a4a5e' },
  PORT1: { id: 'PORT1', x: -208, y: 120, w: 120, d: 88, color: '#2a3445' },
  PORT2: { id: 'PORT2', x: -32, y: 120, w: 120, d: 88, color: '#2a3445' },
  SMIF1: { id: 'SMIF1', x: -208, y: 208, w: 120, d: 68, color: '#1e2838' },
  SMIF2: { id: 'SMIF2', x: -32, y: 208, w: 120, d: 68, color: '#1e2838' },
  PA: { id: 'PA', x: -300, y: -48, w: 120, d: 96, color: '#2d2a4a' },
  ARM: { id: 'ARM', x: -180, y: -120, w: 240, d: 240, color: '#1a2333' },
}

function getUnitCenter(unitId) {
  const u = UNITS[unitId]
  return { x: u.x + u.w / 2, y: u.y + u.d / 2 }
}

const ARM_BASE = getUnitCenter('ARM')
const UPPER_ARM_LEN = 90
const FOREARM_LEN = 130

const PHASES = {
  IDLE: 0,
  MOVE_TO_PORT1: 1,
  PICK_FROM_PORT1: 2,
  LIFT_FROM_PORT1: 3,
  MOVE_TO_PA_FROM_PORT1: 4,
  PLACE_TO_PA: 5,
  LOWER_TO_PA: 6,
  RETREAT_FROM_PA: 7,
  MOVE_TO_PA_FOR_PICK: 8,
  PICK_FROM_PA: 9,
  LIFT_FROM_PA: 10,
  MOVE_TO_CHAMBER: 11,
  PLACE_TO_CHAMBER: 12,
  LOWER_TO_CHAMBER: 13,
  RETREAT_FROM_CHAMBER: 14,
  PROCESSING: 15,
  MOVE_TO_CHAMBER_FOR_UNLOAD: 16,
  PICK_FROM_CHAMBER: 17,
  LIFT_FROM_CHAMBER: 18,
  MOVE_TO_PA_FROM_CHAMBER: 19,
  PLACE_TO_PA_RETURN: 20,
  LOWER_TO_PA_RETURN: 21,
  RETREAT_FROM_PA_RETURN: 22,
  MOVE_TO_PA_FOR_RETURN: 23,
  PICK_FROM_PA_RETURN: 24,
  LIFT_FROM_PA_RETURN: 25,
  MOVE_TO_PORT1_RETURN: 26,
  PLACE_TO_PORT1: 27,
  LOWER_TO_PORT1: 28,
  RETREAT_FROM_PORT1: 29,
  WAIT_NEXT: 30,
}

let currentPhase = PHASES.MOVE_TO_PORT1
let phaseProgress = 0
let currentWafer = 1
const TOTAL_WAFERS = 25
let armHoldingWafer = false
let waferAtPort1 = true
let waferAtPA = false
let waferInChamber = false
let chamberProcessing = false
let chamberProgress = 0

let shoulderAngle = -Math.PI / 2
let elbowAngle = 0
let wristAngle = 0
let gripperOpen = true
let armZ = 10

let lastShoulderAngle = -Math.PI / 2
let lastElbowAngle = 0
let lastWristAngle = 0
let lastGripperOpen = true
let lastArmZ = 10

let targetShoulderAngle = -Math.PI / 2
let targetElbowAngle = 0
let targetWristAngle = 0
let targetGripperOpen = true
let targetArmZ = 10

const PHASE_DURATIONS = {
  [PHASES.MOVE_TO_PORT1]: 60,
  [PHASES.PICK_FROM_PORT1]: 20,
  [PHASES.LIFT_FROM_PORT1]: 15,
  [PHASES.MOVE_TO_PA_FROM_PORT1]: 50,
  [PHASES.PLACE_TO_PA]: 20,
  [PHASES.LOWER_TO_PA]: 15,
  [PHASES.RETREAT_FROM_PA]: 15,
  [PHASES.MOVE_TO_PA_FOR_PICK]: 30,
  [PHASES.PICK_FROM_PA]: 20,
  [PHASES.LIFT_FROM_PA]: 15,
  [PHASES.MOVE_TO_CHAMBER]: 50,
  [PHASES.PLACE_TO_CHAMBER]: 20,
  [PHASES.LOWER_TO_CHAMBER]: 15,
  [PHASES.RETREAT_FROM_CHAMBER]: 50,
  [PHASES.PROCESSING]: 120,
  [PHASES.MOVE_TO_CHAMBER_FOR_UNLOAD]: 30,
  [PHASES.PICK_FROM_CHAMBER]: 20,
  [PHASES.LIFT_FROM_CHAMBER]: 15,
  [PHASES.MOVE_TO_PA_FROM_CHAMBER]: 50,
  [PHASES.PLACE_TO_PA_RETURN]: 20,
  [PHASES.LOWER_TO_PA_RETURN]: 15,
  [PHASES.RETREAT_FROM_PA_RETURN]: 50,
  [PHASES.MOVE_TO_PA_FOR_RETURN]: 30,
  [PHASES.PICK_FROM_PA_RETURN]: 20,
  [PHASES.LIFT_FROM_PA_RETURN]: 15,
  [PHASES.MOVE_TO_PORT1_RETURN]: 60,
  [PHASES.PLACE_TO_PORT1]: 20,
  [PHASES.LOWER_TO_PORT1]: 15,
  [PHASES.RETREAT_FROM_PORT1]: 50,
  [PHASES.WAIT_NEXT]: 20,
}

function easeInOut(t) {
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2
}

function lerpAngle(a, b, t) {
  let diff = b - a
  while (diff > Math.PI) diff -= 2 * Math.PI
  while (diff < -Math.PI) diff += 2 * Math.PI
  return a + diff * t
}

function solveIK(targetX, targetY) {
  const dx = targetX - ARM_BASE.x
  const dy = targetY - ARM_BASE.y
  const dist = Math.sqrt(dx * dx + dy * dy)
  const maxDist = UPPER_ARM_LEN + FOREARM_LEN
  const minDist = Math.abs(UPPER_ARM_LEN - FOREARM_LEN)
  const clampedDist = Math.max(minDist, Math.min(maxDist, dist))

  if (clampedDist < 1) {
    return { shoulder: -Math.PI / 2, elbow: Math.PI / 2, wrist: 0 }
  }

  const cosAngle = (clampedDist * clampedDist + UPPER_ARM_LEN * UPPER_ARM_LEN - FOREARM_LEN * FOREARM_LEN) /
                   (2 * clampedDist * UPPER_ARM_LEN)
  const shoulderBaseAngle = Math.atan2(dy, dx)
  const shoulderOffset = Math.acos(Math.max(-1, Math.min(1, cosAngle)))
  const shoulder = shoulderBaseAngle - shoulderOffset

  const cosElbow = (FOREARM_LEN * FOREARM_LEN + UPPER_ARM_LEN * UPPER_ARM_LEN - clampedDist * clampedDist) /
                   (2 * FOREARM_LEN * UPPER_ARM_LEN)
  const elbow = Math.PI - Math.acos(Math.max(-1, Math.min(1, cosElbow)))

  const wrist = -shoulder - elbow

  return { shoulder, elbow, wrist }
}

function setArmTarget(targetX, targetY, z, gripper) {
  const ik = solveIK(targetX, targetY)
  targetShoulderAngle = ik.shoulder
  targetElbowAngle = ik.elbow
  targetWristAngle = ik.wrist
  targetArmZ = z
  targetGripperOpen = gripper
}

function saveCurrentArmState() {
  lastShoulderAngle = shoulderAngle
  lastElbowAngle = elbowAngle
  lastWristAngle = wristAngle
  lastArmZ = armZ
  lastGripperOpen = gripperOpen
}

function updateArm(progress) {
  const t = easeInOut(progress)
  shoulderAngle = lerpAngle(lastShoulderAngle, targetShoulderAngle, t)
  elbowAngle = lerpAngle(lastElbowAngle, targetElbowAngle, t)
  wristAngle = lerpAngle(lastWristAngle, targetWristAngle, t)
  armZ = lastArmZ + (targetArmZ - lastArmZ) * t
  gripperOpen = lastGripperOpen + (targetGripperOpen - lastGripperOpen) * t
}

function startPhase(phase) {
  currentPhase = phase
  phaseProgress = 0
  saveCurrentArmState()
}

function getPort1PickPos() {
  const c = getUnitCenter('PORT1')
  return { x: c.x + 30, y: c.y - 10 }
}

function getPAPos() {
  const c = getUnitCenter('PA')
  return { x: c.x + 20, y: c.y }
}

function getChamberPos() {
  const c = getUnitCenter('CHAMBER_A')
  return { x: c.x + 10, y: c.y + 20 }
}

function updatePhaseMachine() {
  const duration = PHASE_DURATIONS[currentPhase] || 30
  phaseProgress += 1
  
  const progress = Math.min(1, phaseProgress / duration)
  updateArm(progress)
  
  if (phaseProgress >= duration) {
    switch (currentPhase) {
      case PHASES.MOVE_TO_PORT1:
        startPhase(PHASES.PICK_FROM_PORT1)
        setArmTarget(getPort1PickPos().x, getPort1PickPos().y, 8, false)
        break
      case PHASES.PICK_FROM_PORT1:
        armHoldingWafer = true
        waferAtPort1 = false
        startPhase(PHASES.LIFT_FROM_PORT1)
        setArmTarget(getPort1PickPos().x, getPort1PickPos().y, 25, false)
        break
      case PHASES.LIFT_FROM_PORT1:
        startPhase(PHASES.MOVE_TO_PA_FROM_PORT1)
        setArmTarget(getPAPos().x, getPAPos().y, 25, false)
        break
      case PHASES.MOVE_TO_PA_FROM_PORT1:
        startPhase(PHASES.PLACE_TO_PA)
        setArmTarget(getPAPos().x, getPAPos().y, 25, false)
        break
      case PHASES.PLACE_TO_PA:
        startPhase(PHASES.LOWER_TO_PA)
        setArmTarget(getPAPos().x, getPAPos().y, 8, false)
        break
      case PHASES.LOWER_TO_PA:
        armHoldingWafer = false
        waferAtPA = true
        startPhase(PHASES.RETREAT_FROM_PA)
        setArmTarget(ARM_BASE.x + 30, ARM_BASE.y + 20, 10, true)
        break
      case PHASES.RETREAT_FROM_PA:
        startPhase(PHASES.MOVE_TO_PA_FOR_PICK)
        setArmTarget(getPAPos().x - 20, getPAPos().y, 20, true)
        break
      case PHASES.MOVE_TO_PA_FOR_PICK:
        startPhase(PHASES.PICK_FROM_PA)
        setArmTarget(getPAPos().x, getPAPos().y, 8, false)
        break
      case PHASES.PICK_FROM_PA:
        armHoldingWafer = true
        waferAtPA = false
        startPhase(PHASES.LIFT_FROM_PA)
        setArmTarget(getPAPos().x, getPAPos().y, 30, false)
        break
      case PHASES.LIFT_FROM_PA:
        startPhase(PHASES.MOVE_TO_CHAMBER)
        setArmTarget(getChamberPos().x, getChamberPos().y, 30, false)
        break
      case PHASES.MOVE_TO_CHAMBER:
        startPhase(PHASES.PLACE_TO_CHAMBER)
        setArmTarget(getChamberPos().x, getChamberPos().y, 30, false)
        break
      case PHASES.PLACE_TO_CHAMBER:
        startPhase(PHASES.LOWER_TO_CHAMBER)
        setArmTarget(getChamberPos().x, getChamberPos().y, 8, false)
        break
      case PHASES.LOWER_TO_CHAMBER:
        armHoldingWafer = false
        waferInChamber = true
        chamberProcessing = true
        chamberProgress = 0
        startPhase(PHASES.RETREAT_FROM_CHAMBER)
        setArmTarget(ARM_BASE.x + 30, ARM_BASE.y + 20, 10, true)
        break
      case PHASES.RETREAT_FROM_CHAMBER:
        startPhase(PHASES.PROCESSING)
        break
      case PHASES.PROCESSING:
        chamberProcessing = false
        startPhase(PHASES.MOVE_TO_CHAMBER_FOR_UNLOAD)
        setArmTarget(getChamberPos().x - 15, getChamberPos().y + 15, 25, true)
        break
      case PHASES.MOVE_TO_CHAMBER_FOR_UNLOAD:
        startPhase(PHASES.PICK_FROM_CHAMBER)
        setArmTarget(getChamberPos().x, getChamberPos().y, 8, false)
        break
      case PHASES.PICK_FROM_CHAMBER:
        armHoldingWafer = true
        waferInChamber = false
        startPhase(PHASES.LIFT_FROM_CHAMBER)
        setArmTarget(getChamberPos().x, getChamberPos().y, 30, false)
        break
      case PHASES.LIFT_FROM_CHAMBER:
        startPhase(PHASES.MOVE_TO_PA_FROM_CHAMBER)
        setArmTarget(getPAPos().x, getPAPos().y, 30, false)
        break
      case PHASES.MOVE_TO_PA_FROM_CHAMBER:
        startPhase(PHASES.PLACE_TO_PA_RETURN)
        setArmTarget(getPAPos().x, getPAPos().y, 30, false)
        break
      case PHASES.PLACE_TO_PA_RETURN:
        startPhase(PHASES.LOWER_TO_PA_RETURN)
        setArmTarget(getPAPos().x, getPAPos().y, 8, false)
        break
      case PHASES.LOWER_TO_PA_RETURN:
        armHoldingWafer = false
        waferAtPA = true
        startPhase(PHASES.RETREAT_FROM_PA_RETURN)
        setArmTarget(getPAPos().x - 20, getPAPos().y, 20, true)
        break
      case PHASES.RETREAT_FROM_PA_RETURN:
        startPhase(PHASES.MOVE_TO_PA_FOR_RETURN)
        setArmTarget(getPAPos().x - 20, getPAPos().y, 20, true)
        break
      case PHASES.MOVE_TO_PA_FOR_RETURN:
        startPhase(PHASES.PICK_FROM_PA_RETURN)
        setArmTarget(getPAPos().x, getPAPos().y, 8, false)
        break
      case PHASES.PICK_FROM_PA_RETURN:
        armHoldingWafer = true
        waferAtPA = false
        startPhase(PHASES.LIFT_FROM_PA_RETURN)
        setArmTarget(getPAPos().x, getPAPos().y, 25, false)
        break
      case PHASES.LIFT_FROM_PA_RETURN:
        startPhase(PHASES.MOVE_TO_PORT1_RETURN)
        setArmTarget(getPort1PickPos().x, getPort1PickPos().y, 25, false)
        break
      case PHASES.MOVE_TO_PORT1_RETURN:
        startPhase(PHASES.PLACE_TO_PORT1)
        setArmTarget(getPort1PickPos().x, getPort1PickPos().y, 25, false)
        break
      case PHASES.PLACE_TO_PORT1:
        startPhase(PHASES.LOWER_TO_PORT1)
        setArmTarget(getPort1PickPos().x, getPort1PickPos().y, 8, false)
        break
      case PHASES.LOWER_TO_PORT1:
        armHoldingWafer = false
        waferAtPort1 = true
        startPhase(PHASES.RETREAT_FROM_PORT1)
        setArmTarget(ARM_BASE.x + 30, ARM_BASE.y + 20, 10, true)
        break
      case PHASES.RETREAT_FROM_PORT1:
        currentWafer++
        if (currentWafer > TOTAL_WAFERS) {
          currentWafer = 1
        }
        startPhase(PHASES.WAIT_NEXT)
        break
      case PHASES.WAIT_NEXT:
        updateArm(phaseProgress)
        if (phaseProgress >= 1) {
          startPhase(PHASES.MOVE_TO_PORT1)
          setArmTarget(getPort1PickPos().x + 20, getPort1PickPos().y, 20, true)
        }
        break
    }
  }
  
  if (chamberProcessing) {
    chamberProgress = Math.min(1, chamberProgress + 1 / PHASE_DURATIONS[PHASES.PROCESSING])
  }
}

function project(x, y, z = 0) {
  return {
    x: width.value / 2 + x,
    y: height.value * 0.46 + y - 0.03 * (z || 0),
  }
}

function shadeColor(hex, percent) {
  const c = hex.replace('#', '')
  const r = parseInt(c.slice(0, 2), 16)
  const g = parseInt(c.slice(2, 4), 16)
  const b = parseInt(c.slice(4, 6), 16)
  const o = percent / 100
  const nr = Math.max(0, Math.min(255, Math.round(r + (255 - r) * o)))
  const ng = Math.max(0, Math.min(255, Math.round(g + (255 - g) * o)))
  const nb = Math.max(0, Math.min(255, Math.round(b + (255 - b) * o)))
  return '#' + ((nr << 16) | (ng << 8) | nb).toString(16).padStart(6, '0')
}

function drawPoly(points, fill, stroke, lineWidth) {
  ctx.beginPath()
  ctx.moveTo(points[0].x, points[0].y)
  for (let i = 1; i < points.length; i++) ctx.lineTo(points[i].x, points[i].y)
  ctx.closePath()
  if (fill) { ctx.fillStyle = fill; ctx.fill() }
  if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = lineWidth || 1.2; ctx.stroke() }
}

function drawGroundGrid() {
  ctx.strokeStyle = 'rgba(100, 116, 139, 0.08)'
  ctx.lineWidth = 1
  for (let x = -350; x <= 350; x += 25) {
    const p1 = project(x, -280)
    const p2 = project(x, 320)
    ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke()
  }
  for (let y = -280; y <= 320; y += 25) {
    const p1 = project(-350, y)
    const p2 = project(350, y)
    ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke()
  }
}

function drawUnit(unit, zHeight = 20) {
  const color = unit.color
  const topColor = shadeColor(color, 15)
  const sideColor = shadeColor(color, -10)
  const frontColor = shadeColor(color, -20)
  
  const topPts = [
    project(unit.x, unit.y, zHeight),
    project(unit.x + unit.w, unit.y, zHeight),
    project(unit.x + unit.w, unit.y + unit.d, zHeight),
    project(unit.x, unit.y + unit.d, zHeight),
  ]
  
  const rightSide = [
    project(unit.x + unit.w, unit.y, zHeight),
    project(unit.x + unit.w, unit.y + unit.d, zHeight),
    project(unit.x + unit.w, unit.y + unit.d, 0),
    project(unit.x + unit.w, unit.y, 0),
  ]
  
  const frontSide = [
    project(unit.x, unit.y + unit.d, zHeight),
    project(unit.x + unit.w, unit.y + unit.d, zHeight),
    project(unit.x + unit.w, unit.y + unit.d, 0),
    project(unit.x, unit.y + unit.d, 0),
  ]
  
  drawPoly(rightSide, sideColor, '#1e293b', 1)
  drawPoly(frontSide, frontColor, '#1e293b', 1)
  drawPoly(topPts, topColor, '#475569', 1.2)
  
  const center = project(unit.x + unit.w / 2, unit.y + unit.d / 2, zHeight + 1)
  if (unit.id !== 'ARM') {
    ctx.fillStyle = '#cbd5e1'
    ctx.font = 'bold 10px "Segoe UI", sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(unit.id, center.x, center.y + 4)
  }
}

function drawArmZone() {
  const t = UNITS.ARM
  const cx = t.x + t.w / 2
  const cy = t.y + t.d / 2
  const zH = 8
  
  const topPts = [
    project(cx - t.w * 0.45, cy - t.d * 0.45, zH),
    project(cx + t.w * 0.45, cy - t.d * 0.45, zH),
    project(cx + t.w * 0.5, cy, zH),
    project(cx + t.w * 0.45, cy + t.d * 0.45, zH),
    project(cx - t.w * 0.45, cy + t.d * 0.45, zH),
    project(cx - t.w * 0.5, cy, zH),
  ]
  
  drawPoly(topPts, 'rgba(30, 40, 60, 0.9)', '#334155', 1.5)
  
  const center = project(cx, cy, zH)
  ctx.beginPath(); ctx.arc(center.x, center.y, 16, 0, Math.PI * 2)
  ctx.strokeStyle = '#475569'; ctx.lineWidth = 3; ctx.stroke()
  ctx.beginPath(); ctx.arc(center.x, center.y, 8, 0, Math.PI * 2)
  ctx.fillStyle = '#64748b'; ctx.fill()
  
  const labelPos = project(cx + t.w * 0.25, cy + t.d * 0.28, zH + 1)
  ctx.fillStyle = '#60a5fa'
  ctx.font = 'bold 14px "Segoe UI", sans-serif'
  ctx.textAlign = 'center'
  ctx.fillText('ARM', labelPos.x, labelPos.y + 4)
}

function drawWafer(x, y, z = 8, size = 20) {
  const center = project(x, y, z)
  ctx.save()
  ctx.translate(center.x, center.y)
  ctx.scale(1.15, 0.95)
  
  const gradient = ctx.createRadialGradient(-size * 0.3, -size * 0.3, 0, 0, 0, size)
  gradient.addColorStop(0, '#9ca3af')
  gradient.addColorStop(0.5, '#6b7280')
  gradient.addColorStop(1, '#4b5563')
  
  ctx.beginPath()
  ctx.arc(0, 0, size, 0, Math.PI * 2)
  ctx.fillStyle = gradient
  ctx.fill()
  ctx.strokeStyle = '#374151'
  ctx.lineWidth = 1.2
  ctx.stroke()
  
  ctx.beginPath()
  ctx.arc(size * 0.6, -size * 0.3, size * 0.15, 0, Math.PI * 2)
  ctx.fillStyle = 'rgba(255, 255, 255, 0.2)'
  ctx.fill()
  
  ctx.restore()
}

function drawSCARArm() {
  const baseX = ARM_BASE.x
  const baseY = ARM_BASE.y
  const baseZ = 5
  
  const shoulderX = baseX
  const shoulderY = baseY
  const shoulderZ = baseZ + armZ * 0.3
  
  const upperEndX = shoulderX + Math.cos(shoulderAngle) * UPPER_ARM_LEN
  const upperEndY = shoulderY + Math.sin(shoulderAngle) * UPPER_ARM_LEN
  
  const elbowAngleAbs = shoulderAngle + elbowAngle
  const foreEndX = upperEndX + Math.cos(elbowAngleAbs) * FOREARM_LEN
  const foreEndY = upperEndY + Math.sin(elbowAngleAbs) * FOREARM_LEN
  
  const wristAngleAbs = elbowAngleAbs + wristAngle
  
  const baseTop = project(baseX, baseY, shoulderZ + 8)
  const baseBottom = project(baseX, baseY, 0)
  
  ctx.beginPath()
  ctx.ellipse(baseBottom.x, baseBottom.y, 20, 10, 0, 0, Math.PI * 2)
  ctx.fillStyle = '#374151'
  ctx.fill()
  ctx.strokeStyle = '#1f2937'
  ctx.lineWidth = 1.5
  ctx.stroke()
  
  ctx.fillStyle = '#4b5563'
  ctx.beginPath()
  ctx.moveTo(baseBottom.x - 16, baseBottom.y)
  ctx.lineTo(baseBottom.x - 16, baseTop.y)
  ctx.ellipse(baseTop.x, baseTop.y, 16, 7, 0, Math.PI, 0, true)
  ctx.lineTo(baseBottom.x + 16, baseBottom.y)
  ctx.ellipse(baseBottom.x, baseBottom.y, 16, 8, 0, 0, Math.PI)
  ctx.fill()
  ctx.strokeStyle = '#374151'
  ctx.stroke()
  
  const baseFaceGrad = ctx.createLinearGradient(baseTop.x - 16, 0, baseTop.x + 16, 0)
  baseFaceGrad.addColorStop(0, '#6b7280')
  baseFaceGrad.addColorStop(0.5, '#9ca3af')
  baseFaceGrad.addColorStop(1, '#6b7280')
  
  ctx.beginPath()
  ctx.ellipse(baseTop.x, baseTop.y, 18, 8, 0, 0, Math.PI * 2)
  ctx.fillStyle = baseFaceGrad
  ctx.fill()
  ctx.strokeStyle = '#4b5563'
  ctx.lineWidth = 1.5
  ctx.stroke()
  
  const shoulderPt = project(shoulderX, shoulderY, shoulderZ + 10)
  const upperEndPt = project(upperEndX, upperEndY, shoulderZ + 6)
  
  drawArmSegment(shoulderPt, upperEndPt, 14, '#9ca3af', '#6b7280', '#d1d5db')
  
  const elbowPt = upperEndPt
  const foreEndPt = project(foreEndX, foreEndY, shoulderZ + 4)
  
  drawArmSegment(elbowPt, foreEndPt, 10, '#d1d5db', '#9ca3af', '#e5e7eb')
  
  const wristPt = foreEndPt
  
  ctx.beginPath()
  ctx.arc(elbowPt.x, elbowPt.y, 8, 0, Math.PI * 2)
  const elbowGrad = ctx.createRadialGradient(elbowPt.x - 2, elbowPt.y - 2, 0, elbowPt.x, elbowPt.y, 8)
  elbowGrad.addColorStop(0, '#e5e7eb')
  elbowGrad.addColorStop(1, '#6b7280')
  ctx.fillStyle = elbowGrad
  ctx.fill()
  ctx.strokeStyle = '#4b5563'
  ctx.lineWidth = 1.2
  ctx.stroke()
  
  drawGripper(wristPt, wristAngleAbs, gripperOpen, shoulderZ + 4)
  
  if (armHoldingWafer) {
    drawWafer(foreEndX + Math.cos(wristAngleAbs) * 8, foreEndY + Math.sin(wristAngleAbs) * 8, shoulderZ + 2, 18)
  }
}

function drawArmSegment(start, end, thickness, topColor, sideColor, highlightColor) {
  const dx = end.x - start.x
  const dy = end.y - start.y
  const len = Math.sqrt(dx * dx + dy * dy)
  if (len < 1) return
  
  const nx = -dy / len
  const ny = dx / len
  
  const halfT = thickness / 2
  const depthOffset = 3
  
  const topPts = [
    { x: start.x + nx * halfT, y: start.y + ny * halfT - depthOffset },
    { x: end.x + nx * halfT, y: end.y + ny * halfT - depthOffset },
    { x: end.x - nx * halfT, y: end.y - ny * halfT - depthOffset },
    { x: start.x - nx * halfT, y: start.y - ny * halfT - depthOffset },
  ]
  
  const sidePts = [
    { x: start.x - nx * halfT, y: start.y - ny * halfT - depthOffset },
    { x: end.x - nx * halfT, y: end.y - ny * halfT - depthOffset },
    { x: end.x - nx * halfT, y: end.y - ny * halfT + depthOffset * 0.5 },
    { x: start.x - nx * halfT, y: start.y - ny * halfT + depthOffset * 0.5 },
  ]
  
  const bottomPts = [
    { x: start.x + nx * halfT, y: start.y + ny * halfT + depthOffset * 0.5 },
    { x: end.x + nx * halfT, y: end.y + ny * halfT + depthOffset * 0.5 },
    { x: end.x - nx * halfT, y: end.y - ny * halfT + depthOffset * 0.5 },
    { x: start.x - nx * halfT, y: start.y - ny * halfT + depthOffset * 0.5 },
  ]
  
  drawPoly(bottomPts, sideColor, '#374151', 1)
  drawPoly(sidePts, shadeColor(sideColor, -8), '#374151', 1)
  drawPoly(topPts, topColor, '#4b5563', 1.2)
  
  const hlStart = { x: start.x + nx * (halfT * 0.3), y: start.y + ny * (halfT * 0.3) - depthOffset }
  const hlEnd = { x: end.x + nx * (halfT * 0.3), y: end.y + ny * (halfT * 0.3) - depthOffset }
  
  ctx.beginPath()
  ctx.moveTo(hlStart.x, hlStart.y)
  ctx.lineTo(hlEnd.x, hlEnd.y)
  ctx.strokeStyle = highlightColor
  ctx.lineWidth = 2
  ctx.globalAlpha = 0.6
  ctx.stroke()
  ctx.globalAlpha = 1
}

function drawGripper(wristPt, angle, open, z) {
  const gripLen = 20
  const openAmount = open ? 8 : 3
  
  const cosA = Math.cos(angle)
  const sinA = Math.sin(angle)
  const perpX = -sinA
  const perpY = cosA
  
  const baseW = 6
  const basePt = {
    x: wristPt.x + cosA * 2,
    y: wristPt.y + sinA * 2 - 2,
  }
  
  const baseGrad = ctx.createLinearGradient(
    wristPt.x - perpX * baseW, wristPt.y - perpY * baseW,
    wristPt.x + perpX * baseW, wristPt.y + perpY * baseW
  )
  baseGrad.addColorStop(0, '#9ca3af')
  baseGrad.addColorStop(0.5, '#d1d5db')
  baseGrad.addColorStop(1, '#9ca3af')
  
  ctx.save()
  ctx.translate(wristPt.x, wristPt.y)
  ctx.rotate(angle)
  
  ctx.fillStyle = baseGrad
  ctx.beginPath()
  ctx.roundRect(-2, -baseW, 12, baseW * 2, 2)
  ctx.fill()
  ctx.strokeStyle = '#4b5563'
  ctx.lineWidth = 1
  ctx.stroke()
  
  ctx.fillStyle = '#e5e7eb'
  ctx.strokeStyle = '#6b7280'
  ctx.lineWidth = 1
  
  ctx.beginPath()
  ctx.moveTo(8, -openAmount)
  ctx.lineTo(8 + gripLen, -openAmount - 2)
  ctx.lineTo(8 + gripLen + 3, -openAmount + 1)
  ctx.lineTo(8 + gripLen, -openAmount + 4)
  ctx.lineTo(8, -openAmount + 2)
  ctx.closePath()
  ctx.fill()
  ctx.stroke()
  
  ctx.beginPath()
  ctx.moveTo(8, openAmount)
  ctx.lineTo(8 + gripLen, openAmount + 2)
  ctx.lineTo(8 + gripLen + 3, openAmount - 1)
  ctx.lineTo(8 + gripLen, openAmount - 4)
  ctx.lineTo(8, openAmount - 2)
  ctx.closePath()
  ctx.fill()
  ctx.stroke()
  
  ctx.restore()
}

function drawChamberGlow() {
  if (!chamberProcessing) return
  
  const glow = 0.3 + 0.2 * Math.sin(animTime * 3)
  const u = UNITS.CHAMBER_A
  const center = project(u.x + u.w / 2, u.y + u.d / 2, 25)
  ctx.save()
  ctx.globalAlpha = glow
  const grad = ctx.createRadialGradient(center.x, center.y, 0, center.x, center.y, 45)
  grad.addColorStop(0, '#22c55e')
  grad.addColorStop(1, 'transparent')
  ctx.fillStyle = grad
  ctx.beginPath()
  ctx.arc(center.x, center.y, 45, 0, Math.PI * 2)
  ctx.fill()
  ctx.restore()
}

function drawChamberProcessRing() {
  if (!chamberProcessing) return
  
  const u = UNITS.CHAMBER_A
  const center = project(u.x + u.w / 2, u.y + u.d / 2, 22)
  const radius = 28
  
  ctx.save()
  ctx.beginPath()
  ctx.arc(center.x, center.y, radius, -Math.PI / 2, -Math.PI / 2 + chamberProgress * Math.PI * 2)
  ctx.strokeStyle = '#22c55e'
  ctx.lineWidth = 3
  ctx.lineCap = 'round'
  ctx.stroke()
  ctx.restore()
}

function drawPortDoors() {
  ;['PORT1', 'PORT2'].forEach(id => {
    const u = UNITS[id]
    const zH = 20
    const p1 = project(u.x + 10, u.y + u.d * 0.6, zH)
    const p2 = project(u.x + u.w - 10, u.y + u.d * 0.6, zH)
    const p3 = project(u.x + u.w - 10, u.y + u.d - 2, 0)
    const p4 = project(u.x + 10, u.y + u.d - 2, 0)
    drawPoly([p1, p2, p3, p4], 'rgba(2, 6, 23, 0.6)', 'rgba(15, 23, 42, 0.5)', 1)
  })
}

function drawPods() {
  ;['PORT1', 'PORT2'].forEach((id, idx) => {
    const u = UNITS[id === 'PORT1' ? 'SMIF1' : 'SMIF2']
    const center = project(u.x + u.w / 2, u.y + u.d / 2, 25)
    
    ctx.fillStyle = 'rgba(31, 41, 55, 0.7)'
    ctx.strokeStyle = 'rgba(100, 116, 139, 0.5)'
    ctx.lineWidth = 1.2
    ctx.beginPath()
    ctx.moveTo(center.x - 26, center.y + 24)
    ctx.lineTo(center.x - 26, center.y - 22)
    ctx.quadraticCurveTo(center.x - 23, center.y - 32, center.x - 13, center.y - 32)
    ctx.lineTo(center.x + 13, center.y - 32)
    ctx.quadraticCurveTo(center.x + 23, center.y - 32, center.x + 26, center.y - 22)
    ctx.lineTo(center.x + 26, center.y + 24)
    ctx.quadraticCurveTo(center.x + 24, center.y + 32, center.x + 11, center.y + 32)
    ctx.lineTo(center.x - 11, center.y + 32)
    ctx.quadraticCurveTo(center.x - 24, center.y + 32, center.x - 26, center.y + 24)
    ctx.closePath()
    ctx.fill()
    ctx.stroke()
    
    ctx.fillStyle = 'rgba(96, 165, 250, 0.15)'
    ctx.fillRect(center.x - 14, center.y + 8, 28, 11)
    ctx.strokeStyle = 'rgba(96, 165, 250, 0.3)'
    ctx.strokeRect(center.x - 14, center.y + 8, 28, 11)
  })
}

function drawWaferCounter() {
  ctx.fillStyle = 'rgba(13, 20, 36, 0.9)'
  ctx.strokeStyle = '#2a4060'
  ctx.lineWidth = 1
  ctx.fillRect(10, 10, 180, 52)
  ctx.strokeRect(10, 10, 180, 52)
  
  ctx.fillStyle = '#e5e7eb'
  ctx.font = 'bold 13px "Segoe UI", sans-serif'
  ctx.textAlign = 'left'
  ctx.fillText('WAFER PROGRESS', 20, 30)
  
  ctx.fillStyle = '#94a3b8'
  ctx.font = '12px "Segoe UI", sans-serif'
  ctx.fillText(`Wafer ${currentWafer} / ${TOTAL_WAFERS}`, 20, 50)
  
  const barX = 100
  const barY = 42
  const barW = 82
  const barH = 8
  ctx.fillStyle = '#1e293b'
  ctx.fillRect(barX, barY, barW, barH)
  ctx.fillStyle = '#22c55e'
  ctx.fillRect(barX, barY, barW * (currentWafer / TOTAL_WAFERS), barH)
  ctx.strokeStyle = '#334155'
  ctx.lineWidth = 1
  ctx.strokeRect(barX, barY, barW, barH)
}

function drawStatusLabel() {
  let status = 'IDLE'
  let color = '#64748b'
  
  if (chamberProcessing) {
    status = 'PROCESSING'
    color = '#22c55e'
  } else if (armHoldingWafer) {
    status = 'TRANSFERRING'
    color = '#3b82f6'
  } else {
    status = 'RUNNING'
    color = '#22c55e'
  }
  
  ctx.fillStyle = color
  ctx.font = 'bold 18px "Segoe UI", sans-serif'
  ctx.textAlign = 'center'
  ctx.fillText(status, width.value / 2, 32)
  ctx.textAlign = 'left'
}

function drawScene() {
  if (!ctx) return
  animTime += 0.016

  ctx.clearRect(0, 0, width.value, height.value)
  
  const bgGrad = ctx.createLinearGradient(0, 0, 0, height.value)
  bgGrad.addColorStop(0, '#040712')
  bgGrad.addColorStop(0.5, '#0a0f1c')
  bgGrad.addColorStop(1, '#040712')
  ctx.fillStyle = bgGrad
  ctx.fillRect(0, 0, width.value, height.value)
  
  drawGroundGrid()
  
  drawUnit(UNITS.PA, 18)
  drawUnit(UNITS.CHAMBER_A, 25)
  drawUnit(UNITS.CHAMBER_B, 25)
  drawUnit(UNITS.CHAMBER_C, 22)
  drawUnit(UNITS.ARM, 10)
  drawArmZone()
  
  drawUnit(UNITS.PORT1, 20)
  drawUnit(UNITS.PORT2, 20)
  drawUnit(UNITS.SMIF1, 15)
  drawUnit(UNITS.SMIF2, 15)
  drawPortDoors()
  drawPods()
  
  drawChamberGlow()
  drawChamberProcessRing()
  
  drawSCARArm()
  
  if (waferAtPort1) {
    const c = getUnitCenter('PORT1')
    drawWafer(c.x + 30, c.y - 10, 28)
  }

  if (waferAtPA) {
    const c = getUnitCenter('PA')
    drawWafer(c.x + 20, c.y, 28)
  }

  if (waferInChamber) {
    const c = getUnitCenter('CHAMBER_A')
    drawWafer(c.x + 10, c.y + 20, 33)
  }
  
  drawWaferCounter()
  drawStatusLabel()
}

let isPaused = false

// 监听外部 paused 属性
watch(() => props.paused, (val) => {
  isPaused = val
})

function animate() {
  if (!isPaused) {
    updatePhaseMachine()
  }
  drawScene()
  rafId = requestAnimationFrame(animate)
}

function resizeCanvas() {
  if (!containerRef.value || !canvasRef.value) return
  const rect = containerRef.value.getBoundingClientRect()
  width.value = Math.max(100, rect.width)
  height.value = Math.max(100, rect.height)
  if (canvasRef.value) {
    canvasRef.value.width = width.value
    canvasRef.value.height = height.value
  }
}

onMounted(async () => {
  await nextTick()
  resizeCanvas()
  window.addEventListener('resize', resizeCanvas)
  if (canvasRef.value) {
    ctx = canvasRef.value.getContext('2d')
    
    waferAtPort1 = true
    startPhase(PHASES.MOVE_TO_PORT1)
    setArmTarget(getPort1PickPos().x + 20, getPort1PickPos().y, 20, true)
    shoulderAngle = targetShoulderAngle
    elbowAngle = targetElbowAngle
    wristAngle = targetWristAngle
    armZ = targetArmZ
    gripperOpen = targetGripperOpen
    
    animate()
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeCanvas)
  if (rafId) cancelAnimationFrame(rafId)
})
</script>

<template>
  <div ref="containerRef" class="iso-viewer">
    <canvas ref="canvasRef" :width="width" :height="height" class="iso-canvas" />
    <div class="iso-legend">
      <div class="legend-item"><span class="dot" style="background:#22c55e"></span><span>Processing</span></div>
      <div class="legend-item"><span class="dot" style="background:#3b82f6"></span><span>Transferring</span></div>
      <div class="legend-item"><span class="dot" style="background:#6b7280"></span><span>Wafer</span></div>
      <div class="legend-item"><span class="dot" style="background:#94a3b8"></span><span>Idle</span></div>
    </div>
  </div>
</template>

<style scoped>
.iso-viewer {
  position: relative;
  width: 100%;
  height: 100%;
  background: #040712;
  border-radius: 8px;
  overflow: hidden;
}
.iso-canvas { display: block; }
.iso-legend {
  position: absolute;
  left: 12px;
  bottom: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  background: rgba(13, 20, 36, 0.9);
  backdrop-filter: blur(8px);
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid #1e2d44;
  font-size: 12px;
  color: #94a3b8;
}
.legend-item { display: inline-flex; align-items: center; gap: 6px; }
.dot { width: 10px; height: 10px; border-radius: 50%; }
</style>
