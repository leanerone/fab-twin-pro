// 渲染循环统一管理：后台标签页自动暂停 + 组件卸载自动清理
//
// 2026-10-29 建立。此前仓库里有 5 处 requestAnimationFrame 循环各自实现：
//   FloorView3D / MachineModel3D / MachineVpo3DView / MachineDetail / FloorPlan
// 共同缺陷：① 页面切到后台仍满速空转 ② 部分没有 onUnmounted 清理。
// 数字孪生看板是长时间挂机场景，这两条直接决定 8 小时后浏览器是否还活得下去。

import { onUnmounted, onMounted } from 'vue'

/**
 * 创建一个受管的 rAF 循环
 * @param {(dt:number, elapsed:number) => void} callback 每帧回调，dt 为毫秒
 * @param {{autoStart?:boolean, pauseWhenHidden?:boolean}} options
 */
export function useRafLoop(callback, options = {}) {
  const { autoStart = true, pauseWhenHidden = true } = options

  let rafId = null
  let lastTs = 0
  let elapsed = 0
  let running = false

  function frame(ts) {
    if (!running) return
    const dt = lastTs ? ts - lastTs : 16.7
    lastTs = ts
    elapsed += dt
    try {
      callback(dt, elapsed)
    } catch (e) {
      console.error('[useRafLoop] 回调异常，循环已停止:', e)
      stop()
      return
    }
    rafId = requestAnimationFrame(frame)
  }

  function start() {
    if (running) return
    if (pauseWhenHidden && typeof document !== 'undefined' && document.hidden) {
      // 页面不可见时不启动，等 visibilitychange 再拉起
      return
    }
    running = true
    lastTs = 0
    rafId = requestAnimationFrame(frame)
  }

  function stop() {
    running = false
    if (rafId !== null) {
      cancelAnimationFrame(rafId)
      rafId = null
    }
  }

  function onVisibilityChange() {
    if (document.hidden) {
      stop()
    } else {
      start()
    }
  }

  onMounted(() => {
    if (pauseWhenHidden && typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisibilityChange)
    }
    if (autoStart) start()
  })

  onUnmounted(() => {
    stop()
    if (pauseWhenHidden && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  })

  return { start, stop, isRunning: () => running }
}

/**
 * 受管的定时器：自动在卸载时清理，并在后台标签页暂停。
 * 修 Dashboard.vue 里 setInterval 无句柄、无清理的问题。
 * @param {() => void} fn
 * @param {number} intervalMs
 */
export function useInterval(fn, intervalMs, options = {}) {
  const { pauseWhenHidden = true } = options
  let timer = null

  function start() {
    stop()
    if (pauseWhenHidden && typeof document !== 'undefined' && document.hidden) return
    timer = setInterval(fn, intervalMs)
  }

  function stop() {
    if (timer !== null) {
      clearInterval(timer)
      timer = null
    }
  }

  function onVisibilityChange() {
    if (document.hidden) stop()
    else start()
  }

  onMounted(() => {
    if (pauseWhenHidden && typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisibilityChange)
    }
    start()
  })

  onUnmounted(() => {
    stop()
    if (pauseWhenHidden && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  })

  return { start, stop }
}
