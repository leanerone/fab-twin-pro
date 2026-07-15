<script setup>
import { ref, onMounted, onUnmounted, watch, computed, nextTick } from 'vue'
import { useEventActionMapping } from '../composables/useEventActionMapping.js'

const props = defineProps({
  machine: { type: Object, default: () => null },
  modelConfig: { type: Object, default: null },
  currentState: { type: String, default: 'idle' },
  metrics: { type: Object, default: () => ({}) },
  runState: { type: Object, default: null },
  events: { type: Array, default: () => [] },
})

const containerRef = ref(null)
const svgRef = ref(null)
const width = ref(1000)
const height = ref(800)

// 使用事件动作映射系统
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

// 状态颜色
const stateColors = {
  Idle: '#9CA3AF',
  Running: '#22C55E',
  Hold: '#F59E0B',
  Alarm: '#EF4444',
  Maintenance: '#3B82F6',
}

const currentColor = computed(() => {
  const s = chamberState.value || props.currentState || 'Idle'
  return stateColors[s] || stateColors.Idle
})

// VFEI事件流程序列
const ATTACH_FLOW_SEQUENCE = [
  'ATTACH_POD_PLACE', 'POD_LOCK', 'READ_TAG', 'BATCH_START',
  'ATTACH_POD_UP', 'ATTACH_POD_REACH_STAGE', 'ATTACH_CST_PLACE',
  'UI_CONFIRM', 'ATTACH_POD_DOWN', 'ATTACH_POD_REACH_POS',
  'UI_DOUBLECHECK', 'WRITE_TAG', 'POD_UNLOCK', 'ATTACH_POD_REMOVE', 'IDLE'
]

const DETACH_FLOW_SEQUENCE = [
  'DETACH_POD_PLACE', 'POD_LOCK', 'READ_TAG', 'BATCH_START',
  'DETACH_POD_UP', 'DETACH_POD_REACH_STAGE', 'DETACH_CST_REMOVE',
  'DETACH_POD_DOWN', 'DETACH_POD_REACH_POS', 'WRITE_TAG',
  'POD_UNLOCK', 'DETACH_POD_REMOVE', 'IDLE'
]

// 创建SVG元素
function createSvgElement(tag, attrs = {}) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag)
  Object.entries(attrs).forEach(([key, value]) => {
    el.setAttribute(key, String(value))
  })
  return el
}

// 绘制2D基础结构（完全匹配 VPO2D.HTML 的 draw2DBase）
function draw2DBase() {
  if (!svgRef.value) return
  const svg = svgRef.value
  svg.innerHTML = ''
  svg.setAttribute('viewBox', '0 0 1000 1000')

  // 定义渐变和滤镜（匹配 VPO2D.HTML defs）
  const defs = createSvgElement('defs')

  // 深色渐变
  const darkGrad = createSvgElement('linearGradient', { id: 'darkGradient', x1: '0', x2: '0', y1: '0', y2: '1' })
  darkGrad.appendChild(createSvgElement('stop', { offset: '0%', 'stop-color': '#2b333d' }))
  darkGrad.appendChild(createSvgElement('stop', { offset: '100%', 'stop-color': '#111827' }))
  defs.appendChild(darkGrad)

  // softShadow 滤镜（VPO2D.HTML 中存在，之前缺失）
  const softShadow = createSvgElement('filter', { id: 'softShadow', x: '-20%', y: '-20%', width: '140%', height: '140%' })
  softShadow.appendChild(createSvgElement('feDropShadow', { dx: '0', dy: '16', stdDeviation: '12', 'flood-color': '#0f172a', 'flood-opacity': '0.16' }))
  defs.appendChild(softShadow)

  // 网格图案
  const gridPattern = createSvgElement('pattern', { id: 'gridPattern', width: '50', height: '50', patternUnits: 'userSpaceOnUse' })
  gridPattern.appendChild(createSvgElement('path', { d: 'M 50 0 L 0 0 0 50', fill: 'none', class: 'grid-line' }))
  defs.appendChild(gridPattern)

  svg.appendChild(defs)

  // 背景
  svg.appendChild(createSvgElement('rect', { width: '1000', height: '1000', fill: '#f8fafc' }))
  svg.appendChild(createSvgElement('rect', { width: '1000', height: '1000', fill: 'url(#gridPattern)', opacity: '0.55' }))

  // 阴影椭圆
  svg.appendChild(createSvgElement('ellipse', { cx: '506', cy: '906', rx: '386', ry: '52', fill: '#cbd5e1', opacity: '0.45' }))

  // 机台标签
  const titleText = createSvgElement('text', { x: '56', y: '72', class: 'machine-label' })
  titleText.textContent = 'VPO FRONT VIEW'
  svg.appendChild(titleText)

  const subtitleText = createSvgElement('text', { x: '56', y: '98', fill: '#64748b', 'font-size': '13' })
  subtitleText.textContent = 'Manual FRONT VIEW style'
  svg.appendChild(subtitleText)

  // 主机组（带 softShadow 滤镜）
  const mainGroup = createSvgElement('g', { filter: 'url(#softShadow)' })

  // 底座
  mainGroup.appendChild(createSvgElement('rect', { x: '285', y: '810', width: '430', height: '80', rx: '10', fill: '#5d636a', stroke: '#374151', 'stroke-width': '2' }))
  // 控制盒
  mainGroup.appendChild(createSvgElement('rect', { x: '388', y: '694', width: '224', height: '88', rx: '14', fill: '#1f2937', stroke: '#111827', 'stroke-width': '2' }))
  // 左右立柱
  mainGroup.appendChild(createSvgElement('rect', { x: '320', y: '240', width: '45', height: '570', rx: '8', fill: '#7a8289', stroke: '#334155', 'stroke-width': '2' }))
  mainGroup.appendChild(createSvgElement('rect', { x: '635', y: '240', width: '45', height: '570', rx: '8', fill: '#7a8289', stroke: '#334155', 'stroke-width': '2' }))
  // 中间腔体区域
  mainGroup.appendChild(createSvgElement('rect', { x: '365', y: '278', width: '270', height: '470', rx: '10', fill: '#e5ebf1', stroke: '#475569', 'stroke-width': '2' }))
  // 顶部提升器
  mainGroup.appendChild(createSvgElement('rect', { x: '310', y: '228', width: '380', height: '32', rx: '7', fill: 'url(#darkGradient)', stroke: '#111827', 'stroke-width': '2' }))
  // 顶部提手
  mainGroup.appendChild(createSvgElement('rect', { x: '466', y: '66', width: '68', height: '14', rx: '4', fill: '#1f2937', stroke: '#111827', 'stroke-width': '1' }))
  // 内部导轨
  mainGroup.appendChild(createSvgElement('rect', { x: '470', y: '300', width: '6', height: '440', fill: '#a8b1ba', stroke: '#64748b', 'stroke-width': '1' }))
  mainGroup.appendChild(createSvgElement('rect', { x: '524', y: '300', width: '6', height: '440', fill: '#a8b1ba', stroke: '#64748b', 'stroke-width': '1' }))
  // 16条通风槽
  for (let i = 0; i < 16; i++) {
    mainGroup.appendChild(createSvgElement('line', { x1: '421', y1: String(304 + 24 * i), x2: '579', y2: String(304 + 24 * i), stroke: '#7c8793', 'stroke-width': '1' }))
  }
  // 底部控制区域
  mainGroup.appendChild(createSvgElement('rect', { x: '374', y: '742', width: '252', height: '42', rx: '10', fill: 'rgba(15,23,42,0.92)', stroke: '#0f172a', 'stroke-width': '1' }))

  svg.appendChild(mainGroup)

  // COMM端口
  const commGroup = createSvgElement('g')
  commGroup.appendChild(createSvgElement('rect', { x: '384', y: '790', width: '164', height: '36', rx: '6', fill: 'none', stroke: '#475569', 'stroke-width': '2' }))
  for (let i = 0; i < 2; i++) {
    for (let j = 0; j < 12; j++) {
      commGroup.appendChild(createSvgElement('circle', { cx: String(399 + 12 * j), cy: String(801 + 12 * i), r: '3', class: 'port-pin' }))
    }
  }
  svg.appendChild(commGroup)

  const commLabel = createSvgElement('text', { x: '382', y: '846', fill: '#64748b', 'font-size': '12' })
  commLabel.textContent = 'COMM / SERVICE PORTS'
  svg.appendChild(commLabel)

  // 操作员控制盒（带 softShadow 滤镜）
  const controlGroup = createSvgElement('g', { filter: 'url(#softShadow)' })
  controlGroup.appendChild(createSvgElement('rect', { x: '130', y: '790', width: '165', height: '70', rx: '10', fill: '#111827', stroke: '#0b1020', 'stroke-width': '1.2' }))
  controlGroup.appendChild(createSvgElement('circle', { cx: '214', cy: '824', r: '18', fill: '#f59e0b', stroke: '#7c2d12', 'stroke-width': '1.5' }))
  controlGroup.appendChild(createSvgElement('line', { x1: '295', y1: '824', x2: '390', y2: '788', stroke: '#94a3b8', 'stroke-width': '2' }))
  svg.appendChild(controlGroup)

  // FRONT VIEW 文本（之前缺失）
  const frontViewText = createSvgElement('text', { x: '748', y: '96', fill: '#0f172a', 'font-size': '16', 'font-weight': '700' })
  frontViewText.textContent = 'FRONT VIEW'
  svg.appendChild(frontViewText)

  const opLabel = createSvgElement('text', { x: '92', y: '880', fill: '#0f172a', 'font-size': '12' })
  opLabel.textContent = 'OPERATOR CONTROL BOX'
  svg.appendChild(opLabel)

  // Wafer Port 和 Pod 层（在安装基准点之前，匹配 VPO2D.HTML 顺序）
  svg.appendChild(createSvgElement('g', { id: 'waferPort2dLayer' }))
  svg.appendChild(createSvgElement('g', { id: 'pod2dLayer' }))

  // 安装基准点
  const mountPoints = [[320, 240], [680, 240], [320, 890], [680, 890], [347, 812], [652, 812]]
  mountPoints.forEach(([x, y]) => {
    svg.appendChild(createSvgElement('circle', { cx: String(x), cy: String(y), r: '8', fill: '#f8fafc', stroke: '#334155', 'stroke-width': '2' }))
    svg.appendChild(createSvgElement('circle', { cx: String(x), cy: String(y), r: '3', fill: '#334155' }))
  })

  // 轮廓线
  svg.appendChild(createSvgElement('rect', { x: '250', y: '68', width: '500', height: '824', class: 'machine-outline' }))
}

// 绘制Pod和Wafer（匹配 VPO2D.HTML 的 drawPod2D）
function drawPod2D() {
  const podLayer = document.getElementById('pod2dLayer')
  const waferPortLayer = document.getElementById('waferPort2dLayer')
  if (!podLayer || !waferPortLayer) return

  podLayer.innerHTML = ''
  waferPortLayer.innerHTML = ''

  const progress = podProgress.value
  const isAlarmState = alarmInfo.value !== null

  // Pod y 位置：progress=0 时在顶部(220)，progress=1 时在腔体内(620)
  const s = 620 - 400 * (1 - progress)

  if (progress > 0.02) {
    // Pod 外壳
    podLayer.appendChild(createSvgElement('rect', {
      x: '312', y: String(s), width: '376', height: '34',
      fill: isAlarmState ? '#fecaca' : '#111827',
      stroke: isAlarmState ? '#dc2626' : '#0b1020',
      'stroke-width': isAlarmState ? '2.6' : '1.3'
    }))

    // Pod 主体
    podLayer.appendChild(createSvgElement('rect', {
      x: '438', y: String(s - 8), width: '124', height: '62', rx: '12',
      fill: isAlarmState ? '#fee2e2' : '#d7dde3',
      stroke: isAlarmState ? '#dc2626' : '#6b7280',
      'stroke-width': isAlarmState ? '2.2' : '1.2'
    }))

    // 窗口
    podLayer.appendChild(createSvgElement('rect', {
      x: '452', y: String(s + 6), width: '96', height: '34', rx: '8',
      fill: isAlarmState ? '#fff1f2' : '#f3f4f6',
      stroke: '#9ca3af', 'stroke-width': '1'
    }))

    // Pod 支架（匹配 VPO2D.HTML）
    podLayer.appendChild(createSvgElement('rect', {
      x: '468', y: String(s + 34), width: '10', height: '80',
      fill: '#adb5bd', stroke: '#64748b', 'stroke-width': '1'
    }))
    podLayer.appendChild(createSvgElement('rect', {
      x: '522', y: String(s + 34), width: '10', height: '80',
      fill: '#adb5bd', stroke: '#64748b', 'stroke-width': '1'
    }))

    // 控制区域
    podLayer.appendChild(createSvgElement('rect', {
      x: '374', y: String(s + 10), width: '252', height: '46', rx: '10',
      fill: 'rgba(100,116,139,0.18)', stroke: 'rgba(71,85,105,0.55)', 'stroke-width': '0.9'
    }))

    // LIFT CARRIER 标签
    const label = createSvgElement('text', { x: '562', y: String(s + 54), fill: '#0f172a', 'font-size': '13', 'font-weight': '700' })
    label.textContent = 'LIFT CARRIER'
    podLayer.appendChild(label)

    // 锁定指示器（固定位置，匹配 VPO2D.HTML：348,650 / 348,718 / 664,650 / 664,718）
    const lockColor = podLocked.value ? '#16a34a' : '#dc2626'
    const lockPositions = [
      { x: 348, y: 650, dx: -12 },
      { x: 348, y: 718, dx: -12 },
      { x: 664, y: 650, dx: 12 },
      { x: 664, y: 718, dx: 12 }
    ]

    lockPositions.forEach(pos => {
      podLayer.appendChild(createSvgElement('rect', {
        x: String(pos.x), y: String(pos.y), width: '14', height: '28', rx: '4',
        fill: lockColor, stroke: '#1f2937', 'stroke-width': '1'
      }))
      // 解锁时绘制斜线指示
      if (!podLocked.value) {
        podLayer.appendChild(createSvgElement('line', {
          x1: String(pos.x + 7), y1: String(pos.y + 14),
          x2: String(pos.x + 7 + pos.dx), y2: String(pos.y + 8),
          stroke: lockColor, 'stroke-width': '4', 'stroke-linecap': 'round'
        }))
      }
    })
  }

  // Wafer Port（如果wafer可见）
  if (waferLocation.value === 'port' || progress > 0.5) {
    drawWaferMap(waferPortLayer, 'PORT1', 10, 70)
    drawWaferMap(waferPortLayer, 'PORT2', 835, 70)
  }
}

// 绘制Wafer Map面板
function drawWaferMap(parent, portId, ox, oy) {
  const panelW = 155
  const panelH = 300
  
  const panel = createSvgElement('g')
  
  // 背景
  panel.appendChild(createSvgElement('rect', {
    x: String(ox), y: String(oy), width: String(panelW), height: String(panelH),
    fill: 'rgba(13, 20, 36, 0.92)', stroke: '#2a4060', 'stroke-width': '1'
  }))
  
  // 标题
  const title = createSvgElement('text', { x: String(ox + 8), y: String(oy + 14), fill: '#e5e7eb', 'font-size': '11', 'font-weight': 'bold' })
  title.textContent = `${portId} WAFER MAP`
  panel.appendChild(title)
  
  // 槽位
  for (let s = 25; s >= 1; s--) {
    const sy = oy + 24 + 11.5 * (25 - s)
    const label = s < 10 ? '0' + s : String(s)
    
    panel.appendChild(createSvgElement('text', {
      x: String(ox + 22), y: String(sy + 4), fill: '#475569', 'font-size': '10', 'text-anchor': 'right'
    })).textContent = label
    
    panel.appendChild(createSvgElement('ellipse', {
      cx: String(ox + 88), cy: String(sy + 1), rx: '46', ry: '4.2',
      fill: '#334155', stroke: '#1e2d44', 'stroke-width': '0.8'
    }))
  }
  
  parent.appendChild(panel)
}

// 更新视图
function updateView() {
  drawPod2D()
}

// 处理事件
watch(() => props.events, (evts) => {
  if (!evts || evts.length === 0) return
  
  // 处理所有事件
  processEvents(evts)
  
  updateView()
}, { deep: true })

// 监听状态变化
watch(() => props.currentState, (state) => {
  chamberState.value = (state || 'idle').toLowerCase()
  updateView()
})

onMounted(async () => {
  await nextTick()
  if (containerRef.value) {
    const rect = containerRef.value.getBoundingClientRect()
    width.value = Math.max(100, rect.width)
    height.value = Math.max(100, rect.height)
  }
  draw2DBase()
  updateView()
})

onUnmounted(() => {
  // 清理
})
</script>

<template>
  <div ref="containerRef" class="vpo-viewer">
    <svg ref="svgRef" class="vpo-svg" :viewBox="`0 0 1000 1000`" role="img" aria-label="VPO 2D 视图"></svg>
    
    <!-- 状态指示器 -->
    <div class="vpo-status-bar">
      <div class="status-item">
        <span class="status-label">状态:</span>
        <span class="status-value" :style="{ color: currentColor }">{{ chamberState || currentState }}</span>
      </div>
      <div class="status-item">
        <span class="status-label">Pod进度:</span>
        <span class="status-value">{{ Math.round(podProgress * 100) }}%</span>
      </div>
      <div class="status-item">
        <span class="status-label">锁定:</span>
        <span class="status-value" :class="{ locked: podLocked, unlocked: !podLocked }">
          {{ podLocked ? '已锁定' : '未锁定' }}
        </span>
      </div>
      <div v-if="scanActive" class="status-item scan-active">
        <span class="status-label">扫描:</span>
        <span class="status-value scanning">进行中</span>
      </div>
      <div v-if="signalActive" class="status-item signal-active">
        <span class="status-label">信号:</span>
        <span class="status-value signaling">发送中</span>
      </div>
    </div>
    
    <!-- 图例 -->
    <div class="vpo-legend">
      <div class="legend-item"><span class="dot" style="background:#22c55e"></span><span>Running</span></div>
      <div class="legend-item"><span class="dot" style="background:#f59e0b"></span><span>Hold</span></div>
      <div class="legend-item"><span class="dot" style="background:#ef4444"></span><span>Alarm</span></div>
      <div class="legend-item"><span class="dot" style="background:#64748b"></span><span>Idle</span></div>
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
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid #1e2d44;
  font-size: 11px;
  z-index: 5;
}

.status-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.status-label {
  color: #94a3b8;
}

.status-value {
  color: #e5e7eb;
  font-weight: 600;
}

.status-value.locked {
  color: #22c55e;
}

.status-value.unlocked {
  color: #f59e0b;
}

.vpo-legend {
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

/* SVG样式 */
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