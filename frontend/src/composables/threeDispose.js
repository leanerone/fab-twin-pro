// Three.js 资源释放公共工具
//
// 2026-10-29 建立。仓库里 3 个 3D 组件共 288 处 new THREE.*，卸载时都只调用了
// renderer.dispose()，geometry / material / CanvasTexture 全部泄漏；
// OrbitControls 全仓从未 dispose（挂载在 canvas 上的监听残留）。
// 长时间挂机看板场景下，反复切换页面会导致显存持续增长直至标签页崩溃。

/**
 * 深度释放一个对象及其子树上的 geometry / material / texture
 * @param {THREE.Object3D|null} root
 * @returns {{geometry:number, material:number, texture:number}} 释放计数
 */
export function disposeObject3D(root) {
  const stats = { geometry: 0, material: 0, texture: 0 }
  if (!root) return stats

  const seenGeo = new Set()
  const seenMat = new Set()

  root.traverse((obj) => {
    if (obj.geometry && !seenGeo.has(obj.geometry)) {
      seenGeo.add(obj.geometry)
      obj.geometry.dispose()
      stats.geometry++
    }

    const mats = Array.isArray(obj.material) ? obj.material : obj.material ? [obj.material] : []
    for (const mat of mats) {
      if (seenMat.has(mat)) continue
      seenMat.add(mat)
      // 材质上挂着的所有贴图（map / normalMap / alphaMap ...）
      for (const key of Object.keys(mat)) {
        const val = mat[key]
        if (val && val.isTexture && typeof val.dispose === 'function') {
          val.dispose()
          stats.texture++
        }
      }
      if (typeof mat.dispose === 'function') {
        mat.dispose()
        stats.material++
      }
    }
  })

  // 从父节点摘除，断开引用链
  if (root.parent) root.parent.remove(root)
  return stats
}

/**
 * 完整释放一个 Three.js 场景：场景内容 + renderer + controls + 渲染循环
 * @param {object} ctx { scene, renderer, controls, rafId }
 */
export function disposeScene(ctx = {}) {
  const { scene, renderer, controls, rafId } = ctx
  let stats = { geometry: 0, material: 0, texture: 0 }

  if (rafId !== null && rafId !== undefined) {
    cancelAnimationFrame(rafId)
  }

  if (controls && typeof controls.dispose === 'function') {
    controls.dispose()
  }

  if (scene) {
    stats = disposeObject3D(scene)
    if (typeof scene.clear === 'function') scene.clear()
  }

  if (renderer) {
    if (typeof renderer.dispose === 'function') renderer.dispose()
    // 释放 WebGL 上下文，部分浏览器靠这一步才真正归还显存
    try {
      const gl = renderer.getContext && renderer.getContext()
      const ext = gl && gl.getExtension && gl.getExtension('WEBGL_lose_context')
      if (ext) ext.loseContext()
    } catch (_) { /* 忽略：非 WebGL 渲染器没有这些方法 */ }
  }

  return stats
}
