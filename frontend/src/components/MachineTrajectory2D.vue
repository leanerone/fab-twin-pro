<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { api } from '../api'

/**
 * 机台2D运行轨迹组件
 * 显示机台在工厂楼层平面图上的位置和Lot批次的移动轨迹
 */
const props = defineProps({
  machineId: { type: String, default: 'ETCH-201' },
  floorId: { type: Number, default: 3 },
  lots: { type: Array, default: () => [] },
  selectedLotId: { type: String, default: '' },
  currentState: { type: String, default: 'idle' },
  metrics: { type: Object, default: () => ({ waferCount: 0 }) },
})

const emit = defineEmits(['select-lot'])

// 楼层平面图数据
const floorData = ref(null)
const machines = ref([])
const areas = ref([])
const tracks = ref([])
const vehicles = ref([])

// Lot轨迹数据（实时移动轨迹）
const lotTrajectories = ref([])  // [{ lot_id, path: [{x,y,time}], currentPos, color }]

// 视图状态
const isLoading = ref(true)
const zoomLevel = ref(1)
const showTrajectories = ref(true)
const showAllLots = ref(true)

// 画布引用
const canvasRef = ref(null)
let animationId = null

// 状态颜色映射
const stateColors = {
  run: '#10b981',
  idle: '#f59e0b',
  error: '#ef4444',
  maint: '#3b82f6',
  setup: '#7c3aed',
}

// Lot轨迹颜色（按工艺类型）
const lotColors = {
  ETCH: '#00d4ff',
  WAT: '#10b981',
  WS: '#f59e0b',
  CMP: '#8b5cf6',
  PVD: '#ef4444',
  LITHO: '#ec4899',
  IMP: '#06b6d4',
  default: '#64748b',
}

// 加载楼层数据
async function loadFloorData() {
  isLoading.value = true
  try {
    floorData.value = await api.getFloor(props.floorId)
    machines.value = floorData.value.machines || []
    areas.value = floorData.value.areas || []
    tracks.value = floorData.value.tracks || []
    vehicles.value = floorData.value.vehicles || []
  } catch (e) {
    console.error('加载楼层数据失败:', e)
  }
  isLoading.value = false
}

// 构建Lot轨迹数据（基于事件流）
async function buildLotTrajectories() {
  // 从lots数据构建轨迹路径
  lotTrajectories.value = []

  if (!props.lots || props.lots.length === 0) return

  props.lots.forEach(lot => {
    // 模拟Lot轨迹：从进入机台到完成加工的路径
    // 实际轨迹应该从后端API获取

    const trajectory = {
      lot_id: lot.id,
      recipe: lot.recipe,
      start_time: lot.start_time,
      end_time: lot.end_time,
      color: getLotColor(lot.recipe),
      path: [],
      currentPos: null,
      state: lot.state,
    }

    // 构建路径点（模拟数据）
    // 实际应该从事件数据中提取
    const machine = machines.value.find(m => m.id === props.machineId)
    if (machine) {
      // 起始点：机台位置
      const startPos = { x: machine.floor_x, y: machine.floor_y }

      // 添加模拟轨迹点（实际应该从真实数据构建）
      // 这里创建一个简单的进出路径
      trajectory.path = [
        { x: startPos.x - 5, y: startPos.y, time: lot.start_time, stage: '到达' },
        { x: startPos.x - 2, y: startPos.y, time: lot.start_time + 60000, stage: '进入Load Port' },
        { x: startPos.x, y: startPos.y, time: lot.start_time + 120000, stage: '装载' },
        { x: startPos.x, y: startPos.y, time: lot.start_time + 180000, stage: '加工中', isProcessing: true },
        { x: startPos.x + 2, y: startPos.y, time: lot.end_time - 60000, stage: '卸载' },
        { x: startPos.x + 5, y: startPos.y, time: lot.end_time, stage: '离开' },
      ]

      // 当前位置：根据时间计算
      trajectory.currentPos = getCurrentPosition(trajectory, Date.now())
    }

    lotTrajectories.value.push(trajectory)
  })
}

// 获取Lot颜色
function getLotColor(recipe) {
  if (!recipe) return lotColors.default
  const type = Object.keys(lotColors).find(key => recipe.includes(key))
  return type ? lotColors[type] : lotColors.default
}

// 根据时间计算当前位置（用于动画）
function getCurrentPosition(trajectory, currentTime) {
  if (!trajectory.path || trajectory.path.length === 0) return null

  const path = trajectory.path

  // 如果Lot已完成，位置为最后一个点
  if (trajectory.state === 'completed' || currentTime > trajectory.end_time) {
    return path[path.length - 1]
  }

  // 如果Lot刚开始，位置为第一个点
  if (currentTime < trajectory.start_time) {
    return path[0]
  }

  // 计算当前位置（基于时间插值）
  for (let i = 0; i < path.length - 1; i++) {
    const p1 = path[i]
    const p2 = path[i + 1]

    if (currentTime >= p1.time && currentTime <= p2.time) {
      const ratio = (currentTime - p1.time) / (p2.time - p1.time)
      return {
        x: p1.x + (p2.x - p1.x) * ratio,
        y: p1.y + (p2.y - p1.y) * ratio,
        stage: p1.stage,
      }
    }
  }

  return path[path.length - 1]
}

// Canvas绘制函数
function drawCanvas() {
  const canvas = canvasRef.value
  if (!canvas) return

  const ctx = canvas.getContext('2d')
  const w = canvas.width
  const h = canvas.height

  // 清空画布
  ctx.fillStyle = '#0a1120'
  ctx.fillRect(0, 0, w, h)

  // 绘制网格
  drawGrid(ctx, w, h)

  // 绘制区域
  drawAreas(ctx, w, h)

  // 绘制轨迹轨道
  if (showTrajectories.value) {
    drawTracks(ctx, w, h)
  }

  // 绘制机台
  drawMachines(ctx, w, h)

  // 绘制天车
  drawVehicles(ctx, w, h)

  // 绘制Lot轨迹
  if (showTrajectories.value && showAllLots.value) {
    drawLotTrajectories(ctx, w, h)
  }

  // 绘制当前机台高亮
  highlightCurrentMachine(ctx, w, h)

  // 绘制选中Lot的轨迹高亮
  if (props.selectedLotId) {
    highlightSelectedLot(ctx, w, h)
  }

  // 绘制信息面板
  drawInfoPanel(ctx, w, h)
}

// 绘制网格
function drawGrid(ctx, w, h) {
  ctx.strokeStyle = '#15223a'
  ctx.lineWidth = 1

  const gridSize = 20 * zoomLevel.value

  for (let x = 0; x <= w; x += gridSize) {
    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x, h)
    ctx.stroke()
  }

  for (let y = 0; y <= h; y += gridSize) {
    ctx.beginPath()
    ctx.moveTo(0, y)
    ctx.lineTo(w, y)
    ctx.stroke()
  }
}

// 绘制区域
function drawAreas(ctx, w, h) {
  areas.value.forEach(area => {
    const x = (area.x_pos / 100) * w
    const y = (area.y_pos / 100) * h
    const aw = (area.width / 100) * w
    const ah = (area.height / 100) * h

    const color = area.color || '#1e3a5f'

    ctx.fillStyle = color + '40'
    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.beginPath()
    ctx.rect(x, y, aw, ah)
    ctx.fill()
    ctx.stroke()

    // 区域名称
    ctx.fillStyle = '#ffffff'
    ctx.font = `${11 * zoomLevel.value}px sans-serif`
    ctx.textAlign = 'center'
    ctx.fillText(area.name, x + aw / 2, y + ah / 2)
  })
}

// 绘制轨迹轨道
function drawTracks(ctx, w, h) {
  tracks.value.forEach(track => {
    if (!track.points || track.points.length < 2) return

    const pts = track.points.map(p => ({
      x: (p[0] / 100) * w,
      y: (p[1] / 100) * h,
    }))

    const color = track.color || '#00d4ff'

    ctx.strokeStyle = color
    ctx.lineWidth = 3
    ctx.setLineDash([8, 4])
    ctx.beginPath()
    pts.forEach((p, i) => {
      if (i === 0) ctx.moveTo(p.x, p.y)
      else ctx.lineTo(p.x, p.y)
    })
    ctx.stroke()
    ctx.setLineDash([])

    // 轨迹端点
    pts.forEach(p => {
      ctx.fillStyle = color
      ctx.beginPath()
      ctx.arc(p.x, p.y, 5 * zoomLevel.value, 0, Math.PI * 2)
      ctx.fill()
    })

    // 轨迹名称
    ctx.fillStyle = color
    ctx.font = `bold ${12 * zoomLevel.value}px sans-serif`
    ctx.textAlign = 'left'
    ctx.fillText(track.name, pts[0].x + 10, pts[0].y - 10)
  })
}

// 绘制机台
function drawMachines(ctx, w, h) {
  machines.value.forEach(m => {
    const x = (m.floor_x / 100) * w
    const y = (m.floor_y / 100) * h
    const size = 15 * zoomLevel.value

    const color = stateColors[m.state] || stateColors.idle

    // 机台标记
    ctx.fillStyle = color
    ctx.strokeStyle = '#ffffff'
    ctx.lineWidth = 2
    ctx.beginPath()

    if (m.process_type === 'STK') {
      // STK用矩形
      ctx.rect(x - size, y - size / 3, size * 2, size * 0.7)
    } else {
      // 其他用圆形
      ctx.arc(x, y, size, 0, Math.PI * 2)
    }

    ctx.fill()
    ctx.stroke()

    // 机台发光效果（运行状态）
    if (m.state === 'run') {
      ctx.shadowColor = color
      ctx.shadowBlur = 15
      ctx.beginPath()
      ctx.arc(x, y, size + 3, 0, Math.PI * 2)
      ctx.fillStyle = color + '30'
      ctx.fill()
      ctx.shadowBlur = 0
    }

    // 机台ID
    ctx.fillStyle = '#ffffff'
    ctx.font = `bold ${9 * zoomLevel.value}px sans-serif`
    ctx.textAlign = 'center'
    ctx.fillText(m.id, x, y + size + 12)

    // 告警数量
    if (m.alarm_count > 0) {
      ctx.fillStyle = '#ef4444'
      ctx.beginPath()
      ctx.arc(x + size, y - size, 8, 0, Math.PI * 2)
      ctx.fill()
      ctx.fillStyle = '#ffffff'
      ctx.font = `${7 * zoomLevel.value}px sans-serif`
      ctx.fillText(m.alarm_count, x + size, y - size + 3)
    }
  })
}

// 绘制天车
function drawVehicles(ctx, w, h) {
  vehicles.value.forEach(v => {
    const track = tracks.value.find(t => t.id == v.track_id)
    if (!track || !track.points) return

    // 计算天车位置
    const progress = v.progress || 0
    const pos = getVehiclePosition(track.points, progress)

    const x = (pos.x / 100) * w
    const y = (pos.y / 100) * h

    // 天车图标
    ctx.font = `${18 * zoomLevel.value}px sans-serif`
    ctx.textAlign = 'center'
    ctx.fillText('🚁', x, y)

    // 天车ID
    ctx.fillStyle = '#00d4ff'
    ctx.font = `bold ${8 * zoomLevel.value}px sans-serif`
    ctx.fillText(v.id, x, y + 15)

    // Lot ID（如果有）
    if (v.lot_id) {
      ctx.fillStyle = '#10b981'
      ctx.font = `${7 * zoomLevel.value}px sans-serif`
      ctx.fillText(v.lot_id, x, y + 25)
    }
  })
}

// 计算天车在轨迹上的位置
function getVehiclePosition(points, progress) {
  if (!points || points.length === 0) return { x: 0, y: 0 }

  const totalSegs = points.length - 1
  const segProgress = progress * totalSegs
  const segIdx = Math.floor(segProgress)
  const segFrac = segProgress - segIdx

  const p1 = points[segIdx]
  const p2 = points[Math.min(segIdx + 1, points.length - 1)]

  return {
    x: p1[0] + (p2[0] - p1[0]) * segFrac,
    y: p1[1] + (p2[1] - p1[1]) * segFrac,
  }
}

// 绘制Lot轨迹
function drawLotTrajectories(ctx, w, h) {
  lotTrajectories.value.forEach(trajectory => {
    if (!trajectory.path || trajectory.path.length < 2) return

    const pts = trajectory.path.map(p => ({
      x: (p.x / 100) * w,
      y: (p.y / 100) * h,
      stage: p.stage,
      isProcessing: p.isProcessing,
    }))

    const color = trajectory.color

    // 轨迹路径
    ctx.strokeStyle = color
    ctx.lineWidth = 4
    ctx.setLineDash([])
    ctx.beginPath()
    pts.forEach((p, i) => {
      if (i === 0) ctx.moveTo(p.x, p.y)
      else ctx.lineTo(p.x, p.y)
    })
    ctx.stroke()

    // 轨迹点标记
    pts.forEach((p, i) => {
      // 关键节点
      ctx.fillStyle = p.isProcessing ? '#10b981' : color
      ctx.beginPath()
      ctx.arc(p.x, p.y, 6 * zoomLevel.value, 0, Math.PI * 2)
      ctx.fill()

      // 阶段标签
      if (i === 0 || i === pts.length - 1 || p.isProcessing) {
        ctx.fillStyle = '#ffffff'
        ctx.font = `${9 * zoomLevel.value}px sans-serif`
        ctx.textAlign = 'center'
        ctx.fillText(p.stage, p.x, p.y - 15)
      }
    })

    // 当前位置动画（运行中的Lot）
    if (trajectory.currentPos && trajectory.state === 'processing') {
      const cx = (trajectory.currentPos.x / 100) * w
      const cy = (trajectory.currentPos.y / 100) * h

      // 闪烁效果
      const pulseSize = 10 + Math.sin(Date.now() / 200) * 3
      ctx.fillStyle = color
      ctx.shadowColor = color
      ctx.shadowBlur = 20
      ctx.beginPath()
      ctx.arc(cx, cy, pulseSize * zoomLevel.value, 0, Math.PI * 2)
      ctx.fill()
      ctx.shadowBlur = 0

      // Lot ID
      ctx.fillStyle = '#ffffff'
      ctx.font = `bold ${10 * zoomLevel.value}px sans-serif`
      ctx.fillText(trajectory.lot_id, cx, cy - 20)
    }
  })
}

// 高亮当前机台
function highlightCurrentMachine(ctx, w, h) {
  const machine = machines.value.find(m => m.id === props.machineId)
  if (!machine) return

  const x = (machine.floor_x / 100) * w
  const y = (machine.floor_y / 100) * h

  // 高亮环
  ctx.strokeStyle = '#00d4ff'
  ctx.lineWidth = 3
  ctx.setLineDash([5, 5])
  ctx.beginPath()
  ctx.arc(x, y, 25 * zoomLevel.value, 0, Math.PI * 2)
  ctx.stroke()
  ctx.setLineDash([])

  // 机台名称标注
  ctx.fillStyle = '#00d4ff'
  ctx.font = `bold ${13 * zoomLevel.value}px sans-serif`
  ctx.textAlign = 'center'
  ctx.fillText(`📍 ${machine.id}`, x, y - 35)
}

// 高亮选中Lot轨迹
function highlightSelectedLot(ctx, w, h) {
  const trajectory = lotTrajectories.value.find(t => t.lot_id === props.selectedLotId)
  if (!trajectory || !trajectory.path) return

  const pts = trajectory.path.map(p => ({
    x: (p.x / 100) * w,
    y: (p.y / 100) * h,
  }))

  // 高亮轨迹线
  ctx.strokeStyle = '#00ffcc'
  ctx.lineWidth = 6
  ctx.shadowColor = '#00ffcc'
  ctx.shadowBlur = 15
  ctx.beginPath()
  pts.forEach((p, i) => {
    if (i === 0) ctx.moveTo(p.x, p.y)
    else ctx.lineTo(p.x, p.y)
  })
  ctx.stroke()
  ctx.shadowBlur = 0

  // 高亮节点
  pts.forEach(p => {
    ctx.fillStyle = '#00ffcc'
    ctx.beginPath()
    ctx.arc(p.x, p.y, 8 * zoomLevel.value, 0, Math.PI * 2)
    ctx.fill()
  })
}

// 绘制信息面板
function drawInfoPanel(ctx, w, h) {
  // 左上角信息面板
  const panelX = 10
  const panelY = 10
  const panelW = 200
  const panelH = 100

  ctx.fillStyle = '#0f172a'
  ctx.strokeStyle = '#334155'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.rect(panelX, panelY, panelW, panelH)
  ctx.fill()
  ctx.stroke()

  ctx.fillStyle = '#00d4ff'
  ctx.font = 'bold 14px sans-serif'
  ctx.textAlign = 'left'
  ctx.fillText(`机台: ${props.machineId}`, panelX + 10, panelY + 25)

  ctx.fillStyle = '#64748b'
  ctx.font = '12px sans-serif'
  ctx.fillText(`状态: ${props.currentState}`, panelX + 10, panelY + 45)
  ctx.fillText(`晶圆计数: ${props.metrics.waferCount}`, panelX + 10, panelY + 65)
  ctx.fillText(`楼层: ${floorData.value?.name || '未知'}`, panelX + 10, panelY + 85)

  // 右上角控制提示
  const tipX = w - 150
  const tipY = 10

  ctx.fillStyle = '#0f172a'
  ctx.beginPath()
  ctx.rect(tipX, tipY, 140, 50)
  ctx.fill()
  ctx.strokeStyle = '#334155'
  ctx.stroke()

  ctx.fillStyle = '#94a3b8'
  ctx.font = '11px sans-serif'
  ctx.textAlign = 'left'
  ctx.fillText('🔍 滚轮缩放', tipX + 10, tipY + 20)
  ctx.fillText('🖱 点击Lot查看轨迹', tipX + 10, tipY + 40)
}

// Canvas点击事件：选择Lot轨迹
function handleCanvasClick(e) {
  const canvas = canvasRef.value
  if (!canvas) return

  const rect = canvas.getBoundingClientRect()
  const x = ((e.clientX - rect.left) / rect.width) * 100
  const y = ((e.clientY - rect.top) / rect.height) * 100

  // 检查是否点击了Lot轨迹点
  lotTrajectories.value.forEach(trajectory => {
    if (!trajectory.currentPos) return

    const dx = trajectory.currentPos.x - x
    const dy = trajectory.currentPos.y - y
    const distance = Math.sqrt(dx * dx + dy * dy)

    if (distance < 3) {
      emit('select-lot', { id: trajectory.lot_id })
    }
  })
}

// 动画循环
function animate() {
  animationId = requestAnimationFrame(animate)

  // 更新Lot位置（模拟实时移动）
  lotTrajectories.value.forEach(trajectory => {
    if (trajectory.state === 'processing') {
      trajectory.currentPos = getCurrentPosition(trajectory, Date.now())
    }
  })

  drawCanvas()
}

// 窗口大小调整
function resizeCanvas() {
  const canvas = canvasRef.value
  if (!canvas) return

  const parent = canvas.parentElement
  if (!parent) return

  canvas.width = parent.clientWidth
  canvas.height = parent.clientHeight

  drawCanvas()
}

// 监听lots变化
watch(() => props.lots, () => {
  buildLotTrajectories()
}, { deep: true })

// 监听机台变化
watch(() => props.machineId, () => {
  buildLotTrajectories()
})

// 监听楼层变化
watch(() => props.floorId, () => {
  loadFloorData()
})

onMounted(async () => {
  await loadFloorData()
  buildLotTrajectories()

  resizeCanvas()
  window.addEventListener('resize', resizeCanvas)

  if (canvasRef.value) {
    canvasRef.value.addEventListener('click', handleCanvasClick)
  }

  animate()
})

onUnmounted(() => {
  if (animationId) cancelAnimationFrame(animationId)
  window.removeEventListener('resize', resizeCanvas)
  if (canvasRef.value) {
    canvasRef.value.removeEventListener('click', handleCanvasClick)
  }
})
</script>

<template>
  <div class="trajectory-2d">
    <div class="t2d-header">
      <div class="t2d-title">
        🗺️ 机台运行轨迹 - {{ machineId }}
      </div>
      <div class="t2d-controls">
        <button 
          class="t2d-btn" 
          :class="{ active: showTrajectories }"
          @click="showTrajectories = !showTrajectories"
        >
          {{ showTrajectories ? '👁 显示轨迹' : '👁‍🗨 隐藏轨迹' }}
        </button>
        <button 
          class="t2d-btn" 
          :class="{ active: showAllLots }"
          @click="showAllLots = !showAllLots"
        >
          {{ showAllLots ? '📦 全部Lot' : '📦 仅选中' }}
        </button>
        <button class="t2d-btn" @click="zoomLevel = Math.min(zoomLevel + 0.2, 2)">
          🔍+
        </button>
        <button class="t2d-btn" @click="zoomLevel = Math.max(zoomLevel - 0.2, 0.5)">
          🔍-
        </button>
      </div>
    </div>

    <div class="t2d-canvas-wrapper">
      <canvas ref="canvasRef" class="t2d-canvas" />
      
      <div v-if="isLoading" class="t2d-loading">
        加载中...
      </div>
    </div>

    <div class="t2d-footer">
      <div class="t2d-stats">
        <span>机台: {{ machines.length }}</span>
        <span>区域: {{ areas.length }}</span>
        <span>轨迹: {{ tracks.length }}</span>
        <span>天车: {{ vehicles.length }}</span>
        <span>Lot批次: {{ lotTrajectories.length }}</span>
      </div>
      <div class="t2d-legend">
        <span class="legend-item">
          <span class="legend-dot" style="background:#10b981"></span> 运行
        </span>
        <span class="legend-item">
          <span class="legend-dot" style="background:#f59e0b"></span> 空闲
        </span>
        <span class="legend-item">
          <span class="legend-dot" style="background:#ef4444"></span> 故障
        </span>
        <span class="legend-item">
          <span class="legend-line" style="background:#00d4ff"></span> Lot轨迹
        </span>
      </div>
    </div>

    <!-- Lot轨迹列表 -->
    <div v-if="lotTrajectories.length > 0" class="t2d-lot-list">
      <div class="tll-title">📦 Lot轨迹列表</div>
      <div class="tll-items">
        <div 
          v-for="traj in lotTrajectories" 
          :key="traj.lot_id"
          class="tll-item"
          :class="{ selected: selectedLotId === traj.lot_id }"
          :style="{ borderColor: traj.color }"
          @click="emit('select-lot', { id: traj.lot_id })"
        >
          <div class="tll-header">
            <span class="tll-id" :style="{ color: traj.color }">{{ traj.lot_id }}</span>
            <span class="tll-state">{{ traj.state }}</span>
          </div>
          <div class="tll-info">
            <span>Recipe: {{ traj.recipe }}</span>
            <span>节点: {{ traj.path.length }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.trajectory-2d {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #0a1120;
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}

.t2d-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
}

.t2d-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--accent);
}

.t2d-controls {
  display: flex;
  gap: 8px;
}

.t2d-btn {
  padding: 6px 12px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-dim);
  border-radius: 6px;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s;
}

.t2d-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.t2d-btn.active {
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent);
  border-color: var(--accent);
}

.t2d-canvas-wrapper {
  flex: 1;
  position: relative;
  min-height: 0;
  overflow: hidden;
}

.t2d-canvas {
  width: 100%;
  height: 100%;
  display: block;
}

.t2d-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(10, 17, 32, 0.8);
  color: var(--text-dim);
  font-size: 14px;
}

.t2d-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  background: var(--panel);
  border-top: 1px solid var(--border);
}

.t2d-stats {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--text-dim);
}

.t2d-legend {
  display: flex;
  gap: 12px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text);
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.legend-line {
  width: 20px;
  height: 3px;
  border-radius: 1px;
}

.t2d-lot-list {
  position: absolute;
  top: 60px;
  right: 10px;
  width: 200px;
  background: rgba(15, 23, 42, 0.95);
  border: 1px solid rgba(0, 212, 255, 0.2);
  border-radius: 8px;
  padding: 10px;
  z-index: 10;
}

.tll-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 8px;
}

.tll-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.tll-item {
  padding: 8px;
  border: 1px solid;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
  background: rgba(0, 0, 0, 0.2);
}

.tll-item:hover {
  filter: brightness(1.2);
}

.tll-item.selected {
  background: rgba(0, 255, 204, 0.1);
  border-width: 2px;
}

.tll-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.tll-id {
  font-size: 11px;
  font-weight: 700;
}

.tll-state {
  font-size: 10px;
  color: var(--text-dim);
  background: rgba(0, 0, 0, 0.3);
  padding: 1px 4px;
  border-radius: 2px;
}

.tll-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 10px;
  color: var(--text-dim);
}
</style>