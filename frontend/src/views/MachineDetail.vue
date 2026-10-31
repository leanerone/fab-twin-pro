<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAppStore } from '../stores/app'
import { useModelStore } from '../stores/model'
import { api } from '../api'
import { stateLabels } from '../composables/useThree'
import { parseEventAction } from '../composables/useEventActionMapping'
import MachineModel3D from '../components/MachineModel3D.vue'
import MachineVpo3DView from '../components/MachineVpo3DView.vue'
import MachineMotion2D from '../components/MachineMotion2D.vue'
import PlaybackBar from '../components/PlaybackBar.vue'
import AiAssistant from '../components/AiAssistant.vue'
import HistoryReplay from '../components/HistoryReplay.vue'
import { parseTs, fmtHM, hmToMs, msToHM, fmtDateMs, fmtLocalTs, HOUR_MS, MAX_RANGE_MS } from '../composables/timeFormat.js'
import { calcRunState, createRunState } from '../composables/useRunState.js'
import { useMachinePlayback } from '../composables/useMachinePlayback.js'


// 机台详情：3D 模型 + 2D原理图 + 回放 + 右侧 Tab（告警/事件/Lot/AI）
const props = defineProps({
  id: { type: String, default: '' },
})

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const modelStore = useModelStore()

// === 状态 ===
const machine = ref(null)
// 是否使用外部跳转网站（iframe 嵌入）替代原生 2D/3D 视图
const useExternalView = computed(() => !!(machine.value?.use_external_url && machine.value?.external_url))
// 嵌入用 URL：自动补全协议前缀，避免被浏览器解析为相对路径
const externalFrameUrl = computed(() => {
  const raw = (machine.value?.external_url || '').trim()
  if (!raw) return ''
  return /^https?:\/\//i.test(raw) ? raw : 'https://' + raw
})
const mode = ref('realtime')              // realtime / playback
const playing = ref(true)
const speed = ref(2)
const today = new Date()
const playbackDate = ref(`${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`)
const cursor = ref(0)                     // 回放游标时间戳
const playbackStart = ref(0)
const playbackEnd = ref(0)
const rightTab = ref('replay')
const aiAssistantRef = ref(null)
const motion2dRef = ref(null) // Motion2D 视图：回放跳转时需清空动画状态重新补放
const aiPrefillQuestion = ref('')  // 从回放 Tab 传递过来的预填问题
const currentState = ref('idle')
const processStep = ref('待机')
const metrics = reactive({ temp: 22, pressure: 1, gas: 0, rf: 0, waferCount: 0 })
const events = ref([])
const replayEvents = ref([]) // 回放面板展示的区段事件列表（父级一次性加载）
const transferTrigger = ref(0)
const loading = ref(false)
const currentLotId = ref('')  // 当前正在run的Lot ID
const pendingJumpTs = ref('') // 等待数据加载完成后执行的跳转时间戳

// 时间区段（HH:MM）：默认最近1小时，最大查询跨度12小时
const initNow = new Date()
const playbackStartHM = ref(fmtHM(new Date(initNow.getTime() - HOUR_MS)))
const playbackEndHM = ref(fmtHM(initNow))
// 校正区段：结束<=开始自动补1小时；跨度超12小时从结束时间前收；限制在所选日期内
function normalizeRange(startHM, endHM) {
  const dayStart = new Date(`${playbackDate.value}T00:00:00`).getTime()
  const dayEnd = dayStart + 86400000 - 1
  let s = dayStart + hmToMs(startHM)
  let e = dayStart + hmToMs(endHM)
  if (isNaN(s) || s < dayStart) s = dayStart
  if (isNaN(e) || e > dayEnd) e = dayEnd
  if (e <= s) e = s + HOUR_MS
  if (e - s > MAX_RANGE_MS) s = e - MAX_RANGE_MS
  if (s < dayStart) s = dayStart
  playbackStartHM.value = msToHM(s - dayStart)
  playbackEndHM.value = msToHM(e - dayStart)
}
// 将区段调整为覆盖目标时间（前后各1小时，受日期边界约束）
function setRangeAround(targetMs) {
  const dayStart = new Date(`${playbackDate.value}T00:00:00`).getTime()
  const dayEnd = dayStart + 86400000 - 1
  const s = Math.max(dayStart, targetMs - HOUR_MS)
  const e = Math.min(dayEnd, targetMs + HOUR_MS)
  playbackStartHM.value = msToHM(s - dayStart)
  playbackEndHM.value = msToHM(e - dayStart)
}

// === 视图模式（根据机台型号自动选择） ===
const viewMode = ref('loading')           // loading / motion2d / 3d / vpo3d / external
const currentModelConfig = ref(null)
const modelConfigReady = ref(false)
const loadErrorMsg = ref('')

function resolveViewMode(machineModel) {
  const vm = modelStore.getViewMode(machineModel)
  const cfg = modelStore.getModelById(modelStore.resolveModelId(machineModel))
  // 视图选择完全由机型配置驱动（view_mode / views_config / animation_config）；
  // 2D 已统一为 motion2d 管线，旧 oxe/vpo/iso 2D 组件归档，未知配置回退 3D
  if (vm === 'motion2d' || cfg?.animation_config?.schema_version) return 'motion2d'
  if (vm === 'vpo' || vm === 'svg-vpo' || vm === 'vpo3d' || vm === 'vpo-3d') {
    if (cfg?.views_config?.view_3d?.type === 'vpo') return 'vpo3d'
    return '3d'
  }
  return '3d'
}

const availableViews = computed(() => {
  const cfg = currentModelConfig.value
  if (!cfg) return []
  const views = []
  // Motion JSON 2D 动画视图：绑定 animation_config（含 schema_version）的机型
  const hasMotion = cfg.view_mode === 'motion2d' || !!cfg.animation_config?.schema_version
  if (hasMotion) {
    views.push({ key: 'motion2d', label: '🎬 Motion动画' })
  }
  // 3D 视图：vpo 专用 3D 或通用 threejs
  if (cfg.views_config?.view_3d?.type === 'vpo' || cfg.view_mode === 'vpo3d' || cfg.view_mode === 'vpo-3d') {
    views.push({ key: 'vpo3d', label: '🎯 PODOPENER 3D' })
  } else if (cfg.views_config?.view_3d || cfg.view_mode === 'threejs' || cfg.view_mode === 'hybrid') {
    views.push({ key: '3d', label: '🎯 3D模型' })
  }
  if (views.length === 0) views.push({ key: '3d', label: '🎯 3D模型' })
  return views
})

// ===== Run货动画状态（2D/3D共用） =====
// 常量与 calcRunState 纯函数收拢到 composables/useRunState.js（批次3）
const runState = createRunState()

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
let realtimeTimer = null

// 当前机台
const machineId = computed(() => props.id || appStore.selectedMachineId || 'OXE-01')

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
  // 加载时先清空视图，避免闪现ETCH模型
  modelConfigReady.value = false
  currentModelConfig.value = null
  viewMode.value = 'loading'

  try {
    machine.value = await api.getMachine(machineId.value)
  } catch (e) {
    // 机台不存在/接口失败：给出明确错误态，不再无限转圈
    viewMode.value = 'error'
    modelConfigReady.value = true
    loadErrorMsg.value = e?.message || '机台数据加载失败'
    return
  }
  if (machine.value) {
    currentState.value = machine.value.state
    processStep.value = `步骤 ${machine.value.process_step}/6`
    metrics.temp = machine.value.temp
    metrics.pressure = machine.value.pressure
    metrics.gas = machine.value.gas_flow
    metrics.rf = machine.value.rf_power
    metrics.waferCount = machine.value.wafer_count
    appStore.selectMachine(machineId.value)

    // 外部跳转网站：用 iframe 嵌入，跳过原生 2D/3D 视图配置
    if (useExternalView.value) {
      viewMode.value = 'external'
      modelConfigReady.value = true
    } else {
      if (modelStore.models.length === 0) {
        await modelStore.loadModels()
      }
      const modelId = modelStore.resolveModelId(machine.value.model)
      const cfg = modelStore.getModelById(modelId)
      currentModelConfig.value = cfg
      const resolved = resolveViewMode(machine.value.model)
      viewMode.value = resolved
      modelConfigReady.value = !!cfg
    }
  }
}

// === 实时模式：从 store 接收事件 ===
// 注意：事件时间戳存在两种格式（db_poller 推送 "YYYY-MM-DD HH:mm:ss"，模拟器用 ISO T 格式），
// 字符串直接比较会跨格式误判（空格 < 'T'），必须归一化为 epoch 毫秒再比较
function tsToMs(ts) {
  if (!ts) return 0
  const ms = Date.parse(String(ts).replace(' ', 'T'))
  return Number.isNaN(ms) ? 0 : ms
}
const lastProcessedRealtimeTsMs = ref(0)
const realtimeEventsInitialized = ref(false)
// watch 队首元素（test31）：每个新事件 unshift 后队首引用变化，浅比较即触发；
// 此前 deep:true 每条 WS 事件都要递归遍历 200 个事件对象的全部嵌套属性，
// 回放模式下 guard 虽会拦下处理，但遍历成本已经付出
watch(() => appStore.recentEvents[0], () => {
  if (mode.value !== 'realtime') return
  const evs = appStore.recentEvents
  if (!evs.length) return
  const myEvents = evs.filter(e => e.machine_id === machineId.value)
  if (!myEvents.length) return
  // 首次接收实时事件：用水线 = max(已加载历史最后一条, 本次事件) 初始化，
  // 历史里已经播过的事件不重复播，但**这条新事件本身要照常处理**。
  // 旧实现直接 return 丢掉第一条实时事件，导致进页面后注入/上送的第一个事件
  // 完全不播（表现为「第一次动作没有任何动画」）。
  if (!realtimeEventsInitialized.value) {
    realtimeEventsInitialized.value = true
    const histLastTsMs = events.value.length
      ? tsToMs(events.value[events.value.length - 1].timestamp || events.value[events.value.length - 1].event_ts_utc)
      : 0
    lastProcessedRealtimeTsMs.value = Math.max(lastProcessedRealtimeTsMs.value, histLastTsMs)
    console.log('[MachineDetail] 实时事件初始化, lastProcessedRealtimeTsMs=', lastProcessedRealtimeTsMs.value)
  }
  // 只处理比上次更新的事件
  const newEvents = myEvents.filter(e => {
    return tsToMs(e.timestamp || e.event_ts_utc) > lastProcessedRealtimeTsMs.value
  })
  if (!newEvents.length) return
  console.log('[MachineDetail] 收到新实时事件:', newEvents.length, '个')
  newEvents.forEach(ev => {
    events.value.push(ev)
    if (events.value.length > 200) events.value.shift()
    applyEventData(ev)
    const tsMs = tsToMs(ev.timestamp || ev.event_ts_utc)
    if (tsMs > lastProcessedRealtimeTsMs.value) lastProcessedRealtimeTsMs.value = tsMs
  })
})

// 应用事件数据到模型
function applyEventData(ev) {
  if (!ev) return
  const evtName = (ev.event_name || ev.event_code || '').toUpperCase()
  const evtType = (ev.event_type || '').toUpperCase()

  // 提取当前 Lot ID
  if (ev.lot_id && ev.lot_id !== 'null' && ev.lot_id !== 'NULL') {
    currentLotId.value = ev.lot_id
  }

  if (evtType === 'STATE') {
    currentState.value = ev.event_code || currentState.value
    processStep.value = ev.description || processStep.value
  } else if (evtType === 'SENSOR') {
    if (ev.metric === 'temperature') metrics.temp = ev.value
    if (ev.metric === 'pressure') metrics.pressure = ev.value
    if (ev.metric === 'gasflow') metrics.gas = ev.value
    if (ev.metric === 'rf') metrics.rf = ev.value
  } else if (evtType === 'TRANSFER') {
    // 触发 3D 门/机械臂动画
    transferTrigger.value++
    if (/unload|卸载/i.test(ev.event_code + ev.description)) {
      metrics.waferCount++
    }
  } else if (evtType === 'VFEI' || evtType === 'HOST') {
    // PODOPENER 穿脱流程事件 - 更新状态（动画由3D组件通过watch events自动驱动）
    currentState.value = evtName
    processStep.value = ev.description || evtName
  }
}

// === 回放引擎（批次3抽离至 composables/useMachinePlayback.js） ===
// 传入组件的状态引用与事件分发器，返回全部回放控制函数；函数体为原实现逐字搬运
const {
  switchToPlayback, switchToRealtime, onModeChange, onPlayingChange,
  seek, commitSeek, onDateChange, onStartTimeChange, onEndTimeChange,
  onSpeedChange, jumpToTime, onReplayEvent,
} = useMachinePlayback({
  mode, playing, speed, events, replayEvents, loading,
  playbackDate, playbackStartHM, playbackEndHM,
  playbackStart, playbackEnd, cursor, pendingJumpTs,
  machineId, motion2dRef,
  realtimeEventsInitialized, lastProcessedRealtimeTsMs,
  applyEventData, normalizeRange, setRangeAround,
})

// 回放 Tab 的"AI分析当前回放"：切换到 AI Tab 并预填问题
function onAiAnalyze(payload) {
  const tsStr = payload.timestamp ? String(payload.timestamp).slice(0, 19).replace('T', ' ') : ''
  const dateStr = payload.date || ''
  const machineStr = payload.machine_id || machineId.value || ''
  // 根据机台型号生成不同的预填问题
  if (machineStr.toUpperCase().startsWith('OXE')) {
    aiPrefillQuestion.value = `分析 ${machineStr} 在 ${tsStr} 附近的事件，当前第几片晶圆在加工？是否有异常？`
  } else {
    aiPrefillQuestion.value = `分析 ${machineStr} 在 ${dateStr} ${tsStr} 附近的事件，机台状态是否正常？有无异常告警？`
  }
  rightTab.value = 'ai'
}


// 返回看板
function goBack() {
  router.push('/')
}

// 监听机台 ID 变化（与首次进入一致，默认实时）
watch(() => props.id, () => {
  pendingJumpTs.value = ''
  loadMachine().then(() => switchToRealtime())
})

// 监听 URL query 参数变化（date、mode）—— SPA 中切换 URL 不会重新挂载组件
watch(() => route.query, (q) => {
  if (!q) return
  const qDate = q.date ? String(q.date) : ''
  const qMode = q.mode ? String(q.mode) : ''
  // 仅处理合法日期格式
  if (qDate && /^\d{4}-\d{2}-\d{2}$/.test(qDate) && qDate !== playbackDate.value) {
    playbackDate.value = qDate
    switchToPlayback()
  } else if (qMode === 'playback' && mode.value !== 'playback') {
    switchToPlayback()
  } else if (qMode === 'realtime' && mode.value !== 'realtime') {
    switchToRealtime()
  }
})

// 处理AI跳转（query参数或全局store）
async function applyAIJump() {
  let ts = ''
  if (route.query && route.query.ts) {
    ts = String(route.query.ts)
    // 清理URL中的ts参数，避免刷新重复触发
    const q = { ...route.query }
    delete q.ts
    router.replace({ path: route.path, query: q })
  } else {
    const pending = appStore.consumePendingJump()
    if (pending && pending.timestamp) {
      // 仅当目标机台与当前机台一致（或未指定）时执行
      if (!pending.machine_id || pending.machine_id === props.id) {
        ts = pending.timestamp
      }
    }
  }
  if (!ts) return
  // 等待历史数据加载完成后跳转（不再用固定延时）
  await jumpToTime(ts)
}

onMounted(() => {
  updateRunAnimation()
  // 处理 URL 参数：date、mode
  const queryDate = route.query.date ? String(route.query.date) : ''
  const queryMode = route.query.mode ? String(route.query.mode) : ''
  if (queryDate && /^\d{4}-\d{2}-\d{2}$/.test(queryDate)) {
    playbackDate.value = queryDate
  }
  // 只加载一次机台数据，默认进入实时画面
  // 只有显式指定 mode=playback 才走回放（AI 跳转会在 jumpToTime 内自行切到回放）
  loadMachine().then(async () => {
    if (queryMode === 'playback') {
      await switchToPlayback()
    } else {
      switchToRealtime()
    }
    // 处理 AI 跳转（ts 参数）
    await applyAIJump()
  })
})

// 泄漏修复（test31）：离开详情页停掉 run 货动画 rAF 循环。
// 回放定时器/防抖/未完成请求的清理已内聚到 useMachinePlayback 的 onUnmounted（批次3）。
onUnmounted(() => {
  if (runAnimFrame) {
    cancelAnimationFrame(runAnimFrame)
    runAnimFrame = null
  }
})
</script>

<template>
  <div class="detail-page">
    <!-- 左侧视图区 -->
    <div class="detail-viewer" :class="{ 'is-2d': viewMode === 'motion2d' }">
      <!-- 视图模式切换按钮（多于1个视图时才显示，避免单按钮遮挡内容） -->
      <div v-if="modelConfigReady && availableViews.length > 1" class="view-mode-switcher">
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

      <!-- 外部跳转网站：iframe 嵌入 -->
      <div v-if="useExternalView" class="ext-iframe-wrap">
        <iframe :src="externalFrameUrl" class="oxe-iframe" frameborder="0" allow="fullscreen; clipboard-read; clipboard-write" allowfullscreen></iframe>
      </div>

      <!-- 加载占位（避免闪现ETCH模型） -->
      <div v-else-if="!modelConfigReady" class="model-loading">
        <div class="loading-spinner"></div>
        <div class="loading-text">加载机台模型配置...</div>
      </div>

      <!-- 加载失败/机台不存在（test31：不再无限转圈） -->
      <div v-else-if="viewMode === 'error'" class="model-loading">
        <div class="loading-text">⚠ {{ loadErrorMsg }}</div>
        <div class="loading-text" style="opacity:.6">该机台可能不存在于当前数据库，请返回看板选择其他机台</div>
      </div>

      <!-- 3D模型视图 -->
      <MachineModel3D
        v-else-if="viewMode === '3d'"
        :machine="machine"
        :current-state="currentState"
        :metrics="metrics"
        :process-step="processStep"
        :transfer-trigger="transferTrigger"
        :run-state="runState"
        :current-lot-id="currentLotId"
      />

      <!-- PODOPENER 3D视图 -->
      <MachineVpo3DView
        v-else-if="viewMode === 'vpo3d'"
        :machine="machine"
        :model-config="currentModelConfig"
        :current-state="currentState"
        :metrics="metrics"
        :run-state="runState"
        :events="displayEvents"
        :paused="mode === 'playback' && !playing"
        :mode="mode"
      />

      <!-- Motion JSON 2D 动画视图（新机型：绑定 SVG + Motion JSON） -->
      <MachineMotion2D
        v-else-if="viewMode === 'motion2d'"
        ref="motion2dRef"
        :machine="machine"
        :model-config="currentModelConfig"
        :current-state="currentState"
        :events="events"
        :mode="mode"
      />

      <button class="back-btn" @click="goBack">← 返回看板</button>

      <!-- 悬浮信息面板（2D模式下隐藏，避免遮挡） -->
      <div v-show="viewMode === '3d'" class="detail-left-panel glass-panel">
        <div class="detail-mid">{{ machineId }}</div>
        <div class="detail-model">{{ machine?.name || (machine?.model === 'TEL-DRM-UNIT' ? 'TEL DRM UNITY' : machine?.model) || 'TEL DRM UNITY' }} · 刻蚀机</div>
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

      <!-- 回放控制条（仅回放模式显示） -->
      <PlaybackBar
        v-show="mode === 'playback'"
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
      <!-- 全局日期选择器（实时/回放都可见） -->
      <div class="dr-date-bar">
        <span class="dr-date-label">数据日期</span>
        <input
          type="date"
          class="dr-date-input"
          :value="playbackDate"
          @change="onDateChange($event.target.value)"
        />
        <button class="dr-date-refresh" @click="onDateChange(playbackDate)" title="刷新数据">↻</button>
      </div>

      <!-- 时间区段（最大跨度12小时） -->
      <div class="dr-time-bar">
        <span class="dr-date-label">时间区段</span>
        <input
          type="time"
          class="dr-time-input"
          :value="playbackStartHM"
          @change="onStartTimeChange($event.target.value)"
        />
        <span class="dr-time-sep">~</span>
        <input
          type="time"
          class="dr-time-input"
          :value="playbackEndHM"
          @change="onEndTimeChange($event.target.value)"
        />
        <span class="dr-time-hint">≤12h</span>
      </div>

      <div class="dr-tabs">
        <button class="dr-tab" :class="{ active: rightTab === 'replay' }" @click="rightTab = 'replay'">回放</button>
        <button class="dr-tab" :class="{ active: rightTab === 'ai' }" @click="rightTab = 'ai'">AI</button>
      </div>

      <!-- 回放 Tab -->
      <div v-show="rightTab === 'replay'" class="dr-section">
        <HistoryReplay
          :machine-id="machineId"
          :machine-state="machine?.state"
          :events="replayEvents"
          :loading="loading"
          :jump-timestamp="cursor ? fmtLocalTs(cursor) : ''"
          @jump="jumpToTime"
          @replay-event="onReplayEvent"
          @ai-analyze="onAiAnalyze"
        />
      </div>

      <!-- AI Tab -->
      <div v-show="rightTab === 'ai'" class="dr-section ai-tab-wrap">
        <AiAssistant
          :machine-id="machineId"
          :prefill-question="aiPrefillQuestion"
          @jump="jumpToTime"
        />
      </div>


      <!-- 全局加载遮罩 -->
      <div v-if="loading" class="dr-loading-overlay">
        <div class="dr-loading-spinner"></div>
        <div class="dr-loading-text">数据加载中...</div>
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

/* 加载占位 */
.model-loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  z-index: 5;
  color: #94a3b8;
  font-size: 13px;
  pointer-events: none;
}
.loading-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid rgba(0, 212, 255, 0.2);
  border-top-color: #00d4ff;
  border-radius: 50%;
  animation: loading-spin 0.8s linear infinite;
}
@keyframes loading-spin {
  to { transform: rotate(360deg); }
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

/* 2D模式下，切换按钮保持顶部右侧横排（和3D/vpo3d同一层级），
   不再贴底竖排——之前贴底 bottom:14px 会与 motion2d-debug (right:12px bottom:12px)
   以及回放面板底部控件重叠，用户反馈"挡住时间回放条和调试按钮" */
.detail-viewer.is-2d .view-mode-switcher {
  left: auto;
  right: 14px;
  top: 14px;
  bottom: auto;
  transform: none;
  flex-direction: row;
  gap: 6px;
}

.detail-viewer.is-2d .vms-btn {
  padding: 6px 12px;
  font-size: 11px;
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

/* 外部跳转网站 iframe 容器（铺满详情视图区） */
.ext-iframe-wrap {
  position: absolute;
  inset: 0;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: #fff;
}
.ext-iframe-wrap .oxe-iframe {
  width: 100%;
  height: 100%;
  border: none;
}

/* OXE Canvas 看板 iframe 样式 */
.oxe-iframe {
  width: 100%;
  height: 100%;
  border: none;
  display: block;
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
  position: relative;
}
.dr-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
}

/* 全局日期选择器 */
.dr-date-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: rgba(0, 0, 0, 0.15);
}
.dr-date-label {
  font-size: 11px;
  color: var(--text-dim);
  white-space: nowrap;
}
.dr-date-input {
  flex: 1;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 5px 8px;
  border-radius: 5px;
  font-size: 12px;
  font-family: monospace;
  color-scheme: dark;
}
.dr-date-input:focus {
  border-color: var(--accent);
  outline: none;
}
.dr-date-refresh {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-dim);
  width: 28px;
  height: 28px;
  border-radius: 5px;
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.dr-date-refresh:hover {
  color: var(--accent);
  border-color: var(--accent);
}
.dr-time-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--border);
  background: rgba(0, 0, 0, 0.15);
}
.dr-time-input {
  flex: 1;
  min-width: 0;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 4px 6px;
  border-radius: 5px;
  font-size: 12px;
  font-family: monospace;
  color-scheme: dark;
}
.dr-time-input:focus {
  border-color: var(--accent);
  outline: none;
}
.dr-time-sep {
  color: var(--text-dim);
  font-size: 12px;
}
.dr-time-hint {
  font-size: 10px;
  color: var(--text-dim);
  white-space: nowrap;
  opacity: 0.8;
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

/* 加载遮罩 */
.dr-loading-overlay {
  position: absolute;
  inset: 0;
  background: rgba(4, 7, 18, 0.85);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  z-index: 50;
  pointer-events: none;
}
.dr-loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(0, 212, 255, 0.2);
  border-top-color: #00d4ff;
  border-radius: 50%;
  animation: loading-spin 0.8s linear infinite;
}
.dr-loading-text {
  font-size: 12px;
  color: #94a3b8;
}

/* ===== AI Tab 布局 ===== */
.ai-tab-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ai-tab-wrap .dr-section { min-height: 0; }
</style>
