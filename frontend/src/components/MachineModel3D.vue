<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { stateColors, stateLabels } from '../composables/useThree'

// TEL DRM UNITY 单机 3D 模型：EFEM + VTM + 4 工艺腔 + 气体面板 + 状态灯塔 + 控制屏 + 动画
const props = defineProps({
  // 机台对象
  machine: { type: Object, default: null },
  // 当前状态 run/idle/error/maint/setup
  currentState: { type: String, default: 'run' },
  // 实时指标
  metrics: {
    type: Object,
    default: () => ({ temp: 22, pressure: 1, gas: 0, rf: 0, waferCount: 0 }),
  },
  // 当前工艺步骤
  processStep: { type: String, default: '待机' },
  // 是否触发门开启动画（晶圆传输）
  transferTrigger: { type: Number, default: 0 },
  // Run货动画状态（与2D同步）
  runState: { type: Object, default: null },
})

const canvasRef = ref(null)
let scene, camera, renderer, controls
let machine = null
let ledMat = null
let chambers = []
let robotArm = null
let door = null
let plasmaList = []
let targetDoor = 0
let currentDoor = 0
let targetRobotAngle = 0
let currentRobotAngle = 0
let targetLEDColor = new THREE.Color(stateColors.run)
let screenTex = null
let screenCanvas = null
let animId = null
let resizeHandler = null

// === 晶圆传输动画系统（由runState驱动） ===
let activeWafer = null
let gripperLeft = null
let gripperRight = null

// 3D场景中各模块的位置
const pos3D = {
  port: { x: -2.5, y: 1.9, z: -0.8 },
  pa: { x: -1.5, y: 1.9, z: 0 },
  vtm: { x: 0, y: 2.0, z: 0 },
  chamberA: { x: -2.2, y: 1.8, z: 0 },
  chamberB: { x: 0, y: 1.8, z: 2.2 },
  chamberC: { x: 2.2, y: 1.8, z: 0 },
  idle: { x: 0, y: 1.0, z: 0 },
}

function createWafer() {
  const geo = new THREE.CylinderGeometry(0.35, 0.35, 0.015, 32)
  const mat = new THREE.MeshStandardMaterial({
    color: 0xc0c8d4,
    metalness: 0.95,
    roughness: 0.1,
    emissive: 0x00d4ff,
    emissiveIntensity: 0.3,
  })
  const wafer = new THREE.Mesh(geo, mat)
  wafer.castShadow = true
  return wafer
}

function ensureWafer() {
  if (!activeWafer && machine) {
    activeWafer = createWafer()
    activeWafer.visible = false
    machine.add(activeWafer)
  }
}

// 由 runState 驱动3D动画
function updateFromRunState() {
  if (!props.runState) return
  ensureWafer()
  if (!activeWafer || !robotArm) return
  
  const rs = props.runState
  
  // === 机械臂旋转 ===
  // 2D角度 → 3D角度映射
  // 2D: 0=右(chamberC), 90=下(idle), 150=port, 180=pa, 250=chamberA, 290=chamberB
  // 3D: robotArm绕Y轴旋转
  const angleDeg = rs.armAngle || 90
  targetRobotAngle = -(angleDeg - 90) * Math.PI / 180
  
  // === 机械臂伸缩 ===
  // robotArm的子臂可以伸缩，通过scale或position调整
  const ext = rs.armExtension || 0
  if (robotArm.children.length > 1) {
    // 第二段臂（伸缩臂）
    const extArm = robotArm.children.find(c => c.userData && c.userData.isExtArm)
    if (extArm) {
      extArm.position.y = 0.5 + ext * 0.8
      extArm.scale.y = 1 + ext * 0.5
    }
  }
  
  // === 夹爪开合 ===
  if (gripperLeft && gripperRight) {
    const gap = rs.gripperClosed ? 0.18 : 0.32
    gripperLeft.position.x = -gap
    gripperRight.position.x = gap
  }
  
  // === 晶圆位置 ===
  const loc = rs.waferLocation
  let targetPos = null
  let visible = false
  
  if (loc === 'arm' && rs.armHolding) {
    // 晶圆在机械臂上，跟随臂尖
    visible = true
    // 计算臂尖在3D空间的位置
    const angleRad = targetRobotAngle
    const armLen = 0.5 + ext * 0.8
    // 机械臂从中心向上延伸，旋转角度决定方向
    targetPos = {
      x: robotArm.position.x + Math.sin(angleRad) * armLen * 0.5,
      y: 2.0 + armLen,
      z: robotArm.position.z + Math.cos(angleRad) * armLen * 0.5,
    }
  } else if (loc === 'port') {
    visible = true
    targetPos = pos3D.port
  } else if (loc === 'pa') {
    visible = true
    targetPos = pos3D.pa
  } else if (loc === 'chamberA') {
    visible = true
    targetPos = pos3D.chamberA
  } else if (loc === 'chamberB') {
    visible = true
    targetPos = pos3D.chamberB
  } else if (loc === 'chamberC') {
    visible = true
    targetPos = pos3D.chamberC
  }
  
  if (activeWafer && targetPos) {
    // 平滑移动到目标位置
    activeWafer.position.x += (targetPos.x - activeWafer.position.x) * 0.3
    activeWafer.position.y += (targetPos.y - activeWafer.position.y) * 0.3
    activeWafer.position.z += (targetPos.z - activeWafer.position.z) * 0.3
    activeWafer.visible = visible
    
    // 加工中发光效果
    if (loc && loc.startsWith('chamber')) {
      activeWafer.material.emissiveIntensity = 0.3 + Math.sin(Date.now() * 0.01) * 0.2
    } else {
      activeWafer.material.emissiveIntensity = 0.3
    }
  } else if (activeWafer) {
    activeWafer.visible = false
  }
  
  // 门动画：臂伸出时开门
  targetDoor = ext > 0.3 ? 1 : 0
}

// 构建完整 TEL DRM UNITY 机器模型
function buildMachine() {
  machine = new THREE.Group()
  scene.add(machine)

  const steelMat = new THREE.MeshStandardMaterial({ color: 0x4a5a7a, metalness: 0.7, roughness: 0.3 })
  const steelDarkMat = new THREE.MeshStandardMaterial({ color: 0x2a3a5a, metalness: 0.6, roughness: 0.4 })
  const alumMat = new THREE.MeshStandardMaterial({ color: 0xb0bccc, metalness: 0.85, roughness: 0.2 })

  // === 主底座 ===
  const base = new THREE.Mesh(new THREE.BoxGeometry(5.5, 0.5, 4.5), steelDarkMat)
  base.position.y = 0.25
  base.castShadow = base.receiveShadow = true
  machine.add(base)

  // === EFEM 前端大气模块 ===
  const efem = new THREE.Mesh(new THREE.BoxGeometry(1.5, 2.8, 3.5), steelDarkMat)
  efem.position.set(-2, 1.9, 0)
  efem.castShadow = true
  machine.add(efem)

  // 2 个 Load Port + FOUP
  const lpMat = new THREE.MeshStandardMaterial({ color: 0x0f1828, metalness: 0.5, roughness: 0.5 })
  for (let i = 0; i < 2; i++) {
    const lp = new THREE.Mesh(new THREE.BoxGeometry(0.2, 1.2, 1.3), lpMat)
    lp.position.set(-2.85, 1.8, -0.8 + i * 1.6)
    lp.castShadow = true
    machine.add(lp)

    // FOUP 传片盒
    const foupBody = new THREE.Mesh(
      new THREE.BoxGeometry(0.55, 0.8, 1.1),
      new THREE.MeshStandardMaterial({ color: 0xff7b00, metalness: 0.3, roughness: 0.6 })
    )
    foupBody.position.set(-3.15, 2.0, -0.8 + i * 1.6)
    foupBody.castShadow = true
    machine.add(foupBody)

    // FOUP 门
    const foupDoor = new THREE.Mesh(
      new THREE.BoxGeometry(0.08, 0.5, 0.7),
      new THREE.MeshStandardMaterial({ color: 0xcc5500, metalness: 0.4, roughness: 0.5 })
    )
    foupDoor.position.set(-3.48, 2.0, -0.8 + i * 1.6)
    machine.add(foupDoor)

    // FOUP 标签
    const lblTex = new THREE.CanvasTexture(makeLabelCanvas('FOUP-' + (i + 1), '#fff', 16))
    const lblMat = new THREE.MeshBasicMaterial({ map: lblTex, transparent: true })
    const lbl = new THREE.Mesh(new THREE.PlaneGeometry(0.45, 0.12), lblMat)
    lbl.position.set(-3.16, 2.35, -0.8 + i * 1.6)
    lbl.rotation.y = Math.PI / 2
    machine.add(lbl)
  }

  // EFEM 大气机械臂（夹住晶圆结构）
  const efemRobot = new THREE.Group()
  const efemBase = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.25, 0.3, 12), steelMat)
  efemBase.position.y = 0.8
  efemRobot.add(efemBase)
  const efemArm = new THREE.Mesh(new THREE.BoxGeometry(0.08, 1.2, 0.08), alumMat)
  efemArm.position.y = 1.5
  efemRobot.add(efemArm)
  
  // EFEM夹爪
  const efemGripper = new THREE.Group()
  const efemGripBase = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.05, 0.25), alumMat)
  efemGripBase.position.y = 2.1
  efemGripper.add(efemGripBase)
  const efemGripLeft = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.4, 0.15), alumMat)
  efemGripLeft.position.set(-0.25, 1.9, 0)
  efemGripper.add(efemGripLeft)
  const efemGripRight = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.4, 0.15), alumMat)
  efemGripRight.position.set(0.25, 1.9, 0)
  efemGripper.add(efemGripRight)
  
  efemRobot.add(efemGripper)
  efemRobot.position.set(-2, 0, 0)
  machine.add(efemRobot)

  // === VTM 真空传输室 ===
  const vtm = new THREE.Mesh(new THREE.CylinderGeometry(1.3, 1.3, 2.2, 24), steelDarkMat)
  vtm.position.set(0, 1.6, 0)
  vtm.castShadow = true
  machine.add(vtm)

  const vtmTop = new THREE.Mesh(new THREE.CylinderGeometry(1.4, 1.4, 0.2, 24), steelMat)
  vtmTop.position.set(0, 2.8, 0)
  machine.add(vtmTop)

  // VTM 真空机械臂（旋转+伸缩+夹爪）
  const vacRobot = new THREE.Group()
  const vacBase = new THREE.Mesh(new THREE.CylinderGeometry(0.25, 0.3, 0.25, 12), steelMat)
  vacBase.position.y = 0.8
  vacRobot.add(vacBase)
  
  // 第一段臂（固定段）
  const vacArm1 = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.8, 0.08), alumMat)
  vacArm1.position.y = 1.4
  vacRobot.add(vacArm1)
  
  // 第二段臂（伸缩段）- 标记为可伸缩
  const vacArm2 = new THREE.Group()
  vacArm2.userData.isExtArm = true
  const extArmMesh = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.6, 0.06), alumMat)
  extArmMesh.position.y = 0.3
  vacArm2.add(extArmMesh)
  vacArm2.position.set(0, 1.8, 0)
  vacRobot.add(vacArm2)
  
  // 夹爪结构（在伸缩臂末端）
  const gripperGroup = new THREE.Group()
  gripperGroup.position.set(0, 0.6, 0) // 相对于伸缩臂末端
  vacArm2.add(gripperGroup)
  
  const gripperBase = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.05, 0.2), alumMat)
  gripperGroup.add(gripperBase)
  
  // 左夹爪（可开合）
  gripperLeft = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.3, 0.12), alumMat)
  gripperLeft.position.set(-0.25, 0.15, 0)
  gripperGroup.add(gripperLeft)
  
  // 右夹爪（可开合）
  gripperRight = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.3, 0.12), alumMat)
  gripperRight.position.set(0.25, 0.15, 0)
  gripperGroup.add(gripperRight)
  
  robotArm = vacRobot
  robotArm.position.set(0, 0.5, 0)
  machine.add(robotArm)

  // === 4 个工艺腔 PM-1~PM-4（环绕 VTM）===
  const chamMat = new THREE.MeshStandardMaterial({ color: 0x5a6a8a, metalness: 0.7, roughness: 0.3 })
  const chamTopMat = new THREE.MeshStandardMaterial({ color: 0x6a7a9a, metalness: 0.6, roughness: 0.35 })

  const chamPositions = [
    { x: 2.2, z: 0, angle: 0 },
    { x: 0, z: 2.2, angle: Math.PI / 2 },
    { x: -2.2, z: 0, angle: Math.PI },
    { x: 0, z: -2.2, angle: -Math.PI / 2 },
  ]

  chambers = []
  plasmaList = []
  chamPositions.forEach((cp, idx) => {
    const chGroup = new THREE.Group()

    // 腔体主体
    const body = new THREE.Mesh(new THREE.CylinderGeometry(0.8, 0.9, 1.5, 24), chamMat)
    body.position.y = 1.8
    body.castShadow = true
    chGroup.add(body)

    // 腔体顶盖
    const lid = new THREE.Mesh(new THREE.CylinderGeometry(0.95, 0.95, 0.25, 24), chamTopMat)
    lid.position.y = 2.7
    chGroup.add(lid)

    // 顶部 RF 电源
    const rfGen = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.5, 0.4), steelDarkMat)
    rfGen.position.y = 3.1
    chGroup.add(rfGen)

    // 等离子体辉光（工艺时显示）
    const plasma = new THREE.Mesh(
      new THREE.CylinderGeometry(0.5, 0.5, 1, 24),
      new THREE.MeshBasicMaterial({ color: 0x00d4ff, transparent: true, opacity: 0 })
    )
    plasma.position.y = 1.8
    chGroup.add(plasma)
    plasmaList.push(plasma)

    // PM 标签
    const lblTex = new THREE.CanvasTexture(makeLabelCanvas('PM-' + (idx + 1), '#00d4ff', 16))
    const lblMat = new THREE.MeshBasicMaterial({ map: lblTex, transparent: true })
    const lbl = new THREE.Mesh(new THREE.PlaneGeometry(0.6, 0.15), lblMat)
    if (cp.x > 0) {
      lbl.position.set(0.92, 2.2, 0)
      lbl.rotation.y = -Math.PI / 2
    } else if (cp.x < 0) {
      lbl.position.set(-0.92, 2.2, 0)
      lbl.rotation.y = Math.PI / 2
    } else if (cp.z > 0) {
      lbl.position.set(0, 2.2, 0.92)
    } else {
      lbl.position.set(0, 2.2, -0.92)
      lbl.rotation.y = Math.PI
    }
    chGroup.add(lbl)

    // 槽阀（VTM 与腔体之间的门）
    const valve = new THREE.Mesh(
      new THREE.BoxGeometry(0.6, 0.6, 0.1),
      new THREE.MeshStandardMaterial({ color: 0x1a243a, metalness: 0.6, roughness: 0.4 })
    )
    const vx = cp.x === 0 ? 0 : (cp.x > 0 ? 1.15 : -1.15)
    const vz = cp.z === 0 ? 0 : (cp.z > 0 ? 1.15 : -1.15)
    valve.position.set(vx, 1.8, vz)
    if (cp.x !== 0) valve.rotation.y = Math.PI / 2
    chGroup.add(valve)

    chGroup.position.set(cp.x, 0, cp.z)
    machine.add(chGroup)
    chambers.push({ group: chGroup, plasma, idx })
  })

  // === 状态灯塔（三色塔灯）===
  const towerBase = new THREE.Mesh(
    new THREE.CylinderGeometry(0.06, 0.08, 0.3, 8),
    steelMat
  )
  towerBase.position.set(2.5, 3.4, -1.8)
  machine.add(towerBase)

  ledMat = new THREE.MeshStandardMaterial({
    color: stateColors.run, emissive: stateColors.run, emissiveIntensity: 1.5,
  })
  const led = new THREE.Mesh(new THREE.SphereGeometry(0.18, 16, 16), ledMat)
  led.position.set(2.5, 3.8, -1.8)
  machine.add(led)

  // === 气体面板 ===
  const gasPanel = new THREE.Mesh(
    new THREE.BoxGeometry(0.6, 2.5, 2),
    new THREE.MeshStandardMaterial({ color: 0x0a1120, metalness: 0.5, roughness: 0.5 })
  )
  gasPanel.position.set(2.9, 1.8, 0)
  machine.add(gasPanel)

  // 6 路彩色工艺气管
  const pipeColors = [0xef4444, 0x10b981, 0x3b82f6, 0xf59e0b, 0x8b5cf6, 0xec4899]
  for (let i = 0; i < 6; i++) {
    const pipe = new THREE.Mesh(
      new THREE.CylinderGeometry(0.05, 0.05, 2.2, 8),
      new THREE.MeshStandardMaterial({ color: pipeColors[i], metalness: 0.7, roughness: 0.3 })
    )
    pipe.position.set(2.9 + (i % 2 === 0 ? -0.2 : 0.2), 1.8, -0.7 + Math.floor(i / 2) * 0.7)
    machine.add(pipe)
  }

  // === EFEM 与 VTM 之间的门 ===
  const doorMat = new THREE.MeshStandardMaterial({
    color: 0x1a243a, metalness: 0.6, roughness: 0.4,
    emissive: 0x001100, emissiveIntensity: 0.3,
  })
  door = new THREE.Mesh(new THREE.BoxGeometry(0.1, 1.2, 0.8), doorMat)
  door.position.set(-1.25, 1.8, 0)
  machine.add(door)

  // === 控制面板屏幕（Canvas 实时刷新）===
  screenCanvas = document.createElement('canvas')
  screenCanvas.width = 512
  screenCanvas.height = 320
  drawScreen()
  screenTex = new THREE.CanvasTexture(screenCanvas)
  const screenMat = new THREE.MeshBasicMaterial({ map: screenTex })
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(1.8, 1.1), screenMat)
  screen.position.set(-0.5, 3.6, -1.8)
  screen.rotation.x = -0.3
  machine.add(screen)

  // === 排气管道 ===
  const exhaust = new THREE.Mesh(
    new THREE.CylinderGeometry(0.2, 0.2, 1.5, 12),
    steelMat
  )
  exhaust.position.set(0, 0.75, -2.2)
  exhaust.rotation.x = Math.PI / 2
  machine.add(exhaust)

  // === 顶部电缆桥架 ===
  const cableTray = new THREE.Mesh(
    new THREE.BoxGeometry(5, 0.15, 0.6),
    new THREE.MeshStandardMaterial({ color: 0x1a243a, metalness: 0.5, roughness: 0.5 })
  )
  cableTray.position.set(0, 4.5, 0)
  machine.add(cableTray)
}

// 生成标签 Canvas
function makeLabelCanvas(text, color = '#00d4ff', fontSize = 16) {
  const c = document.createElement('canvas')
  c.width = 128
  c.height = 32
  const ctx = c.getContext('2d')
  ctx.font = `bold ${fontSize}px monospace`
  ctx.fillStyle = color
  ctx.textAlign = 'center'
  ctx.fillText(text, 64, 22)
  return c
}

// 绘制控制面板屏幕
function drawScreen() {
  if (!screenCanvas) return
  const ctx = screenCanvas.getContext('2d')
  const mid = props.machine?.id || 'ETCH-201'
  const state = props.currentState || 'run'

  // 背景
  ctx.fillStyle = '#000814'
  ctx.fillRect(0, 0, screenCanvas.width, screenCanvas.height)
  // 边框
  ctx.strokeStyle = '#00d4ff'
  ctx.lineWidth = 3
  ctx.strokeRect(4, 4, screenCanvas.width - 8, screenCanvas.height - 8)
  // 标题
  ctx.fillStyle = '#00d4ff'
  ctx.font = 'bold 28px monospace'
  ctx.fillText(mid, 20, 45)
  ctx.fillStyle = '#6b7a94'
  ctx.font = '13px monospace'
  ctx.fillText('TEL DRM UNITY · ETCH', 20, 68)
  // 状态
  const stateColorHex = '#' + (stateColors[state] || stateColors.idle).toString(16).padStart(6, '0')
  ctx.fillStyle = stateColorHex
  ctx.font = 'bold 24px monospace'
  ctx.fillText(stateLabels[state] || state, 20, 110)
  // 分隔线
  ctx.fillStyle = '#0f1a30'
  ctx.fillRect(20, 125, screenCanvas.width - 40, 2)

  // 指标
  const m = props.metrics || { temp: 22, pressure: 1, gas: 0, rf: 0, waferCount: 0 }
  ctx.font = '14px monospace'
  ctx.fillStyle = '#6b7a94'
  ctx.fillText('TEMP', 20, 160)
  ctx.fillStyle = m.temp > 70 ? '#f59e0b' : '#e5e7eb'
  ctx.fillText((m.temp || 22).toFixed(1) + ' °C', 120, 160)

  ctx.fillStyle = '#6b7a94'
  ctx.fillText('PRESSURE', 20, 185)
  ctx.fillStyle = '#e5e7eb'
  ctx.fillText((m.pressure || 1).toFixed(3) + ' Pa', 120, 185)

  ctx.fillStyle = '#6b7a94'
  ctx.fillText('GAS FLOW', 20, 210)
  ctx.fillStyle = '#e5e7eb'
  ctx.fillText((m.gas || 0).toFixed(0) + ' sccm', 120, 210)

  ctx.fillStyle = '#6b7a94'
  ctx.fillText('RF POWER', 20, 235)
  ctx.fillStyle = (m.rf || 0) > 0 ? '#10b981' : '#6b7a94'
  ctx.fillText((m.rf || 0).toFixed(0) + ' W', 120, 235)

  // 腔体状态
  ctx.fillStyle = '#6b7a94'
  ctx.font = '12px monospace'
  ctx.fillText('PM1', 260, 155)
  ctx.fillText('PM2', 360, 155)
  ctx.fillText('PM3', 260, 210)
  ctx.fillText('PM4', 360, 210)
  for (let i = 0; i < 4; i++) {
    const col = state === 'run' ? '#10b981' : '#f59e0b'
    ctx.fillStyle = col
    ctx.beginPath()
    ctx.arc(275 + (i % 2) * 100, 148 + Math.floor(i / 2) * 55, 5, 0, Math.PI * 2)
    ctx.fill()
  }

  // 底部状态
  ctx.fillStyle = '#4b5a75'
  ctx.font = '11px monospace'
  ctx.fillText('TIBRV: LIVE | SECS-GEM: OK', 20, 280)
  ctx.fillText(new Date().toTimeString().slice(0, 8), screenCanvas.width - 100, 280)

  if (screenTex) screenTex.needsUpdate = true
}

// 初始化场景
function initScene() {
  const canvas = canvasRef.value
  if (!canvas) return
  const w = canvas.clientWidth || 800
  const h = canvas.clientHeight || 600

  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x040712)
  scene.fog = new THREE.Fog(0x040712, 8, 25)

  camera = new THREE.PerspectiveCamera(42, w / h, 0.1, 100)
  camera.position.set(6, 4.5, 7)

  renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
  renderer.setSize(w, h)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap

  controls = new OrbitControls(camera, canvas)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.minDistance = 4
  controls.maxDistance = 18
  controls.maxPolarAngle = Math.PI / 2.1
  controls.target.set(0, 2.2, 0)

  // 灯光（大幅提亮）
  scene.add(new THREE.AmbientLight(0x8090b0, 1.2))
  const key = new THREE.DirectionalLight(0xffffff, 1.5)
  key.position.set(8, 12, 6)
  key.castShadow = true
  key.shadow.mapSize.set(2048, 2048)
  key.shadow.camera.left = -8
  key.shadow.camera.right = 8
  key.shadow.camera.top = 8
  key.shadow.camera.bottom = -8
  scene.add(key)
  const rim = new THREE.DirectionalLight(0xb0c4de, 0.8)
  rim.position.set(-6, 8, -5)
  scene.add(rim)
  const fill = new THREE.DirectionalLight(0xffffff, 0.6)
  fill.position.set(0, 5, 10)
  scene.add(fill)
  const cyan = new THREE.PointLight(0x00d4ff, 1.0, 20)
  cyan.position.set(-4, 4, 3)
  scene.add(cyan)
  const warm = new THREE.PointLight(0xffaa44, 0.6, 15)
  warm.position.set(4, 3, -3)
  scene.add(warm)

  // 地板
  const fGeo = new THREE.PlaneGeometry(30, 30)
  const fMat = new THREE.MeshStandardMaterial({ color: 0x060d1a, metalness: 0.1, roughness: 0.9 })
  const floor = new THREE.Mesh(fGeo, fMat)
  floor.rotation.x = -Math.PI / 2
  floor.receiveShadow = true
  scene.add(floor)
  const grid = new THREE.GridHelper(30, 30, 0x0f1a30, 0x080f1e)
  grid.position.y = 0.01
  scene.add(grid)

  buildMachine()
  ensureWafer()

  resizeHandler = () => onResize()
  window.addEventListener('resize', resizeHandler)
  animate()
}

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
  if (!controls) return
  controls.update()

  // LED 颜色过渡
  if (ledMat) {
    ledMat.color.lerp(targetLEDColor, 0.08)
    ledMat.emissive.lerp(targetLEDColor, 0.08)
    if (props.currentState === 'run') {
      ledMat.emissiveIntensity = 1.0 + Math.sin(Date.now() * 0.004) * 0.5
    } else if (props.currentState === 'error') {
      ledMat.emissiveIntensity = 0.5 + Math.abs(Math.sin(Date.now() * 0.01)) * 1.5
    } else {
      ledMat.emissiveIntensity = 1.0
    }
  }

  // 门动画
  currentDoor += (targetDoor - currentDoor) * 0.1
  if (door) {
    door.position.y = 1.8 + currentDoor * 0.6
    door.material.emissive.setHex(currentDoor > 0.3 ? 0x002200 : 0x000000)
  }

  // 机械臂旋转
  currentRobotAngle += (targetRobotAngle - currentRobotAngle) * 0.05
  if (robotArm) robotArm.rotation.y = currentRobotAngle

  // 等离子体辉光（运行时）
  plasmaList.forEach(p => {
    const targetOp = props.currentState === 'run'
      ? 0.3 + Math.sin(Date.now() * 0.01 + p.position.x) * 0.1
      : 0
    p.material.opacity += (targetOp - p.material.opacity) * 0.1
  })

  // 晶圆传输动画（由runState驱动）
  updateFromRunState()

  renderer.render(scene, camera)
}

// 监听状态变化
watch(() => props.currentState, (newState) => {
  targetLEDColor.setHex(stateColors[newState] || stateColors.idle)
  drawScreen()
})

// 监听指标变化，刷新屏幕
watch(() => props.metrics, () => {
  drawScreen()
}, { deep: true })

// 监听传输触发：开门 + 机械臂旋转
watch(() => props.transferTrigger, () => {
  if (props.transferTrigger > 0) {
    targetDoor = 1
    targetRobotAngle += Math.PI / 2
    // 延时关门
    setTimeout(() => { targetDoor = 0 }, 2000)
  }
})

// 监听工艺步骤变化
watch(() => props.processStep, () => {
  drawScreen()
})

onMounted(() => {
  setTimeout(() => {
    initScene()
  }, 50)
})

onUnmounted(() => {
  if (animId) cancelAnimationFrame(animId)
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  if (renderer) renderer.dispose()
})
</script>

<template>
  <div class="machine-model-3d">
    <canvas ref="canvasRef" class="model-canvas"></canvas>
  </div>
</template>

<style scoped>
.machine-model-3d {
  width: 100%;
  height: 100%;
  position: relative;
  background: #040712;
}
.model-canvas {
  width: 100%;
  height: 100%;
  display: block;
}
</style>
