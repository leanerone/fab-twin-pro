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
import { evalWhen, resolveMotionRule, enrichMotionParams, extractParamKeys } from './useExprEval.motion'
import { computeExtendVec } from './derivers/amatMetsput'
import { getMotionDeriver } from './derivers'
// P3-A：调试页与机台详情页统一使用「逐帧同步圆弧」单引擎（原 .motion.js 的事后屏幕测量补偿已废弃）
import { playMotion, resetMotionState, invalidateMotionGeometry } from './useMotionPlayback'
import { scopeSvgPaintIds } from '../../utils/svgPaintScope'

const props = defineProps({
  /** SVG 文件 URL */
  svgUrl: { type: String, default: '' },
  /** Motion JSON 配置对象 */
  motionConfig: { type: Object, default: null },
  /** 动画调试页接收的实时 raw_event；每次事件由父组件生成新对象 */
  realtimeEvent: { type: Object, default: null },
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

function normalizeChamber(value) {
  const s = String(value ?? '').trim()
  const m = s.match(/^CHAMBER[_-]?(.+)$/i)
  return (m ? m[1] : s).toUpperCase()
}

function toMotionPayload(event) {
  const src = { ...(event?.payload || {}), ...event }
  const pick = (...keys) => {
    for (const key of keys) {
      const value = src[key]
      if (value !== undefined && value !== null && value !== '' && value !== 'NULL') return value
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
    // 等待 DOM 更新后丢弃旧几何缓存（新 SVG 元素重新测量），并按默认状态隐藏模块
    await nextTick()
    invalidateMotionGeometry(svgContainer.value)
    // 默认保持 data-motion-base-visibility="hidden" 的模块隐藏；事件触发显示暂预留
    applyMotionBaseVisibility()
    refreshSvgIds()
  } catch (e) {
    errorMsg.value = `加载 SVG 失败: ${e.message}`
  } finally {
    loading.value = false
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

// 参数面板只显示当前 Motion JSON 真正用到的键：ext.param_defaults + 所有 when 表达式引用的 params.xxx
// （固定清单会带出别的机型的参数，例如 OXE 没有 CHAMBER/'E'、却需要 SM01~SM25）
const paramDefaults = computed(() => {
  const cfg = props.motionConfig || {}
  return { ...(cfg.param_defaults || {}), ...(cfg.ext?.param_defaults || {}) }
})

// 与机台详情同一条链路：ext.deriver 指定业务推导器（oxe / amat_metsput / podopener）
const ext = computed(() => props.motionConfig?.ext || {})
const deriverName = computed(() => ext.value.deriver || '')

const PARAM_ORDER = ['LOT_ID', 'PORT', 'SLOT', 'CHAMBER', 'BATCH_ID', 'Qty', 'RunMode', 'RECIPE1']

// deriver 内部派生参数：由推导器按事件算出来，不需要用户手填
const DERIVER_INTERNAL_KEYS = new Set(['has_entered_chamber', 'cross_arm', 'cycle',
  'pod_shell', 'POD', 'POD_LK', 'CST', 'DOOR', 'MAP', 'SMIF_C', 'PORT_C', 'SLOT_ANCHOR',
  'CH_C', 'WAFER_CH', 'CH_RUN', 'CH_ALARM', 'CH_UNLOAD', 'ARM_HOME', 'ARM_PORT_ANGLE',
  'ARM_CH_ANGLE', 'ARM_PA_ANGLE', 'ARM_EXTEND_OUT', 'ARM_EXTEND_PORT', 'ARM_EXTEND_PA',
  'ARM_EXTEND_CH', 'DONE_COUNT', 'ALARM_PORT', 'ALARM_COUNT', 'AL1', 'AL2', 'AL3',
  'ARM_T1_PORT', 'ARM_T2_PORT', 'ARM_T3_PORT', 'ARM_T1_PA', 'ARM_T2_PA', 'ARM_T3_PA',
  'ARM_T1_CH', 'ARM_T2_CH', 'ARM_T3_CH'])
// SM01..SM25 = deriver 展开的逐槽 mapping 字符（只在 when 里用），同样不展示
const DERIVER_INTERNAL_RE = /^SM\d{2}$/
// 业务输入白名单：其余键即使出现在 when 里也由 deriver 产出
const USER_INPUT_KEYS = new Set(['LOT_ID', 'PORT', 'SLOT', 'CHAMBER', 'BATCH_ID', 'Qty',
  'RunMode', 'RECIPE1', 'SMIFPORTID'])

const paramKeys = computed(() => {
  const whens = []
  for (const m of motions.value) {
    if (m.when) whens.push(m.when)
    for (const r of (m.rules || [])) if (r.when) whens.push(r.when)
  }
  const keys = new Set(Object.keys(paramDefaults.value))
  for (const k of extractParamKeys(whens)) keys.add(k)
  let list = Array.from(keys)
  // 有 deriver 的机型：只保留业务输入，避免 OXE 面板出现 SM01~SM25 / ARM_* 等 30+ 个手填框；
  // CHAMBER 即使 when 没引用也保留（OXE 靠它把片送进 CH_A/B/C 不同腔，需要手动指定）
  if (deriverName.value) {
    list = Array.from(new Set([...list, 'CHAMBER'])).filter(k => USER_INPUT_KEYS.has(k)
      && !DERIVER_INTERNAL_KEYS.has(k) && !DERIVER_INTERNAL_RE.test(k))
  }
  return list.sort((a, b) => {
    const ia = PARAM_ORDER.indexOf(a)
    const ib = PARAM_ORDER.indexOf(b)
    if (ia !== -1 || ib !== -1) return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
    return String(a).localeCompare(String(b))
  })
})

watch(paramKeys, (keys) => {
  for (const k of keys) {
    if (!(k in paramValues.value)) {
      // OXE 等有 deriver 的机型腔体编号是 A/B/C，不是 AMAT 的 E
      const fallback = k === 'CHAMBER' && deriverName.value ? 'A' : DEFAULT_PARAM_VALUES[k]
      paramValues.value[k] = paramDefaults.value[k] ?? fallback ?? ''
    }
  }
}, { immediate: true })

// === 触发事件 ===
async function triggerStep(stepName, eventPayload = null) {
  if (stepPlaying) logEvent(stepName, '已排队，等待上一个事件播完', 'info')
  const run = async () => {
    stepPlaying = true
    try {
      await playQueuedStep(stepName, eventPayload)
    } catch (e) {
      logEvent(stepName, e?.message || '播放失败', 'error')
    } finally {
      stepPlaying = false
    }
  }
  stepPlayQueue = stepPlayQueue.then(run, run)
  await stepPlayQueue
}

async function playQueuedStep(stepName, eventPayload = null) {
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

  // 与机台详情同一条参数链路：有 ext.deriver 的机型由推导器按事件产出参数
  // （ARM_T1/T2/T3、ARM_PORT_ANGLE、部件 id 占位符等）。缺这一步时参数为空，
  // rule.when 全不命中、角度占位符解析成 0，点了事件动画也不会动。
  const deriver = getMotionDeriver(deriverName.value)
  const panelPayload = Object.fromEntries(
    paramKeys.value.map(k => [k, paramValues.value[k] ?? ''])
  )
  const payload = eventPayload ? { ...panelPayload, ...eventPayload } : panelPayload

  if (!deriver && stepName === 'BATCH_INFO_FROM_ECUI') {
    const lotId = String(payload.LOT_ID || '').trim()
    if (lotId) {
      lotRegistry.set(lotId, {
        PORT: payload.PORT,
        BATCH_ID: payload.BATCH_ID,
        Qty: payload.Qty,
        RunMode: payload.RunMode,
        RECIPE1: payload.RECIPE1,
      })
      logEvent(stepName, `登记 LOT_ID=${lotId} → PORT=${payload.PORT || '?'}`, 'info')
    }
  }

  let params
  let info = {}
  let matchedBy = 'PORT'
  let lotId = ''
  let carrier = ''
  let slot = ''
  if (deriver) {
    const r = deriver.derive(motion.step, payload, { motionConfig: props.motionConfig, ext: ext.value })
    if (!r?.ok) {
      logEvent(stepName, r?.warn || '参数推导失败', 'warn')
      return
    }
    params = r.params
    info = r.info || {}
    lotId = String(params.LOT_ID || '').trim()
    slot = params.SLOT || '1'
  } else {
    ;({ params, matchedBy, lotId, carrier, slot } = enrichMotionParams(payload, lotRegistry))
  }

  if (!evalWhen(motion.when, params)) {
    logEvent(stepName, `未命中 step.when: ${motion.when || 'true'}`, 'warn')
    return
  }

  if (!deriver && stepName === 'CHAMBER_PS') {
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

  if (!deriver && stepName === 'WAFER_PROCESS_COMPLETE') {
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
    params,
    reset: false,
    partAliases: props.motionConfig?.ext?.part_aliases || {},
    offsetMode: ext.value.offset_mode === 'absolute' ? 'absolute' : 'relative',
    onWarn: (msg) => logEvent(stepName, msg, 'warn'),
  })

  if (!result.ok) {
    const reasonMap = {
      container: 'SVG 容器尚未渲染',
      svg: 'SVG 内容尚未加载',
      geometry: 'SVG 几何测量失败（可能尚未渲染）',
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

  // deriver 业务状态推进（lastPort 记忆 / 槽位状态机），与机台详情一致
  if (deriver) deriver.commit(motion.step, params, info)

  if (!deriver && stepName === 'CHAMBER_PS') {
    const chamber = String(params.CHAMBER || '').trim()
    if (lotId && chamber) {
      waferPosRegistry.set(waferPosKey(lotId, slot), { chamber })
      logEvent(stepName, `登记晶圆位置: LOT_ID=${lotId} SLOT=${slot || '1'} → CH_${chamber}`, 'info')
    }
  }

  if (!deriver && stepName === 'WAFER_PROCESS_COMPLETE') {
    if (lotId) {
      waferPosRegistry.delete(waferPosKey(lotId, slot))
      logEvent(stepName, `晶圆回槽: LOT_ID=${lotId} SLOT=${slot || '1'} → ${carrier}${slot || '1'}`, 'info')
    }
  }
}

// === 重置 ===
function resetAll(options = {}) {
  if (!svgContainer.value) return
  // 引擎级复位：清文字、清全部播放状态与内联样式、恢复 data-motion-base-visibility
  resetMotionState(svgContainer.value)
  invalidateMotionGeometry(svgContainer.value)
  waferPosRegistry.clear()
  getMotionDeriver(deriverName.value)?.reset()
  if (!options.silent) logEvent('初始化', '所有部件已重置', 'info')
}

// === 事件日志 ===
function logEvent(step, msg, type = 'info') {
  const time = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  eventLog.value.unshift({ time, step, msg, type })
  if (eventLog.value.length > 50) eventLog.value.pop()
}

// === 部件检查（调试用：点选部件，看它叫什么、当前变换、被哪些规则引用） ===
const inspectOn = ref(false)
const selectedPartId = ref('')
const partProbe = ref(null)
const svgIds = ref([])
const missingTargets = ref([])

// 规则索引：target_part_id → [{step, phase, when, types}]
const targetRules = computed(() => {
  const map = {}
  for (const m of motions.value) {
    for (const r of (m.rules || [])) {
      const tid = r.target_part_id || m.target_part_id
      if (!tid) continue
      if (!map[tid]) map[tid] = []
      map[tid].push({
        step: m.step,
        phase: r.phase,
        when: r.when || '',
        types: (r.actions || []).map(a => a.type).join('/'),
      })
    }
  }
  return map
})
const targetIds = computed(() => Object.keys(targetRules.value))
// 部件清单 = 规则引用 ∪ SVG 里有 data-pid 的部件，这样即使机型没配 Motion JSON 也能提取部件
const inspIds = computed(() => {
  const set = new Set([...targetIds.value, ...svgIds.value])
  return Array.from(set).sort()
})
const partMeta = computed(() => {
  const map = {}
  for (const p of parts.value) if (p?.part_id) map[p.part_id] = p
  return map
})

// SVG 实际存在的 id ↔ 规则引用对照，直接暴露"名字写错了"的部件
function refreshSvgIds() {
  const root = svgContainer.value?.querySelector('svg')
  if (!root) { svgIds.value = []; missingTargets.value = []; return }
  // 只取带 data-pid 的部件（排除渐变/滤镜等绘制资源 id）
  svgIds.value = [...root.querySelectorAll('[data-pid]')].map(el => el.id).filter(Boolean)
  const allIds = new Set([...root.querySelectorAll('[id]')].map(el => el.id))
  const validIds = new Set([...allIds, ...Object.keys(ext.value.part_aliases || {})])
  missingTargets.value = targetIds.value.filter(t => !t.includes('{') && !validIds.has(t))
}

function selectInspPart(id) {
  selectedPartId.value = id
  partProbe.value = null
  const root = svgContainer.value?.querySelector('svg')
  if (!root) return
  root.querySelectorAll('.mp-inspecting').forEach(el => el.classList.remove('mp-inspecting'))
  if (id.includes('{')) return
  const alias = ext.value.part_aliases?.[id]
  const candidates = Array.isArray(alias) ? alias : [alias || id]
  const targetId = candidates.find(t => typeof t === 'string' && t && !t.includes('{')) || id
  const el = root.querySelector(`[id="${String(targetId).replace(/"/g, '\\"')}"]`)
  if (!el) return
  el.classList.add('mp-inspecting')
  const cs = getComputedStyle(el)
  // 未施加过变换时 computed transform 是 'none'，直接 new DOMMatrix 会抛错
  const tf = cs.transform
  const m = tf && tf !== 'none' ? new DOMMatrix(tf) : null
  // 名称优先取 parts 元数据，其次 SVG 自身标注（data-name / <title>），最后留空
  const name = partMeta.value[id]?.part_name
    || el.getAttribute('data-name')
    || el.querySelector('title')?.textContent?.trim()
    || ''
  // 所属装配：父链上最近的两级带 id 的祖先，便于定位"这是哪个部件的子件"
  const chain = []
  let node = el.parentElement
  while (node && node.tagName && node.tagName.toLowerCase() !== 'svg') {
    const aid = node.getAttribute?.('id')
    if (aid) chain.unshift(aid)
    node = node.parentElement
  }
  partProbe.value = {
    id: targetId,
    name,
    type: partMeta.value[id]?.part_type || el.tagName.toLowerCase(),
    family: chain.join(' › ') || '根',
    visible: cs.visibility,
    rotate: m ? Math.round((Math.atan2(m.b, m.a) * 180) / Math.PI) : 0,
    tx: m ? Math.round(m.e) : 0,
    ty: m ? Math.round(m.f) : 0,
  }
}

function onSvgInspectClick(e) {
  if (!inspectOn.value) return
  const el = e.target?.closest?.('[id]')
  if (!el) return
  selectInspPart(el.id)
}

// === 监听 ===
watch(() => props.svgUrl, () => {
  if (props.svgUrl) loadSvg()
})

watch(() => props.motionConfig, () => {
  // 配置变更时重置
  resetAll()
  eventLog.value = []
  refreshSvgIds()
}, { deep: true })

watch(() => props.realtimeEvent, (event) => {
  if (!event) return
  let stepName = String(event.event_name || event.event_code || '').trim().toUpperCase()
  if (!stepName) return
  const alias = ext.value.event_aliases?.[stepName]
  if (alias) stepName = String(alias).toUpperCase()
  logEvent(stepName, `接收实时事件${event.raw_id ? ` #${event.raw_id}` : ''}`, 'info')
  triggerStep(stepName, toMotionPayload(event))
})

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
          :class="{ 'inspect-on': inspectOn }"
          v-html="svgInline"
          @click="onSvgInspectClick"
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

      <!-- 右列：部件检查 + 事件日志 -->
      <div class="log-panel">
        <div class="inspect-section">
          <h4>
            部件检查
            <label class="insp-toggle">
              <input type="checkbox" v-model="inspectOn" @change="!inspectOn && (selectedPartId = '')" />
              点选
            </label>
          </h4>
          <div v-if="missingTargets.length" class="miss-box">
            ⚠ 规则引用但 SVG 中不存在：{{ missingTargets.join('、') }}
          </div>
          <div class="insp-list">
            <div
              v-for="tid in inspIds"
              :key="tid"
              class="insp-item"
              :class="{
                active: tid === selectedPartId,
                miss: missingTargets.includes(tid),
                tpl: tid.includes('{'),
              }"
              @click="selectInspPart(tid)"
            >
              <span class="dot"></span>{{ tid }}
            </div>
            <div v-if="inspIds.length === 0" class="empty-row">无部件（SVG 未加载或无 data-pid）</div>
          </div>
          <div v-if="partProbe" class="insp-detail">
            <div class="insp-row"><span>名称</span>{{ partProbe.name || '—（无 parts 元数据）' }}</div>
            <div class="insp-row"><span>类型</span>{{ partProbe.type || '—' }}</div>
            <div class="insp-row"><span>所属</span>{{ partProbe.family }}</div>
            <div class="insp-row"><span>可见</span>{{ partProbe.visible === 'visible' ? '是' : '否' }}</div>
            <div class="insp-row"><span>旋转</span>{{ partProbe.rotate }}°</div>
            <div class="insp-row"><span>位移</span>x {{ partProbe.tx }} / y {{ partProbe.ty }}</div>
            <button class="btn-small" @click="selectInspPart(selectedPartId)">刷新状态</button>
          </div>
          <div v-else-if="selectedPartId" class="empty-row">
            模板部件，运行时按参数解析为具体 id
          </div>
          <div class="insp-rules-title">
            命中规则（{{ (targetRules[selectedPartId] || []).length }}）
          </div>
          <div class="insp-rules">
            <div v-for="(r, idx) in (targetRules[selectedPartId] || [])" :key="idx" class="insp-rule">
              <span class="ir-step">{{ r.step }}</span>
              <span class="ir-phase">P{{ r.phase }}</span>
              <span class="ir-actions">{{ r.types }}</span>
              <span v-if="r.when" class="ir-when">{{ r.when }}</span>
            </div>
            <div v-if="!(targetRules[selectedPartId] || []).length" class="empty-row">暂无规则</div>
          </div>
        </div>
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
/* === 部件检查 === */
.inspect-section {
  padding: 10px 16px 12px;
  border-bottom: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  max-height: 62%;
  overflow-y: auto;
}
.inspect-section h4 {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.insp-toggle {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: normal;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}
.miss-box {
  margin: 6px 0;
  padding: 5px 8px;
  border-radius: 4px;
  font-size: 11px;
  line-height: 1.5;
  color: #f87171;
  background: rgba(244, 67, 54, 0.1);
  border: 1px solid rgba(244, 67, 54, 0.35);
}
.insp-list {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 132px;
  overflow-y: auto;
}
.insp-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-family: monospace;
  color: var(--text-muted);
  cursor: pointer;
}
.insp-item:hover { background: var(--panel); }
.insp-item.active { background: rgba(245, 158, 11, 0.16); color: #fbbf24; }
.insp-item .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--green, #22c55e);
  flex: none;
}
.insp-item.miss { color: #f87171; }
.insp-item.miss .dot { background: #ef4444; }
.insp-item.tpl { font-style: italic; }
.insp-item.tpl .dot { background: var(--text-muted); }
.insp-detail {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border);
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.insp-row {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: var(--text);
}
.insp-row span {
  width: 34px;
  flex: none;
  color: var(--text-muted);
}
.insp-detail .btn-small { margin-top: 6px; }
.insp-rules-title {
  margin-top: 10px;
  font-size: 11px;
  color: var(--text-muted);
}
.insp-rules {
  margin-top: 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-height: 120px;
  overflow-y: auto;
}
.insp-rule {
  display: flex;
  gap: 6px;
  align-items: baseline;
  font-size: 10px;
  font-family: monospace;
  color: var(--text-muted);
  padding: 2px 4px;
  border-radius: 3px;
  background: var(--panel);
}
.insp-rule .ir-step { color: var(--text); }
.insp-rule .ir-phase { color: #60a5fa; }
.insp-rule .ir-when { color: #fbbf24; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.svg-container.inspect-on { cursor: crosshair; }
/* 点选模式下放开 SVG 内 pointer-events="none" 的装饰件，否则很多可见部件点不中；
   不可见参照框是 fill="none" stroke="none"，visiblePainted 不会命中，不影响遮挡判断 */
.svg-container.inspect-on :deep(svg *) { pointer-events: visiblePainted; }
.svg-container :deep(.mp-inspecting) {
  filter: drop-shadow(0 0 4px #f59e0b);
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
