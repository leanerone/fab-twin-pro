/**
 * PODOPENER 开盖机 Motion 参数推导器
 *
 * 业务语义（移植自旧 MachineVpoView 的 ATTACH/DETACH 流程）：
 * - cycle（穿入/脱出）由 BATCH_INFO_FROM_ECUI 事件的 RunMode 参数决定，
 *   未收到批次信息前默认 PACKING；POD_REMOVED 后复位为 PACKING。
 * - cycle 决定 SVG 内 rules 分支：
 *   PACKING（穿入）：空 POD 从左侧进入，POD 上升后放置晶舟，满 POD 向右侧移出；
 *   UNPACKING（脱出）：满 POD 从右侧进入，POD 上升后移走晶舟，空 POD 向左侧移出。
 * - 纯状态推导，不产生几何参数（几何分支全部在 Motion JSON 的 when 里）。
 */
export default { name: 'podopener', factory: createPodopenerDeriver }

export function createPodopenerDeriver() {
  let cycle = 'PACKING'

  function normalizeRunMode(value) {
    const mode = String(value ?? '').trim().toUpperCase()
    if (mode.includes('UNPACK') || mode.includes('DETACH')) return 'UNPACKING'
    return 'PACKING'
  }

  /** 实机报文用 ATTACH_* / DETACH_* 前缀区分穿入与脱出（旧 MachineVpoView 同样按前缀分流）。 */
  function cycleFromEventName(name) {
    const s = String(name ?? '').trim().toUpperCase()
    if (s.startsWith('DETACH') || s.includes('UNPACK')) return 'UNPACKING'
    if (s.startsWith('ATTACH') || s.includes('PACK')) return 'PACKING'
    return null
  }

  return {
    derive(step, payload) {
      // 批次信息（BATCH_INFO_FROM_ECUI）到达前 cycle 还是上一轮的，POD_PLACED/OPEN_POD
      // 会按旧方向播错侧；先用事件名前缀定方向，保证穿入/脱出首帧方向正确。
      // DB 回放事件只有 event_code，WS/调试事件才有 event_name，两者都要看
      const hinted = cycleFromEventName(
        payload?.event_name ?? payload?.eventName ?? payload?.event_code)
      if (hinted) cycle = hinted
      const params = { ...(payload || {}), cycle }
      return { ok: true, params, info: { cycle } }
    },

    commit(step, params) {
      if (step === 'BATCH_INFO_FROM_ECUI') {
        cycle = normalizeRunMode(params?.RunMode)
      }
      if (step === 'POD_REMOVED') {
        cycle = 'PACKING'
      }
    },

    reset() {
      cycle = 'PACKING'
    },
  }
}
