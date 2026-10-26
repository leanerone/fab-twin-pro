/**
 * OXE DRM（TEL UNITY 刻蚀机）Motion 参数推导器
 *
 * 业务语义移植自旧 MachineOxeView.applyEvent（Canvas 看板）：
 * - 端口归一：port_id/port → PORT1/PORT2；SMIF1→PORT1；CHAMBER_A→PORT1、CHAMBER_B→PORT2；
 *   记忆 lastEventPortId（连续事件缺 port 时沿用上一端口）
 * - 腔体归一：CHAMBER_A/B/C → A/B/C；WAFERLOADED/WAFERUNLOADED 等缺 chamber 时按端口默认（1→A，2→B）
 * - MIC（line1 OXE）无 SMIF 外壳：pod_shell='0'，POD_PLACED 只出晶舟不出壳
 * - 机械臂角度：blade 基座朝东（0°），rotate 到目标单元方位角（SVG 顶视图几何）
 * - 产出占位符 id（POD/CST/DOOR/MAP/SLOT_ANCHOR/CH_*），Motion JSON 用 {param} 引用
 */
const ARM_ANGLES = {
  HOME: -45,
  PORT1: 118.2,
  PORT2: 61.8,
  CH_A: -117.4,
  CH_B: -62.6,
  CH_C: 0,
  PA: -90,
}

function normalizeChamber(val) {
  const s = String(val ?? '').trim().toUpperCase()
  const m = s.match(/^CHAMBER[_-]?([ABC])$/)
  if (m) return m[1]
  if (['A', 'B', 'C'].includes(s)) return s
  return ''
}

function normalizePort(val) {
  const s = String(val ?? '').trim().toUpperCase()
  if (/^(PORT)?1$/.test(s) || s === 'SMIF1' || s === 'SMIF_1') return '1'
  if (/^(PORT)?2$/.test(s) || s === 'SMIF2' || s === 'SMIF_2') return '2'
  return ''
}

function pick(src, ...keys) {
  for (const k of keys) {
    const v = src?.[k]
    if (v !== undefined && v !== null && v !== '' && String(v).toUpperCase() !== 'NULL') return v
  }
  return ''
}

export function createOxeDeriver() {
  let lastPort = '1'

  function resolvePort(payload, eventName) {
    // STARTMAPPING_LEFT/RIGHT 显式指定映射端口
    const name = String(eventName || '').toUpperCase()
    if (name === 'STARTMAPPING_LEFT') return '1'
    if (name === 'STARTMAPPING_RIGHT') return '2'
    const direct = normalizePort(pick(payload, 'PORT', 'port_id', 'portid', 'PORTID', 'port_no'))
    if (direct) return direct
    const smif = normalizePort(pick(payload, 'SMIF_ID', 'smif_id', 'SMIFPORTID'))
    if (smif) return smif
    const ch = normalizeChamber(pick(payload, 'CHAMBER', 'chamber_id', 'chamber'))
    if (ch === 'A') return '1'
    if (ch === 'B') return '2'
    return lastPort
  }

  function resolveChamber(payload, port) {
    const ch = normalizeChamber(pick(payload, 'CHAMBER', 'chamber_id', 'chamber'))
    if (ch) return ch
    return port === '2' ? 'B' : 'A'
  }

  return {
    derive(step, payload) {
      const src = payload || {}
      const eventName = String(pick(src, 'event_name', 'event_code') || step || '').toUpperCase()
      const port = resolvePort(src, eventName)
      const ch = resolveChamber(src, port)
      const slotRaw = Number(pick(src, 'SLOT', 'slot', 'slot_id', 'wafer_id') || 1)
      const slot = Math.min(25, Math.max(1, Number.isFinite(slotRaw) ? Math.floor(slotRaw) : 1))
      const stateVal = String(pick(src, 'state', 'machine_state') || '').toUpperCase()
      const transferStage = String(pick(src, 'transfer_stage', 'action') || '').toUpperCase()

      const params = {
        ...src,
        // 归一化业务参数
        PORT: port,
        CH: ch,
        SLOT: String(slot),
        STATE: stateVal,
        TRANSFER_STAGE: transferStage,
        // line1 OXE（MIC）没有 SMIF 外壳
        pod_shell: eventName === 'MIC' ? '0' : '1',
        // 部件 id 占位符
        POD: `POD_P${port}`,
        POD_LK: `POD_P${port}_LK`,
        CST: `CST_P${port}`,
        DOOR: `DOOR_P${port}`,
        MAP: `MAP_P${port}`,
        SMIF_C: `SMIF${port}_C`,
        PORT_C: `PORT${port}_C`,
        SLOT_ANCHOR: `P${port}_SLOT_${slot}`,
        CH_C: `CH_${ch}_C`,
        WAFER_CH: `WAFER_CH_${ch}`,
        CH_RUN: `CH_${ch}_run`,
        CH_ALARM: `CH_${ch}_alarm`,
        CH_UNLOAD: `CH_${ch}_unload`,
        // 机械臂目标角（deg，blade 朝东为 0，SVG 顺时针为正）
        ARM_HOME: String(ARM_ANGLES.HOME),
        ARM_PORT_ANGLE: String(port === '2' ? ARM_ANGLES.PORT2 : ARM_ANGLES.PORT1),
        ARM_CH_ANGLE: String(ARM_ANGLES[`CH_${ch}`] ?? ARM_ANGLES.HOME),
        ARM_PA_ANGLE: String(ARM_ANGLES.PA),
      }
      return { ok: true, params, info: { port, chamber: ch, slot } }
    },

    commit(step, params) {
      if (params?.PORT === '1' || params?.PORT === '2') lastPort = params.PORT
    },

    reset() {
      lastPort = '1'
    },
  }
}
