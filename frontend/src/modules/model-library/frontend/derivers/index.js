/**
 * Motion 参数推导器注册表（批次5：import.meta.glob 自动发现）
 *
 * 新机型上线：在 derivers/ 下新建 .js 文件并 default 导出
 *   export default { name: '机型标识', factory: createXxxDeriver }
 * 一文件多形态用 aliases（如 lam2300 派生 sym3/synapse）：
 *   export default { name, factory, aliases: { sym3: () => createClusterDeriver({...}) } }
 * Motion JSON 的 ext.deriver 填同名即可绑定，注册表零编辑。
 */
const modules = import.meta.glob('./*.js', { eager: true })

const factories = {}
for (const [path, mod] of Object.entries(modules)) {
  const file = path.split('/').pop().replace(/\.js$/, '')
  if (file === 'index') continue
  // 约定一：default 导出 { name, factory, aliases? }
  if (mod.default && mod.default.name && mod.default.factory) {
    factories[mod.default.name] = mod.default.factory
    if (mod.default.aliases) Object.assign(factories, mod.default.aliases)
    continue
  }
  // 约定二：按文件名找 createXxxDeriver 导出
  const camel = file[0].toUpperCase() + file.slice(1)
  if (mod[`create${camel}Deriver`]) factories[file] = mod[`create${camel}Deriver`]
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

export function listDeriverNames() {
  return Object.keys(factories)
}

export default { getMotionDeriver, registerMotionDeriver, resetMotionDerivers, listDeriverNames }
