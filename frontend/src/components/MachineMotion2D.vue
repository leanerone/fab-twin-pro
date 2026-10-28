<script setup>
/**
 * 通用 2D Motion 视图（新机型标准视图）
 *
 * 与模型组 MotionPreview 语义对齐的平台版：
 * - SVG 内联加载（views_config.view_2d.model_source，来自机型绑定上传）
 * - Motion JSON 从机型 animation_config 读取（schema_version 格式）
 * - 事件驱动：event_name → motion.step → deriver 推导参数 → resolveMotionRule → playMotion
 * - 历史回放 seek：批量补放用 instant 模式（无动画直接落终态），最后一条 animate
 *
 * 不写死任何机型业务：PORT 映射/缺省值/别名读 Motion JSON ext，业务推导走 motionDerivers。
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useModelStore } from '../stores/model'
import {
  playMotion,
  resetMotionState,
  applyMotionBaseVisibility,
  invalidateMotionGeometry,
} from '../composables/useMotionPlayback'
import { evalWhen, resolveMotionRule, extractParamKeys } from '../composables/useExprEval'
import { getMotionDeriver } from '../motionDerivers'
import { scopeSvgPaintIds } from '../utils/svgPaintScope'
import api from '../api'

const props = defineProps({
  machine: { type: Object, default: null },
  modelConfig: { type: Object, default: null },
  currentState: { type: String, default: 'idle' },
  // 升序事件列表（MachineDetail 的 events，不是倒序的 displayEvents）
  events: { type: Array, default: () => [] },
  mode: { type: String, default: 'realtime' }, // realtime / playback
})

const modelStore = useModelStore()

const svgHost = ref(null)
const svgMarkup = ref('')
const ready = ref(false)
const loadError = ref('')
const motionConfig = ref(null)
const warnings = ref([])
const lastStep = ref('')

const ext = computed(() => motionConfig.value?.ext || {})
const deriverName = computed(() => ext.value.deriver || '')

function pushWarn(msg) {
  if (!msg) return
  warnings.value.push(msg)
  if (warnings.value.length > 5) warnings.value.shift()
}

// === 加载 SVG + Motion JSON ===
async function loadAssets() {
  ready.value = false
  loadError.value = ''
  svgMarkup.value = ''
  motionConfig.value = null

  const modelId = props.modelConfig?.model_id
  if (!modelId) {
    loadError.value = '缺少机型配置'
    return
  }
  const detail = await modelStore.loadModelDetail(modelId)
  let anim = detail?.animation_config
  if (typeof anim === 'string') {
    try { anim = JSON.parse(anim) } catch { anim = null }
  }
  if (!anim || !anim.schema_version || !Array.isArray(anim.motions)) {
    loadError.value = '该机型未绑定 Motion JSON（animation_config 为空或格式不符）'
    return
  }
  motionConfig.value = anim

  let viewsCfg = detail?.views_config
  if (typeof viewsCfg === 'string') {
    try { viewsCfg = JSON.parse(viewsCfg) } catch { viewsCfg = null }
  }
  const svgUrl = viewsCfg?.view_2d?.model_source || viewsCfg?.view_2d?.source || viewsCfg?.view_2d?.svg_source
  if (!svgUrl) {
    loadError.value = '该机型未绑定 2D SVG（views_config.view_2d.model_source 为空）'
    return
  }
  // 强制破缓存：静态 SVG 经 vite/后端静态挂载会带 etag，开发期改图后需确保拿到最新版
  const bustUrl = svgUrl + (svgUrl.includes('?') ? '&' : '?') + '_v=' + Date.now()
  try {
    const resp = await fetch(bustUrl, { cache: 'no-store' })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    svgMarkup.value = scopeSvgPaintIds(await resp.text())
  } catch (e) {
    loadError.value = `SVG 加载失败: ${e.message}`
    return
  }

  await nextTick()
  const svg = svgHost.value?.querySelector('svg')
  if (!svg) {
    loadError.value = 'SVG 内容无效'
    return
  }
  // 缺 viewBox 时用 Motion JSON document.viewBox / ext.viewBox_fallback 补上，保证可缩放
  if (!svg.getAttribute('viewBox')) {
    const vb = anim.document?.viewBox || anim.document?.coord?.viewBox || ext.value.viewBox_fallback
    if (Array.isArray(vb) && vb.length === 4) {
      svg.setAttribute('viewBox', vb.join(' '))
      pushWarn('SVG 缺 viewBox，已按配置兜底')
    }
  }
  svg.setAttribute('width', '100%')
  svg.setAttribute('height', '100%')
  svg.removeAttribute('style')

  invalidateMotionGeometry(svgHost.value)
  resetMotionState(svgHost.value)
  applyMotionBaseVisibility(svgHost.value)
  getMotionDeriver(deriverName.value)?.reset()

  ready.value = true
}

// === 事件 → Motion ===
function normalizeChamber(val) {
  const s = String(val ?? '').trim()
  const m = s.match(/^CHAMBER[_-]?(.+)$/i)
  return (m ? m[1] : s).toUpperCase()
}

function toMotionPayload(ev) {
  const src = { ...(ev?.payload || {}), ...ev }
  const pick = (...keys) => {
    for (const k of keys) {
      const v = src[k]
      if (v !== undefined && v !== null && v !== '' && v !== 'NULL') return v
    }
    return ''
  }
  return {
    ...src,
    LOT_ID: pick('LOT_ID', 'lot_id'),
    PORT: pick('PORT', 'port_id', 'port'),
    SLOT: pick('SLOT', 'slot_id', 'slot'),
    CHAMBER: normalizeChamber(pick('CHAMBER', 'chamber_id', 'chamber')),
    BATCH_ID: pick('BATCH_ID', 'batch_id'),
    Qty: pick('Qty', 'qty'),
    RunMode: pick('RunMode', 'run_mode'),
    RECIPE1: pick('RECIPE1', 'recipe', 'recipe1'),
  }
}

// 串行播放队列（与模型组语义一致：事件排队，逐个播完）
let playQueue = Promise.resolve()
let processedCount = 0

async function processEvent(ev, playMode) {
  const cfg = motionConfig.value
  if (!cfg || !svgHost.value) return
  let stepName = String(ev?.event_name || ev?.event_code || '').toUpperCase()
  if (!stepName) return
  const extCfg = ext.value
  // 事件名别名（ext.event_aliases）：同一动作的多种上报名（MIC/POD_PLACE/MOC/OPEN_DOOR…）
  // 映射到 Motion JSON 的规范 step，避免为每个别名复制一份 motion
  const alias = extCfg.event_aliases?.[stepName]
  if (alias) stepName = String(alias).toUpperCase()
  const motion = (cfg.motions || []).find(m => String(m.step || '').toUpperCase() === stepName)
  if (!motion) return

  const payload = toMotionPayload(ev)
  const deriver = getMotionDeriver(deriverName.value)

  let params = payload
  let info = {}
  if (deriver) {
    const r = deriver.derive(motion.step, payload, { motionConfig: cfg, ext: extCfg })
    if (!r.ok) {
      pushWarn(`${stepName}: ${r.warn}`)
      return
    }
    params = r.params
    info = r.info || {}
  }

  if (!evalWhen(motion.when, params)) return

  const matchedRules = []
  for (const rule of motion.rules || []) {
    if (!evalWhen(rule.when, params)) continue
    matchedRules.push(resolveMotionRule(rule, params, extCfg))
  }
  // 与模型组一致：when 全不命中时回退播该 step 全部 rules
  if (matchedRules.length === 0) {
    for (const rule of motion.rules || []) {
      matchedRules.push(resolveMotionRule(rule, params, extCfg))
    }
  }
  if (matchedRules.length === 0) return

  const result = await playMotion({
    container: svgHost.value,
    rules: matchedRules,
    params,
    mode: playMode,
    reset: false,
    partAliases: extCfg.part_aliases || {},
    onWarn: pushWarn,
  })
  if (!result.ok) {
    if (result.reason !== 'no-rules') pushWarn(`${stepName}: 播放失败(${result.reason})`)
    return
  }
  lastStep.value = stepName
  if (deriver) deriver.commit(motion.step, params, info)
}

function resetView() {
  if (!svgHost.value) return
  resetMotionState(svgHost.value)
  applyMotionBaseVisibility(svgHost.value)
  invalidateMotionGeometry(svgHost.value)
  getMotionDeriver(deriverName.value)?.reset()
  processedCount = 0
  warnings.value = []
}

watch(() => props.events, (list) => {
  if (!ready.value) return
  // seek/重建：列表变短 → 整体重置后批量补放
  if (list.length < processedCount) resetView()
  const pending = list.slice(processedCount)
  processedCount = list.length
  if (!pending.length) return
  // 批量补放（seek）：前面的 instant 落终态，最后一条 animate
  pending.forEach((ev, i) => {
    const isCatchup = pending.length > 1 && i < pending.length - 1
    const playMode = isCatchup ? 'instant' : 'animate'
    playQueue = playQueue.then(() => processEvent(ev, playMode), () => processEvent(ev, playMode))
  })
}, { deep: true })

watch(() => props.modelConfig?.model_id, () => {
  processedCount = 0
  loadAssets()
})

onMounted(loadAssets)
onBeforeUnmount(() => { processedCount = 0 })

// 供父组件 seek 时显式重置（回放跳转时清空动画状态重新补放）
defineExpose({
  resetReplayCursor: resetView,
})

// === 消息调试台（方案A）：注入事件走真实 DB 轮询链路驱动动画 ===
const debugOpen = ref(false)
const debugStep = ref('')
const debugParams = ref([]) // [{ key, value }]
const debugSending = ref(false)
const debugPlaying = ref(false)
const debugMsg = ref('')

const debugSteps = computed(() => (motionConfig.value?.motions || []).map(m => m.step))

// deriver 内部派生参数，不需要用户填
const DEBUG_INTERNAL_KEYS = new Set(['has_entered_chamber', 'cross_arm', 'cycle',
  'pod_shell', 'POD', 'POD_LK', 'CST', 'DOOR', 'MAP', 'SMIF_C', 'PORT_C', 'SLOT_ANCHOR',
  'CH_C', 'WAFER_CH', 'CH_RUN', 'CH_ALARM', 'CH_UNLOAD', 'ARM_HOME', 'ARM_PORT_ANGLE',
  'ARM_CH_ANGLE', 'ARM_PA_ANGLE', 'ARM_EXTEND_OUT',
  'DONE_COUNT', 'ALARM_PORT', 'ALARM_COUNT', 'AL1', 'AL2', 'AL3'])
// SM01..SM25 为 deriver 展开的逐槽 mapping 字符（when 用），同样不展示
const DEBUG_INTERNAL_RE = /^SM\d{2}$/
// 常用参数示例值（默认值优先取 ext.param_defaults）
const DEBUG_PARAM_EXAMPLES = {
  SMIFPORTID: '1', PORT: '1', LOT_ID: 'DEMO_LOT01', SLOT: '1', CHAMBER: 'E',
  BATCH_ID: 'BT_DEMO01', Qty: '25', RunMode: 'PACKING', RECIPE1: 'RCP_AU_01',
}

// 选中 step 后，从 motion.when + 各 rule.when 自动提取引用参数并预填示例值
watch(debugStep, (step) => {
  const motion = (motionConfig.value?.motions || []).find(m => m.step === step)
  if (!motion) {
    debugParams.value = []
    return
  }
  const whens = [motion.when, ...(motion.rules || []).map(r => r.when)]
  const keys = extractParamKeys(whens).filter(k =>
    !DEBUG_INTERNAL_KEYS.has(k) && !DEBUG_INTERNAL_RE.test(k))
  const defaults = ext.value.param_defaults || {}
  debugParams.value = keys.map(k => ({
    key: k,
    value: String(defaults[k] ?? DEBUG_PARAM_EXAMPLES[k] ?? ''),
  }))
  debugMsg.value = ''
})

function debugAddParam() {
  debugParams.value.push({ key: '', value: '' })
}

function debugRemoveParam(i) {
  debugParams.value.splice(i, 1)
}

function collectDebugParams() {
  const params = {}
  for (const row of debugParams.value) {
    const k = String(row.key || '').trim()
    if (k) params[k] = row.value
  }
  return params
}

async function debugSend(stepName, params) {
  const machineId = props.machine?.id
  if (!machineId) throw new Error('无机台信息')
  return api.debugSendEvent({ tool_id: machineId, event_name: stepName, params })
}

async function debugSendOnce() {
  if (!debugStep.value || debugSending.value || debugPlaying.value) return
  debugSending.value = true
  debugMsg.value = ''
  try {
    const r = await debugSend(debugStep.value, collectDebugParams())
    debugMsg.value = `已发送 ${r.event_name}（约 1 秒后动画响应）`
  } catch (e) {
    debugMsg.value = `发送失败: ${e.message}`
  } finally {
    debugSending.value = false
  }
}

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms))

/**
 * 按 deriver 选调试流程——不同机型的 Motion step 完全不同，硬编码一条全机型共用会导致
 * "播放完整流程"实际只命中首尾 2 步（OXE/PODOPENER 都存在这个现象）。
 * 各机型序列均来自其 Motion JSON 里实际存在的 step。
 */
function pickDebugFlow(deriver) {
  const LOT = 'DEMO_LOT01'
  const PORT = '1'
  if (deriver === 'oxe') {
    return [
      ['POD_PLACED', { PORT }, 3500],
      ['START', { PORT }, 3000],       // LOTSTAT: PP-SELECT OK
      ['PS', { PORT }, 3500],           // LOTSTAT: PROCESSING
      ['PE', { PORT }, 3500],           // LOTSTAT 下一态
      ['MVOU', { PORT }, 3500],         // LOTSTAT: LOT OUT
      ['POD_REMOVED', { PORT }, 0],
    ]
  }
  if (deriver === 'podopener') {
    return [
      ['POD_PLACED', { port_id: PORT, RunMode: 'PACKING' }, 2200],
      ['COMPLETED_PORT_LOCK', { port_id: PORT }, 1800],
      ['READ_BATTERY', { port_id: PORT }, 1800],
      ['READ_TAG', { port_id: PORT, LOT_ID: LOT }, 1800],
      ['BATCH_INFO_FROM_ECUI', { BATCH_ID: 'BT_DEMO01', LOT_ID: LOT, Qty: '25', RunMode: 'PACKING', RECIPE1: 'RCP_AU_01', PORT }, 2200],
      ['OPEN_POD', { port_id: PORT }, 2500],
      ['REACH_STAGE', { port_id: PORT }, 2000],
      ['UI_CONFIRM', { port_id: PORT }, 2500],
      ['CLOSE_POD', { port_id: PORT }, 2500],
      ['ACK_UI_DOUBLECHECK', { port_id: PORT }, 1500],
      ['REACH_POS', { port_id: PORT }, 2000],
      ['WRITE_TAG', { port_id: PORT, LOT_ID: LOT }, 1800],
      ['COMPLETED_PORT_UNLOCK', { port_id: PORT }, 1800],
      ['POD_REMOVED', { port_id: PORT }, 0],
    ]
  }
  // AMAT METSPUT 默认流程（与 backend/demo_amat_motion.py 对齐）
  return [
    ['POD_PLACED', { SMIFPORTID: '1' }, 3500],
    ['BATCH_INFO_FROM_ECUI', { BATCH_ID: 'BT_DEMO01', LOT_ID: LOT, Qty: '25', RunMode: 'PACKING', RECIPE1: 'RCP_AU_01', PORT: '1' }, 3500],
    ['CASSETTE_ARRIVAL', { PORT: '1' }, 3500],
    ['CHAMBER_PS', { LOT_ID: LOT, SLOT: '1', CHAMBER: 'E' }, 8000],
    ['CHAMBER_PS', { LOT_ID: LOT, SLOT: '2', CHAMBER: '1' }, 8000],
    ['WAFER_PROCESS_COMPLETE', { LOT_ID: LOT, SLOT: '1' }, 5500],
    ['WAFER_PROCESS_COMPLETE', { LOT_ID: LOT, SLOT: '2' }, 5500],
    ['POD_REMOVED', { SMIFPORTID: '1' }, 0],
  ]
}

async function debugPlayFlow() {
  if (debugPlaying.value || debugSending.value) return
  const seq = pickDebugFlow(deriverName.value)
  debugPlaying.value = true
  try {
    // 开播前复位：清 deriver 业务状态（waferPosRegistry 等）+ 运动状态，
    // 否则上次流程的残留（如 SLOT2 晶圆位置记录、臂角度）会污染本次推导
    await playQueue.catch(() => {})
    resetView()
    processedCount = (props.events || []).length // 跳过历史事件，只播本次新发的
    for (let i = 0; i < seq.length; i++) {
      const [name, params, gap] = seq[i]
      await debugSend(name, params)
      debugMsg.value = `流程播放中 (${i + 1}/${seq.length}) ${name}`
      if (gap) await sleep(gap)
    }
    debugMsg.value = '完整流程发送完毕'
  } catch (e) {
    debugMsg.value = `流程中断: ${e.message}`
  } finally {
    debugPlaying.value = false
  }
}
</script>

<template>
  <div class="motion2d-view">
    <div v-if="loadError" class="motion2d-error">
      <div class="motion2d-error-text">{{ loadError }}</div>
    </div>
    <div v-show="!loadError" ref="svgHost" class="motion2d-svg-host" v-html="svgMarkup"></div>

    <div v-if="ready" class="motion2d-status">
      <span class="motion2d-state">{{ currentState }}</span>
      <span v-if="lastStep" class="motion2d-step">{{ lastStep }}</span>
    </div>

    <div v-if="warnings.length" class="motion2d-warnings">
      <div v-for="(w, i) in warnings" :key="i" class="motion2d-warn-item">⚠ {{ w }}</div>
    </div>

    <!-- 消息调试台（实时模式可用）：注入事件走真实 DB 轮询链路驱动动画 -->
    <div v-if="ready && !loadError && mode === 'realtime'" class="motion2d-debug">
      <button class="motion2d-debug-toggle" @click="debugOpen = !debugOpen">
        {{ debugOpen ? '收起调试' : '消息调试' }}
      </button>
      <div v-if="debugOpen" class="motion2d-debug-panel">
        <div class="motion2d-debug-row">
          <label>事件</label>
          <select v-model="debugStep">
            <option value="" disabled>选择 step</option>
            <option v-for="s in debugSteps" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
        <div v-for="(row, i) in debugParams" :key="i" class="motion2d-debug-row">
          <input v-model="row.key" class="param-key" placeholder="参数名" />
          <input v-model="row.value" class="param-value" placeholder="参数值" />
          <button class="param-remove" title="删除" @click="debugRemoveParam(i)">×</button>
        </div>
        <div class="motion2d-debug-actions">
          <button class="debug-btn" @click="debugAddParam">+ 参数</button>
          <button class="debug-btn primary" :disabled="!debugStep || debugSending || debugPlaying" @click="debugSendOnce">
            {{ debugSending ? '发送中…' : '发送' }}
          </button>
          <button class="debug-btn" :disabled="debugSending || debugPlaying" @click="debugPlayFlow">
            {{ debugPlaying ? '播放中…' : '播放完整流程' }}
          </button>
        </div>
        <div v-if="debugMsg" class="motion2d-debug-msg">{{ debugMsg }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.motion2d-view {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  background: radial-gradient(ellipse at center, #16213e 0%, #0f172a 100%);
}
.motion2d-svg-host {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.motion2d-svg-host :deep(svg) {
  max-width: 100%;
  max-height: 100%;
}
.motion2d-error {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.motion2d-error-text {
  color: #fbbf24;
  font-size: 14px;
  padding: 12px 20px;
  background: rgba(0, 0, 0, 0.5);
  border: 1px solid rgba(251, 191, 36, 0.4);
  border-radius: 8px;
}
.motion2d-status {
  position: absolute;
  top: 12px;
  left: 12px;
  display: flex;
  gap: 8px;
  align-items: center;
  pointer-events: none;
}
.motion2d-state {
  padding: 4px 10px;
  font-size: 12px;
  color: #e2e8f0;
  background: rgba(34, 197, 94, 0.15);
  border: 1px solid rgba(34, 197, 94, 0.4);
  border-radius: 6px;
}
.motion2d-step {
  padding: 4px 10px;
  font-size: 12px;
  color: #93c5fd;
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(59, 130, 246, 0.4);
  border-radius: 6px;
}
.motion2d-warnings {
  position: absolute;
  bottom: 12px;
  left: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  pointer-events: none;
}
.motion2d-warn-item {
  font-size: 11px;
  color: #fcd34d;
  background: rgba(0, 0, 0, 0.45);
  padding: 3px 8px;
  border-radius: 4px;
}
/* 消息调试台 */
.motion2d-debug {
  position: absolute;
  right: 12px;
  bottom: 12px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  z-index: 5;
}
.motion2d-debug-toggle {
  padding: 4px 12px;
  font-size: 12px;
  color: #a5b4fc;
  background: rgba(49, 46, 129, 0.35);
  border: 1px solid rgba(129, 140, 248, 0.4);
  border-radius: 6px;
  cursor: pointer;
}
.motion2d-debug-toggle:hover {
  background: rgba(49, 46, 129, 0.55);
}
.motion2d-debug-panel {
  width: 280px;
  max-height: 320px;
  overflow-y: auto;
  padding: 10px;
  background: rgba(15, 23, 42, 0.92);
  border: 1px solid rgba(129, 140, 248, 0.35);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.motion2d-debug-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.motion2d-debug-row label {
  font-size: 12px;
  color: #94a3b8;
  flex: 0 0 28px;
}
.motion2d-debug-row select,
.motion2d-debug-row input {
  flex: 1;
  min-width: 0;
  padding: 4px 6px;
  font-size: 12px;
  color: #e2e8f0;
  background: rgba(30, 41, 59, 0.9);
  border: 1px solid rgba(100, 116, 139, 0.5);
  border-radius: 4px;
  outline: none;
}
.motion2d-debug-row input.param-key {
  flex: 0 0 42%;
}
.motion2d-debug-row .param-remove {
  flex: 0 0 auto;
  width: 20px;
  height: 22px;
  font-size: 13px;
  line-height: 1;
  color: #f87171;
  background: transparent;
  border: none;
  cursor: pointer;
}
.motion2d-debug-actions {
  display: flex;
  gap: 6px;
  margin-top: 2px;
}
.debug-btn {
  flex: 1;
  padding: 5px 6px;
  font-size: 12px;
  color: #cbd5e1;
  background: rgba(51, 65, 85, 0.8);
  border: 1px solid rgba(100, 116, 139, 0.5);
  border-radius: 5px;
  cursor: pointer;
  white-space: nowrap;
}
.debug-btn:hover:not(:disabled) {
  background: rgba(71, 85, 105, 0.9);
}
.debug-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.debug-btn.primary {
  color: #fff;
  background: rgba(59, 130, 246, 0.55);
  border-color: rgba(59, 130, 246, 0.7);
}
.debug-btn.primary:hover:not(:disabled) {
  background: rgba(59, 130, 246, 0.75);
}
.motion2d-debug-msg {
  font-size: 11px;
  color: #86efac;
  word-break: break-all;
}
</style>
