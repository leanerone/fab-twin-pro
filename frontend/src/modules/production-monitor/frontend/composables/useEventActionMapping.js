/**
 * 事件动作映射系统
 * 将VFEI事件（如EC_ALARM_REPORT、WaferLoaded、POD_ATTACH等）映射到机台动画动作
 */
import { ref, computed, watch } from 'vue'

// 事件类型到动作的默认映射
const EVENT_ACTION_DEFAULTS = {
  // Alarm相关
  'EC_ALARM_REPORT': { action: 'alarm', params: { flash: true, color: '#ef4444' } },
  'ALARM': { action: 'alarm', params: { flash: true } },
  'ALARM_REPORT': { action: 'alarm', params: { flash: true } },

  // Pod/晶舟相关 - 完整的ATTACH/DETACH流程
  'POD_ATTACH': { action: 'podMove', params: { direction: 'attach', progress: 1 } },
  'POD_DETACH': { action: 'podMove', params: { direction: 'detach', progress: 0 } },
  
  // ATTACH流程（空POD放入，拿走满POD）
  'ATTACH_POD_PLACE': { action: 'podMove', params: { direction: 'attach', progress: 0.1 } },
  'ATTACH_POD_UP': { action: 'podMove', params: { direction: 'attach', progress: 0.25 } },
  'ATTACH_POD_REACH_STAGE': { action: 'podMove', params: { direction: 'attach', progress: 0.35 } },
  'ATTACH_CST_PLACE': { action: 'waferShow', params: { visible: true } },
  'ATTACH_POD_DOWN': { action: 'podMove', params: { direction: 'attach', progress: 0.65 } },
  'ATTACH_POD_REACH_POS': { action: 'podMove', params: { direction: 'attach', progress: 0.85 } },
  'ATTACH_POD_REMOVE': { action: 'podMove', params: { direction: 'attach', progress: 1 } },
  
  // DETACH流程（满POD放入，拿走空POD）
  'DETACH_POD_PLACE': { action: 'podMove', params: { direction: 'detach', progress: 0.9 } },
  'DETACH_POD_UP': { action: 'podMove', params: { direction: 'detach', progress: 0.75 } },
  'DETACH_POD_REACH_STAGE': { action: 'podMove', params: { direction: 'detach', progress: 0.6 } },
  'DETACH_CST_REMOVE': { action: 'waferShow', params: { visible: false } },
  'DETACH_POD_DOWN': { action: 'podMove', params: { direction: 'detach', progress: 0.35 } },
  'DETACH_POD_REACH_POS': { action: 'podMove', params: { direction: 'detach', progress: 0.15 } },
  'DETACH_POD_REMOVE': { action: 'podMove', params: { direction: 'detach', progress: 0 } },

  // PODOPENER 穿入流程（PACKING）
  'POD_PLACED': { action: 'podPlace', params: { placed: true } },
  'COMPLETED_PORT_LOCK': { action: 'podLock', params: { locked: true } },
  'READ_BATTERY': { action: 'signalBlink', params: { type: 'battery' } },
  'READ_TAG': { action: 'tagScan', params: { scan: true } },
  'BATCH_INFO_FROM_ECUI': { action: 'uiConfirm', params: { type: 'batch_info' } },
  'OPEN_POD': { action: 'podDoor', params: { open: true } },
  'REACH_STAGE': { action: 'robotMove', params: { stage: true } },
  'UI_CONFIRM': { action: 'uiConfirm', params: { type: 'confirm' } },
  'CLOSE_POD': { action: 'podDoor', params: { open: false } },
  'ACK_UI_DOUBLECHECK': { action: 'uiDoubleCheck', params: { scanner: true } },
  'REACH_POS': { action: 'robotMove', params: { stage: false } },
  'WRITE_TAG': { action: 'tagWrite', params: { signal: true } },
  'COMPLETED_PORT_UNLOCK': { action: 'podLock', params: { locked: false } },
  'POD_REMOVED': { action: 'podPlace', params: { placed: false } },

  // 锁定/解锁
  'POD_LOCK': { action: 'podLock', params: { locked: true } },
  'LOCK_PORT_COMPLETED': { action: 'podLock', params: { locked: true } },
  'POD_UNLOCK': { action: 'podLock', params: { locked: false } },
  'UNLOCK_PORT_COMPLETED': { action: 'podLock', params: { locked: false } },

  // Tag操作
  'READ_TAG': { action: 'tagScan', params: { scan: true } },
  'WRITE_TAG': { action: 'tagWrite', params: { signal: true } },

  // UI确认流程
  'BATCH_START': { action: 'uiConfirm', params: { type: 'batch_start' } },
  'UI_CONFIRM': { action: 'uiConfirm', params: { type: 'confirm' } },
  'UI_DOUBLECHECK': { action: 'uiDoubleCheck', params: { scanner: true } },

  // Wafer相关
  'WaferLoaded': { action: 'waferTransfer', params: { location: 'chamber' } },
  'WaferUnloaded': { action: 'waferTransfer', params: { location: 'port' } },

  // 状态变化
  'STATE_CHANGE': { action: 'stateChange', params: {} },
  'PROCESS_START': { action: 'processStart', params: {} },
  'PROCESS_END': { action: 'processEnd', params: {} },
  'PS': { action: 'processStep', params: { step: 'start' } },
  'PE': { action: 'processStep', params: { step: 'end' } },

  // Port操作
  'POD_PLACED': { action: 'podPlace', params: { placed: true } },
  'POD_REMOVED': { action: 'podPlace', params: { placed: false } },

  // Mapping
  'StartMapping_LEFT': { action: 'mapping', params: { port: 'PORT1' } },
  'StartMapping_RIGHT': { action: 'mapping', params: { port: 'PORT2' } },
  'EndMapping': { action: 'mappingEnd', params: {} },

  // IDLE状态
  'IDLE': { action: 'idle', params: {} },
}

// 严重度颜色映射
const SEVERITY_COLORS = {
  crit: '#ef4444',
  warn: '#f59e0b',
  info: '#3b82f6',
}

/**
 * 解析事件并返回对应的动作
 */
export function parseEventAction(event, modelConfig = null) {
  if (!event) return null

  const eventType = (event.event_type || event.event_name || '').toUpperCase()
  const eventName = (event.event_name || event.event_type || '').toUpperCase()

  // 先从配置中查找
  if (modelConfig?.event_action_mappings) {
    const mapping = modelConfig.event_action_mappings.find(m =>
      m.trigger_event_type === eventType ||
      m.trigger_event_code === eventName
    )
    if (mapping) {
      return {
        action: mapping.action_type,
        params: mapping.action_params || {},
        duration: mapping.duration_ms || 1000,
        easing: mapping.easing || 'easeInOut',
      }
    }
  }

  // 使用默认映射
  const defaultAction = EVENT_ACTION_DEFAULTS[eventType] || EVENT_ACTION_DEFAULTS[eventName]
  if (defaultAction) {
    return {
      ...defaultAction,
      duration: 1000,
      easing: 'easeInOut',
    }
  }

  return null
}

/**
 * 解析Alarm事件
 */
export function parseAlarmEvent(event) {
  if (!event) return null

  const isAlarm = event.event_name === 'EC_ALARM_REPORT' ||
                  event.event_type === 'ALARM' ||
                  event.machine_state?.toLowerCase() === 'alarm'

  if (!isAlarm) return null

  const alarmId = event.alarm_id || ''
  const alarmText = event.alarm_text || ''

  let severity = 'warn'
  if (['9004', '0201'].includes(alarmId)) severity = 'crit'
  else if (['9003', '20011'].includes(alarmId)) severity = 'warn'
  else if (alarmId === '0411') severity = 'info'

  return {
    isAlarm: true,
    alarmId,
    alarmText,
    severity,
    color: SEVERITY_COLORS[severity] || SEVERITY_COLORS.warn,
  }
}

/**
 * 解析Pod动作
 */
export function parsePodAction(event) {
  const evtName = (event.event_name || event.event_type || '').toUpperCase()

  if (evtName.includes('ATTACH') || evtName === 'POD_ATTACH') {
    return { direction: 'attach', active: true }
  }
  if (evtName.includes('DETACH') || evtName === 'POD_DETACH') {
    return { direction: 'detach', active: true }
  }

  return null
}

/**
 * 解析Wafer位置
 */
export function parseWaferLocation(event) {
  const evtName = (event.event_name || '').toUpperCase()

  if (evtName === 'WaferLoaded') {
    return {
      location: event.chamber_id || 'chamber',
      waferId: event.wafer_id || event.slot_id,
      slot: event.slot,
    }
  }
  if (evtName === 'WaferUnloaded') {
    return {
      location: event.port_id || 'port',
      waferId: event.wafer_id || event.slot_id,
      slot: event.slot,
    }
  }

  return null
}

/**
 * 事件动作映射 composable
 */
export function useEventActionMapping(props) {
  const currentAction = ref(null)
  const podProgress = ref(0)
  const podDirection = ref(null)
  const waferLocation = ref('port')
  const chamberState = ref('idle')
  const alarmInfo = ref(null)
  const podLocked = ref(false)
  const scanActive = ref(false)
  const signalActive = ref(false)
  const podDoorOpen = ref(false)
  const robotAtStage = ref(false)
  const currentPhase = ref('IDLE')

  // 处理单个事件
  function processEvent(event) {
    if (!event) return

    const evtName = (event.event_name || event.event_type || '').toUpperCase()
    const evtAction = EVENT_ACTION_DEFAULTS[evtName]

    // 解析Alarm
    const alarm = parseAlarmEvent(event)
    if (alarm) {
      alarmInfo.value = alarm
      chamberState.value = 'alarm'
    }

    // 解析Pod动作
    const podAction = parsePodAction(event)
    if (podAction) {
      podDirection.value = podAction.direction
      if (podAction.direction === 'attach') {
        podProgress.value = Math.min(1, podProgress.value + 0.1)
      } else {
        podProgress.value = Math.max(0, podProgress.value - 0.1)
      }
    }

    // 解析Pod锁定
    if (evtName === 'POD_LOCK' || evtName === 'LOCK_PORT_COMPLETED' || evtName === 'COMPLETED_PORT_LOCK') {
      podLocked.value = true
    } else if (evtName === 'POD_UNLOCK' || evtName === 'UNLOCK_PORT_COMPLETED' || evtName === 'COMPLETED_PORT_UNLOCK') {
      podLocked.value = false
    }

    // POD盖开关
    if (evtName === 'OPEN_POD') {
      podDoorOpen.value = true
    } else if (evtName === 'CLOSE_POD') {
      podDoorOpen.value = false
    }

    // 机械臂位置
    if (evtName === 'REACH_STAGE') {
      robotAtStage.value = true
    } else if (evtName === 'REACH_POS') {
      robotAtStage.value = false
    }

    // 更新当前阶段（来自mode）
    if (event.mode || event.run_mode) {
      currentPhase.value = event.mode || event.run_mode
    }

    // 解析Tag扫描
    if (evtName === 'READ_TAG') {
      scanActive.value = true
      setTimeout(() => { scanActive.value = false }, 1200)
    } else if (evtName === 'WRITE_TAG') {
      signalActive.value = true
      setTimeout(() => { signalActive.value = false }, 2000)
    }

    // 解析Wafer位置
    const waferLoc = parseWaferLocation(event)
    if (waferLoc) {
      waferLocation.value = waferLoc.location
    }

    // 解析状态变化
    const state = event.machine_state?.toLowerCase()
    if (state) {
      chamberState.value = state
      if (state !== 'alarm') {
        alarmInfo.value = null
      }
    }

    // 根据事件动作更新进度
    if (evtAction) {
      currentAction.value = evtAction
      
      // 根据动作类型更新状态
      if (evtAction.action === 'podMove') {
        podDirection.value = evtAction.params.direction
        podProgress.value = evtAction.params.progress
      } else if (evtAction.action === 'podLock') {
        podLocked.value = evtAction.params.locked
      } else if (evtAction.action === 'tagScan') {
        scanActive.value = true
        setTimeout(() => { scanActive.value = false }, 1200)
      } else if (evtAction.action === 'tagWrite') {
        signalActive.value = true
        setTimeout(() => { signalActive.value = false }, 2000)
      } else if (evtAction.action === 'waferShow') {
        if (evtAction.params.visible) {
          waferLocation.value = 'port'
        }
      }
    }
  }

  // 批量处理事件列表
  function processEvents(events) {
    if (!events || events.length === 0) return

    // 重置状态
    podProgress.value = 0
    podDirection.value = null
    waferLocation.value = 'port'
    chamberState.value = 'idle'
    alarmInfo.value = null
    podLocked.value = false
    scanActive.value = false
    signalActive.value = false
    podDoorOpen.value = false
    robotAtStage.value = false
    currentPhase.value = 'IDLE'

    // 按时间顺序处理所有事件
    events.forEach(event => processEvent(event))
  }

  return {
    currentAction,
    podProgress,
    podDirection,
    waferLocation,
    chamberState,
    alarmInfo,
    podLocked,
    scanActive,
    signalActive,
    podDoorOpen,
    robotAtStage,
    currentPhase,
    phaseProgress: podProgress,
    processEvent,
    processEvents,
    parseEventAction,
    parseAlarmEvent,
    parsePodAction,
    parseWaferLocation,
  }
}

export default useEventActionMapping