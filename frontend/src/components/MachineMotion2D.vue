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
import { evalWhen, resolveMotionRule } from '../composables/useExprEval'
import { getMotionDeriver } from '../motionDerivers'
import { scopeSvgPaintIds } from '../utils/svgPaintScope'

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
    offsetMode: extCfg.offset_mode === 'absolute' ? 'absolute' : 'relative',
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
</style>
