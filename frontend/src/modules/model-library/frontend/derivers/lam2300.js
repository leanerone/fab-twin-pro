/**
 * Cluster 机型通用 Motion 参数推导器（LAM2300 / Centris Sym3 / TEL Synapse 共用）
 *
 * 布局照各机台 build_*.py：ATM 大气端（Load Port LP1..LPn + Aligner + EFEM）
 * → 中央真空传输腔（VTM/TM/ESC）→ PM1..PMm 放射。事件词表复用 OXE 26 步
 * 标准集，Motion JSON 只用 {PORT}/{CH} 两个部件 id 占位符（{PORT}_CST /
 * {CH}_run 等），本 deriver 的核心职责是把 DB 事件 payload 归一成这两个参数：
 * - 端口归一 → LP1..LPn：port_id 实测取值 "1"/"2"（或 "NULL"），
 *   兼容 PORT1 / SMIF1 / LP2 / STATION 3 等写法；无法识别时沿用 lastPort
 *   （量产告警会把描述词错填进 port_id，必须拒绝，否则带偏后续事件）
 * - 腔体归一 → PM1..PMm：chamber_id 实测取值 "A"/"B"/"C"，
 *   映射 A→PM1 / B→PM2 / …（六腔机到 F→PM6）；PM1..PMm 写法直接透传
 * - 事件缺 port 时沿用 lastPort；缺 chamber 时按端口默认（LP1→PM1、LP2→PM2…）
 * - SLOT 夹取 1..25，STATE 大写透传（param_defaults 引用）
 *
 * @param {{ maxPort?: number, maxCh?: number }} opts
 */
export function createClusterDeriver({ maxPort = 3, maxCh = 4 } = {}) {
  const portSet = Array.from({ length: maxPort }, (_, i) => i + 1).join('')
  const chLetters = Array.from({ length: maxCh }, (_, i) => String.fromCharCode(65 + i)).join('')

  const VALID_PORT_RE = new RegExp(
    `^(PORT)?([${portSet}])$|^SMIF[_-]?([${portSet}])$|^LP[_-]?([${portSet}])$|^STATION[_ -]?([${portSet}])$`
  )

  function normalizePort(val) {
    const s = String(val ?? '').trim().toUpperCase()
    if (!VALID_PORT_RE.test(s)) return ''
    const m = s.match(/([\d])/)
    return m ? `LP${m[1]}` : ''
  }

  function normalizeChamber(val) {
    const s = String(val ?? '').trim().toUpperCase()
    if (!s || s === 'NULL') return ''
    // CHAMBER_A / CHAMBER-A → A（MachineMotion2D 已剥过一轮，这里兜底原始 payload）
    const m = s.match(/^CHAMBER[_-]?(.+)$/)
    const base = m ? m[1].trim() : s
    const pm = base.match(/^PM(\d+)$/)
    if (pm && Number(pm[1]) >= 1 && Number(pm[1]) <= maxCh) return base
    const digit = base.match(/^[1-9]$/)
    if (digit && Number(digit[0]) <= maxCh) return `PM${digit[0]}`
    const letter = base.match(new RegExp(`^[${chLetters}]$`))
    if (letter) return `PM${letter[0].charCodeAt(0) - 64}`
    return ''
  }

  function pick(src, ...keys) {
    for (const k of keys) {
      const v = src?.[k]
      if (v !== undefined && v !== null && v !== '' && String(v).toUpperCase() !== 'NULL') return v
    }
    return ''
  }

  let lastPort = 'LP1'
  let lastCh = 'PM1'
  const portDefaultCh = Object.fromEntries(
    Array.from({ length: Math.min(maxPort, maxCh) }, (_, i) => [`LP${i + 1}`, `PM${i + 1}`])
  )

  /** 告警等事件无端口：显式端口优先，否则沿用上一端口 */
  function resolvePort(src) {
    const direct = normalizePort(pick(src, 'PORT', 'port_id', 'portid', 'PORTID', 'port_no'))
    if (direct) return direct
    const smif = normalizePort(pick(src, 'SMIF_ID', 'smif_id', 'SMIFPORTID'))
    if (smif) return smif
    return lastPort
  }

  /** 腔体：显式 chamber 优先；缺省按端口映射（LP1→PM1、LP2→PM2…） */
  function resolveChamber(src, port) {
    const ch = normalizeChamber(pick(src, 'CHAMBER', 'chamber_id', 'chamber', 'unit_id'))
    if (ch) return ch
    return portDefaultCh[port] || lastCh
  }

  function slotNo(src) {
    const raw = Number(pick(src, 'SLOT', 'slot', 'slot_id', 'wafer_id') || 1)
    return Math.min(25, Math.max(1, Number.isFinite(raw) ? Math.floor(raw) : 1))
  }

  function reset() {
    lastPort = 'LP1'
    lastCh = 'PM1'
  }

  return {
    derive(step, payload) {
      const src = payload || {}
      const port = resolvePort(src)
      const ch = resolveChamber(src, port)
      const slot = slotNo(src)
      const stateVal = String(pick(src, 'state', 'machine_state') || '').toUpperCase()

      const params = {
        ...src,
        // 归一化业务参数（resolveMotionRule 用它们展开 {PORT}_CST / {CH}_run 等）
        PORT: port,
        CH: ch,
        SLOT: String(slot),
        STATE: stateVal,
        LOT_ID: pick(src, 'LOT_ID', 'lot_id', 'lot'),
      }
      return { ok: true, params, info: { port, chamber: ch, slot } }
    },

    commit(step, params) {
      if (new RegExp(`^LP[${portSet}]$`).test(params?.PORT || '')) lastPort = params.PORT
      if (/^PM\d+$/.test(params?.CH || '') && Number(params.CH.slice(2)) <= maxCh) lastCh = params.CH
    },

    reset,
  }
}

export default {
  name: 'lam2300',
  factory: createLam2300Deriver,
  // 六腔 cluster（2×Load Port + 6×PM），共用同一归一化工厂
  aliases: {
    sym3: () => createClusterDeriver({ maxPort: 2, maxCh: 6 }),
    synapse: () => createClusterDeriver({ maxPort: 2, maxCh: 6 }),
  },
}

export function createLam2300Deriver() {
  // LAM 2300：3×Load Port + 4×PM
  return createClusterDeriver({ maxPort: 3, maxCh: 4 })
}
