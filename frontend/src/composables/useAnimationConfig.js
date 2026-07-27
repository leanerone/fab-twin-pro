/**
 * 机台动画统一配置加载器 v2.0
 * 
 * v2.0 重构：
 * - 从 DB 运行时加载配置（通过 API）
 * - 删除 import.meta.glob 静态加载
 * - 支持热更新，无需重新构建
 * 
 * 用法：
 *   const { config, loadConfig, getPhaseByEvent, getAnimation, getTarget } = useAnimationConfig()
 *   await loadConfig('PODOPENER-2200')  // 从 DB 加载指定机型配置
 *   const phaseInfo = getPhaseByEvent('POD_PLACED', 'PACKING')
 */

import { ref, readonly, computed } from 'vue'
import { api } from '../api'

// 全局配置缓存（按 model_id 缓存）
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

/**
 * 从 API 加载机型配置
 * @param {string} modelId - 机型 ID（如 'PODOPENER-2200'）
 * @returns {Promise<object|null>} 配置对象或 null
 */
async function loadConfigFromAPI(modelId) {
  try {
    const modelData = await api.getModel(modelId)
    if (!modelData) {
      console.warn(`[useAnimationConfig] 未找到机型: ${modelId}`)
      return null
    }
    
    // 优先从 animation_config 字段读取（v2.0 新字段）
    let animConfig = modelData.animation_config
    
    // 如果 animation_config 为空，尝试从 views_config 读取（兼容旧数据）
    if (!animConfig || Object.keys(animConfig).length === 0) {
      console.log(`[useAnimationConfig] ${modelId} animation_config 为空，尝试兼容模式`)
      // 从静态文件 fallback（仅用于兼容）
      animConfig = await loadConfigFromStatic(modelId)
    }
    
    return animConfig
  } catch (e) {
    console.error(`[useAnimationConfig] 加载配置失败: ${modelId}`, e)
    return null
  }
}

/**
 * 从静态文件加载配置（仅用于兼容旧版本）
 * @param {string} modelId - 机型 ID
 * @returns {Promise<object|null>}
 */
async function loadConfigFromStatic(modelId) {
  // 机型 ID 到配置文件名的映射
  const modelToConfig = {
    'PODOPENER-2200': 'podopener',
    'PODOPENER-1': 'podopener',
    'PODOPENER': 'podopener',
  }
  
  const configName = modelToConfig[modelId] || modelId.toLowerCase()
  
  try {
    const response = await fetch(`/configs/machine-animations/${configName}.json`)
    if (!response.ok) {
      console.warn(`[useAnimationConfig] 静态文件不存在: ${configName}.json`)
      return null
    }
    return await response.json()
  } catch (e) {
    console.error(`[useAnimationConfig] 加载静态配置失败: ${configName}`, e)
    return null
  }
}

export function useAnimationConfig(initialModelId = null) {
  const config = ref(null)
  const loading = ref(false)
  const error = ref(null)
  const currentModelId = ref(initialModelId)

  /**
   * 加载配置
   * @param {string} modelId - 机型 ID（如 'PODOPENER-2200'）
   */
  async function loadConfig(modelId = null) {
    const targetModelId = modelId || currentModelId.value
    if (!targetModelId) {
      error.value = 'modelId 未指定'
      return null
    }
    
    currentModelId.value = targetModelId
    
    // 命中缓存
    if (configCache.has(targetModelId)) {
      config.value = configCache.get(targetModelId)
      return config.value
    }
    
    loading.value = true
    error.value = null
    
    try {
      const data = await loadConfigFromAPI(targetModelId)
      
      if (!data) {
        throw new Error(`未找到机型 "${targetModelId}" 的配置`)
      }
      
      // 校验配置
      const errs = validateConfig(data)
      if (errs.length > 0) {
        throw new Error(`配置校验失败: ${errs.join('; ')}`)
      }
      
      // 缓存配置
      configCache.set(targetModelId, data)
      config.value = data
      
      console.log(`[useAnimationConfig] 加载成功: ${targetModelId}`, {
        machine_type: data.machine_type,
        flows: Object.keys(data.flows || {}),
        animations: Object.keys(data.animations || {}).length,
        targets: Object.keys(data.targets || {}).length,
      })
      
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
    configCache.set(currentModelId.value, newConfig)
    config.value = newConfig
  }

  /**
   * 导出当前配置为 JSON 字符串
   */
  function exportConfig() {
    if (!config.value) return ''
    return JSON.stringify(config.value, null, 2)
  }

  /**
   * 清除缓存
   */
  function clearCache() {
    configCache.clear()
    config.value = null
  }

  /**
   * 获取所有可用流程
   */
  const availableFlows = computed(() => {
    if (!config.value) return []
    return Object.keys(config.value.flows || {})
  })

  /**
   * 获取所有部件目标
   */
  const availableTargets = computed(() => {
    if (!config.value) return []
    return Object.keys(config.value.targets || {})
  })

  /**
   * 获取所有动画原语
   */
  const availableAnimations = computed(() => {
    if (!config.value) return []
    return Object.keys(config.value.animations || {})
  })

  // 如果提供了初始 modelId，立即加载
  if (initialModelId) {
    loadConfig(initialModelId)
  }

  return {
    // 状态
    config: readonly(config),
    loading: readonly(loading),
    error: readonly(error),
    currentModelId: readonly(currentModelId),
    
    // 计算属性
    availableFlows,
    availableTargets,
    availableAnimations,
    
    // 方法
    loadConfig,
    getPhaseByEvent,
    getAnimation,
    getTarget,
    getPhases,
    getEventMap,
    inferFlowByEvent,
    updateConfig,
    exportConfig,
    clearCache,
  }
}

export default useAnimationConfig