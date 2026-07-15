<script setup>
import { ref, onMounted, onUnmounted, watch, computed, nextTick } from 'vue'
import { useEventActionMapping } from '../composables/useEventActionMapping'

const props = defineProps({
  machine: { type: Object, default: () => null },
  modelConfig: { type: Object, default: null },
  currentState: { type: String, default: 'idle' },
  metrics: { type: Object, default: () => ({}) },
  runState: { type: Object, default: null },
})

const containerRef = ref(null)
const canvasRef = ref(null)
const width = ref(800)
const height = ref(600)

let ctx = null
let rafId = null
let animTime = 0

// 使用事件动作映射
const { podProgress, podDirection, waferLocation, chamberState, alarmInfo, processEvent } = useEventActionMapping(props)

// 监听runState变化
watch(() => props.runState, (rs) => {
  if (rs) processEvent(rs)
}, { deep: true })

// 部件布局（与OXE_2D.html一致）
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

const stateColors = {
  idle: '#64748b',
  run: '#22c55e',
  running: '#22c55e',
  error: '#ef4444',
  alarm: '#ef4444',
  maint: '#3b82f6',
  maintenance: '#3b82f6',
  setup: '#f59e0b',
  hold: '#f59e0b',
}

const currentColor = computed(() => {
  if (alarmInfo.value) return alarmInfo.value.color
  const s = (chamberState.value || props.currentState || 'idle').toLowerCase()
  return stateColors[s] || stateColors.idle
})

// 简单2D投影（与OXE_2D.html的project函数一致）
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

function getUnitColor(unit) {
  if (unit.id === 'ARM') return '#1a2333'
  if (unit.id.startsWith('CHAMBER')) {
    const state = chamberState.value?.toLowerCase() || props.currentState?.toLowerCase()
    if (state === 'run' || state === 'running') return '#15803d'
    if (state === 'alarm' || state === 'error') return '#991b1b'
    return '#3a4a5e'
  }
  return unit.color
}

function drawGroundGrid() {
  ctx.strokeStyle = 'rgba(100, 116, 139, 0.1)'
  ctx.lineWidth = 1
  for (let x = -300; x <= 300; x += 30) {
    const p1 = project(x, -240)
    const p2 = project(x, 280)
    ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke()
  }
  for (let y = -240; y <= 280; y += 30) {
    const p1 = project(-300, y)
    const p2 = project(300, y)
    ctx.beginPath(); ctx.moveTo(p1.x, p1.y); ctx.lineTo(p2.x, p2.y); ctx.stroke()
  }
}

function drawUnit(unit) {
  const color = getUnitColor(unit)
  const fill = shadeColor(color, 8)
  const pts = [
    project(unit.x, unit.y),
    project(unit.x + unit.w, unit.y),
    project(unit.x + unit.w, unit.y + unit.d),
    project(unit.x, unit.y + unit.d),
  ]
  drawPoly(pts, fill, '#334155', 1.2)

  // 标签
  const center = project(unit.x + unit.w / 2, unit.y + unit.d / 2)
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
  const i1 = 0.26 * t.w
  const i2 = 0.26 * t.d
  const r1 = 0.5 * t.w
  const r2 = 0.5 * t.d
  drawPoly([
    project(cx - i1, cy - i2),
    project(cx + i1, cy - i2),
    project(cx + r1, cy - r2),
    project(cx + r1, cy + r2),
    project(cx + i1, cy + i2),
    project(cx - i1, cy + i2),
    project(cx - r1, cy + r2),
    project(cx - r1, cy - r2),
  ], 'rgba(30, 40, 60, 0.85)', '#475569', 1.5)

  // 中心圆
  const center = project(cx, cy)
  ctx.beginPath(); ctx.arc(center.x, center.y, 12, 0, Math.PI * 2)
  ctx.strokeStyle = '#64748b'; ctx.lineWidth = 4; ctx.stroke()
  ctx.beginPath(); ctx.arc(center.x, center.y, 5, 0, Math.PI * 2)
  ctx.fillStyle = '#e2e8f0'; ctx.fill()

  // ARM标签
  const labelPos = project(cx + 0.16 * t.w, cy + 0.18 * t.d)
  ctx.fillStyle = '#60a5fa'
  ctx.font = 'bold 14px "Segoe UI", sans-serif'
  ctx.textAlign = 'center'
  ctx.fillText('ARM', labelPos.x, labelPos.y + 4)
}

function drawRobotArm() {
  const t = UNITS.ARM
  const cx = t.x + t.w / 2
  const cy = t.y + t.d / 2
  const home = project(cx, cy)
  // 目标位置（根据状态）
  const state = props.currentState?.toLowerCase()
  let targetX = cx - 8, targetY = cy - 12
  if (state === 'run' || state === 'running') {
    targetX = cx - 80 + Math.sin(animTime * 1.5) * 40
    targetY = cy - 40 + Math.cos(animTime * 1.5) * 20
  }
  const target = project(targetX, targetY)

  const dx = target.x - home.x
  const dy = target.y - home.y
  const dist = Math.sqrt(dx * dx + dy * dy)
  const len = Math.min(220, Math.max(24, dist))
  const ux = dist > 0 ? dx / dist : 1
  const uy = dist > 0 ? dy / dist : 0
  const endX = home.x + ux * len
  const endY = home.y + uy * len

  // 第一段
  ctx.strokeStyle = '#475569'; ctx.lineWidth = 12; ctx.lineCap = 'round'
  ctx.beginPath(); ctx.moveTo(home.x, home.y)
  ctx.lineTo(home.x + ux * len * 0.55, home.y + uy * len * 0.55); ctx.stroke()
  // 第二段
  ctx.strokeStyle = '#94a3b8'; ctx.lineWidth = 8
  ctx.beginPath(); ctx.moveTo(home.x + ux * len * 0.55, home.y + uy * len * 0.55)
  ctx.lineTo(endX, endY); ctx.stroke()
  // 手爪
  const px = -uy, py = ux
  ctx.strokeStyle = '#cbd5e1'; ctx.lineWidth = 5
  ctx.beginPath(); ctx.moveTo(endX, endY)
  ctx.lineTo(endX + 9 * px - 2 * ux, endY + 9 * py - 2 * uy)
  ctx.moveTo(endX, endY)
  ctx.lineTo(endX - 9 * px - 2 * ux, endY - 9 * py - 2 * uy); ctx.stroke()
  // 底座
  ctx.fillStyle = '#64748b'
  ctx.beginPath(); ctx.arc(home.x, home.y, 13, 0, Math.PI * 2); ctx.fill()
  ctx.fillStyle = '#e2e8f0'
  ctx.beginPath(); ctx.arc(home.x, home.y, 6, 0, Math.PI * 2); ctx.fill()
}

function drawPortDoors() {
  ;['PORT1', 'PORT2'].forEach(id => {
    const u = UNITS[id]
    const p1 = project(u.x + 8, u.y + u.d * 0.66)
    const p2 = project(u.x + u.w - 8, u.y + u.d * 0.66)
    const p3 = project(u.x + u.w - 8, u.y + u.d - 4)
    const p4 = project(u.x + 8, u.y + u.d - 4)
    drawPoly([p1, p2, p3, p4], 'rgba(2, 6, 23, 0.5)', 'rgba(15, 23, 42, 0.4)', 1)
  })
}

function drawPods() {
  ;['PORT1', 'PORT2'].forEach(id => {
    const u = UNITS[id]
    const smifId = id === 'PORT1' ? 'SMIF1' : 'SMIF2'
    const smif = UNITS[smifId]

    // 根据podProgress计算偏移（attach时pod下降）
    const yOffset = podProgress.value > 0 ? -30 * podProgress.value : 0
    const center = project(smif.x + smif.w / 2, smif.y + smif.d / 2 + yOffset, 2)

    // Pod外壳透明度根据progress变化
    const alpha = 0.4 + 0.3 * podProgress.value
    ctx.fillStyle = `rgba(31, 41, 55, ${alpha})`
    ctx.strokeStyle = 'rgba(100, 116, 139, 0.6)'
    ctx.lineWidth = 1.2
    ctx.beginPath()
    ctx.moveTo(center.x - 24, center.y + 21)
    ctx.lineTo(center.x - 24, center.y - 19)
    ctx.quadraticCurveTo(center.x - 21, center.y - 29, center.x - 12, center.y - 29)
    ctx.lineTo(center.x + 12, center.y - 29)
    ctx.quadraticCurveTo(center.x + 21, center.y - 29, center.x + 24, center.y - 19)
    ctx.lineTo(center.x + 24, center.y + 21)
    ctx.quadraticCurveTo(center.x + 22, center.y + 29, center.x + 10, center.y + 29)
    ctx.lineTo(center.x - 10, center.y + 29)
    ctx.quadraticCurveTo(center.x - 22, center.y + 29, center.x - 24, center.y + 21)
    ctx.closePath()
    ctx.fill(); ctx.stroke()

    // 窗口（attach时窗口更亮）
    const windowAlpha = 0.15 + 0.2 * podProgress.value
    ctx.fillStyle = `rgba(96, 165, 250, ${windowAlpha})`
    ctx.fillRect(center.x - 13, center.y + 7, 26, 10)
  })
}

function drawWafer(id) {
  const u = UNITS[id]
  const center = project(u.x + u.w / 2, u.y + u.d / 2, 8)
  ctx.save()
  ctx.translate(center.x, center.y)
  ctx.scale(1.45, 0.9)
  ctx.beginPath(); ctx.arc(0, 0, 9.5, 0, Math.PI * 2)
  ctx.fillStyle = '#fde68a'; ctx.fill()
  ctx.strokeStyle = '#92400e'; ctx.lineWidth = 1; ctx.stroke()
  ctx.restore()
}

function drawChamberGlow() {
  const state = props.currentState?.toLowerCase()
  if (state !== 'run' && state !== 'running') return
  const glow = 0.3 + 0.2 * Math.sin(animTime * 3)
  ;['CHAMBER_A', 'CHAMBER_B'].forEach(id => {
    const u = UNITS[id]
    const center = project(u.x + u.w / 2, u.y + u.d / 2)
    ctx.save()
    ctx.globalAlpha = glow
    ctx.fillStyle = currentColor.value
    ctx.beginPath(); ctx.arc(center.x, center.y, 30, 0, Math.PI * 2); ctx.fill()
    ctx.restore()
  })
}

function drawWaferMapPanel(portId, side) {
  const panelW = 155
  const panelH = 330
  const panelY = 74
  const ox = side === 'right' ? width.value - panelW - 10 : 10
  const lotId = props.machine?.lot_id || '-'
  const status = props.currentState || 'Idle'

  // Lot信息
  ctx.fillStyle = 'rgba(13, 20, 36, 0.92)'
  ctx.strokeStyle = '#2a4060'; ctx.lineWidth = 1
  ctx.fillRect(ox, 10, panelW, 58); ctx.strokeRect(ox, 10, panelW, 58)
  ctx.fillStyle = '#e5e7eb'; ctx.font = 'bold 11px "Segoe UI", sans-serif'
  ctx.textAlign = 'left'
  ctx.fillText(portId + ' LOT:' + lotId, ox + 8, 28)
  ctx.fillText('Status:', ox + 8, 46)
  ctx.fillStyle = currentColor.value
  ctx.fillText(status, ox + 60, 46)

  // Wafer Map
  ctx.fillStyle = 'rgba(13, 20, 36, 0.92)'
  ctx.strokeStyle = '#2a4060'; ctx.lineWidth = 1
  ctx.fillRect(ox, panelY, panelW, panelH); ctx.strokeRect(ox, panelY, panelW, panelH)
  ctx.fillStyle = '#e5e7eb'; ctx.font = 'bold 11px "Segoe UI", sans-serif'
  ctx.textAlign = 'left'
  ctx.fillText(portId + ' WAFER MAP', ox + 8, panelY + 14)

  for (let s = 25; s >= 1; s--) {
    const sy = panelY + 24 + 11.5 * (25 - s)
    ctx.fillStyle = '#475569'; ctx.font = '10px "Segoe UI", sans-serif'
    ctx.textAlign = 'right'
    const label = s < 10 ? '0' + s : String(s)
    ctx.fillText(label, ox + 22, sy + 4)
    ctx.beginPath(); ctx.ellipse(ox + 88, sy + 1, 46, 4.2, 0, 0, Math.PI * 2)
    ctx.fillStyle = '#334155'; ctx.fill()
    ctx.strokeStyle = '#1e2d44'; ctx.lineWidth = 0.8; ctx.stroke()
  }
}

function drawStatusLabel() {
  const state = props.currentState?.toUpperCase() || 'IDLE'
  ctx.fillStyle = currentColor.value
  ctx.font = 'bold 16px "Segoe UI", sans-serif'
  ctx.textAlign = 'center'
  ctx.fillText(state, width.value / 2, 30)
  ctx.textAlign = 'left'
}

function drawScene() {
  if (!ctx) return
  animTime += 0.016
  ctx.clearRect(0, 0, width.value, height.value)

  drawGroundGrid()

  // 按Z顺序绘制
  drawUnit(UNITS.PA)
  drawUnit(UNITS.CHAMBER_A)
  drawUnit(UNITS.CHAMBER_B)
  drawUnit(UNITS.CHAMBER_C)
  drawUnit(UNITS.ARM)
  drawArmZone()
  drawRobotArm()
  drawUnit(UNITS.PORT1)
  drawUnit(UNITS.PORT2)
  drawUnit(UNITS.SMIF1)
  drawUnit(UNITS.SMIF2)
  drawPortDoors()
  drawPods()
  drawChamberGlow()

  // Wafer Map面板
  drawWaferMapPanel('PORT1', 'left')
  drawWaferMapPanel('PORT2', 'right')

  drawStatusLabel()
}

function animate() {
  drawScene()
  rafId = requestAnimationFrame(animate)
}

function resizeCanvas() {
  if (!containerRef.value || !canvasRef.value) return
  const rect = containerRef.value.getBoundingClientRect()
  width.value = Math.max(100, rect.width)
  height.value = Math.max(100, rect.height)
}

onMounted(async () => {
  await nextTick()
  resizeCanvas()
  window.addEventListener('resize', resizeCanvas)
  if (canvasRef.value) {
    ctx = canvasRef.value.getContext('2d')
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
      <div class="legend-item"><span class="dot" style="background:#22c55e"></span><span>Running</span></div>
      <div class="legend-item"><span class="dot" style="background:#f59e0b"></span><span>Hold</span></div>
      <div class="legend-item"><span class="dot" style="background:#ef4444"></span><span>Alarm</span></div>
      <div class="legend-item"><span class="dot" style="background:#64748b"></span><span>Idle</span></div>
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
