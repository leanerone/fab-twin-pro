/**
 * OXE DRM（TEL UNITY 刻蚀机）Motion 参数推导器
 *
 * 业务语义移植自旧 MachineOxeView.applyEvent（Canvas 看板）：
 * - 端口归一：port_id/port → PORT1/PORT2；SMIF1→PORT1；CHAMBER_A→PORT1、CHAMBER_B→PORT2；
 *   记忆 lastEventPortId（连续事件缺 port 时沿用上一端口）
 * - 腔体归一：CHAMBER_A/B/C → A/B/C；WAFERLOADED/WAFERUNLOADED 等缺 chamber 时按端口默认（1→A，2→B）
 * - MIC（line1 OXE）无 SMIF 外壳：pod_shell='0'，POD_PLACED 只出晶舟不出壳
 * - 机械臂角度：blade 基座朝东（0°），rotate 到目标单元方位角
 *   （v2.5 镜像对称居中布局，hub=(444,400)：CH_A=-120 / CH_B=-60 / CH_C=0 /
 *   LL1=60 / LL2=120 / PA=180 / HOME=-90 朝 Gas Box）
 *   动作模型：收回(ARM_EXTEND offset 0)状态下 rotate → 伸出(offset +80)取/放 → 收回，
 *   晶圆(WAFER_MOVE)是叉端子件，随臂一起转/伸缩，不独立 snap，不会空中飞
 * - Wafer Map 状态机（每端口 25 槽）：0 空 / 1 等待 / 2 加工中 / 3 完成
 *   · POD_PLACED 初始化为全 1；WAFER_MAPPING 以事件值覆盖（25 位 0/1/2/3）
 *   · WAFERLOADED 本槽 1→2；WAFERUNLOADED 本槽 2→3 并累加完成计数
 * - 产出占位符 id（POD/CST/DOOR/MAP/SLOT_ANCHOR/CH_x/面板徽章/WM 三态条），
 *   Motion JSON 用 {param} / when 引用
 */
const ARM_ANGLES = {
  HOME: -90,
  PORT1: 116.3,
  PORT2: 63.0,
  CH_A: -120,
  CH_B: -60,
  CH_C: 0,
  PA: 180,
}
// 各单元中心到 hub 的距离（v2.5 镜像对称布局，SVG user space，hub=(538.5,388.6) 绝对坐标）
// 机械臂收回叉托在局部 r=70；伸出 offset = 单元距离 - 70，使叉托精确到单元中心
// 实测：CH_A/B=(443.5|633.5,224.1)→190、CH_C=(739.5,388.6)→201、PA=(346.5,388.6)→192、
// PORT1 装载口=(452.9,561.7)→193.2、PORT2 装载口=(626.4,560.7)→193.2（旧值 205 会让叉子越过中心 12px）
const UNIT_DIST = {
  CH_A: 190, CH_B: 190, CH_C: 201, PA: 192, PORT1: 193.2, PORT2: 193.2,
}
const ARM_REACH_IN = 81
const ARM_EXTEND_OUT = UNIT_DIST.CH_C - ARM_REACH_IN   // 兜底默认（CH_C）
function reachFor(unitKey) {
  return Math.round((UNIT_DIST[unitKey] ?? 200) - ARM_REACH_IN)
}

// 三段连杆几何（与 oxe-drm-topview.svg 的 ARM_UPPER / ARM_FORE / ARM_WRIST 一致）：
// 肩、肘各 90，腕关节收回时半径 40，叉端晶圆中心再外伸 41（= ARM_REACH_IN 81，晶圆在叉前端）。
// 折臂基态 α₀ = acos(40/180) ≈ 77.16°，伸直（α=0）即完全伸出（腕 180，晶圆 221）。
const LINK_LEN = 90
const WRIST_BASE_R = 40
const FORK_REACH = 41
const ALPHA_BASE = (Math.acos(WRIST_BASE_R / (LINK_LEN * 2)) * 180) / Math.PI

/**
 * 目标单元的三段关节角度（相对折臂基态的增量，单位 deg）
 * t1 肩、t2 肘（相对肩的两倍反向）、t3 腕（回正，保证叉始终朝径向）
 */
function linkAngles(unitKey, aliasKey = unitKey) {
  const dist = UNIT_DIST[unitKey] ?? 200
  const wristR = Math.min(LINK_LEN * 2, Math.max(WRIST_BASE_R, dist - FORK_REACH))
  const alpha = (Math.acos(wristR / (LINK_LEN * 2)) * 180) / Math.PI
  const t1 = ALPHA_BASE - alpha
  return {
    [`ARM_T1_${aliasKey}`]: t1.toFixed(2),
    [`ARM_T2_${aliasKey}`]: (2 * (alpha - ALPHA_BASE)).toFixed(2),
    [`ARM_T3_${aliasKey}`]: t1.toFixed(2),
  }
}

// 量产告警：bridge 会把描述词错填进 port_id/chamber_id（AGC / Light / Time / Out / Error…），
// 这些不是合法端口，端口归一必须拒绝并回退，否则一条告警会把后续事件的 lastPort 带偏
const VALID_PORT_RE = /^(PORT)?[12]$|^SMIF[_-]?[12]$/

function normalizeChamber(val) {
  const s = String(val ?? '').trim().toUpperCase()
  const m = s.match(/^CHAMBER[_-]?([ABC])$/)
  if (m) return m[1]
  if (['A', 'B', 'C'].includes(s)) return s
  return ''
}

function normalizePort(val) {
  const s = String(val ?? '').trim().toUpperCase()
  if (!VALID_PORT_RE.test(s)) return ''
  if (s.includes('2')) return '2'
  return '1'
}

function pick(src, ...keys) {
  for (const k of keys) {
    const v = src?.[k]
    if (v !== undefined && v !== null && v !== '' && String(v).toUpperCase() !== 'NULL') return v
  }
  return ''
}

/** mapping 值 → 25 位 0/1/2/3 串（只保留这些字符，缺补 0），无值返回 '' */
function parseSlotMap(raw) {
  const s = String(raw ?? '').replace(/[^0-3]/g, '')
  if (!s) return ''
  return (s + '0'.repeat(25)).slice(0, 25)
}

/** mapping 事件值的取值键（移植旧 Canvas 看板 getWaferMappingValue） */
function mappingValueOf(src) {
  return pick(src, 'EVENT_VALUE', 'event_value', 'EVENTVALUE', 'eventvalue',
    'EventValue', 'mapping_value', 'MAPPING_VALUE', 'alarm_text', 'ALARM_TEXT', 'ALTX')
}

export default { name: 'oxe', factory: createOxeDeriver }

export function createOxeDeriver() {
  let lastPort = '1'
  // 每端口槽位状态：0 空 / 1 等待 / 2 加工 / 3 完成
  const slotState = { 1: new Array(25).fill(0), 2: new Array(25).fill(0) }
  // 每端口告警消息队列（最近 3 条，Motion JSON 写 ALARM_Px_L1..L3）与计数
  const alarms = { 1: [], 2: [] }
  const alarmCount = { 1: 0, 2: 0 }
  const doneCount = { 1: 0, 2: 0 }
  // 每端口当前 LOT（POD_REMOVED 清空）
  const lotOf = { 1: '', 2: '' }

  function resolvePort(payload, eventName) {
    const name = String(eventName || '').toUpperCase()
    // STARTMAPPING_LEFT/RIGHT 显式指定映射端口
    if (name === 'STARTMAPPING_LEFT') return '1'
    if (name === 'STARTMAPPING_RIGHT') return '2'
    const direct = normalizePort(pick(payload, 'PORT', 'port_id', 'portid', 'PORTID', 'port_no'))
    if (direct) return direct
    const smif = normalizePort(pick(payload, 'SMIF_ID', 'smif_id', 'SMIFPORTID'))
    if (smif) return smif
    const ch = normalizeChamber(pick(payload, 'CHAMBER', 'chamber_id', 'chamber'))
    if (ch === 'A' || ch === 'C') return '1'
    if (ch === 'B') return '2'
    return lastPort
  }

  function resolveChamber(payload, port) {
    const ch = normalizeChamber(pick(payload, 'CHAMBER', 'chamber_id', 'chamber'))
    if (ch) return ch
    // 缺腔时按端口默认（移植旧看板：1→A，2→B）
    return port === '2' ? 'B' : 'A'
  }

  /** 告警归属端口：显式端口优先；LOT 归属次之；告警描述词 P1/P2；否则沿用上一端口 */
  function resolveAlarmPort(src) {
    const direct = normalizePort(pick(src, 'PORT', 'port_id', 'portid', 'PORTID',
      'SMIF_ID', 'smif_id', 'SMIFPORTID'))
    if (direct) return direct
    const lot = String(pick(src, 'LOT_ID', 'lot_id', 'lot') || '').trim().toUpperCase()
    if (lot && lot === lotOf[1].toUpperCase()) return '1'
    if (lot && lot === lotOf[2].toUpperCase()) return '2'
    const txt = String(mappingValueOf(src) || '').toUpperCase()
    if (txt === 'P2') return '2'
    if (txt === 'P1') return '1'
    return lastPort
  }

  function slotNo(src) {
    const raw = Number(pick(src, 'SLOT', 'slot', 'slot_id', 'wafer_id') || 1)
    return Math.min(25, Math.max(1, Number.isFinite(raw) ? Math.floor(raw) : 1))
  }

  function reset() {
    lastPort = '1'
    slotState[1] = new Array(25).fill(0)
    slotState[2] = new Array(25).fill(0)
    alarms[1] = []
    alarms[2] = []
    alarmCount[1] = 0
    alarmCount[2] = 0
    doneCount[1] = 0
    doneCount[2] = 0
    lotOf[1] = ''
    lotOf[2] = ''
  }

  return {
    derive(step, payload) {
      const src = payload || {}
      const eventName = String(pick(src, 'event_name', 'event_code') || step || '').toUpperCase()
      const port = resolvePort(src, eventName)
      const ch = resolveChamber(src, port)
      const slot = slotNo(src)
      const stateVal = String(pick(src, 'state', 'machine_state') || '').toUpperCase()
      const transferStage = String(pick(src, 'transfer_stage', 'action') || '').toUpperCase()

      // ===== 状态机推进（derive 即事件处理点；commit 只做 lastPort 记忆） =====
      if (eventName === 'POD_PLACED') {
        slotState[port] = new Array(25).fill(1)
        alarms[port] = []
        alarmCount[port] = 0
        doneCount[port] = 0
        lotOf[port] = ''
      } else if (eventName === 'WAFER_MAPPING' || eventName === 'ENDMAPPING') {
        const smap = parseSlotMap(mappingValueOf(src))
        if (smap) {
          slotState[port] = smap.split('').map(c => Number(c))
          // mapping 后完成计数与映射串对齐（可能携带历史 3 态）
          doneCount[port] = slotState[port].filter(v => v === 3).length
        }
      } else if (eventName === 'BATCH_INFO_FROM_ECUI') {
        const lot = String(pick(src, 'LOT_ID', 'lot_id', 'lot') || '').trim()
        if (lot) lotOf[port] = lot
      } else if (eventName === 'WAFERLOADED') {
        slotState[port][slot - 1] = 2
      } else if (eventName === 'WAFERUNLOADED') {
        if (slotState[port][slot - 1] !== 3) {
          slotState[port][slot - 1] = 3
          doneCount[port] += 1
        }
      } else if (eventName === 'POD_REMOVED' || eventName === 'MOC') {
        slotState[port] = new Array(25).fill(0)
        alarms[port] = []
        alarmCount[port] = 0
        doneCount[port] = 0
        lotOf[port] = ''
      }

      // 告警队列（ALARM/EC_ALARM_REPORT 经别名统一到 ALARM_REPORT；裸 ALARM 事件同样处理）
      let alarmPort = ''
      if (eventName === 'ALARM_REPORT' || eventName === 'ALARM' || eventName === 'EC_ALARM_REPORT') {
        alarmPort = resolveAlarmPort(src)
        alarmCount[alarmPort] += 1
        const text = String(pick(src, 'alarm_text', 'ALARM_TEXT', 'alarm_id', 'ALID',
          'EVENT_VALUE', 'event_value') || 'ALARM').slice(0, 22)
        const hhmm = (() => {
          const ts = pick(src, 'timestamp', 'event_ts_utc', 'TIMESTAMP')
          const m = String(ts || '').match(/(\d{2}:\d{2})(?::\d{2})?/)
          return m ? m[1] : ''
        })()
        alarms[alarmPort].unshift(`${hhmm ? hhmm + ' ' : ''}${text}`)
        if (alarms[alarmPort].length > 3) alarms[alarmPort].length = 3
      }

      // ===== 参数产出 =====
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
        // 外臂径向伸出量（ARM_EXTEND offset_x）：各单元中心距离不同，分别给出
        ARM_EXTEND_PORT: String(reachFor(port === '2' ? 'PORT2' : 'PORT1')),
        ARM_EXTEND_PA: String(reachFor('PA')),
        ARM_EXTEND_CH: String(reachFor(`CH_${ch}`)),
        // 兼容旧引用（默认伸出量）
        ARM_EXTEND_OUT: String(reachFor(`CH_${ch}`)),
        // 三段连杆关节角（ARM_UPPER / ARM_FORE / ARM_WRIST 的 rotate 目标角）
        ...linkAngles(`PORT${port}`, 'PORT'),
        ...linkAngles('PA'),
        ...linkAngles(`CH_${ch}`, 'CH'),
        // 面板：完成计数（{DONE_COUNT} 文本模板）
        DONE_COUNT: `${doneCount[port]}/25`,
        // 面板：告警归属 + 计数 + 最近 3 行
        ALARM_PORT: alarmPort,
        ALARM_COUNT: String(alarmPort ? alarmCount[alarmPort] : 0),
        AL1: alarmPort ? alarms[alarmPort][0] || '' : '',
        AL2: alarmPort ? alarms[alarmPort][1] || '' : '',
        AL3: alarmPort ? alarms[alarmPort][2] || '' : '',
      }
      // 面板：mapping 逐槽字符 SM01..SM25（when 白名单不允许 []，下标必须在 deriver 展开）
      const smap = slotState[port].map(v => String(v)).join('')
      for (let i = 0; i < 25; i += 1) {
        params[`SM${String(i + 1).padStart(2, '0')}`] = smap[i] || '0'
      }
      return { ok: true, params, info: { port, chamber: ch, slot } }
    },

    commit(step, params) {
      if (params?.PORT === '1' || params?.PORT === '2') lastPort = params.PORT
    },

    reset,
  }
}
