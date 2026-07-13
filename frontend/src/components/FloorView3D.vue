<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { api } from '../api'
import { stateColors, makeTextSprite } from '../composables/useThree'

// 楼层 3D 视图：按楼层加载机台，用简单模型占位，支持后续替换为真实模型
const props = defineProps({
  floorId: { type: Number, default: 3 },
  forceRefresh: { type: Number, default: 0 },
})
const emit = defineEmits(['select-machine'])

const canvasRef = ref(null)
let scene, camera, renderer, controls
let machineGroups = {}
let machineLEDs = {}
let areaMeshes = []
let animId = null
let resizeHandler = null
let raycaster, mouse

const floorData = ref(null)
const machines = ref([])
const areas = ref([])
const tracks = ref([])
const vehicles = ref([])

// 3D 轨迹和天车对象
let trackMeshes = []
let vehicleObjs = {}  // { id: { group, trackPoints, progress, speed } }

// 楼层颜色主题
const floorThemes = {
  1: { floor: 0x0a1a2a, accent: 0x00d4ff, label: '1F 测试与分选区' },
  2: { floor: 0x0a2a1a, accent: 0x10b981, label: '2F 电梯与通道(办公区)' },
  3: { floor: 0x1a0a2a, accent: 0xa78bfa, label: '3F 主生产楼层' },
  4: { floor: 0x2a1a0a, accent: 0xf59e0b, label: '4F 刻蚀区扩展' },
}

async function loadFloor() {
  try {
    floorData.value = await api.getFloor(props.floorId)
    machines.value = floorData.value.machines || []
    areas.value = floorData.value.areas || []
    tracks.value = floorData.value.tracks || []
    vehicles.value = floorData.value.vehicles || []
    rebuildScene()
  } catch (e) {
    console.error('加载楼层数据失败:', e)
  }
}

function initScene() {
  const canvas = canvasRef.value
  if (!canvas) return
  const w = canvas.clientWidth || 800
  const h = canvas.clientHeight || 600

  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x050814)
  scene.fog = new THREE.Fog(0x050814, 40, 100)

  camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 300)
  camera.position.set(25, 30, 35)

  renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
  renderer.setSize(w, h)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap

  controls = new OrbitControls(camera, canvas)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.minDistance = 10
  controls.maxDistance = 80
  controls.maxPolarAngle = Math.PI / 2.1
  controls.target.set(0, 0, 0)

  // 灯光
  scene.add(new THREE.AmbientLight(0x3a4a6a, 0.5))
  const sun = new THREE.DirectionalLight(0xffffff, 0.7)
  sun.position.set(20, 35, 15)
  sun.castShadow = true
  sun.shadow.mapSize.set(2048, 2048)
  sun.shadow.camera.left = -30
  sun.shadow.camera.right = 30
  sun.shadow.camera.top = 30
  sun.shadow.camera.bottom = -30
  scene.add(sun)
  const fill = new THREE.DirectionalLight(0x5a7aaa, 0.3)
  fill.position.set(-15, 15, -15)
  scene.add(fill)
  const pt = new THREE.PointLight(0x00d4ff, 0.5, 50)
  pt.position.set(0, 10, 0)
  scene.add(pt)

  raycaster = new THREE.Raycaster()
  mouse = new THREE.Vector2()
  canvas.addEventListener('click', onCanvasClick)

  resizeHandler = () => onResize()
  window.addEventListener('resize', resizeHandler)
  animate()
}

function clearScene() {
  // 清除旧机台和区域
  Object.values(machineGroups).forEach(g => {
    scene.remove(g)
    g.traverse(child => {
      if (child.geometry) child.geometry.dispose()
      if (child.material) child.material.dispose()
    })
  })
  machineGroups = {}
  machineLEDs = {}

  areaMeshes.forEach(m => {
    scene.remove(m)
    if (m.geometry) m.geometry.dispose()
    if (m.material) m.material.dispose()
  })
  areaMeshes = []

  // 清除轨迹
  trackMeshes.forEach(m => {
    scene.remove(m)
    if (m.geometry) m.geometry.dispose()
    if (m.material) m.material.dispose()
  })
  trackMeshes = []

  // 清除天车
  Object.values(vehicleObjs).forEach(v => {
    scene.remove(v.group)
    v.group.traverse(child => {
      if (child.geometry) child.geometry.dispose()
      if (child.material) child.material.dispose()
    })
  })
  vehicleObjs = {}
}

function rebuildScene() {
  if (!scene) return
  clearScene()
  buildFloor()
  buildAreas()
  buildMachines()
  buildTracks()
  buildVehicles()
}

function buildFloor() {
  const theme = floorThemes[props.floorId] || floorThemes[3]
  
  // 地板
  const floorGeo = new THREE.PlaneGeometry(60, 50)
  const floorMat = new THREE.MeshStandardMaterial({ color: theme.floor, metalness: 0.1, roughness: 0.9 })
  const floor = new THREE.Mesh(floorGeo, floorMat)
  floor.rotation.x = -Math.PI / 2
  floor.receiveShadow = true
  scene.add(floor)
  areaMeshes.push(floor)

  // 网格
  const grid = new THREE.GridHelper(60, 60, 0x15223a, 0x0d1525)
  grid.position.y = 0.01
  scene.add(grid)
  areaMeshes.push(grid)

  // 墙面
  const wallMat = new THREE.MeshStandardMaterial({ color: 0x0a0f1a, metalness: 0.1, roughness: 0.7, side: THREE.BackSide })
  const room = new THREE.BoxGeometry(60, 12, 50)
  const roomMesh = new THREE.Mesh(room, wallMat)
  roomMesh.position.y = 6
  scene.add(roomMesh)
  areaMeshes.push(roomMesh)

  // 天花板灯条
  for (let i = 0; i < 6; i++) {
    for (let j = 0; j < 5; j++) {
      const lightGeo = new THREE.PlaneGeometry(3, 0.6)
      const lightMat = new THREE.MeshBasicMaterial({ color: 0xaaccff, transparent: true, opacity: 0.12 })
      const light = new THREE.Mesh(lightGeo, lightMat)
      light.rotation.x = Math.PI / 2
      light.position.set(-22 + i * 9, 10, -15 + j * 8)
      scene.add(light)
      areaMeshes.push(light)
    }
  }

  // 楼层标签
  const label = makeTextSprite(theme.label, {
    fontSize: 40, color: '#' + theme.accent.toString(16).padStart(6, '0'), 
    width: 512, height: 80, planeWidth: 25, planeHeight: 3,
  })
  label.rotation.x = -Math.PI / 2
  label.position.set(0, 0.1, -22)
  scene.add(label)
  areaMeshes.push(label)
}

function buildAreas() {
  areas.value.forEach(area => {
    // 百分比转 3D 坐标: x% -> -25..25, y% -> -20..20
    const cx = (area.x_pos + area.width / 2 - 50) * 0.5
    const cz = (area.y_pos + area.height / 2 - 40) * 0.4
    const w = (area.width / 100) * 50
    const d = (area.height / 100) * 40

    const color = parseInt(area.color.replace('#', ''), 16) || 0x1e293b
    
    if (area.area_type === 'walkway' || area.area_type === 'stk') {
      // 过道和STK用扁平区域
      const mat = new THREE.MeshStandardMaterial({ 
        color, transparent: true, opacity: 0.4,
        metalness: 0.2, roughness: 0.6,
      })
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, 0.1, d), mat)
      mesh.position.set(cx, 0.05, cz)
      mesh.receiveShadow = true
      scene.add(mesh)
      areaMeshes.push(mesh)

      // 区域标签
      const lbl = makeTextSprite(area.name, {
        fontSize: 24, color: '#ffffff', width: 256, height: 48, planeWidth: Math.min(w, 8), planeHeight: 1,
      })
      lbl.rotation.x = -Math.PI / 2
      lbl.position.set(cx, 0.2, cz)
      scene.add(lbl)
      areaMeshes.push(lbl)
    } else if (area.area_type === 'elevator' || area.area_type === 'exit') {
      // 电梯和逃生门用柱状
      const mat = new THREE.MeshStandardMaterial({ color, transparent: true, opacity: 0.6 })
      const h = area.area_type === 'elevator' ? 6 : 2
      const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat)
      mesh.position.set(cx, h / 2, cz)
      mesh.castShadow = true
      scene.add(mesh)
      areaMeshes.push(mesh)
    } else {
      // 设备区用半透明平面
      const mat = new THREE.MeshStandardMaterial({ 
        color, transparent: true, opacity: 0.25,
        metalness: 0.1, roughness: 0.8,
      })
      const mesh = new THREE.Mesh(new THREE.PlaneGeometry(w, d), mat)
      mesh.rotation.x = -Math.PI / 2
      mesh.position.set(cx, 0.02, cz)
      mesh.receiveShadow = true
      scene.add(mesh)
      areaMeshes.push(mesh)

      // 边框
      const edges = new THREE.EdgesGeometry(new THREE.PlaneGeometry(w, d))
      const lineMat = new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.5 })
      const line = new THREE.LineSegments(edges, lineMat)
      line.rotation.x = -Math.PI / 2
      line.position.set(cx, 0.03, cz)
      scene.add(line)
      areaMeshes.push(line)

      // 区域标签
      const lbl = makeTextSprite(area.name, {
        fontSize: 22, color: '#aaccff', width: 256, height: 48, planeWidth: Math.min(w, 8), planeHeight: 1,
      })
      lbl.rotation.x = -Math.PI / 2
      lbl.position.set(cx, 0.15, cz)
      scene.add(lbl)
      areaMeshes.push(lbl)
    }
  })
}

function buildMachines() {
  machines.value.forEach(m => {
    const x = (m.floor_x - 50) * 0.5
    const z = (m.floor_y - 40) * 0.4
    buildMachineModel(m, x, z)
  })
}

// 百分比坐标转3D坐标
function pctTo3D(px, py) {
  return {
    x: (px - 50) * 0.5,
    z: (py - 40) * 0.4,
  }
}

// 3D坐标转百分比
function pos3D(x, z) {
  return {
    x: x / 0.5 + 50,
    y: z / 0.4 + 40,
  }
}

function buildTracks() {
  tracks.value.forEach(t => {
    if (!t.points || t.points.length < 2) return
    
    // 轨道高度（天车悬挂在天花板下方）
    const railY = 7
    
    // 转换为3D点
    const pts3D = t.points.map(p => {
      const pos = pctTo3D(p[0], p[1])
      return new THREE.Vector3(pos.x, railY, pos.z)
    })
    
    const trackColor = parseInt(t.color.replace('#', ''), 16) || 0x00d4ff

    // 主轨道 — 明亮发光效果
    const curve = new THREE.CatmullRomCurve3(pts3D, false)
    const tubeGeo = new THREE.TubeGeometry(curve, Math.max(50, pts3D.length * 10), 0.12, 8, false)
    const tubeMat = new THREE.MeshStandardMaterial({
      color: trackColor,
      metalness: 0.3,
      roughness: 0.5,
      emissive: trackColor,
      emissiveIntensity: 0.6,
    })
    const tube = new THREE.Mesh(tubeGeo, tubeMat)
    tube.castShadow = true
    scene.add(tube)
    trackMeshes.push(tube)

    // 轨道发光外层（更宽、半透明）
    const glowGeo = new THREE.TubeGeometry(curve, Math.max(50, pts3D.length * 10), 0.3, 8, false)
    const glowMat = new THREE.MeshBasicMaterial({
      color: trackColor,
      transparent: true,
      opacity: 0.15,
    })
    const glow = new THREE.Mesh(glowGeo, glowMat)
    scene.add(glow)
    trackMeshes.push(glow)
    
    // 支撑柱
    pts3D.forEach(p => {
      const colGeo = new THREE.CylinderGeometry(0.08, 0.08, railY, 8)
      const colMat = new THREE.MeshStandardMaterial({ color: 0x333333, metalness: 0.6, roughness: 0.4 })
      const col = new THREE.Mesh(colGeo, colMat)
      col.position.set(p.x, railY / 2, p.z)
      col.castShadow = true
      scene.add(col)
      trackMeshes.push(col)
    })
    
    // 轨道标签
    const startPos = pts3D[0]
    const lbl = makeTextSprite(t.name, {
      fontSize: 24, color: t.color, width: 256, height: 48, planeWidth: 4, planeHeight: 0.6,
    })
    lbl.position.set(startPos.x, railY + 0.5, startPos.z)
    scene.add(lbl)
    trackMeshes.push(lbl)
  })
}

function buildVehicles() {
  vehicles.value.forEach(v => {
    // 确保 track_id 类型匹配（后端返回的可能是 number 或 string）
    const track = tracks.value.find(t => t.id == v.track_id)
    if (!track || !track.points || track.points.length < 2) {
      console.warn('[FloorView3D] 天车', v.id, '找不到轨道 track_id=', v.track_id, '可用轨道=', tracks.value.map(t => t.id))
      return
    }
    
    const railY = 7
    const pts3D = track.points.map(p => {
      const pos = pctTo3D(p[0], p[1])
      return new THREE.Vector3(pos.x, railY, pos.z)
    })
    const curve = new THREE.CatmullRomCurve3(pts3D, false)
    
    // ========== OHT 天车模型 ==========
    const g = new THREE.Group()
    
    // --- 顶部滑轨连接器（与轨道的连接件）---
    const connectorMat = new THREE.MeshStandardMaterial({ color: 0x555555, metalness: 0.8, roughness: 0.2 })
    const connectorL = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.15, 0.4), connectorMat)
    connectorL.position.set(-0.5, 0.38, 0)
    g.add(connectorL)
    const connectorR = connectorL.clone()
    connectorR.position.set(0.5, 0.38, 0)
    g.add(connectorR)
    
    // --- 天车主体（车厢）---
    const bodyMat = new THREE.MeshStandardMaterial({ color: 0x2a4a6a, metalness: 0.5, roughness: 0.4 })
    const body = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.5, 1.0), bodyMat)
    body.position.y = 0.05
    body.castShadow = true
    g.add(body)
    
    // 车身侧面装饰条
    const stripeMat = new THREE.MeshStandardMaterial({ color: 0x00d4ff, emissive: 0x00d4ff, emissiveIntensity: 0.3, metalness: 0.3, roughness: 0.5 })
    const stripeL = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.06, 0.02), stripeMat)
    stripeL.position.set(0, 0.05, 0.51)
    g.add(stripeL)
    const stripeR = stripeL.clone()
    stripeR.position.z = -0.51
    g.add(stripeR)
    
    // --- 悬挂臂（从车身向下连接POD）---
    const armMat = new THREE.MeshStandardMaterial({ color: 0x444444, metalness: 0.7, roughness: 0.3 })
    const armL = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.6, 0.08), armMat)
    armL.position.set(-0.4, -0.35, 0)
    g.add(armL)
    const armR = armL.clone()
    armR.position.set(0.4, -0.35, 0)
    g.add(armR)
    
    // --- POD（承载FOUP的载台）---
    const podMat = new THREE.MeshStandardMaterial({ color: 0x3a5a7a, metalness: 0.4, roughness: 0.5 })
    const pod = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.2, 0.8), podMat)
    pod.position.y = -0.65
    pod.castShadow = true
    g.add(pod)
    
    // POD底座边框
    const podEdgeMat = new THREE.MeshStandardMaterial({ color: 0x556677, metalness: 0.5, roughness: 0.4 })
    const podEdgeF = new THREE.Mesh(new THREE.BoxGeometry(1.22, 0.08, 0.04), podEdgeMat)
    podEdgeF.position.set(0, -0.75, 0.39)
    g.add(podEdgeF)
    const podEdgeB = podEdgeF.clone()
    podEdgeB.position.z = -0.39
    g.add(podEdgeB)
    const podEdgeL = new THREE.Mesh(new THREE.BoxGeometry(0.04, 0.08, 0.78), podEdgeMat)
    podEdgeL.position.set(-0.59, -0.75, 0)
    g.add(podEdgeL)
    const podEdgeR = podEdgeL.clone()
    podEdgeR.position.set(0.59, -0.75, 0)
    g.add(podEdgeR)
    
    // --- FOUP (Front Opening Unified Pod) — 晶圆传送盒 ---
    // FOUP是圆角方形盒子，半透明盖子
    const foupColor = v.lot_id ? 0x00aacc : 0x778899  // 有lot时青色，空时灰色
    const foupMat = new THREE.MeshStandardMaterial({ 
      color: foupColor, metalness: 0.2, roughness: 0.6,
      emissive: v.lot_id ? 0x004455 : 0x000000, 
      emissiveIntensity: v.lot_id ? 0.3 : 0,
    })
    const foup = new THREE.Mesh(new THREE.BoxGeometry(0.7, 0.55, 0.55), foupMat)
    foup.position.set(0, -1.03, 0)
    foup.castShadow = true
    g.add(foup)
    
    // FOUP盖子（顶部半透明）
    const foupLidMat = new THREE.MeshStandardMaterial({ 
      color: 0x99aabb, metalness: 0.1, roughness: 0.7, 
      transparent: true, opacity: 0.6,
    })
    const foupLid = new THREE.Mesh(new THREE.BoxGeometry(0.72, 0.06, 0.57), foupLidMat)
    foupLid.position.set(0, -0.73, 0)
    g.add(foupLid)
    
    // FOUP把手
    const handleMat = new THREE.MeshStandardMaterial({ color: 0x333333, metalness: 0.6, roughness: 0.3 })
    const handleL = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.12, 8), handleMat)
    handleL.position.set(-0.3, -0.72, 0)
    g.add(handleL)
    const handleR = handleL.clone()
    handleR.position.set(0.3, -0.72, 0)
    g.add(handleR)
    
    // FOUP标签（有lot时显示）
    if (v.lot_id) {
      const foupLbl = makeTextSprite(v.lot_id, {
        fontSize: 18, color: '#00ffcc', width: 128, height: 32, planeWidth: 0.8, planeHeight: 0.2,
      })
      foupLbl.position.set(0, -1.03, 0.3)
      g.add(foupLbl)
    }
    
    // --- Cassettes（FOUP内部的晶圆卡盒，侧面可见）---
    // 在FOUP正面画几条细线表示内部wafer
    const waferMat = new THREE.MeshStandardMaterial({ 
      color: 0xaabbcc, metalness: 0.7, roughness: 0.2,
      transparent: true, opacity: 0.7,
    })
    const waferCount = 5  // 可见的wafer数量
    for (let i = 0; i < waferCount; i++) {
      const wafer = new THREE.Mesh(new THREE.PlaneGeometry(0.45, 0.35), waferMat)
      const zOff = -0.12 + (i * 0.06)
      wafer.position.set(0, -1.0, zOff)
      wafer.rotation.y = Math.PI / 2  // 侧面朝外
      g.add(wafer)
    }
    
    // --- 状态灯 ---
    const ledColor = v.state === 'moving' ? 0x10b981 : 0xf59e0b
    const ledMat = new THREE.MeshStandardMaterial({
      color: ledColor, emissive: ledColor, emissiveIntensity: 1.5,
    })
    const led = new THREE.Mesh(new THREE.SphereGeometry(0.1, 12, 12), ledMat)
    led.position.set(0.85, 0.35, 0)
    g.add(led)
    
    // --- ID标签 ---
    const lbl = makeTextSprite(v.id, {
      fontSize: 22, color: '#00d4ff', width: 128, height: 32, planeWidth: 1.8, planeHeight: 0.4,
    })
    lbl.position.set(0, 0.65, 0)
    g.add(lbl)
    
    scene.add(g)
    
    vehicleObjs[v.id] = {
      group: g,
      curve,
      progress: v.progress || 0,
      speed: v.speed || 1.0,
      state: v.state,
      ledMat,
    }
  })
}

function buildMachineModel(m, x, z) {
  const g = new THREE.Group()
  g.position.set(x, 0, z)

  if (m.process_type === 'STK') {
    // STK 传输机：长方形扁平模型
    const baseMat = new THREE.MeshStandardMaterial({ color: 0x1a4a3a, metalness: 0.6, roughness: 0.3 })
    const base = new THREE.Mesh(new THREE.BoxGeometry(6, 0.5, 2), baseMat)
    base.position.y = 0.25
    base.castShadow = base.receiveShadow = true
    g.add(base)

    const bodyMat = new THREE.MeshStandardMaterial({ color: 0x0f2a1a, metalness: 0.5, roughness: 0.4 })
    const body = new THREE.Mesh(new THREE.BoxGeometry(5.5, 1.5, 1.8), bodyMat)
    body.position.y = 1.25
    body.castShadow = true
    g.add(body)

    // 顶部轨道
    const railMat = new THREE.MeshStandardMaterial({ color: 0x2a4a3a, metalness: 0.7, roughness: 0.3 })
    const rail = new THREE.Mesh(new THREE.BoxGeometry(5, 0.2, 0.3), railMat)
    rail.position.y = 2.2
    g.add(rail)

  } else if (m.process_type === 'WAT' || m.process_type === 'WS') {
    // 测试/分选机：中型方块
    const baseMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, metalness: 0.5, roughness: 0.4 })
    const base = new THREE.Mesh(new THREE.BoxGeometry(3, 0.4, 2.5), baseMat)
    base.position.y = 0.2
    base.castShadow = base.receiveShadow = true
    g.add(base)

    const bodyMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, metalness: 0.6, roughness: 0.35 })
    const body = new THREE.Mesh(new THREE.BoxGeometry(2.5, 1.8, 2), bodyMat)
    body.position.y = 1.3
    body.castShadow = true
    g.add(body)

    // 顶部显示屏
    const screenMat = new THREE.MeshBasicMaterial({ color: 0x00d4ff, transparent: true, opacity: 0.3 })
    const screen = new THREE.Mesh(new THREE.PlaneGeometry(1.5, 0.6), screenMat)
    screen.position.set(0, 1.6, 1.01)
    g.add(screen)

  } else {
    // ETCH 等标准机台：带4个腔体的模型
    const baseMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, metalness: 0.5, roughness: 0.4 })
    const base = new THREE.Mesh(new THREE.BoxGeometry(3.5, 0.4, 3), baseMat)
    base.position.y = 0.2
    base.castShadow = base.receiveShadow = true
    g.add(base)

    const bodyMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, metalness: 0.6, roughness: 0.35 })
    const body = new THREE.Mesh(new THREE.BoxGeometry(3, 2, 2.5), bodyMat)
    body.position.y = 1.4
    body.castShadow = true
    g.add(body)

    // 4 个工艺腔顶部
    const chamMat = new THREE.MeshStandardMaterial({ color: 0x2a3a5a, metalness: 0.7, roughness: 0.3 })
    const positions = [[-0.9, 0.9], [0.9, 0.9], [-0.9, -0.9], [0.9, -0.9]]
    positions.forEach(p => {
      const c = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.8, 16), chamMat)
      c.position.set(p[0], 2.8, p[1])
      c.castShadow = true
      g.add(c)
    })

    // 中央传输柱
    const col = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.4, 2, 16), bodyMat)
    col.position.y = 1.4
    g.add(col)

    // Load Port
    const lpMat = new THREE.MeshStandardMaterial({ color: 0x1a2742, metalness: 0.4, roughness: 0.5 })
    for (let i = 0; i < 2; i++) {
      const lp = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.6, 0.3), lpMat)
      lp.position.set(-0.7 + i * 1.4, 0.6, 1.3)
      g.add(lp)
    }
  }

  // 状态 LED (所有机台通用)
  const ledMat = new THREE.MeshStandardMaterial({
    color: stateColors[m.state] || stateColors.idle,
    emissive: stateColors[m.state] || stateColors.idle,
    emissiveIntensity: 1.2,
  })
  const led = new THREE.Mesh(new THREE.SphereGeometry(0.2, 16, 16), ledMat)
  led.position.set(1.2, 3.2, 0)
  g.add(led)
  machineLEDs[m.id] = ledMat

  // ID 标签
  const label = makeTextSprite(m.id, {
    fontSize: 28, color: '#00d4ff', width: 256, height: 64, planeWidth: 2, planeHeight: 0.5,
  })
  label.position.set(0, 3.8, 1.5)
  g.add(label)

  g.userData.mid = m.id
  machineGroups[m.id] = g
  scene.add(g)
}

function onCanvasClick(e) {
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
  mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(mouse, camera)
  const groups = Object.values(machineGroups)
  const intersects = raycaster.intersectObjects(groups, true)
  if (intersects.length) {
    let obj = intersects[0].object
    while (obj && !obj.userData.mid) {
      obj = obj.parent
    }
    if (obj && obj.userData.mid) {
      const m = machines.value.find(x => x.id === obj.userData.mid)
      if (m) emit('select-machine', m)
    }
  }
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

  // 机台状态灯实时更新
  Object.entries(machineLEDs).forEach(([mid, mat]) => {
    const m = machines.value.find(x => x.id === mid)
    if (m) {
      const target = new THREE.Color(stateColors[m.state] || stateColors.idle)
      mat.color.lerp(target, 0.05)
      mat.emissive.lerp(target, 0.05)
      if (m.state === 'run') {
        mat.emissiveIntensity = 0.8 + Math.sin(Date.now() * 0.003) * 0.4
      } else if (m.state === 'error') {
        mat.emissiveIntensity = 0.5 + Math.abs(Math.sin(Date.now() * 0.008)) * 1.2
      } else {
        mat.emissiveIntensity = 1.0
      }
    }
  })

  // 天车沿轨迹移动动画
  const dt = 0.016  // 约60fps
  Object.values(vehicleObjs).forEach(v => {
    if (v.curve) {
      // 所有绑定轨迹的天车都循环移动
      v.progress += dt * v.speed * 0.05
      if (v.progress >= 1) v.progress = 0  // 循环
      const pos = v.curve.getPointAt(v.progress)
      v.group.position.copy(pos)
      
      // 朝向运动方向
      const lookAhead = Math.min(v.progress + 0.01, 1)
      const nextPos = v.curve.getPointAt(lookAhead)
      if (nextPos.distanceTo(pos) > 0.001) {
        v.group.lookAt(nextPos)
      }

      // 状态灯颜色：运行中绿色闪烁，空闲黄色
      if (v.ledMat) {
        const isMoving = v.state === 'moving'
        const targetColor = isMoving ? new THREE.Color(0x10b981) : new THREE.Color(0xf59e0b)
        v.ledMat.color.lerp(targetColor, 0.1)
        v.ledMat.emissive.lerp(targetColor, 0.1)
        v.ledMat.emissiveIntensity = isMoving 
          ? 1.0 + Math.sin(Date.now() * 0.005) * 0.5 
          : 0.6
      }
    }
  })

  renderer.render(scene, camera)
}

watch(() => props.floorId, () => {
  loadFloor()
})

watch(() => props.forceRefresh, () => {
  loadFloor()
})

onMounted(() => {
  setTimeout(() => {
    initScene()
    loadFloor()
  }, 50)
})

onUnmounted(() => {
  if (animId) cancelAnimationFrame(animId)
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  if (canvasRef.value) canvasRef.value.removeEventListener('click', onCanvasClick)
  if (renderer) renderer.dispose()
})
</script>

<template>
  <div class="floor-view-3d">
    <canvas ref="canvasRef" class="fv-canvas"></canvas>
    <div class="viewer-overlay">
      <div class="vo-left">
        <div class="floor-badge glass-panel">
          <div class="name">{{ floorData?.name || '楼层' }} 3D视图</div>
          <div class="meta">{{ floorData?.description }}</div>
        </div>
      </div>
      <div class="vo-right">
        <div class="view-legend glass-panel">
          <div class="title">机台类型</div>
          <div class="legend-row"><span class="legend-dot" style="background:#1e293b"></span> ETCH 刻蚀机</div>
          <div class="legend-row"><span class="legend-dot" style="background:#1a4a3a"></span> STK 传输机</div>
          <div class="legend-row"><span class="legend-dot" style="background:#0f172a"></span> WAT/WS 测试分选</div>
        </div>
      </div>
    </div>
    <div class="bottom-info-bar">
      <div class="bib-card glass-panel"><span class="k">机台:</span><span class="v">{{ machines.length }}</span></div>
      <div class="bib-card glass-panel"><span class="k">区域:</span><span class="v">{{ areas.length }}</span></div>
      <div class="bib-card glass-panel"><span class="k">轨迹:</span><span class="v">{{ tracks.length }}</span></div>
      <div class="bib-card glass-panel"><span class="k">天车:</span><span class="v">{{ vehicles.length }}</span></div>
      <div class="bib-card glass-panel"><span class="k">楼层:</span><span class="v">{{ floorData?.name }}</span></div>
    </div>
  </div>
</template>

<style scoped>
.floor-view-3d {
  position: relative;
  width: 100%;
  height: 100%;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}
.fv-canvas {
  width: 100%;
  height: 100%;
  display: block;
}
.viewer-overlay {
  position: absolute;
  top: 12px;
  left: 12px;
  right: 12px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  pointer-events: none;
}
.vo-left, .vo-right {
  pointer-events: auto;
}
.floor-badge {
  padding: 8px 14px;
}
.floor-badge .name {
  font-size: 14px;
  font-weight: 700;
  color: var(--accent);
}
.floor-badge .meta {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 2px;
}
.view-legend {
  padding: 8px 12px;
  font-size: 11px;
}
.view-legend .title {
  font-weight: 700;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.8px;
  font-size: 10px;
  margin-bottom: 6px;
}
.legend-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 3px;
}
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.bottom-info-bar {
  position: absolute;
  bottom: 12px;
  left: 12px;
  right: 12px;
  display: flex;
  gap: 8px;
  pointer-events: none;
}
.bib-card {
  padding: 6px 12px;
  font-size: 11px;
  pointer-events: auto;
}
.bib-card .k {
  color: var(--text-dim);
}
.bib-card .v {
  font-weight: 700;
  color: var(--text);
  margin-left: 4px;
}
</style>
