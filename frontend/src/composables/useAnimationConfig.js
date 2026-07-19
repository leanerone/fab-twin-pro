/**
 * 机台动画统一配置加载器
 * 替代 useEventActionMapping.js 中硬编码的 EVENT_ACTION_DEFAULTS
 *
 * 用法：
 *   const { config, getPhaseByEvent, getAnimation, getTarget, loading } = useAnimationConfig('podopener')
 *   await loadConfig()
 *   const phaseInfo = getPhaseByEvent('POD_PLACED', 'PACKING')
 *   // => { phase: 'POD_PLACE', anim: 'pod.enter', phaseIndex: 0, phaseDef: {...} }
 */
import { ref, readonly } from 'vue'

// 用 import.meta.glob 预加载所有配置（Vite 构建时会打包进 bundle，dev 和 build 都可用）
// eager: true 表示同步加载，避免异步等待
const configModules = import.meta.glob('../configs/machine-animations/*.json', { eager: true, as: 'raw' })

// 把 raw 字符串解析为 JSON 对象，按 machine_type（小写）建立索引
const builtInConfigs = {}
for (const [path, raw] of Object.entries(configModules)) {
  // path 形如 '../configs/machine-animations/podopener.json'
  const match = path.match(/\/([^/]+)\.json$/)
  if (!match) continue
  const typeName = match[1].toLowerCase()
  if (typeName === '_schema') continue  // 跳过 schema 文件
  try {
    builtInConfigs[typeName] = JSON.parse(raw)
  } catch (e) {
    console.error('[useAnimationConfig] 解析配置失败:', path, e)
  }
}

// 全局配置缓存（按 machine_type 缓存，可被 updateConfig 热更新覆盖）
const configCache = new Map()

// Schema 校验（轻量级，仅校验关键字段）
function validateConfig(config) {
  const errors = []
  if (!config?.machine_type) errors.push('缺少 machine_type')
  if (!config?.version) errors.push('缺少 version')
  if (!config?.flows || typeof config.flows !== 'object') {
    errors.push('缺少 flows 对象')
  } else {
    for (const [flowKey, flow] of Object.entries(config.flows)) {
      if (!Array.isArray(flow.phases)) {
        errors.push(`flows.${flowKey}.phases 必须是数组`)
        continue
      }
      flow.phases.forEach((phase, idx) => {
        if (!phase.key) errors.push(`flows.${flowKey}.phases[${idx}].key 缺失`)
        if (!phase.label) errors.push(`flows.${flowKey}.phases[${idx}].label 缺失`)
        if (!phase.duration_ms || phase.duration_ms < 100) {
          errors.push(`flows.${flowKey}.phases[${idx}].duration_ms 无效`)
        }
      })
      if (!flow.event_to_phase || typeof flow.event_to_phase !== 'object') {
        errors.push(`flows.${flowKey}.event_to_phase 必须是对象`)
      }
    }
  }
  if (!config?.animations || typeof config.animations !== 'object') {
    errors.push('缺少 animations 对象')
  }
  if (!config?.targets || typeof config.targets !== 'object') {
    errors.push('缺少 targets 对象')
  }
  return errors
}

export function useAnimationConfig(machineType) {
  const config = ref(null)
  const loading = ref(false)
  const error = ref(null)

  async function loadConfig(type = machineType) {
    if (!type) {
      error.value = 'machineType 未指定'
      return null
    }
    const typeLower = type.toLowerCase()
    // 命中缓存
    if (configCache.has(typeLower)) {
      config.value = configCache.get(typeLower)
      return config.value
    }
    loading.value = true
    error.value = null
    try {
      // 优先从内置配置（Vite 打包）加载
      const data = builtInConfigs[typeLower]
      if (!data) {
        throw new Error(`未找到机台类型 "${type}" 的配置文件（查找: configs/machine-animations/${typeLower}.json）`)
      }
      const errs = validateConfig(data)
      if (errs.length > 0) {
        throw new Error(`配置校验失败: ${errs.join('; ')}`)
      }
      configCache.set(typeLower, data)
      config.value = data
      return data
    } catch (e) {
      error.value = e.message
      console.error('[useAnimationConfig]', e.message)
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * 根据事件名获取阶段信息
   * @param {string} eventName - 事件名（如 'POD_PLACED'）
   * @param {string} flowType - 流程类型（'PACKING' | 'UNPACKING'）
   * @returns {null|{phase, anim, phaseIndex, phaseDef, eventDef}}
   */
  function getPhaseByEvent(eventName, flowType = 'PACKING') {
    if (!config.value) return null
    const flow = config.value.flows?.[flowType]
    if (!flow) return null
    const eventDef = flow.event_to_phase?.[eventName]
    if (!eventDef) return null
    const phaseIndex = flow.phases.findIndex(p => p.key === eventDef.phase)
    if (phaseIndex < 0) return null
    return {
      phase: eventDef.phase,
      anim: eventDef.anim,
      phaseIndex,
      phaseDef: flow.phases[phaseIndex],
      eventDef,
    }
  }

  /**
   * 获取动画原语定义
   * @param {string} animKey - 动画 key（如 'pod.enter'）
   */
  function getAnimation(animKey) {
    if (!config.value) return null
    return config.value.animations?.[animKey] || null
  }

  /**
   * 获取部件目标绑定
   * @param {string} targetKey - 部件 key（如 'podShell'）
   */
  function getTarget(targetKey) {
    if (!config.value) return null
    return config.value.targets?.[targetKey] || null
  }

  /**
   * 获取指定流程的所有阶段
   */
  function getPhases(flowType = 'PACKING') {
    if (!config.value) return []
    return config.value.flows?.[flowType]?.phases || []
  }

  /**
   * 获取指定流程的事件映射表
   */
  function getEventMap(flowType = 'PACKING') {
    if (!config.value) return {}
    return config.value.flows?.[flowType]?.event_to_phase || {}
  }

  /**
   * 根据事件名推断流程类型（PACKING/UNPACKING）
   * 优先匹配 PACKING，其次 UNPACKING
   */
  function inferFlowByEvent(eventName) {
    if (!config.value) return 'PACKING'
    if (config.value.flows.PACKING?.event_to_phase?.[eventName]) return 'PACKING'
    if (config.value.flows.UNPACKING?.event_to_phase?.[eventName]) return 'UNPACKING'
    return 'PACKING'
  }

  /**
   * 热更新配置（调试面板用）
   */
  function updateConfig(newConfig) {
    const errs = validateConfig(newConfig)
    if (errs.length > 0) {
      throw new Error(`配置校验失败: ${errs.join('; ')}`)
    }
    configCache.set(newConfig.machine_type, newConfig)
    config.value = newConfig
  }

  /**
   * 导出当前配置为 JSON 字符串（调试面板"导出"按钮用）
   */
  function exportConfig() {
    if (!config.value) return ''
    return JSON.stringify(config.value, null, 2)
  }

  return {
    config: readonly(config),
    loading: readonly(loading),
    error: readonly(error),
    loadConfig,
    getPhaseByEvent,
    getAnimation,
    getTarget,
    getPhases,
    getEventMap,
    inferFlowByEvent,
    updateConfig,
    exportConfig,
  }
}

export default useAnimationConfig
