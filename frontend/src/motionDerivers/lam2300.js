/**
 * LAM 2300（Lam cluster 刻蚀台）Motion 参数推导器
 *
 * 布局与契约照 models/build_lam2300.py：ATM 大气端（3×Load Port LP1..LP3 +
 * Aligner + 2×Buffer）→ 2×Airlock → 中央圆形 VTM → 4×PM（PM1..PM4）放射。
 * 事件词表复用 OXE 的 26 步标准集，Motion JSON 只用 {PORT}/{CH} 两个部件 id
 * 占位符（{PORT}_CST / {CH}_run 等），本 deriver 的核心职责是把 DB 事件
 * payload 归一成这两个参数：
 * - 端口归一 → LP1/LP2/LP3：port_id 实测取值 "1"/"2"（或 "NULL"），
 *   兼容 PORT1 / SMIF1 / LP2 / STATION 3 等写法；无法识别时沿用 lastPort
 *   （量产告警会把描述词错填进 port_id，必须拒绝，否则带偏后续事件）
 * - 腔体归一 → PM1..PM4：chamber_id 实测取值 "A"/"B"/"C"，
 *   映射 A→PM1 / B→PM2 / C→PM3 / D→PM4；PM1..PM4 写法直接透传
 * - 事件缺 port 时沿用 lastPort；缺 chamber 时按端口默认（LP1→PM1、LP2→PM2、
 *   LP3→PM3，与 OXE「1→A，2→B」同一约定）
 * - SLOT 夹取 1..25，STATE 大写透传（param_defaults 引用）
 */

const VALID_PORT_RE = /^(PORT)?([123])$|^SMIF[_-]?([123])$|^LP[_-]?([123])$|^STATION[_ -]?([123])$/

function normalizePort(val) {
  const s = String(val ?? '').trim().toUpperCase()
  if (!VALID_PORT_RE.test(s)) return ''
  const m = s.match(/([123])/)
  return m ? `LP${m[1]}` : ''
}

function normalizeChamber(val) {
  const s = String(val ?? '').trim().toUpperCase()
  if (!s || s === 'NULL') return ''
  // CHAMBER_A / CHAMBER-A → A（MachineMotion2D 已剥过一轮，这里兜底原始 payload）
  const m = s.match(/^CHAMBER[_-]?(.+)$/)
  const base = m ? m[1].trim() : s
  if (/^PM[1-4]$/.test(base)) return base
  const digit = base.match(/^[1-4]$/)
  if (digit) return `PM${digit[0]}`
  const letter = base.match(/^[A-D]$/)
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

export function createLam2300Deriver() {
  let lastPort = 'LP1'
  let lastCh = 'PM1'

  /** 告警等事件无端口：显式端口优先，否则沿用上一端口 */
  function resolvePort(src) {
    const direct = normalizePort(pick(src, 'PORT', 'port_id', 'portid', 'PORTID', 'port_no'))
    if (direct) return direct
    const smif = normalizePort(pick(src, 'SMIF_ID', 'smif_id', 'SMIFPORTID'))
    if (smif) return smif
    return lastPort
  }

  /** 腔体：显式 chamber 优先；缺省按端口映射（LP1→PM1、LP2→PM2、LP3→PM3） */
  function resolveChamber(src, port) {
    const ch = normalizeChamber(pick(src, 'CHAMBER', 'chamber_id', 'chamber', 'unit_id'))
    if (ch) return ch
    return { LP1: 'PM1', LP2: 'PM2', LP3: 'PM3' }[port] || lastCh
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
      if (/^LP[123]$/.test(params?.PORT || '')) lastPort = params.PORT
      if (/^PM[1-4]$/.test(params?.CH || '')) lastCh = params.CH
    },

    reset,
  }
}
