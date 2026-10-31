/**
 * Motion 参数推导器注册表
 *
 * 新机型上线：实现一个 deriver（derive/commit/reset），在此注册名字，
 * Motion JSON 的 ext.deriver 填同名即可绑定，前端无需改其他代码。
 */
import { createAmatMetsputDeriver } from './amatMetsput'
import { createPodopenerDeriver } from './podopener'
import { createOxeDeriver } from './oxe'
import { createLam2300Deriver, createClusterDeriver } from './lam2300'

const factories = {
  amat_metsput: createAmatMetsputDeriver,
  podopener: createPodopenerDeriver,
  oxe: createOxeDeriver,
  lam2300: createLam2300Deriver,
  // 六腔 cluster（2×Load Port + 6×PM），共用同一归一化工厂
  sym3: () => createClusterDeriver({ maxPort: 2, maxCh: 6 }),
  synapse: () => createClusterDeriver({ maxPort: 2, maxCh: 6 }),
}

const instances = new Map()

/**
 * 按名字取 deriver 实例（每机型单例，内部持有 lot/wafer 登记状态）
 * @param {string} name - Motion JSON ext.deriver
 * @returns {{ derive: Function, commit: Function, reset: Function } | null}
 */
export function getMotionDeriver(name) {
  if (!name) return null
  const factory = factories[name]
  if (!factory) return null
  if (!instances.has(name)) instances.set(name, factory())
  return instances.get(name)
}

export function registerMotionDeriver(name, factory) {
  factories[name] = factory
  instances.delete(name)
}

export function resetMotionDerivers() {
  for (const inst of instances.values()) inst?.reset?.()
}

export default { getMotionDeriver, registerMotionDeriver, resetMotionDerivers }
