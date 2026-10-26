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
export function createPodopenerDeriver() {
  let cycle = 'PACKING'

  function normalizeRunMode(value) {
    const mode = String(value ?? '').trim().toUpperCase()
    if (mode.includes('UNPACK') || mode.includes('DETACH')) return 'UNPACKING'
    return 'PACKING'
  }

  return {
    derive(step, payload) {
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
