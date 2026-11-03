// Three.js 场景管理通用逻辑：统一的初始化、灯光、动画循环、resize 处理
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'

// 创建标准场景（深色背景 + 雾效）
export function createScene(bgColor = 0x050814, fogNear = 30, fogFar = 70) {
  const scene = new THREE.Scene()
  scene.background = new THREE.Color(bgColor)
  scene.fog = new THREE.Fog(bgColor, fogNear, fogFar)
  return scene
}

// 创建透视相机
export function createCamera(canvas, fov = 40, position = [15, 18, 22]) {
  const w = canvas.clientWidth || 1
  const h = canvas.clientHeight || 1
  const camera = new THREE.PerspectiveCamera(fov, w / h, 0.1, 200)
  camera.position.set(...position)
  return camera
}

// 创建 WebGL 渲染器（开启阴影）
export function createRenderer(canvas) {
  const w = canvas.clientWidth || 1
  const h = canvas.clientHeight || 1
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true })
  renderer.setSize(w, h)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  return renderer
}

// 创建轨道控制器
export function createControls(camera, canvas, options = {}) {
  const controls = new OrbitControls(camera, canvas)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.minDistance = options.minDistance || 10
  controls.maxDistance = options.maxDistance || 50
  controls.maxPolarAngle = options.maxPolarAngle || Math.PI / 2.2
  if (options.target) controls.target.set(...options.target)
  return controls
}

// 添加标准灯光（环境光 + 主方向光 + 补光 + 点光源）
export function addStandardLights(scene, options = {}) {
  scene.add(new THREE.AmbientLight(options.ambient || 0x3a4a6a, options.ambientIntensity || 0.5))

  const sun = new THREE.DirectionalLight(0xffffff, options.sunIntensity || 0.6)
  sun.position.set(...(options.sunPos || [15, 25, 12]))
  sun.castShadow = true
  sun.shadow.mapSize.set(2048, 2048)
  if (options.shadowBounds) {
    sun.shadow.camera.left = -options.shadowBounds
    sun.shadow.camera.right = options.shadowBounds
    sun.shadow.camera.top = options.shadowBounds
    sun.shadow.camera.bottom = -options.shadowBounds
  }
  sun.shadow.camera.near = 1
  sun.shadow.camera.far = 60
  scene.add(sun)

  const fill = new THREE.DirectionalLight(0x5a7aaa, 0.3)
  fill.position.set(-10, 10, -10)
  scene.add(fill)

  const pt = new THREE.PointLight(0x00d4ff, options.pointIntensity || 0.4, options.pointDistance || 40)
  pt.position.set(...(options.pointPos || [0, 8, 0]))
  scene.add(pt)

  return { sun, fill, pt }
}

// 添加地面网格（厂房地板）
export function addFloor(scene, size = 80, divisions = 80, floorColor = 0x0a1120, gridColor = 0x15223a, gridColor2 = 0x0d1525) {
  const floorGeo = new THREE.PlaneGeometry(size, size)
  const floorMat = new THREE.MeshStandardMaterial({ color: floorColor, metalness: 0.1, roughness: 0.9 })
  const floor = new THREE.Mesh(floorGeo, floorMat)
  floor.rotation.x = -Math.PI / 2
  floor.receiveShadow = true
  scene.add(floor)

  const grid = new THREE.GridHelper(size, divisions, gridColor, gridColor2)
  grid.position.y = 0.01
  scene.add(grid)

  return floor
}

// 状态颜色常量（与参考实现一致）
export const stateColors = {
  run: 0x10b981,
  idle: 0xf59e0b,
  error: 0xef4444,
  maint: 0x3b82f6,
  setup: 0x7c3aed,
}

export const stateLabels = {
  run: '运行中',
  idle: '空闲',
  error: '故障',
  maint: '维护',
  setup: '准备中',
}

// 创建 Canvas 文字标签纹理
export function makeTextTexture(text, options = {}) {
  const {
    fontSize = 28,
    fontFamily = 'monospace',
    color = '#00d4ff',
    bgAlpha = 0,
    width = 256,
    height = 64,
    align = 'center',
  } = options

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')

  if (bgAlpha > 0) {
    ctx.fillStyle = `rgba(0,0,0,${bgAlpha})`
    ctx.fillRect(0, 0, width, height)
  }

  ctx.font = `bold ${fontSize}px ${fontFamily}`
  ctx.fillStyle = color
  ctx.textAlign = align
  ctx.textBaseline = 'middle'
  ctx.fillText(text, width / 2, height / 2)

  const texture = new THREE.CanvasTexture(canvas)
  texture.needsUpdate = true
  return texture
}

// 创建文字标签 Mesh
export function makeTextSprite(text, options = {}) {
  const {
    fontSize = 28,
    color = '#00d4ff',
    width = 256,
    height = 64,
    planeWidth = 2,
    planeHeight = 0.5,
  } = options

  const texture = makeTextTexture(text, { fontSize, color, width, height })
  const material = new THREE.MeshBasicMaterial({ map: texture, transparent: true })
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(planeWidth, planeHeight), material)
  return mesh
}

// resize 处理工具函数
export function handleResize(camera, renderer, canvas) {
  if (!renderer || !canvas) return
  const w = canvas.clientWidth || 1
  const h = canvas.clientHeight || 1
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  renderer.setSize(w, h)
}
