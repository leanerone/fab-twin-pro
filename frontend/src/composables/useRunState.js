// Run货动画状态引擎（批次3自 MachineDetail.vue 抽出的纯逻辑，零组件依赖）
// 反应性粘合（rAF 循环 / cursor·mode watch）仍留在 MachineDetail，
// 本文件只含常量与纯函数：calcRunState(时间偏移) → 完整视觉状态。
// 内容为原 MachineDetail.vue L158-482 的逐字搬运（仅 reactive 改为工厂函数）。
import { reactive } from 'vue'

// === Run货动画状态（2D/3D共用） ===
export const TOTAL_WAFERS = 25

// SVG坐标系中各模块相对ARM中心的角度（0=右, 90=下, 180=左, 270=上）
export const TARGET_ANGLES = {
  port: 150,        // PORT1方向（左下）
  pa: 180,          // PA方向（左）
  chamberA: 250,    // Chamber A（左上）
  chamberB: 290,    // Chamber B（右上）
  chamberC: 0,      // Chamber C（右）
  idle: 90,         // 待机（向下）
}
export const CHAMBER_KEYS = ['chamberA', 'chamberB', 'chamberC']

// 每片晶圆的完整run货流程（10步，每步含子阶段）
export const RUN_STEPS = [
  { key: 'pick_port',     name: 'PORT取片',   duration: 2500 },
  { key: 'place_pa',      name: '放置PA',     duration: 2000 },
  { key: 'pa_align',      name: 'PA对准',     duration: 2500 },
  { key: 'pick_pa',       name: 'PA取片',     duration: 2000 },
  { key: 'place_chamber', name: '放入腔体',   duration: 2500 },
  { key: 'chamber_proc',  name: '腔体加工',   duration: 6000 },
  { key: 'pick_chamber',  name: '腔体取片',   duration: 2500 },
  { key: 'place_pa2',     name: 'PA放回',     duration: 2000 },
  { key: 'pick_pa2',      name: 'PA取回',     duration: 2000 },
  { key: 'place_port',    name: 'PORT放回',   duration: 2500 },
]
export const SINGLE_WAFER_MS = RUN_STEPS.reduce((s, st) => s + st.duration, 0)
export const TOTAL_RUN_MS = SINGLE_WAFER_MS * TOTAL_WAFERS

export function createRunState() {
  return reactive({
    currentWafer: 0,
    currentStep: 0,
    stepProgress: 0,
    armAngle: 90,          // 当前角度
    armExtension: 0,       // 0=收回, 1=完全伸出
    gripperClosed: false,  // 夹爪是否闭合
    armHolding: null,      // 夹持的晶圆ID
    waferLocation: null,   // 晶圆所在位置: 'port'|'pa'|'chamberA'|'chamberB'|'chamberC'|'arm'|null
    chambers: [
      { id: 'A', state: 'idle', wafer: null, progress: 0 },
      { id: 'B', state: 'idle', wafer: null, progress: 0 },
      { id: 'C', state: 'idle', wafer: null, progress: 0 },
    ],
    waferStatuses: Array.from({ length: TOTAL_WAFERS }, (_, i) => ({
      id: `W${String(i + 1).padStart(2, '0')}`,
      status: 'pending',
    })),
  })
}

export function lerp(a, b, t) { return a + (b - a) * Math.max(0, Math.min(1, t)) }
export function easeInOut(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2 }

// 根据时间偏移计算run货状态
export function calcRunState(timeOffsetMs) {
  if (timeOffsetMs < 0) timeOffsetMs = 0
  const totalMs = timeOffsetMs % TOTAL_RUN_MS
  const waferIdx = Math.floor(totalMs / SINGLE_WAFER_MS)
  const waferTime = totalMs - waferIdx * SINGLE_WAFER_MS
  const waferId = `W${String(waferIdx + 1).padStart(2, '0')}`

  let stepIdx = 0
  let stepProgress = 0
  let acc = 0
  for (let i = 0; i < RUN_STEPS.length; i++) {
    if (waferTime < acc + RUN_STEPS[i].duration) {
      stepIdx = i
      stepProgress = (waferTime - acc) / RUN_STEPS[i].duration
      break
    }
    acc += RUN_STEPS[i].duration
    stepIdx = i
    stepProgress = 1
  }

  const chamberIdx = waferIdx % 3
  const chamberKey = CHAMBER_KEYS[chamberIdx]
  const chamberAngle = TARGET_ANGLES[chamberKey]
  const stepKey = RUN_STEPS[stepIdx].key
  const p = stepProgress

  // 默认值
  let armAngle = TARGET_ANGLES.idle
  let armExtension = 0
  let gripperClosed = false
  let armHolding = null
  let waferLocation = null

  const chambers = [
    { id: 'A', state: 'idle', wafer: null, progress: 0 },
    { id: 'B', state: 'idle', wafer: null, progress: 0 },
    { id: 'C', state: 'idle', wafer: null, progress: 0 },
  ]

  // 每步分4个子阶段: 旋转(0-0.25) → 伸出(0.25-0.5) → 夹爪动作(0.5-0.6) → 收回(0.6-1.0)
  const rotEnd = 0.25
  const extEnd = 0.5
  const gripEnd = 0.6
  const rotT = easeInOut(p / rotEnd)
  const extT = easeInOut((p - rotEnd) / (extEnd - rotEnd))
  const retT = easeInOut((p - gripEnd) / (1 - gripEnd))

  switch (stepKey) {
    case 'pick_port': // 从PORT取片
      if (p < rotEnd) {
        armAngle = lerp(TARGET_ANGLES.idle, TARGET_ANGLES.port, rotT)
      } else if (p < extEnd) {
        armAngle = TARGET_ANGLES.port
        armExtension = extT
      } else if (p < gripEnd) {
        armAngle = TARGET_ANGLES.port
        armExtension = 1
        gripperClosed = p > (gripEnd + extEnd) / 2
        if (gripperClosed) { armHolding = waferId; waferLocation = 'arm' }
        else { waferLocation = 'port' }
      } else {
        armAngle = TARGET_ANGLES.port
        armExtension = 1 - retT
        gripperClosed = true
        armHolding = waferId
        waferLocation = 'arm'
      }
      break

    case 'place_pa': // 放到PA上
      if (p < rotEnd) {
        armAngle = lerp(TARGET_ANGLES.port, TARGET_ANGLES.pa, rotT)
        armHolding = waferId
        waferLocation = 'arm'
      } else if (p < extEnd) {
        armAngle = TARGET_ANGLES.pa
        armExtension = extT
        armHolding = waferId
        waferLocation = 'arm'
      } else if (p < gripEnd) {
        armAngle = TARGET_ANGLES.pa
        armExtension = 1
        gripperClosed = p < (gripEnd + extEnd) / 2
        if (gripperClosed) { armHolding = waferId; waferLocation = 'arm' }
        else { armHolding = null; waferLocation = 'pa' }
      } else {
        armAngle = TARGET_ANGLES.pa
        armExtension = 1 - retT
        waferLocation = 'pa'
      }
      break

    case 'pa_align': // PA对准中，臂收回待机
      armAngle = TARGET_ANGLES.idle
      armExtension = 0
      waferLocation = 'pa'
      break

    case 'pick_pa': // 从PA取片
      if (p < rotEnd) {
        armAngle = lerp(TARGET_ANGLES.idle, TARGET_ANGLES.pa, rotT)
        waferLocation = 'pa'
      } else if (p < extEnd) {
        armAngle = TARGET_ANGLES.pa
        armExtension = extT
        waferLocation = 'pa'
      } else if (p < gripEnd) {
        armAngle = TARGET_ANGLES.pa
        armExtension = 1
        gripperClosed = p > (gripEnd + extEnd) / 2
        if (gripperClosed) { armHolding = waferId; waferLocation = 'arm' }
        else { waferLocation = 'pa' }
      } else {
        armAngle = lerp(TARGET_ANGLES.pa, chamberAngle, retT)
        armExtension = 1 - retT
        gripperClosed = true
        armHolding = waferId
        waferLocation = 'arm'
      }
      break

    case 'place_chamber': // 放入腔体
      if (p < rotEnd) {
        armAngle = lerp(TARGET_ANGLES.pa, chamberAngle, rotT)
        armHolding = waferId
        chambers[chamberIdx].state = 'loading'
        waferLocation = 'arm'
      } else if (p < extEnd) {
        armAngle = chamberAngle
        armExtension = extT
        armHolding = waferId
        chambers[chamberIdx].state = 'loading'
        waferLocation = 'arm'
      } else if (p < gripEnd) {
        armAngle = chamberAngle
        armExtension = 1
        gripperClosed = p < (gripEnd + extEnd) / 2
        if (gripperClosed) { armHolding = waferId; waferLocation = 'arm' }
        else { armHolding = null; waferLocation = chamberKey }
      } else {
        armAngle = chamberAngle
        armExtension = 1 - retT
        chambers[chamberIdx].state = 'run'
        waferLocation = chamberKey
      }
      break

    case 'chamber_proc': // 腔体加工中
      armAngle = TARGET_ANGLES.idle
      armExtension = 0
      chambers[chamberIdx].state = 'run'
      chambers[chamberIdx].wafer = waferId
      chambers[chamberIdx].progress = p
      waferLocation = chamberKey
      break

    case 'pick_chamber': // 从腔体取片
      if (p < rotEnd) {
        armAngle = lerp(TARGET_ANGLES.idle, chamberAngle, rotT)
        chambers[chamberIdx].state = 'unloading'
        waferLocation = chamberKey
      } else if (p < extEnd) {
        armAngle = chamberAngle
        armExtension = extT
        chambers[chamberIdx].state = 'unloading'
        waferLocation = chamberKey
      } else if (p < gripEnd) {
        armAngle = chamberAngle
        armExtension = 1
        gripperClosed = p > (gripEnd + extEnd) / 2
        if (gripperClosed) { armHolding = waferId; chambers[chamberIdx].wafer = null; waferLocation = 'arm' }
        else { waferLocation = chamberKey }
      } else {
        armAngle = chamberAngle
        armExtension = 1 - retT
        gripperClosed = true
        armHolding = waferId
        waferLocation = 'arm'
      }
      break

    case 'place_pa2': // 放回PA
      if (p < rotEnd) {
        armAngle = lerp(chamberAngle, TARGET_ANGLES.pa, rotT)
        armHolding = waferId
        waferLocation = 'arm'
      } else if (p < extEnd) {
        armAngle = TARGET_ANGLES.pa
        armExtension = extT
        armHolding = waferId
        waferLocation = 'arm'
      } else if (p < gripEnd) {
        armAngle = TARGET_ANGLES.pa
        armExtension = 1
        gripperClosed = p < (gripEnd + extEnd) / 2
        if (gripperClosed) { armHolding = waferId; waferLocation = 'arm' }
        else { armHolding = null; waferLocation = 'pa' }
      } else {
        armAngle = TARGET_ANGLES.pa
        armExtension = 1 - retT
        waferLocation = 'pa'
      }
      break

    case 'pick_pa2': // 从PA取回
      if (p < rotEnd) {
        armAngle = TARGET_ANGLES.pa
        waferLocation = 'pa'
      } else if (p < extEnd) {
        armAngle = TARGET_ANGLES.pa
        armExtension = extT
        waferLocation = 'pa'
      } else if (p < gripEnd) {
        armAngle = TARGET_ANGLES.pa
        armExtension = 1
        gripperClosed = p > (gripEnd + extEnd) / 2
        if (gripperClosed) { armHolding = waferId; waferLocation = 'arm' }
        else { waferLocation = 'pa' }
      } else {
        armAngle = lerp(TARGET_ANGLES.pa, TARGET_ANGLES.port, retT)
        armExtension = 1 - retT
        gripperClosed = true
        armHolding = waferId
        waferLocation = 'arm'
      }
      break

    case 'place_port': // 放回PORT
      if (p < rotEnd) {
        armAngle = lerp(TARGET_ANGLES.pa, TARGET_ANGLES.port, rotT)
        armHolding = waferId
        waferLocation = 'arm'
      } else if (p < extEnd) {
        armAngle = TARGET_ANGLES.port
        armExtension = extT
        armHolding = waferId
        waferLocation = 'arm'
      } else if (p < gripEnd) {
        armAngle = TARGET_ANGLES.port
        armExtension = 1
        gripperClosed = p < (gripEnd + extEnd) / 2
        if (gripperClosed) { armHolding = waferId; waferLocation = 'arm' }
        else { armHolding = null; waferLocation = 'port' }
      } else {
        armAngle = lerp(TARGET_ANGLES.port, TARGET_ANGLES.idle, retT)
        armExtension = 1 - retT
        waferLocation = 'port'
      }
      break
  }

  const waferStatuses = Array.from({ length: TOTAL_WAFERS }, (_, i) => {
    if (i < waferIdx) return { id: `W${String(i + 1).padStart(2, '0')}`, status: 'done' }
    if (i === waferIdx) return { id: `W${String(i + 1).padStart(2, '0')}`, status: 'processing' }
    return { id: `W${String(i + 1).padStart(2, '0')}`, status: 'pending' }
  })

  return {
    currentWafer: waferIdx,
    currentStep: stepIdx,
    stepProgress,
    armAngle,
    armExtension,
    gripperClosed,
    armHolding,
    waferLocation,
    chambers,
    waferStatuses,
  }
}
