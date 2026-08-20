/**
 * when 表达式求值器
 * 用于通用 Motion JSON 中 rules[].when 条件表达式的求值
 *
 * 支持运算符：== != > < >= <= && || !
 * 支持值类型：字符串(单引号) 数字 true false
 * params 字段自动从 event payload 提取（下划线转驼峰）
 *
 * 示例：
 *   evalWhen("params.chamber == '1'", { chamber_id: '1' })  → true
 *   evalWhen("params.port == '2'", { port_id: '1' })        → false
 *   evalWhen("true", {})                                      → true
 *   evalWhen("params.chamber == '1' && params.port == '2'", { chamber_id: '1', port_id: '2' }) → true
 */

/**
 * 从事件 payload 提取 params（下划线转驼峰）
 * chamber_id → chamber, port_id → port, wafer_id → wafer
 */
function extractParams(payload) {
  const params = {}
  if (!payload || typeof payload !== 'object') return params
  for (const [k, v] of Object.entries(payload)) {
    // 去掉 _id 后缀
    let key = k.replace(/_id$/, '')
    // 下划线转驼峰
    key = key.replace(/_(\w)/g, (_, c) => c.toUpperCase())
    params[key] = v
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
 * @param {string} when - 条件表达式，如 "params.chamber == '1'"
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

export default { evalWhen, extractParamKeys, extractParams }
