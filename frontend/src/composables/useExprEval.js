/**
 * when 表达式求值器 + Motion 模板解析器
 *
 * 与模型组返回包 useExprEval.js 语义对齐，差异：
 * - PORT→carrier 映射、模板缺省值、部件别名全部从 Motion JSON 的 ext 配置节读取，
 *   不写死（ext.port_carrier_map / ext.param_defaults / ext.part_aliases）
 * - pickup_part / drop_part / 各角度参数由 deriver（motionDerivers/）填充进 params，
 *   本模块只负责通用模板替换，不含 AMAT 业务规则
 *
 * when 表达式：支持 == != > < >= <= && || !，字符串(单引号) 数字 true false
 */

/**
 * 从事件 payload 提取 params（保留下划线转驼峰兼容键）
 * chamber_id → 同时保留 chamber_id 和 chamber
 */
export function extractParams(payload) {
  const params = {}
  if (!payload || typeof payload !== 'object') return params
  for (const [k, v] of Object.entries(payload)) {
    params[k] = v
    let key = k.replace(/_id$/, '')
    key = key.replace(/_(\w)/g, (_, c) => c.toUpperCase())
    if (key !== k) params[key] = v
  }
  return params
}

/**
 * 安全求值表达式（白名单字符 + 危险关键字过滤）
 */
function safeEval(expr) {
  if (!/^[\w\s'".()==!<>&|+-]*$/.test(expr)) {
    console.warn('[useExprEval] 非法字符，拒绝求值:', expr)
    return false
  }
  if (/\b(?:function|constructor|prototype|__proto__|window|globalThis|eval|setTimeout|setInterval)\b/.test(expr)) {
    console.warn('[useExprEval] 检测到危险关键字，拒绝求值:', expr)
    return false
  }
  try {
    // eslint-disable-next-line no-new-func
    return Function(`"use strict"; return (${expr});`)()
  } catch (e) {
    console.warn('[useExprEval] 求值失败:', expr, e.message)
    return false
  }
}

/**
 * 求值 when 表达式
 * @param {string} when - 如 "params.CHAMBER == '1'"
 * @param {object} eventPayload - 事件 payload
 * @returns {boolean}
 */
export function evalWhen(when, eventPayload) {
  if (!when || when === 'true') return true
  const params = extractParams(eventPayload)
  let expr = when.replace(/params\.(\w+)/g, (_, key) => {
    const val = params[key]
    if (val === undefined || val === null) return 'false'
    if (typeof val === 'string') return `'${val}'`
    return String(val)
  })
  return safeEval(expr)
}

/**
 * 从 when 表达式中提取所有引用的 params 字段名
 */
export function extractParamKeys(whenList) {
  const keys = new Set()
  for (const when of whenList) {
    if (!when || when === 'true') continue
    const matches = when.matchAll(/params\.(\w+)/g)
    for (const m of matches) keys.add(m[1])
  }
  return Array.from(keys)
}

/* ------------------------------------------------------------------ */
/* Motion 模板解析（ext 注入，不写死）                                    */
/* ------------------------------------------------------------------ */

/**
 * PORT → carrier 映射（读 ext.port_carrier_map，如 {"1":"LLA","2":"LLB"}）
 */
export function portToCarrier(port, ext = {}) {
  const p = String(port ?? '').trim()
  const map = ext.port_carrier_map || {}
  return map[p] || ''
}

function readRegistryRecord(lotRegistry, lotId) {
  if (!lotId || !lotRegistry) return null
  if (typeof lotRegistry.get === 'function') return lotRegistry.get(lotId) || null
  return lotRegistry[lotId] || null
}

/**
 * 先用 LOT_ID 查 BATCH_INFO 登记的 PORT，查不到回退当前 PORT，得到 carrier。
 * @returns {{ params, matchedBy, lotId, carrier, slot }}
 */
export function enrichMotionParams(eventPayload, lotRegistry, ext = {}) {
  const params = { ...extractParams(eventPayload) }
  delete params.lot
  const lotId = String(params.LOT_ID || '').trim()
  const rec = readRegistryRecord(lotRegistry, lotId)
  let matchedBy = 'PORT'
  const currentPort = params.PORT
  if (rec && rec.PORT != null && String(rec.PORT).trim() !== '') {
    params.PORT = rec.PORT
    matchedBy = 'LOT_ID'
  } else if (currentPort != null && String(currentPort).trim() !== '') {
    params.PORT = currentPort
    matchedBy = 'PORT'
  }
  const carrier = portToCarrier(params.PORT, ext)
  if (carrier) params.carrier = carrier
  const defaults = ext.param_defaults || {}
  params.SLOT = (params.SLOT != null && params.SLOT !== '') ? params.SLOT : (defaults.SLOT ?? '1')
  return { params, matchedBy, lotId, carrier, slot: params.SLOT }
}

/**
 * 解析零件 ID 模板，如 {carrier}{SLOT} / CH_{CHAMBER} / {pickup_part}
 * 缺省值读 ext.param_defaults[key]，解析后再过 ext.part_aliases 别名表。
 */
export function resolvePartIdTemplate(partId, eventPayload, ext = {}) {
  if (!partId || typeof partId !== 'string') return partId || ''
  const params = extractParams(eventPayload)
  const defaults = ext.param_defaults || {}
  const resolved = partId.replace(/\{(\w+)\}/g, (match, key) => {
    let val = params[key]
    if (val === undefined || val === null || val === '') {
      // 大小写兼容：slot/SLOT、chamber/CHAMBER、arm/ARM
      const upper = key.toUpperCase()
      if (params[upper] !== undefined && params[upper] !== null && params[upper] !== '') val = params[upper]
    }
    if (val !== undefined && val !== null && val !== '') return String(val)
    if (key === 'carrier') return portToCarrier(params.PORT, ext) || defaults.carrier || match
    if (defaults[key] !== undefined) return String(defaults[key])
    return match
  })
  const aliases = ext.part_aliases || {}
  return aliases[resolved] || resolved
}

/**
 * 文本模板：先 params.KEY 替换，再 {KEY} 替换；缺省值读 ext.param_defaults
 */
export function resolveTextTemplate(text, eventPayload, ext = {}) {
  if (text == null) return ''
  const params = extractParams(eventPayload)
  const defaults = ext.param_defaults || {}
  let out = String(text)
  const keys = Object.keys(params).sort((a, b) => b.length - a.length)
  for (const key of keys) {
    const val = params[key]
    if (val === undefined || val === null || val === '') continue
    out = out.split(`params.${key}`).join(String(val))
  }
  return out.replace(/\{(\w+)\}/g, (match, key) => {
    let val = params[key]
    if (val === undefined || val === null || val === '') {
      const upper = key.toUpperCase()
      if (params[upper] !== undefined && params[upper] !== null && params[upper] !== '') val = params[upper]
    }
    if (val === undefined || val === null || val === '') val = defaults[key]
    if (val === undefined || val === null || val === '') return match
    return String(val)
  })
}

/**
 * 解析整条 motion rule：target_part_id / follow_part_id / to_part_id / 角度 token / 文本
 * 角度 token（角度值由 deriver 填入 params）：
 *   {CHAMBER}/{to_angle} → params.to_angle
 *   {carrier}            → params.carrier_angle，缺省回退 params.from_angle
 *   {from_chamber}/{from_angle} → params.from_angle
 *   {Cross}              → 目标臂是 to_arm 用 cross_angle_to，否则 cross_angle_from
 */
export function resolveMotionRule(rule, eventPayload, ext = {}) {
  if (!rule) return rule
  return {
    ...rule,
    target_part_id: resolvePartIdTemplate(rule.target_part_id, eventPayload, ext),
    actions: (Array.isArray(rule.actions) ? rule.actions : []).map((action) => {
      if (!action) return action
      const next = { ...action }
      if (next.follow_part_id) next.follow_part_id = resolvePartIdTemplate(next.follow_part_id, eventPayload, ext)
      if (next.to_part_id) next.to_part_id = resolvePartIdTemplate(next.to_part_id, eventPayload, ext)
      if (next.target_part_id) next.target_part_id = resolvePartIdTemplate(next.target_part_id, eventPayload, ext)
      if (next.type === 'rotate' || next.angle != null) {
        let raw = next.angle
        const token = typeof raw === 'string' ? raw.trim() : raw
        const params = extractParams(eventPayload)
        const useChamber = raw === '' || raw == null || token === '{CHAMBER}' || token === '{to_angle}'
        const useCarrier = token === '{carrier}'
        const useFromPos = token === '{from_chamber}' || token === '{from_angle}'
        const useCross = token === '{Cross}' || token === '{cross}'
        if (useChamber) {
          const toAngle = Number(params.to_angle)
          next.angle = Number.isFinite(toAngle) ? toAngle : 0
        } else if (useCarrier) {
          const carrierAngle = Number(params.carrier_angle)
          const fromAngle = Number(params.from_angle)
          next.angle = Number.isFinite(carrierAngle) ? carrierAngle : (Number.isFinite(fromAngle) ? fromAngle : 0)
        } else if (useFromPos) {
          const fromAngle = Number(params.from_angle)
          next.angle = Number.isFinite(fromAngle) ? fromAngle : 0
        } else if (useCross) {
          const targetArm = resolvePartIdTemplate(rule.target_part_id, eventPayload, ext)
          const crossTo = Number(params.cross_angle_to)
          const crossFrom = Number(params.cross_angle_from)
          if (targetArm && targetArm === params.to_arm && Number.isFinite(crossTo)) next.angle = crossTo
          else next.angle = Number.isFinite(crossFrom) ? crossFrom : (Number.isFinite(crossTo) ? crossTo : 0)
        } else {
          if (typeof raw === 'string') raw = resolvePartIdTemplate(raw, eventPayload, ext)
          const num = Number(raw)
          next.angle = Number.isFinite(num) ? num : 0
        }
      }
      if (next.type === 'text' && next.content != null) {
        next.content = resolveTextTemplate(next.content, eventPayload, ext)
      }
      return next
    }),
  }
}

export default {
  evalWhen,
  extractParamKeys,
  extractParams,
  portToCarrier,
  enrichMotionParams,
  resolvePartIdTemplate,
  resolveTextTemplate,
  resolveMotionRule,
}
