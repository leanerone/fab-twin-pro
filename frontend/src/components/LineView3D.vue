<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { useAppStore } from '../stores/app'
import { stateColors, makeTextSprite } from '../composables/useThree'

// 产线 3D 视图：所有机台俯瞰，包含 Cleanroom 厂房、SMIF OHT 天车
const appStore = useAppStore()
const emit = defineEmits(['select-machine'])

const canvasRef = ref(null)
let scene, camera, renderer, controls
let machineGroups = {}    // mid -> THREE.Group
let machineLEDs = {}      // mid -> LED material
let ohtTrains = []
let animId = null
let resizeHandler = null
let raycaster, mouse
// OHT 标签是否已构建
let smifBuilt = false

// 构建厂房地板 + 墙面 + 天花板灯
function buildFabFloor() {
  // 地板
  const floorGeo = new THREE.PlaneGeometry(80, 50)
  const floorMat = new THREE.MeshStandardMaterial({ color: 0x0a1120, metalness: 0.1, roughness: 0.9 })
  const floor = new THREE.Mesh(floorGeo, floorMat)
  floor.rotation.x = -Math.PI / 2
  floor.receiveShadow = true
  scene.add(floor)

  // 网格
  const grid = new THREE.GridHelper(80, 80, 0x15223a, 0x0d1525)
  grid.position.y = 0.01
  scene.add(grid)

  // 墙面（简单盒体，背面材质）
  const wallMat = new THREE.MeshStandardMaterial({ color: 0x0a0f1a, metalness: 0.1, roughness: 0.7, side: THREE.BackSide })
  const room = new THREE.BoxGeometry(80, 15, 50)
  const roomMesh = new THREE.Mesh(room, wallMat)
  roomMesh.position.y = 7.5
  scene.add(roomMesh)

  // 天花板灯条
  for (let i = 0; i < 8; i++) {
    for (let j = 0; j < 6; j++) {
      const lightGeo = new THREE.PlaneGeometry(3, 0.6)
      const lightMat = new THREE.MeshBasicMaterial({ color: 0xaaccff, transparent: true, opacity: 0.15 })
      const light = new THREE.Mesh(lightGeo, lightMat)
      light.rotation.x = Math.PI / 2
      light.position.set(-30 + i * 9, 12, -17.5 + j * 7)
      scene.add(light)
    }
  }

  // 两条产线区域标识
  const areaMat = new THREE.MeshStandardMaterial({ color: 0x0d1725, transparent: true, opacity: 0.8 })
  const area1 = new THREE.Mesh(new THREE.PlaneGeometry(34, 16), areaMat)
  area1.rotation.x = -Math.PI / 2
  area1.position.set(0, 0.02, -10)
  scene.add(area1)
  const area2 = new THREE.Mesh(new THREE.PlaneGeometry(34, 16), areaMat)
  area2.rotation.x = -Math.PI / 2
  area2.position.set(0, 0.02, 10)
  scene.add(area2)

  // 产线标签
  const sign1 = makeTextSprite('LINE 1 · 介质/金属/硅刻蚀 · 无 SMIF', {
    fontSize: 36, color: '#00d4ff', width: 512, height: 64, planeWidth: 20, planeHeight: 2.5,
  })
  sign1.rotation.x = -Math.PI / 2
  sign1.position.set(0, 0.1, -17.5)
  scene.add(sign1)

  const sign2 = makeTextSprite('LINE 2 · SMIF OHT 自动运输 · 刻蚀区', {
    fontSize: 36, color: '#a78bfa', width: 512, height: 64, planeWidth: 20, planeHeight: 2.5,
  })
  sign2.rotation.x = -Math.PI / 2
  sign2.position.set(0, 0.1, 17.5)
  scene.add(sign2)
}

// 构建单台机台的简化 3D 模型
function buildMiniMachine(mid, line, x) {
  const g = new THREE.Group()
  const baseZ = line === 1 ? -10 : 10
  g.position.set(x, 0, baseZ)

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

  // 状态 LED
  const ledMat = new THREE.MeshStandardMaterial({
    color: stateColors.run, emissive: stateColors.run, emissiveIntensity: 1.2,
  })
  const led = new THREE.Mesh(new THREE.SphereGeometry(0.2, 16, 16), ledMat)
  led.position.set(1.2, 3.2, 0)
  g.add(led)
  machineLEDs[mid] = ledMat

  // Load Port
  const lpMat = new THREE.MeshStandardMaterial({ color: 0x1a2742, metalness: 0.4, roughness: 0.5 })
  for (let i = 0; i < 2; i++) {
    const lp = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.6, 0.3), lpMat)
    lp.position.set(-0.7 + i * 1.4, 0.6, line === 1 ? -1.65 : 1.65)
    g.add(lp)
  }

  // ID 标签
  const label = makeTextSprite(mid, {
    fontSize: 28, color: '#00d4ff', width: 256, height: 64, planeWidth: 2, planeHeight: 0.5,
  })
  label.position.set(0, 3.8, line === 1 ? 1.5 : -1.5)
  label.rotation.y = line === 1 ? Math.PI : 0
  g.add(label)

  g.userData.mid = mid
  machineGroups[mid] = g
  scene.add(g)
}

// 构建 Line 2 的 SMIF OHT 轨道 + 天车
function buildSMIF() {
  if (smifBuilt) return
  smifBuilt = true

  const railMat = new THREE.MeshStandardMaterial({ color: 0x2a3a5a, metalness: 0.6, roughness: 0.4 })
  const rail = new THREE.Mesh(new THREE.BoxGeometry(40, 0.2, 0.4), railMat)
  rail.position.set(0, 5.5, 15)
  rail.castShadow = true
  scene.add(rail)

  // 垂直支撑柱
  for (let i = -2; i <= 2; i++) {
    const sup = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 5.5, 8), railMat)
    sup.position.set(i * 9, 2.75, 16.2)
    scene.add(sup)
  }

  // 2 台 OHT 天车
  for (let i = 0; i < 2; i++) {
    const train = new THREE.Group()
    const body = new THREE.Mesh(
      new THREE.BoxGeometry(1.8, 0.8, 0.6),
      new THREE.MeshStandardMaterial({ color: 0x7c3aed, metalness: 0.5, roughness: 0.4, emissive: 0x2d1b69, emissiveIntensity: 0.3 })
    )
    body.castShadow = true
    train.add(body)

    // 悬挂的 FOUP
    const foup = new THREE.Mesh(
      new THREE.BoxGeometry(0.7, 0.6, 0.5),
      new THREE.MeshStandardMaterial({ color: 0xff7b00, metalness: 0.3, roughness: 0.5 })
    )
    foup.position.y = -0.7
    foup.castShadow = true
    train.add(foup)

    // LED 指示灯
    const led = new THREE.Mesh(
      new THREE.SphereGeometry(0.08, 8, 8),
      new THREE.MeshBasicMaterial({ color: 0x10b981 })
    )
    led.position.set(0.7, 0.25, 0.25)
    train.add(led)

    train.position.set(-15 + i * 20, 5.5, 15)
    train.userData.speed = 0.02 + i * 0.008
    train.userData.dir = 1
    ohtTrains.push(train)
    scene.add(train)
  }
}

// 初始化场景
function initScene() {
  const canvas = canvasRef.value
  if (!canvas) return
  const w = canvas.clientWidth || 800
  const h = canvas.clientHeight || 600

  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x050814)
  scene.fog = new THREE.Fog(0x050814, 30, 70)

  camera = new THREE.PerspectiveCamera(40, w / h, 0.1, 200)
  camera.position.set(15, 18, 22)

  renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
  renderer.setSize(w, h)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap

  controls = new OrbitControls(camera, canvas)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.minDistance = 10
  controls.maxDistance = 50
  controls.maxPolarAngle = Math.PI / 2.2
  controls.target.set(0, 2, 0)

  // 灯光
  scene.add(new THREE.AmbientLight(0x3a4a6a, 0.5))
  const sun = new THREE.DirectionalLight(0xffffff, 0.6)
  sun.position.set(15, 25, 12)
  sun.castShadow = true
  sun.shadow.mapSize.set(2048, 2048)
  sun.shadow.camera.left = -25
  sun.shadow.camera.right = 25
  sun.shadow.camera.top = 25
  sun.shadow.camera.bottom = -25
  sun.shadow.camera.near = 1
  sun.shadow.camera.far = 60
  scene.add(sun)
  const fill = new THREE.DirectionalLight(0x5a7aaa, 0.3)
  fill.position.set(-10, 10, -10)
  scene.add(fill)
  const pt = new THREE.PointLight(0x00d4ff, 0.4, 40)
  pt.position.set(0, 8, 0)
  scene.add(pt)

  buildFabFloor()
  buildSMIF()

  // 构建已有机台
  appStore.machines.forEach(m => {
    const x = m.line === 1 ? -10 + (appStore.line1Machines.indexOf(m) * 10) : -10 + (appStore.line2Machines.indexOf(m) * 10)
    buildMiniMachine(m.id, m.line, x)
  })

  // 射线拾取（点击机台）
  raycaster = new THREE.Raycaster()
  mouse = new THREE.Vector2()
  canvas.addEventListener('click', onCanvasClick)

  resizeHandler = () => onResize()
  window.addEventListener('resize', resizeHandler)
  animate()
}

// 机台位置计算
function getMachineX(m) {
  const list = m.line === 1 ? appStore.line1Machines : appStore.line2Machines
  const idx = list.indexOf(m)
  return -10 + idx * 10
}

// 点击拾取
function onCanvasClick(e) {
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1
  mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1
  raycaster.setFromCamera(mouse, camera)
  // 检测机台分组
  const groups = Object.values(machineGroups)
  const intersects = raycaster.intersectObjects(groups, true)
  if (intersects.length) {
    // 向上找包含 mid 的 group
    let obj = intersects[0].object
    while (obj && !obj.userData.mid) {
      obj = obj.parent
    }
    if (obj && obj.userData.mid) {
      const m = appStore.machines.find(x => x.id === obj.userData.mid)
      if (m) emit('select-machine', m)
    }
  }
}

// 同步新增机台
function syncMachines() {
  if (!scene) return
  appStore.machines.forEach(m => {
    if (!machineGroups[m.id]) {
      buildMiniMachine(m.id, m.line, getMachineX(m))
    }
  })
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

  // OHT 天车往返动画
  ohtTrains.forEach(t => {
    t.position.x += t.userData.speed * t.userData.dir
    if (t.position.x > 18) t.userData.dir = -1
    if (t.position.x < -18) t.userData.dir = 1
    t.position.y = 5.5 + Math.sin(Date.now() * 0.002 + t.position.x) * 0.03
  })

  // 机台状态灯实时更新
  Object.entries(machineLEDs).forEach(([mid, mat]) => {
    const m = appStore.machines.find(x => x.id === mid)
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

  renderer.render(scene, camera)
}

// 监听机台列表变化
watch(() => appStore.machines.length, () => {
  syncMachines()
})

onMounted(() => {
  // 延迟一帧确保 canvas 已布局
  setTimeout(() => {
    initScene()
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
  <div class="line-view-3d">
    <canvas ref="canvasRef" class="line-canvas"></canvas>
    <div class="viewer-overlay">
      <div class="vo-left">
        <div class="line-badge glass-panel">
          <div class="name">产线总览</div>
          <div class="meta">TEL DRM UNITY 刻蚀机 · 双产线布局</div>
        </div>
      </div>
      <div class="vo-right">
        <div class="view-legend glass-panel">
          <div class="title">状态图例</div>
          <div class="legend-row"><span class="legend-dot" style="background:var(--green)"></span> 运行 Run</div>
          <div class="legend-row"><span class="legend-dot" style="background:var(--yellow)"></span> 空闲 Idle</div>
          <div class="legend-row"><span class="legend-dot" style="background:var(--red)"></span> 故障 Error</div>
          <div class="legend-row"><span class="legend-dot" style="background:var(--accent-2)"></span> 准备 Setup</div>
          <div class="legend-row"><span class="legend-dot" style="background:var(--blue)"></span> 维护 Maint</div>
        </div>
      </div>
    </div>
    <div class="bottom-info-bar">
      <div class="bib-card glass-panel"><span class="k">机台数:</span><span class="v">{{ appStore.totalMachines }}</span></div>
      <div class="bib-card glass-panel"><span class="k">运行:</span><span class="v" style="color:var(--green)">{{ appStore.stats.running }}</span></div>
      <div class="bib-card glass-panel"><span class="k">空闲:</span><span class="v" style="color:var(--yellow)">{{ appStore.stats.idle }}</span></div>
      <div class="bib-card glass-panel"><span class="k">告警:</span><span class="v" style="color:var(--red)">{{ appStore.stats.total_alarms }}</span></div>
      <div class="bib-card glass-panel"><span class="k">OHT:</span><span class="v" style="color:var(--accent)">运行中</span></div>
    </div>
  </div>
</template>

<style scoped>
.line-view-3d {
  position: relative;
  width: 100%;
  height: 100%;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}
.line-canvas {
  width: 100%;
  height: 100%;
  display: block;
}
.viewer-overlay {
  position: absolute;
  top: 14px;
  left: 14px;
  right: 14px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  pointer-events: none;
}
.vo-left, .vo-right {
  pointer-events: auto;
}
.line-badge {
  padding: 8px 14px;
}
.line-badge .name {
  font-size: 14px;
  font-weight: 700;
  color: var(--accent);
}
.line-badge .meta {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 2px;
}
.view-legend {
  padding: 10px 12px;
  font-size: 11px;
}
.view-legend .title {
  font-weight: 700;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.8px;
  font-size: 10px;
  margin-bottom: 8px;
}
.legend-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.bottom-info-bar {
  position: absolute;
  bottom: 14px;
  left: 14px;
  right: 14px;
  display: flex;
  gap: 10px;
  pointer-events: none;
}
.bib-card {
  padding: 8px 14px;
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
