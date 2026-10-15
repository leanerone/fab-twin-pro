/**
 * when 表达式求值器
 * 用于通用 Motion JSON 中 motions[].when / rules[].when 条件表达式的求值
 *
 * 支持运算符：== != > < >= <= && || !
 * 支持值类型：字符串(单引号) 数字 true false
 * params 字段自动从 event payload 提取（下划线转驼峰）
 *
 * 示例：
 * evalWhen("params.CHAMBER == '1'", { CHAMBER: '1' }) → true
 * evalWhen("params.port == '2'", { port_id: '1' }) → false
 * evalWhen("true", {}) → true
 * evalWhen("params.LOT_ID && params.SLOT && params.CHAMBER", { LOT_ID: 'NPPNC', SLOT: 1, CHAMBER: 'C' }) → true
 */

/**
 * 从事件 payload 提取 params（下划线转驼峰）
 * chamber_id → chamber, port_id → port, wafer_id → wafer
 */
export function extractParams(payload) {
  const params = {}
  if (!payload || typeof payload !== 'object') return params
  for (const [k, v] of Object.entries(payload)) {
    params[k] = v
    // 兼容 chamber_id → chamber，同时保留 BATCH_ID 这类原始键
    let key = k.replace(/_id$/, '')
    key = key.replace(/_(\w)/g, (_, c) => c.toUpperCase())
    if (key !== k) params[key] = v
  }
  return params
}

/**
 * 安全求值表达式
 * 仅允许比较和逻辑运算，禁止函数调用和属性访问
 */
function safeEval(expr) {
  // 白名单字符：字母 数字 下划线 单引号 双引号 空格 和运算符
  if (!/^[\w\s'".()==!<>&|+-]*$/.test(expr)) {
    console.warn('[useExprEval] 非法字符，拒绝求值:', expr)
    return false
  }
  // 禁止函数调用
  if (/\b(?:function|constructor|prototype|__proto__|window|globalThis|eval|setTimeout|setInterval)\b/.test(expr)) {
    console.warn('[useExprEval] 检测到危险关键字，拒绝求值:', expr)
    return false
  }
  try {
    // 使用 Function 构造器（已过滤危险字符）
    // eslint-disable-next-line no-new-func
    return Function(`"use strict"; return (${expr});`)()
  } catch (e) {
    console.warn('[useExprEval] 求值失败:', expr, e.message)
    return false
  }
}

/**
 * 求值 when 表达式
 * @param {string} when - 条件表达式，如 "params.CHAMBER == '1'"
 * @param {object} eventPayload - 事件 payload，如 { chamber_id: '1', port_id: '2' }
 * @returns {boolean}
 */
export function evalWhen(when, eventPayload) {
  if (!when || when === 'true') return true
  const params = extractParams(eventPayload)
  // 替换 params.xxx 为实际值
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
 * 用于自动生成参数输入面板
 * @param {string[]} whenList - 多个 when 表达式
 * @returns {string[]} 去重的字段名列表
 */
export function extractParamKeys(whenList) {
  const keys = new Set()
  for (const when of whenList) {
    if (!when || when === 'true') continue
    const matches = when.matchAll(/params\.(\w+)/g)
    for (const m of matches) {
      keys.add(m[1])
    }
  }
  return Array.from(keys)
}

/**
 * PORT=1 → LLA（SMIF-1），PORT=2 → LLB（SMIF-2）
 */
export function portToCarrier(port) {
  const p = String(port ?? '').trim()
  if (p === '2') return 'LLB'
  if (p === '1') return 'LLA'
  return ''
}

function readRegistryRecord(lotRegistry, lotId) {
  if (!lotId || !lotRegistry) return null
  if (typeof lotRegistry.get === 'function') return lotRegistry.get(lotId) || null
  return lotRegistry[lotId] || null
}

/**
 * 先用 LOT_ID 查 BATCH_INFO 登记的 PORT，查不到再回退当前 PORT，得到 carrier=LLA/LLB。
 */
export function enrichMotionParams(eventPayload, lotRegistry) {
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
  const carrier = portToCarrier(params.PORT)
  if (carrier) params.carrier = carrier
  const slot = (params.SLOT != null && params.SLOT !== '') ? params.SLOT : '1'
  params.SLOT = slot
  return { params, matchedBy, lotId, carrier, slot }
}

/**
 * 解析零件 ID 模板，如 {carrier}{SLOT} / CH_{CHAMBER}
 * 未提供对应参数时保持原样；SLOT 默认 1，carrier 默认 LLA。
 */
export function resolvePartIdTemplate(partId, eventPayload) {
  if (!partId || typeof partId !== 'string') return partId || ''
  const params = extractParams(eventPayload)
  return partId.replace(/\{(\w+)\}/g, (match, key) => {
    let val = params[key]
    if (val === undefined || val === null || val === '') {
      if (key === 'slot' || key === 'SLOT') val = params.SLOT
      else if (key === 'chamber' || key === 'CHAMBER') val = params.CHAMBER
      else if (key === 'arm' || key === 'ARM') val = params.ARM || params.arm
      else if (key === 'from_arm') val = params.from_arm || params.ARM || params.arm
      else if (key === 'to_arm') val = params.to_arm || params.ARM || params.arm
      else if (key === 'pickup_part') val = params.pickup_part
      else if (key === 'drop_part') val = params.drop_part
    }
    if (val !== undefined && val !== null && val !== '') return String(val)
    if (key === 'slot' || key === 'SLOT') return '1'
    if (key === 'carrier') return portToCarrier(params.PORT) || 'LLA'
    if (key === 'chamber' || key === 'CHAMBER') return 'E'
    if (key === 'arm' || key === 'ARM' || key === 'from_arm' || key === 'to_arm') return 'ARM_1'
    if (key === 'from_part' || key === 'pickup_part' || key === 'drop_part') {
      const arm = String(
        key === 'drop_part'
          ? (params.to_arm || params.ARM || params.arm || 'ARM_1')
          : (params.from_arm || params.ARM || params.arm || 'ARM_1')
      )
      const m = arm.match(/(\d+)\s*$/)
      return `Wafer_Chuck${m ? m[1] : '1'}`
    }
    if (key === 'from_angle') return '190'
    if (key === 'to_angle') return '205'
    return match
  })
}

/**
 * 将文本中的 params.xxx 替换为实际值（写法与 when 相同）
 * 未提供对应参数时保持原样。
 * 例：LOT_ID: params.LOT_ID + { LOT_ID: 'NPPNC' } → LOT_ID: NPPNC
 */
export function resolveTextTemplate(text, eventPayload) {
  if (text == null) return ''
  const params = extractParams(eventPayload)
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
      if (key === 'slot' || key === 'SLOT') val = params.SLOT
      else if (key === 'chamber' || key === 'CHAMBER') val = params.CHAMBER
    }
    if (val === undefined || val === null || val === '') return match
    return String(val)
  })
}

export function resolveMotionRule(rule, eventPayload) {
  if (!rule) return rule
  return {
    ...rule,
    target_part_id: resolvePartIdTemplate(rule.target_part_id, eventPayload),
    actions: (Array.isArray(rule.actions) ? rule.actions : []).map((action) => {
      if (!action) return action
      const next = { ...action }
      if (next.follow_part_id) next.follow_part_id = resolvePartIdTemplate(next.follow_part_id, eventPayload)
      if (next.to_part_id) next.to_part_id = resolvePartIdTemplate(next.to_part_id, eventPayload)
      if (next.target_part_id) next.target_part_id = resolvePartIdTemplate(next.target_part_id, eventPayload)
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
          const targetArm = resolvePartIdTemplate(rule.target_part_id, eventPayload)
          const crossTo = Number(params.cross_angle_to)
          const crossFrom = Number(params.cross_angle_from)
          if (targetArm && targetArm === params.to_arm && Number.isFinite(crossTo)) next.angle = crossTo
          else next.angle = Number.isFinite(crossFrom) ? crossFrom : (Number.isFinite(crossTo) ? crossTo : 0)
        } else {
          if (typeof raw === 'string') raw = resolvePartIdTemplate(raw, eventPayload)
          const num = Number(raw)
          next.angle = Number.isFinite(num) ? num : 0
        }
      }
      if (next.type === 'text' && next.content != null) {
        next.content = resolveTextTemplate(next.content, eventPayload)
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
