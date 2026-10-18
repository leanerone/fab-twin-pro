<script setup>
/**
 * MotionPreview.vue — 通用 Motion JSON 动画预览组件
 *
 * 功能：
 * 1. 内联渲染 SVG（fetch → v-html，可直接操作 DOM）
 * 2. 自动从 motions 中提取所有 step 作为触发按钮
 * 3. 自动从 when 表达式中提取参数生成输入面板
 * 4. 触发事件 → 匹配 rule → 应用 action 到 SVG 元素
 * 5. 支持 offset/rotate/scale/opacity/visibility/flash/color 动作类型
 * 6. 重置按钮恢复所有部件到初始状态
 */
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { evalWhen, resolveMotionRule, enrichMotionParams } from '../composables/useExprEval.motion'
import { computeExtendVec } from '../motionDerivers/amatMetsput'
import { playMotion } from '../composables/useMotionPlayback.motion'
import { scopeSvgPaintIds } from '../utils/svgPaintScope'

const props = defineProps({
  /** SVG 文件 URL */
  svgUrl: { type: String, default: '' },
  /** Motion JSON 配置对象 */
  motionConfig: { type: Object, default: null },
})

const svgContainer = ref(null)
const svgInline = ref('')
const loading = ref(false)
const errorMsg = ref('')
const eventLog = ref([])

// 参数面板
const paramValues = ref({})
// BATCH_INFO_FROM_ECUI 登记：LOT_ID → { PORT, BATCH_ID, ... }
const lotRegistry = new Map()
// CHAMBER_PS 登记：LOT_ID::slot → { chamber }，下次从该腔取片
const waferPosRegistry = new Map()

function waferPosKey(lotId, slot) {
  return `${String(lotId || '').trim()}::${String(slot || '1').trim()}`
}

function normalizeKey(value) {
  return String(value || '').trim().toUpperCase()
}

function armAngleMap() {
  const src = props.motionConfig?.arm_chamber_angles || {}
  const out = {}
  for (const [armId, angles] of Object.entries(src)) {
    if (!armId || !angles || typeof angles !== 'object' || Array.isArray(angles)) continue
    const table = {}
    for (const [k, v] of Object.entries(angles)) {
      const key = String(k ?? '').trim()
      const num = Number(v)
      if (!key || !Number.isFinite(num)) continue
      table[key] = num
      table[normalizeKey(key)] = num
    }
    out[armId] = table
  }
  return out
}

function findArmByPos(posKey) {
  const key = String(posKey ?? '').trim()
  if (!key) return ''
  const upper = normalizeKey(key)
  const src = armAngleMap()
  for (const [armId, table] of Object.entries(src)) {
    if (table[key] != null || table[upper] != null) return armId
  }
  return ''
}

function armAngleFor(armId, posKey) {
  if (!armId) return null
  const key = String(posKey ?? '').trim()
  if (!key) return null
  const table = armAngleMap()[armId] || {}
  const angle = table[key] ?? table[normalizeKey(key)]
  return Number.isFinite(angle) ? angle : null
}

function armPickupAngle(armId) {
  for (const key of ['CHUCK', '1']) {
    const angle = armAngleFor(armId, key)
    if (angle != null) return angle
  }
  const table = armAngleMap()[armId] || {}
  const first = Object.keys(table)[0]
  const angle = first ? table[first] : null
  return Number.isFinite(angle) ? angle : null
}

function armChuckPart(armId) {
  const m = String(armId || '').match(/(\d+)\s*$/)
  return `Wafer_Chuck${m ? m[1] : '1'}`
}

function armLinkPart(armId) {
  const m = String(armId || '').match(/(\d+)\s*$/)
  return `ARM${m ? m[1] : '1'}_Link`
}

// 缓存每个部件的初始 transform（用于 reset）
const initialTransforms = new Map()
let stepPlayQueue = Promise.resolve()
let stepPlaying = false

// === 加载 SVG ===
async function loadSvg() {
  if (!props.svgUrl) {
    errorMsg.value = '未设置 SVG URL'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    let svgText = ''
    // 先尝试 HTTP fetch
    try {
      const resp = await fetch(props.svgUrl, { cache: 'no-store' })
      if (resp.ok) {
        svgText = await resp.text()
        // Vite dev server 对不存在的路径返回 SPA index.html（200 OK），需要检测
        if (!svgText.includes('<svg') && !svgText.trimStart().startsWith('<?xml')) {
          throw new Error('返回内容不是 SVG（可能是 SPA fallback 页面）')
        }
      } else {
        throw new Error(`HTTP ${resp.status}`)
      }
    } catch (fetchErr) {
      throw new Error(`SVG 网络加载失败: ${fetchErr.message}`)
    }
    if (!svgText.includes('<svg')) {
      console.error('[MotionPreview] 内容不包含 <svg 标签, URL:', props.svgUrl, 'text length:', svgText.length, 'text start:', svgText.slice(0, 100))
      if (svgText.length < 50 && !svgText.includes('<')) {
        throw new Error('返回内容不是 SVG（内容为空或非 HTML）')
      }
      console.warn('[MotionPreview] 使用宽松模式，尝试用 DOMParser 验证')
      try {
        const parser = new DOMParser()
        const doc = parser.parseFromString(svgText, 'image/svg+xml')
        const parseError = doc.querySelector('parsererror')
        if (parseError) throw new Error('XML 解析失败: ' + parseError.textContent)
        const svgEl = doc.querySelector('svg') || doc.documentElement
        if (svgEl && svgEl.tagName && svgEl.tagName.toLowerCase() === 'svg') {
          console.log('[MotionPreview] DOMParser 验证通过，是有效 SVG')
        } else {
          throw new Error('XML 根元素不是 <svg>')
        }
      } catch (parseErr) {
        throw new Error('返回内容不是 SVG: ' + parseErr.message)
      }
    }
    svgInline.value = scopeSvgPaintIds(svgText)
    // 等待 DOM 更新后缓存初始 transform
    await nextTick()
    cacheInitialTransforms()
    // 默认保持 data-motion-base-visibility="hidden" 的模块隐藏；事件触发显示暂预留
    applyMotionBaseVisibility()
  } catch (e) {
    errorMsg.value = `加载 SVG 失败: ${e.message}`
  } finally {
    loading.value = false
  }
}

function cacheInitialTransforms() {
  if (!svgContainer.value) return
  initialTransforms.clear()
  const els = svgContainer.value.querySelectorAll('[id]')
  for (const el of els) {
    const id = el.getAttribute('id')
    if (!id) continue
    // 只缓存 CSS 内联 transform，避免把 SVG 属性 transform 再写一遍导致画布错乱
    initialTransforms.set(id, el.style.transform || '')
  }
}

// 默认隐藏 data-motion-base-visibility="hidden" 的模块（如 Group1_POD / CST_TOPVIEW）
// 事件触发后再显示：暂预留，不在此处自动 reveal
function applyMotionBaseVisibility() {
  if (!svgContainer.value) return
  const hiddenEls = svgContainer.value.querySelectorAll('[data-motion-base-visibility="hidden"]')
  for (const el of hiddenEls) {
    el.setAttribute('visibility', 'hidden')
    el.style.visibility = 'hidden'
  }
}

// === Motion 数据计算 ===
const isMotionFormat = computed(() => {
  return props.motionConfig && props.motionConfig.schema_version
})

const motions = computed(() => {
  if (!isMotionFormat.value) return []
  return props.motionConfig.motions || []
})

const parts = computed(() => {
  if (!isMotionFormat.value) return []
  return props.motionConfig.parts || []
})

// 提取所有 step 名称
const stepList = computed(() => {
  return motions.value.map(m => m.step).filter(Boolean)
})

const DEFAULT_PARAM_VALUES = {
  BATCH_ID: '2312432141',
  LOT_ID: 'N1234',
  Qty: '25',
  RunMode: 'PR_RUN',
  RECIPE1: 'ALC12',
  PORT: '1',
  SLOT: '1',
  CHAMBER: 'E',
  SMIFPORTID: '1',
}

const paramKeys = computed(() => Object.keys(DEFAULT_PARAM_VALUES))

watch(paramKeys, (keys) => {
  for (const k of keys) {
    if (!(k in paramValues.value)) {
      paramValues.value[k] = DEFAULT_PARAM_VALUES[k] ?? ''
    }
  }
}, { immediate: true })

// === 触发事件 ===
async function triggerStep(stepName) {
  if (stepPlaying) logEvent(stepName, '已排队，等待上一个事件播完', 'info')
  const run = async () => {
    stepPlaying = true
    try {
      await playQueuedStep(stepName)
    } catch (e) {
      logEvent(stepName, e?.message || '播放失败', 'error')
    } finally {
      stepPlaying = false
    }
  }
  stepPlayQueue = stepPlayQueue.then(run, run)
  await stepPlayQueue
}

async function playQueuedStep(stepName) {
  // 填伸缩量参数：prefix 为空填放片侧 ext 系，'pk_' 填取还片侧；rdx/rdy 为 root 版（晶圆同步用）
  const fillExtend = (params, v, prefix = '') => {
    if (!v) return
    params[`${prefix}ext_dx`] = v.dx
    params[`${prefix}ext_dy`] = v.dy
    params[`${prefix}ret_dx`] = -v.dx
    params[`${prefix}ret_dy`] = -v.dy
    params[`${prefix}ext_rdx`] = v.rdx
    params[`${prefix}ext_rdy`] = v.rdy
    params[`${prefix}ret_rdx`] = -v.rdx
    params[`${prefix}ret_rdy`] = -v.rdy
    // 伸缩臂杆参数（与 deriver fillExtendParams 对齐）：伸出 scale_y 拉长 + offset_y=+e/2；收回反向
    params[`${prefix}link_ext_sy`] = v.link_sy ?? 1
    params[`${prefix}link_ext_oy`] = +((v.e || 0) / 2).toFixed(2)
    params[`${prefix}link_ret_sy`] = 1
    params[`${prefix}link_ret_oy`] = -(+((v.e || 0) / 2).toFixed(2))
  }
  const motion = motions.value.find(m => m.step === stepName)
  if (!motion) {
    logEvent(stepName, '未找到 step', 'error')
    return
  }

  if (stepName === 'BATCH_INFO_FROM_ECUI') {
    const lotId = String(paramValues.value.LOT_ID || '').trim()
    if (lotId) {
      lotRegistry.set(lotId, {
        PORT: paramValues.value.PORT,
        BATCH_ID: paramValues.value.BATCH_ID,
        Qty: paramValues.value.Qty,
        RunMode: paramValues.value.RunMode,
        RECIPE1: paramValues.value.RECIPE1,
      })
      logEvent(stepName, `登记 LOT_ID=${lotId} → PORT=${paramValues.value.PORT || '?'}`, 'info')
    }
  }

  const { params, matchedBy, lotId, carrier, slot } = enrichMotionParams(paramValues.value, lotRegistry)

  if (!evalWhen(motion.when, params)) {
    logEvent(stepName, `未命中 step.when: ${motion.when || 'true'}`, 'warn')
    return
  }

  if (stepName === 'CHAMBER_PS') {
    if (matchedBy !== 'LOT_ID' || !carrier) {
      logEvent(stepName, `未找到 LOT_ID=${lotId || '?'} 的载具映射，请先触发 BATCH_INFO_FROM_ECUI`, 'warn')
      return
    }
    const chamber = String(params.CHAMBER || '').trim()
    const waferId = `${carrier}${slot || '1'}`
    const prev = waferPosRegistry.get(waferPosKey(lotId, slot))
    const fromChamber = String(prev?.chamber || '').trim()
    let fromArm = fromChamber ? findArmByPos(fromChamber) : findArmByPos(carrier)
    if (fromChamber && !fromArm) {
      logEvent(stepName, `未在 arm_chamber_angles 中找到上次腔体 ${fromChamber}`, 'warn')
      return
    }
    let toArm = findArmByPos(chamber)
    if (fromArm && armAngleFor(fromArm, chamber) != null) toArm = fromArm
    if (!fromArm) fromArm = toArm
    const toAngle = armAngleFor(toArm, chamber)
    if (!chamber || !toArm) {
      logEvent(stepName, `未在 arm_chamber_angles 中找到位置 ${chamber || '?'}`, 'warn')
      return
    }
    if (toAngle == null) {
      logEvent(stepName, `未配置 ${toArm} 到腔体 ${chamber} 的角度`, 'warn')
      return
    }
    const pickupPart = armChuckPart(fromArm)
    const dropPart = armChuckPart(toArm)
    const crossArm = Boolean(fromArm && toArm && fromArm !== toArm)
    params.from_arm = fromArm
    params.to_arm = toArm
    params.arm = toArm
    params.ARM = toArm
    params.pickup_part = pickupPart
    params.drop_part = dropPart
    params.pickup_link = armLinkPart(fromArm)
    params.drop_link = armLinkPart(toArm)
    params.cross_arm = crossArm
    params.has_entered_chamber = Boolean(fromChamber)
    if (fromChamber) {
      const fromAngle = armAngleFor(fromArm, fromChamber)
      if (fromAngle == null) {
        logEvent(stepName, `未配置 ${fromArm} 到上次腔体 ${fromChamber} 的角度`, 'warn')
        return
      }
      params.from_chamber = fromChamber
      params.from_angle = fromAngle
      params.from_part = `CH_${fromChamber}`
      fillExtend(params, computeExtendVec(props.motionConfig?.ext, fromArm, fromChamber, fromAngle), 'pk_')
    } else {
      const pickupAngle = armAngleFor(fromArm, carrier)
      if (pickupAngle == null) {
        logEvent(stepName, `未配置 ${fromArm} 到 ${carrier || '?'} 的角度`, 'warn')
        return
      }
      params.from_chamber = ''
      params.from_angle = pickupAngle
      params.from_part = pickupPart
      fillExtend(params, computeExtendVec(props.motionConfig?.ext, fromArm, carrier, pickupAngle), 'pk_')
    }
    if (crossArm) {
      const crossFrom = armAngleFor(fromArm, 'Cross')
      const crossTo = armAngleFor(toArm, 'Cross')
      if (crossFrom == null) {
        logEvent(stepName, `未配置 ${fromArm} 的 Cross 角度`, 'warn')
        return
      }
      if (crossTo == null) {
        logEvent(stepName, `未配置 ${toArm} 的 Cross 角度`, 'warn')
        return
      }
      params.cross_angle_from = crossFrom
      params.cross_angle_to = crossTo
      logEvent(stepName, `跨臂交接: ${waferId} ${fromArm} → ${toArm}（Cross ${crossFrom}/${crossTo}，LOT_ID=${lotId}）`, 'info')
    } else if (fromChamber) {
      logEvent(stepName, `转腔: ${waferId} CH_${fromChamber} → ${pickupPart} → CH_${chamber}（${toArm}，LOT_ID=${lotId}）`, 'info')
    } else {
      logEvent(stepName, `进腔: ${waferId} ${carrier} → ${pickupPart} → CH_${chamber}（${toArm}，LOT_ID=${lotId}）`, 'info')
    }
    params.to_angle = toAngle
    const extVec = computeExtendVec(props.motionConfig?.ext, toArm, chamber, toAngle)
    if (extVec) {
      fillExtend(params, extVec)
      logEvent(stepName, `R轴伸缩: ${toArm} CH_${chamber} θ=${toAngle} ext=(${extVec.dx}, ${extVec.dy})`, 'info')
    } else {
      logEvent(stepName, `R轴伸缩参数缺失: arm=${toArm} ch=${chamber} θ=${toAngle} geo=${props.motionConfig?.ext?.extend_geometry ? 'ok' : 'missing'}`, 'warn')
    }
  }

  if (stepName === 'WAFER_PROCESS_COMPLETE') {
    if (matchedBy !== 'LOT_ID' || !carrier) {
      logEvent(stepName, `未找到 LOT_ID=${lotId || '?'} 的载具映射，请先触发 BATCH_INFO_FROM_ECUI`, 'warn')
      return
    }
    const prev = waferPosRegistry.get(waferPosKey(lotId, slot))
    const fromChamber = String(prev?.chamber || params.CHAMBER || '').trim()
    if (!fromChamber) {
      logEvent(stepName, `未找到 LOT_ID=${lotId} SLOT=${slot || '1'} 的上次腔体，请先触发 CHAMBER_PS`, 'warn')
      return
    }
    // 取片臂 = 实际服务该腔体的臂（CH_1-4 → ARM_2，A-F → ARM_1）；还片臂 = 服务载具的臂（LLA/LLB → ARM_1）
    const chamberArm = findArmByPos(fromChamber)
    if (!chamberArm) {
      logEvent(stepName, `未在 arm_chamber_angles 中找到上次腔体 ${fromChamber}`, 'warn')
      return
    }
    const returnArm = findArmByPos(carrier)
    if (!returnArm) {
      logEvent(stepName, `未在 arm_chamber_angles 中找到载具 ${carrier}`, 'warn')
      return
    }
    const fromAngle = armAngleFor(chamberArm, fromChamber)
    if (fromAngle == null) {
      logEvent(stepName, `未配置 ${chamberArm} 到上次腔体 ${fromChamber} 的角度`, 'warn')
      return
    }
    const carrierAngle = armAngleFor(returnArm, carrier)
    if (carrierAngle == null) {
      logEvent(stepName, `未配置 ${returnArm} 到 ${carrier} 的角度`, 'warn')
      return
    }
    const crossArm = chamberArm !== returnArm
    params.ARM = returnArm
    params.arm = returnArm
    params.from_arm = chamberArm
    params.to_arm = returnArm
    params.from_chamber = fromChamber
    params.from_angle = fromAngle
    params.carrier_angle = carrierAngle
    params.to_angle = carrierAngle
    params.pickup_part = armChuckPart(chamberArm)
    params.drop_part = armChuckPart(returnArm)
    params.pickup_link = armLinkPart(chamberArm)
    params.drop_link = armLinkPart(returnArm)
    params.cross_arm = crossArm
    if (crossArm) {
      const crossFrom = armAngleFor(chamberArm, 'Cross')
      const crossTo = armAngleFor(returnArm, 'Cross')
      if (crossFrom == null) {
        logEvent(stepName, `未配置 ${chamberArm} 的 Cross 角度`, 'warn')
        return
      }
      if (crossTo == null) {
        logEvent(stepName, `未配置 ${returnArm} 的 Cross 角度`, 'warn')
        return
      }
      params.cross_angle_from = crossFrom
      params.cross_angle_to = crossTo
    }
    // 腔体取片侧伸缩量：blade 伸出进源腔（ext）/带片收回（ret）
    fillExtend(params, computeExtendVec(props.motionConfig?.ext, chamberArm, fromChamber, fromAngle))
    // cassette 还片侧伸缩量：blade 伸出到槽位（pk_ext）/抽刀（pk_ret）
    fillExtend(params, computeExtendVec(props.motionConfig?.ext, returnArm, carrier, carrierAngle), 'pk_')
    logEvent(stepName, crossArm
      ? `回载具: ${carrier}${slot || '1'} CH_${fromChamber} → ${params.pickup_part} → Cross → ${params.drop_part} → ${carrier}（${chamberArm}→${returnArm}，LOT_ID=${lotId}）`
      : `回载具: ${carrier}${slot || '1'} CH_${fromChamber} → ${params.pickup_part} → ${carrier}（${chamberArm}，LOT_ID=${lotId}）`, 'info')
  }

  const matchedRules = []
  for (const rule of motion.rules || []) {
    if (!evalWhen(rule.when, params)) continue
    matchedRules.push(resolveMotionRule(rule, params))
  }
  // 参数未填导致 rule.when 全不命中时，回退为配置页行为：播该 step 全部 rules
  if (matchedRules.length === 0) {
    for (const rule of motion.rules || []) {
      matchedRules.push(resolveMotionRule(rule, params))
    }
  }

  if (matchedRules.length === 0) {
    logEvent(stepName, '无匹配 rule', 'warn')
    return
  }

  const result = await playMotion({
    container: svgContainer.value,
    rules: matchedRules,
    reset: false,
    onWarn: (msg) => logEvent(stepName, msg, 'warn'),
  })

  if (!result.ok) {
    const reasonMap = {
      container: 'SVG 容器尚未渲染',
      svg: 'SVG 内容尚未加载',
      ctm: 'SVG 坐标系不可用',
      'ctm-scale': 'SVG 当前不可见',
      'no-rules': '无匹配 rule',
    }
    logEvent(stepName, reasonMap[result.reason] || '播放失败', 'warn')
    return
  }

  if (result.playedPids.size === 0 && !result.hasText) {
    logEvent(stepName, '动作中引用的部件未在 SVG 中找到', 'warn')
    return
  }

  for (const rule of matchedRules) {
    const targetId = rule.target_part_id || motion.target_part_id
    const actions = rule.actions || []
    logEvent(stepName, `命中: ${motion.when || rule.when || 'true'} → ${targetId || '文本'} ${actions.length}个动作`, 'success')
  }

  if (stepName === 'CHAMBER_PS') {
    const chamber = String(params.CHAMBER || '').trim()
    if (lotId && chamber) {
      waferPosRegistry.set(waferPosKey(lotId, slot), { chamber })
      logEvent(stepName, `登记晶圆位置: LOT_ID=${lotId} SLOT=${slot || '1'} → CH_${chamber}`, 'info')
    }
  }

  if (stepName === 'WAFER_PROCESS_COMPLETE') {
    if (lotId) {
      waferPosRegistry.delete(waferPosKey(lotId, slot))
      logEvent(stepName, `晶圆回槽: LOT_ID=${lotId} SLOT=${slot || '1'} → ${carrier}${slot || '1'}`, 'info')
    }
  }
}

// === 重置 ===
function resetAll(options = {}) {
  if (!svgContainer.value) return
  svgContainer.value.querySelectorAll('[data-motion-text]').forEach(el => el.remove())
  for (const [id, transform] of initialTransforms) {
    const el = svgContainer.value.querySelector(`#${id}`)
    if (el) {
      el.style.transform = transform || ''
      el.style.transformOrigin = ''
      el.style.transformBox = ''
      el.style.opacity = ''
      el.style.transition = ''
      el.style.visibility = ''
      el.removeAttribute('visibility')
      delete el.dataset.transform
    }
  }
  applyMotionBaseVisibility()
  waferPosRegistry.clear()
  if (!options.silent) logEvent('初始化', '所有部件已重置', 'info')
}

// === 事件日志 ===
function logEvent(step, msg, type = 'info') {
  const time = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  eventLog.value.unshift({ time, step, msg, type })
  if (eventLog.value.length > 50) eventLog.value.pop()
}

// === 监听 ===
watch(() => props.svgUrl, () => {
  if (props.svgUrl) loadSvg()
})

watch(() => props.motionConfig, () => {
  // 配置变更时重置
  resetAll()
  eventLog.value = []
}, { deep: true })

onMounted(() => {
  if (props.svgUrl) loadSvg()
})
</script>

<template>
  <div class="motion-preview">
    <div class="preview-body">
      <!-- 左侧：SVG 预览区 -->
      <div class="svg-area">
        <div v-if="errorMsg" class="error-msg">⚠️ {{ errorMsg }}</div>
        <div
          ref="svgContainer"
          class="svg-container"
          v-html="svgInline"
        ></div>
        <div v-if="!svgUrl" class="empty-hint">
          请先上传 SVG 文件
        </div>
      </div>

      <!-- 中列：初始化 + 参数 + 事件触发 -->
      <div class="control-panel">
        <div class="init-section">
          <button class="btn-small btn-reset-canvas" @click="resetAll" :disabled="!svgInline">初始化</button>
        </div>
        <div v-if="paramKeys.length > 0" class="param-section">
          <h4>参数</h4>
          <div class="param-grid">
            <div v-for="key in paramKeys" :key="key" class="param-item">
              <label>{{ key }}</label>
              <input
                v-model="paramValues[key]"
                :placeholder="`如: 1`"
                @keyup.enter="paramValues[key] = paramValues[key]"
              />
            </div>
          </div>
        </div>
        <div class="trigger-section">
          <h4>事件触发</h4>
          <div v-if="stepList.length === 0" class="empty-row">无可用 step</div>
          <div v-else class="trigger-grid">
            <button
              v-for="step in stepList"
              :key="step"
              class="trigger-btn"
              @click="triggerStep(step)"
            >
              <div class="btn-step">{{ step }}</div>
              <div class="btn-desc">
                {{ motions.find(m => m.step === step)?.rules?.length || 0 }} 条规则
              </div>
            </button>
          </div>
        </div>
      </div>

      <!-- 右列：事件日志 -->
      <div class="log-panel">
        <div class="log-section">
          <h4>事件日志 ({{ eventLog.length }})</h4>
          <div v-if="eventLog.length === 0" class="empty-row">暂无事件</div>
          <div v-else class="log-list">
            <div
              v-for="(log, idx) in eventLog"
              :key="idx"
              class="log-item"
              :class="log.type"
            >
              <span class="log-time">{{ log.time }}</span>
              <span class="log-step">{{ log.step }}</span>
              <span class="log-msg">{{ log.msg }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.motion-preview {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--panel);
  border-radius: 8px;
  overflow: hidden;
}

.btn-small {
  width: 100%;
  background: var(--panel-2);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
}
.btn-small:hover { border-color: var(--accent); }
.btn-small:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-reset-canvas {
  background: rgba(59, 130, 246, 0.12);
  border-color: rgba(59, 130, 246, 0.4);
}
.btn-reset-canvas:hover {
  border-color: rgba(59, 130, 246, 0.8);
  color: #60a5fa;
}

.preview-body {
  display: grid;
  grid-template-columns: 1fr 400px 360px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
@media (max-width: 1280px) {
  .preview-body { grid-template-columns: 1fr 360px 320px; }
}

.svg-area {
  background: var(--bg);
  display: flex;
  align-items: flex-start;
  justify-content: center;
  overflow: auto;
  position: relative;
  padding: 8px 16px 16px;
}
.svg-container {
  max-width: 100%;
  max-height: 100%;
}
.svg-container :deep(svg) {
  max-width: 100%;
  height: auto;
  display: block;
}
.error-msg {
  color: var(--red);
  font-size: 13px;
  padding: 8px 12px;
  background: rgba(244, 67, 54, 0.1);
  border-radius: 4px;
  margin-bottom: 8px;
}
.empty-hint {
  color: var(--text-dim);
  font-size: 14px;
  font-style: italic;
}

.control-panel,
.log-panel {
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--panel-2);
  min-width: 0;
}
.control-panel {
  overflow-y: auto;
}
.control-panel h4,
.log-panel h4 {
  font-size: 12px;
  color: var(--accent);
  margin: 0 0 8px 0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.init-section,
.param-section,
.trigger-section,
.log-section {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.log-section {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-bottom: none;
}

.param-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.param-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.param-item label {
  font-size: 12px;
  color: var(--text-dim);
  min-width: 70px;
  flex-shrink: 0;
}
.param-item input {
  flex: 1;
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 4px 8px;
  border-radius: 3px;
  font-size: 12px;
  outline: none;
  min-width: 0;
}
.param-item input:focus { border-color: var(--accent); }

.trigger-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.trigger-btn {
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 8px;
  cursor: pointer;
  text-align: center;
  transition: all 0.15s;
}
.trigger-btn:hover {
  background: var(--panel);
  border-color: var(--accent);
}
.btn-step {
  font-weight: 600;
  color: var(--yellow);
  font-size: 11px;
}
.btn-desc {
  color: var(--text-dim);
  font-size: 10px;
  margin-top: 2px;
}

.log-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.log-item {
  display: flex;
  gap: 6px;
  padding: 4px 6px;
  border-bottom: 1px solid var(--border);
  font-size: 11px;
  align-items: center;
}
.log-item:last-child { border-bottom: none; }
.log-item.success { background: rgba(34, 197, 94, 0.05); }
.log-item.error { background: rgba(244, 67, 54, 0.05); }
.log-item.warn { background: rgba(245, 158, 11, 0.05); }
.log-time {
  color: var(--text-dim);
  font-family: monospace;
  flex-shrink: 0;
}
.log-step {
  color: var(--yellow);
  font-weight: 600;
  flex-shrink: 0;
  min-width: 80px;
}
.log-msg {
  color: var(--text);
  flex: 1;
  min-width: 0;
  word-break: break-all;
}

.empty-row {
  color: var(--text-dim);
  font-size: 11px;
  font-style: italic;
  text-align: center;
  padding: 8px;
}
</style>
