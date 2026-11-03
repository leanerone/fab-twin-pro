// 时间格式化纯函数（批次3自 MachineDetail.vue 抽出，零组件依赖）
// HistoryReplay.vue 内还有一份同名 parseTs 拷贝，第二批合并

export const HOUR_MS = 3600 * 1000
export const MAX_RANGE_MS = 12 * HOUR_MS

// 时间戳解析：统一处理东八区时间
// 后端返回的时间戳已去掉Z后缀，但需兼容历史数据可能带Z的情况
// 带Z的时间戳实际上是东八区时间被误标为UTC，需要去掉Z后按本地时间解析
export function parseTs(ts) {
  if (!ts) return 0
  const str = String(ts).trim()
  // 去掉Z后缀和时区偏移，按本地时间（东八区）解析
  const localStr = str.replace(/Z$/, '').replace(/[+-]\d{2}:\d{2}$/, '')
  const d = new Date(localStr)
  return isNaN(d.getTime()) ? 0 : d.getTime()
}

export function fmtHM(d) {
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export function hmToMs(hm) {
  const [h, m] = String(hm || '0:0').split(':').map(Number)
  return ((h || 0) * 3600 + (m || 0) * 60) * 1000
}

export function msToHM(ms) {
  const totalMin = Math.max(0, Math.floor(ms / 60000))
  return `${String(Math.floor(totalMin / 60)).padStart(2, '0')}:${String(totalMin % 60).padStart(2, '0')}`
}

export function fmtDateMs(ms) {
  const d = new Date(ms)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function fmtLocalTs(ms) {
  const d = new Date(ms)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
