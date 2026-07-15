<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '../stores/app'
import { useModelStore } from '../stores/model'
import { api } from '../api'
import { stateLabels } from '../composables/useThree'
import MachineModel3D from '../components/MachineModel3D.vue'
import MachineModel2D from '../components/MachineModel2D.vue'
import MachineIsoView from '../components/MachineIsoView.vue'
import MachineVpoView from '../components/MachineVpoView.vue'
import PlaybackBar from '../components/PlaybackBar.vue'
import AlarmStats from '../components/AlarmStats.vue'
import EventList from '../components/EventList.vue'
import LotList from '../components/LotList.vue'
import AiAssistant from '../components/AiAssistant.vue'
import HistoryReplay from '../components/HistoryReplay.vue'

// 机台详情：3D 模型 + 2D原理图 + 回放 + 右侧 Tab（告警/事件/Lot/AI）
const props = defineProps({
  id: { type: String, default: '' },
})

const router = useRouter()
const appStore = useAppStore()
const modelStore = useModelStore()

// === 状态 ===
const machine = ref(null)
const mode = ref('realtime')              // realtime / playback
const playing = ref(false)
const speed = ref(2)
const playbackDate = ref(new Date().toISOString().slice(0, 10))
const cursor = ref(0)                     // 回放游标时间戳
const playbackStart = ref(0)
const playbackEnd = ref(0)
const rightTab = ref('alarms')
const currentState = ref('idle')
const processStep = ref('待机')
const metrics = reactive({ temp: 22, pressure: 1, gas: 0, rf: 0, waferCount: 0 })
const events = ref([])
const alarms = ref([])
const lots = ref([])
const alarmStats = ref({ total: 0, crit: 0, warn: 0, temperature: 0, pressure: 0, rf_drift: 0, gas_leak: 0, resolved: 0, unresolved: 0 })
const selectedLotId = ref('')
const transferTrigger = ref(0)

// === 视图模式（根据机台型号自动选择） ===
const viewMode = ref('3d')                // 3d / 2d / iso / hybrid
const currentModelConfig = ref(null)

function resolveViewMode(machineModel) {
  const vm = modelStore.getViewMode(machineModel)
  if (vm === 'isometric' || vm === 'iso') return 'iso'
  if (vm === 'vpo' || vm === 'svg-vpo') return 'vpo'
  if (vm === 'hybrid') return '2d'
  if (vm === 'svg') return '2d'
  return '3d'
}

const availableViews = computed(() => {
  const cfg = currentModelConfig.value
  if (!cfg) return [{ key: '3d', label: '🎯 3D模型' }, { key: '2d', label: '📐 2D原理图' }]
  const views = []
  if (cfg.views_config?.view_3d || cfg.view_mode === 'threejs' || cfg.view_mode === 'hybrid') {
    views.push({ key: '3d', label: '🎯 3D模型' })
  }
  if (cfg.view_mode === 'isometric' || cfg.view_mode === 'iso' || cfg.views_config?.view_2d?.type === 'isometric') {
    views.push({ key: 'iso', label: '📐 2.5D等角' })
  }
  if (cfg.view_mode === 'vpo' || cfg.view_mode === 'svg-vpo' || cfg.views_config?.view_2d?.type === 'vpo') {
    views.push({ key: 'vpo', label: '📋 VPO 2D' })
  }
  if (cfg.views_config?.view_2d?.type === 'svg' || cfg.view_mode === 'svg' || cfg.view_mode === 'hybrid') {
    views.push({ key: '2d', label: '📋 2D视图' })
  }
  if (views.length === 0) views.push({ key: '3d', label: '🎯 3D模型' })
  return views
})

// ===== Run货动画状态（2D/3D共用） =====
const TOTAL_WAFERS = 25

// SVG坐标系中各模块相对ARM中心的角度（0=右, 90=下, 180=左, 270=上）
const TARGET_ANGLES = {
  port: 150,        // PORT1方向（左下）
  pa: 180,          // PA方向（左）
  chamberA: 250,    // Chamber A（左上）
  chamberB: 290,    // Chamber B（右上）
  chamberC: 0,      // Chamber C（右）
  idle: 90,         // 待机（向下）
}
const CHAMBER_KEYS = ['chamberA', 'chamberB', 'chamberC']

// 每片晶圆的完整run货流程（10步，每步含子阶段）
const RUN_STEPS = [
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
const SINGLE_WAFER_MS = RUN_STEPS.reduce((s, st) => s + st.duration, 0)
const TOTAL_RUN_MS = SINGLE_WAFER_MS * TOTAL_WAFERS

const runState = reactive({
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

function lerp(a, b, t) { return a + (b - a) * Math.max(0, Math.min(1, t)) }
function easeInOut(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2 }

// 根据时间偏移计算run货状态
function calcRunState(timeOffsetMs) {
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

// 实时模式动画时间
let realtimeRunTime = 0
let runAnimFrame = null

function updateRunAnimation() {
  if (mode.value === 'realtime' && playing.value) {
    realtimeRunTime += 16 * speed.value
    const state = calcRunState(realtimeRunTime)
    Object.assign(runState, state)
  }
  runAnimFrame = requestAnimationFrame(updateRunAnimation)
}

// 监听回放游标，更新run货状态
watch(cursor, (val) => {
  if (mode.value === 'playback' && playbackEnd.value > playbackStart.value) {
    const offset = val - playbackStart.value
    const state = calcRunState(offset)
    Object.assign(runState, state)
  }
})

// 监听模式切换
watch(mode, (newMode) => {
  if (newMode === 'playback') {
    // 回放模式：根据cursor计算
    const offset = cursor.value - playbackStart.value
    const state = calcRunState(offset)
    Object.assign(runState, state)
  }
})

// 历史回放数据
let historyData = []
let playbackIdx = 0
let playbackTimer = null
let realtimeTimer = null

// 当前机台
const machineId = computed(() => props.id || appStore.selectedMachineId || 'ETCH-201')

// 温度告警等级
const tempClass = computed(() => {
  if (metrics.temp > 80) return 'crit'
  if (metrics.temp > 70) return 'warn'
  return ''
})

// 进度百分比
const playProgress = computed(() => {
  if (!playbackEnd.value || playbackEnd.value <= playbackStart.value) return 0
  return Math.max(0, Math.min(100, ((cursor.value - playbackStart.value) / (playbackEnd.value - playbackStart.value)) * 100))
})

// 显示的事件（最新 60 条，倒序）
const displayEvents = computed(() => events.value.slice(-60).reverse())

// === 加载数据 ===
async function loadMachine() {
  machine.value = await api.getMachine(machineId.value)
  if (machine.value) {
    currentState.value = machine.value.state
    processStep.value = `步骤 ${machine.value.process_step}/6`
    metrics.temp = machine.value.temp
    metrics.pressure = machine.value.pressure
    metrics.gas = machine.value.gas_flow
    metrics.rf = machine.value.rf_power
    metrics.waferCount = machine.value.wafer_count
    appStore.selectMachine(machineId.value)

    const modelId = modelStore.resolveModelId(machine.value.model)
    if (modelId && modelStore.models.length === 0) {
      await modelStore.loadModels()
    }
    const cfg = modelStore.getModelById(modelId)
    currentModelConfig.value = cfg
    viewMode.value = resolveViewMode(machine.value.model)
  }
  // 并行加载右侧面板数据
  loadAlarms()
  loadLots()
  loadLatestEvents()
}

// 加载告警
async function loadAlarms() {
  const [list, stats] = await Promise.all([
    api.getAlarms(machineId.value, playbackDate.value),
    api.getAlarmStats(machineId.value, playbackDate.value),
  ])
  alarms.value = list || []
  alarmStats.value = stats || alarmStats.value
}

// 加载 Lot
async function loadLots() {
  lots.value = (await api.getLots(machineId.value, playbackDate.value)) || []
}

// 加载最新事件
async function loadLatestEvents() {
  const data = await api.getLatestEvents(machineId.value, 60)
  if (data) {
    events.value = data.reverse()
    // 应用最新事件到模型
    if (data.length) {
      const latest = data[data.length - 1]
      applyEventData(latest)
    }
  }
}

// === 实时模式：从 store 接收事件 ===
watch(() => appStore.recentEvents, (evs) => {
  if (mode.value !== 'realtime') return
  if (!evs.length) return
  // 找到当前机台的事件
  const myEvents = evs.filter(e => e.machine_id === machineId.value)
  myEvents.forEach(ev => {
    events.value.push(ev)
    if (events.value.length > 200) events.value.shift()
    applyEventData(ev)
  })
}, { deep: true })

// 应用事件数据到模型
function applyEventData(ev) {
  if (!ev) return
  if (ev.event_type === 'STATE') {
    currentState.value = ev.event_code || currentState.value
    processStep.value = ev.description || processStep.value
  } else if (ev.event_type === 'SENSOR') {
    if (ev.metric === 'temperature') metrics.temp = ev.value
    if (ev.metric === 'pressure') metrics.pressure = ev.value
    if (ev.metric === 'gasflow') metrics.gas = ev.value
    if (ev.metric === 'rf') metrics.rf = ev.value
  } else if (ev.event_type === 'ALARM') {
    // 加入告警列表
    if (!alarms.value.find(a => a.id === ev.id)) {
      alarms.value.unshift({
        id: ev.id,
        description: ev.description,
        level: ev.level || 'warn',
        timestamp: ev.timestamp,
        alarm_code: ev.event_code,
      })
      if (alarms.value.length > 30) alarms.value.pop()
    }
  } else if (ev.event_type === 'TRANSFER') {
    // 触发 3D 门/机械臂动画
    transferTrigger.value++
    if (/unload|卸载/i.test(ev.event_code + ev.description)) {
      metrics.waferCount++
    }
  }
}

// === 回放模式 ===
async function switchToPlayback() {
  mode.value = 'playback'
  stopPlayback()
  events.value = []
  alarms.value = []
  // 加载历史事件
  historyData = (await api.getEvents(machineId.value, playbackDate.value)) || []
  if (!historyData.length) {
    console.warn('无历史数据')
    return
  }
  // 解析时间戳
  historyData.forEach(e => {
    e._ts = new Date(e.timestamp).getTime()
  })
  playbackStart.value = historyData[0]._ts
  playbackEnd.value = historyData[historyData.length - 1]._ts
  cursor.value = playbackStart.value
  playbackIdx = 0
  playing.value = false
  // 重新加载告警与 Lot
  loadAlarms()
  loadLots()
}

function switchToRealtime() {
  mode.value = 'realtime'
  stopPlayback()
  events.value = []
  alarms.value = []
  loadLatestEvents()
  loadAlarms()
}

// 模式切换
function onModeChange(newMode) {
  if (newMode === mode.value) return
  if (newMode === 'playback') {
    switchToPlayback()
  } else {
    switchToRealtime()
  }
}

// 播放/暂停
function onPlayingChange(val) {
  playing.value = val
  if (val) {
    startPlaybackLoop()
  } else {
    stopPlayback()
  }
}

// 回放循环
function startPlaybackLoop() {
  stopPlayback()
  if (mode.value !== 'playback') return
  playbackTimer = setTimeout(() => {
    if (!playing.value) return
    const targetTime = cursor.value + 800 * speed.value
    while (playbackIdx < historyData.length && historyData[playbackIdx]._ts <= targetTime) {
      applyEventData(historyData[playbackIdx])
      events.value.push(historyData[playbackIdx])
      if (events.value.length > 200) events.value.shift()
      playbackIdx++
    }
    cursor.value = Math.min(targetTime, playbackEnd.value)
    if (cursor.value >= playbackEnd.value) {
      playing.value = false
      return
    }
    startPlaybackLoop()
  }, 100)
}

function stopPlayback() {
  if (playbackTimer) {
    clearTimeout(playbackTimer)
    playbackTimer = null
  }
}

// 时间轴跳转
function seek(pct) {
  if (!historyData.length) return
  const targetTime = playbackStart.value + pct * (playbackEnd.value - playbackStart.value)
  cursor.value = targetTime
  playbackIdx = historyData.findIndex(e => e._ts >= targetTime)
  if (playbackIdx < 0) playbackIdx = historyData.length
  // 重放到此点
  events.value = []
  alarms.value = []
  let i = 0
  while (i < historyData.length && historyData[i]._ts <= targetTime) {
    applyEventData(historyData[i])
    events.value.push(historyData[i])
    if (events.value.length > 200) events.value.shift()
    i++
  }
  playbackIdx = i
}

// 日期变化
function onDateChange(newDate) {
  playbackDate.value = newDate
  if (mode.value === 'playback') {
    switchToPlayback()
  }
}

// 倍速变化
function onSpeedChange(s) {
  speed.value = s
}

// 选择 Lot
function selectLot(lot) {
  selectedLotId.value = lot.id
  // 切换到回放模式并跳转到 Lot 开始时间
  if (mode.value !== 'playback') {
    switchToPlayback().then(() => {
      jumpToTime(lot.start_time)
    })
  } else {
    jumpToTime(lot.start_time)
  }
}

// 跳转到指定时间
function jumpToTime(ts) {
  if (mode.value !== 'playback') {
    switchToPlayback().then(() => doJump(ts))
  } else {
    doJump(ts)
  }
}

function doJump(ts) {
  if (!historyData.length) return
  const target = new Date(ts).getTime()
  if (isNaN(target)) return
  const clamped = Math.max(playbackStart.value, Math.min(playbackEnd.value, target))
  const pct = (clamped - playbackStart.value) / (playbackEnd.value - playbackStart.value)
  seek(pct)
}

// 回放历史事件（从历史回放面板触发）
function onReplayEvent(ev) {
  if (!ev || !ev.timestamp) return
  // 切换到回放模式
  if (mode.value !== 'playback') {
    switchToPlayback().then(() => {
      doJump(ev.timestamp)
    })
  } else {
    doJump(ev.timestamp)
  }
}

// 返回看板
function goBack() {
  router.push('/')
}

// 监听机台 ID 变化
watch(() => props.id, () => {
  if (mode.value === 'playback') switchToRealtime()
  loadMachine()
})

onMounted(() => {
  loadMachine()
  updateRunAnimation()
})
</script>

<template>
  <div class="detail-page">
    <!-- 左侧视图区 -->
    <div class="detail-viewer" :class="{ 'is-2d': viewMode === '2d' || viewMode === 'vpo', 'is-vpo': viewMode === 'vpo' }">
      <!-- 视图模式切换按钮（根据机台型号动态显示） -->
      <div class="view-mode-switcher">
        <button
          v-for="v in availableViews"
          :key="v.key"
          class="vms-btn"
          :class="{ active: viewMode === v.key }"
          @click="viewMode = v.key"
        >
          {{ v.label }}
        </button>
      </div>

      <!-- 3D模型视图 -->
      <MachineModel3D
        v-if="viewMode === '3d'"
        :machine="machine"
        :current-state="currentState"
        :metrics="metrics"
        :process-step="processStep"
        :transfer-trigger="transferTrigger"
        :run-state="runState"
      />

      <!-- 2D原理图视图 -->
      <MachineModel2D
        v-else-if="viewMode === '2d'"
        :machine="machine"
        :current-state="currentState"
        :metrics="metrics"
        :process-step="processStep"
        :run-state="runState"
      />

      <!-- 2.5D等角视图（OXE/DRM专用） -->
      <MachineIsoView
        v-else-if="viewMode === 'iso'"
        :machine="machine"
        :model-config="currentModelConfig"
        :current-state="currentState"
        :metrics="metrics"
        :run-state="runState"
      />

      <!-- VPO 2D视图 -->
      <MachineVpoView
        v-else-if="viewMode === 'vpo'"
        :machine="machine"
        :model-config="currentModelConfig"
        :current-state="currentState"
        :metrics="metrics"
        :run-state="runState"
        :events="displayEvents"
      />

      <button class="back-btn" @click="goBack">← 返回看板</button>

      <!-- 悬浮信息面板（2D模式下隐藏，避免遮挡） -->
      <div v-show="viewMode === '3d'" class="detail-left-panel glass-panel">
        <div class="detail-mid">{{ machineId }}</div>
        <div class="detail-model">{{ machine?.model || 'TEL DRM UNITY' }} · 刻蚀机</div>
        <div class="state-badge" :class="currentState">{{ stateLabels[currentState] || currentState }}</div>
        <div class="detail-metrics">
          <div class="dm">
            <div class="dm-label">温度</div>
            <div class="dm-val" :class="tempClass">{{ metrics.temp.toFixed(1) }}°C</div>
          </div>
          <div class="dm">
            <div class="dm-label">压力</div>
            <div class="dm-val">{{ metrics.pressure.toFixed(3) }} Pa</div>
          </div>
          <div class="dm">
            <div class="dm-label">气体流量</div>
            <div class="dm-val">{{ metrics.gas.toFixed(0) }} sccm</div>
          </div>
          <div class="dm">
            <div class="dm-label">RF 功率</div>
            <div class="dm-val">{{ metrics.rf.toFixed(0) }} W</div>
          </div>
          <div class="dm">
            <div class="dm-label">晶圆计数</div>
            <div class="dm-val">{{ metrics.waferCount }}</div>
          </div>
          <div class="dm">
            <div class="dm-label">工艺步骤</div>
            <div class="dm-val small">{{ processStep }}</div>
          </div>
        </div>
      </div>

      <!-- 回放控制条 -->
      <PlaybackBar
        :mode="mode"
        :playing="playing"
        :speed="speed"
        :date="playbackDate"
        :cursor="cursor"
        :start="playbackStart"
        :end="playbackEnd"
        @update:mode="onModeChange"
        @update:playing="onPlayingChange"
        @update:speed="onSpeedChange"
        @update:date="onDateChange"
        @seek="seek"
      />
    </div>

    <!-- 右侧面板 -->
    <div class="detail-right">
      <div class="dr-tabs">
        <button class="dr-tab" :class="{ active: rightTab === 'alarms' }" @click="rightTab = 'alarms'">告警</button>
        <button class="dr-tab" :class="{ active: rightTab === 'events' }" @click="rightTab = 'events'">事件</button>
        <button class="dr-tab" :class="{ active: rightTab === 'replay' }" @click="rightTab = 'replay'">回放</button>
        <button class="dr-tab" :class="{ active: rightTab === 'lots' }" @click="rightTab = 'lots'">Lot</button>
        <button class="dr-tab" :class="{ active: rightTab === 'ai' }" @click="rightTab = 'ai'">AI</button>
      </div>

      <!-- 告警 Tab -->
      <div v-show="rightTab === 'alarms'" class="dr-section">
        <AlarmStats :stats="alarmStats" :alarms="alarms" />
      </div>

      <!-- 事件 Tab -->
      <div v-show="rightTab === 'events'" class="dr-section">
        <EventList :events="displayEvents" />
      </div>

      <!-- 回放 Tab -->
      <div v-show="rightTab === 'replay'" class="dr-section">
        <HistoryReplay
          :machine-id="machineId"
          :machine-state="machine?.state"
          @jump="jumpToTime"
          @replay-event="onReplayEvent"
        />
      </div>

      <!-- Lot Tab -->
      <div v-show="rightTab === 'lots'" class="dr-section">
        <LotList :lots="lots" :selected-lot-id="selectedLotId" @select="selectLot" />
      </div>

      <!-- AI Tab -->
      <div v-show="rightTab === 'ai'" class="dr-section">
        <AiAssistant :machine-id="machineId" @jump="jumpToTime" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail-page {
  display: flex;
  height: 100%;
}
.detail-viewer {
  flex: 1;
  position: relative;
  background: #040712;
  overflow: hidden;
}

/* 新增：视图模式切换按钮 */
.view-mode-switcher {
  position: absolute;
  top: 14px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 8px;
  z-index: 15;
}

/* 2D模式下，切换按钮移到右上角（与返回按钮并排），避免遮挡2D内容 */
.detail-viewer.is-2d .view-mode-switcher {
  left: auto;
  right: 120px;
  transform: none;
  top: 10px;
}

.detail-viewer.is-2d .vms-btn {
  padding: 6px 12px;
  font-size: 11px;
}

/* VPO视图专用样式：按钮移到顶部两侧，避免遮挡PORT2和机台主体 */
.detail-viewer.is-vpo .view-mode-switcher {
  left: 14px;
  right: auto;
  transform: none;
  top: 14px;
  z-index: 20;
}

.detail-viewer.is-vpo .vms-btn {
  padding: 6px 12px;
  font-size: 11px;
  background: rgba(13, 20, 36, 0.9);
}

.detail-viewer.is-vpo .back-btn {
  top: 14px;
  right: 14px;
  padding: 6px 12px;
  font-size: 11px;
  z-index: 20;
  background: rgba(13, 20, 36, 0.9);
}

.vms-btn {
  padding: 8px 16px;
  border: 1px solid var(--border);
  background: rgba(13, 20, 36, 0.9);
  backdrop-filter: blur(8px);
  color: var(--text-dim);
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.vms-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.vms-btn.active {
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent);
  border-color: var(--accent);
  box-shadow: 0 0 12px rgba(0, 212, 255, 0.3);
}

.back-btn {
  position: absolute;
  top: 14px;
  right: 14px;
  background: rgba(13, 20, 36, 0.9);
  backdrop-filter: blur(8px);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  z-index: 10;
}

/* 2D模式下，返回按钮紧凑显示 */
.detail-viewer.is-2d .back-btn {
  top: 10px;
  right: 14px;
  padding: 6px 12px;
  font-size: 11px;
}
.back-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.detail-left-panel {
  position: absolute;
  top: 14px;
  left: 14px;
  padding: 14px 18px;
  min-width: 280px;
  z-index: 5;
}
.detail-mid {
  font-size: 22px;
  font-weight: 800;
}
.detail-model {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 2px;
  letter-spacing: 0.5px;
}
.detail-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 14px;
}
.dm {
  background: rgba(0, 0, 0, 0.25);
  padding: 8px 10px;
  border-radius: 6px;
}
.dm-label {
  font-size: 10px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.dm-val {
  font-size: 16px;
  font-weight: 700;
  margin-top: 3px;
}
.dm-val.small {
  font-size: 13px;
}
.dm-val.warn {
  color: var(--yellow);
}
.dm-val.crit {
  color: var(--red);
}
.detail-right {
  width: 340px;
  background: var(--panel);
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.dr-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
}
.dr-tab {
  flex: 1;
  padding: 8px 10px;
  background: none;
  border: none;
  color: var(--text-dim);
  font-size: 11px;
  font-weight: 600;
  border-bottom: 2px solid transparent;
}
.dr-tab:hover {
  color: var(--text);
}
.dr-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  background: rgba(0, 212, 255, 0.05);
}
.dr-section {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
</style>
