// 机台回放引擎（批次3自 MachineDetail.vue 抽出）
// 工厂接收组件的响应式状态与事件分发器，函数体为原实现逐字搬运；
// 仅两处适配：realtimeEventsInitialized / lastProcessedRealtimeTsMs 由组件
// let 改为 ref 传入（.value），卸载清理改为在本工厂内自注册 onUnmounted。
import { onUnmounted } from 'vue'
import { api } from '../api'
import { parseTs, msToHM, fmtDateMs, MAX_RANGE_MS } from './timeFormat.js'

// 回放区段一次最多拉多少条：量产数据量大，一次 5000 条会让后端逐条解析 CLOB、
// 前端再排序，首屏明显变慢
const PLAYBACK_EVENT_LIMIT = 2000
// 实时模式只拉最新多少条（实时画面不需要区段全量历史）
const REALTIME_EVENT_LIMIT = 200

export function useMachinePlayback(ctx) {
  const {
    mode, playing, speed, events, replayEvents, loading,
    playbackDate, playbackStartHM, playbackEndHM,
    playbackStart, playbackEnd, cursor, pendingJumpTs,
    machineId, motion2dRef,
    realtimeEventsInitialized, lastProcessedRealtimeTsMs,
    applyEventData, normalizeRange, setRangeAround,
  } = ctx

  let historyData = []
  let playbackIdx = 0
  let playbackTimer = null

  // 把 /history 返回的原始事件映射成回放面板期望的结构（升序）
  function mapEventList(resp) {
    const list = (resp?.events || []).map(e => ({
      ...e,
      machine_id: e.tool_id || machineId.value,
      event_code: e.event_name,
      description: e.description || e.event_name,
      _ts: parseTs(e.timestamp),
    }))
    list.sort((a, b) => a._ts - b._ts)
    return list
  }

  // 历史数据取数控制器（test31）：切换机台/日期/区段时取消上一个未完成的请求，
  // 防止慢响应乱序返回覆盖新数据（竞态）
  let historyAbort = null
  function newHistorySignal() {
    if (historyAbort) historyAbort.abort()
    historyAbort = new AbortController()
    return historyAbort.signal
  }

  // 拉取当前日期+时间区段的事件（升序）
  async function fetchRangeEvents() {
    const start = `${playbackDate.value}T${playbackStartHM.value}:00`
    const end = `${playbackDate.value}T${playbackEndHM.value}:59.999`
    const resp = await api.getHistory(machineId.value, {
      start_time: start,
      end_time: end,
      limit: PLAYBACK_EVENT_LIMIT,
    }, newHistorySignal())
    return mapEventList(resp)
  }

  // 拉取最新 N 条事件（实时模式用，不带时间区段）
  async function fetchLatestEvents() {
    const resp = await api.getHistory(machineId.value, { limit: REALTIME_EVENT_LIMIT }, newHistorySignal())
    return mapEventList(resp)
  }

  // === 回放模式 ===
  async function switchToPlayback() {
    mode.value = 'playback'
    stopPlayback()
    playing.value = false
    events.value = []
    // test31：加载前先清上一台机台/上一区段的事件列表，
    // 避免请求期间残留显示旧数据（切换机台时旧列表一直挂到新数据返回）
    replayEvents.value = []
    loading.value = true
    try {
      // 按所选日期+时间区段加载该区间历史事件
      const list = await fetchRangeEvents()
      historyData = list
      if (!list.length) {
        console.warn('所选时间段内无历史数据')
        playbackStart.value = 0
        playbackEnd.value = 0
        cursor.value = 0
        playbackIdx = 0
        replayEvents.value = []
        pendingJumpTs.value = ''
        return
      }
      playbackStart.value = list[0]._ts
      playbackEnd.value = list[list.length - 1]._ts
      cursor.value = playbackStart.value
      playbackIdx = 0
      // 区段事件列表交给回放面板（LOT 统计/事件列表/回放驱动）
      replayEvents.value = list
      // 加载历史数据后先初始化到起始位置，批量重建初始视觉状态
      seek(0)
      // 如果有等待中的跳转，执行它（覆盖上面seek(0)的位置）
      if (pendingJumpTs.value) {
        const ts = pendingJumpTs.value
        pendingJumpTs.value = ''
        doJump(ts)
      }
    } catch (e) {
      // 被新请求取消（切换机台/日期/区段）时保持静默，让新请求接管
      if (e && (e.name === 'AbortError' || e.name === 'TimeoutError')) return
      console.warn('回放数据加载失败:', e?.message || e)
      playbackStart.value = 0
      playbackEnd.value = 0
      cursor.value = 0
      replayEvents.value = []
    } finally {
      loading.value = false
    }
  }

  function switchToRealtime() {
    mode.value = 'realtime'
    stopPlayback()
    playing.value = false
    events.value = []
    // test31：同 switchToPlayback——加载前清残留，避免显示上一台机台的事件
    replayEvents.value = []
    // 重置回放状态
    cursor.value = 0
    playbackStart.value = 0
    playbackEnd.value = 0
    historyData = []
    playbackIdx = 0
    // 重置实时事件初始化标记
    realtimeEventsInitialized.value = false
    lastProcessedRealtimeTsMs.value = 0
    // 实时模式下回放面板展示最新事件（不驱动模型）
    // 只取最新 N 条：实时画面不需要区段全量历史，量产数据量下这是首屏快慢的关键
    loading.value = true
    fetchLatestEvents()
      .then(list => { replayEvents.value = list })
      .catch(e => {
        if (e && (e.name === 'AbortError' || e.name === 'TimeoutError')) return
        console.warn('实时事件加载失败:', e?.message || e)
      })
      .finally(() => { loading.value = false })
  }

  // 模式切换
  function onModeChange(newMode) {
    if (newMode === mode.value) return
    if (newMode === 'playback') {
      switchToPlayback()
    } else {
      switchToRealtime()
    }
  }

  // 播放/暂停
  function onPlayingChange(val) {
    playing.value = val
    if (val) {
      startPlaybackLoop()
    } else {
      stopPlayback()
    }
  }

  // 回放循环
  function startPlaybackLoop() {
    stopPlayback()
    if (mode.value !== 'playback') return
    playbackTimer = setTimeout(() => {
      if (!playing.value) return
      const targetTime = cursor.value + 800 * speed.value
      while (playbackIdx < historyData.length && historyData[playbackIdx]._ts <= targetTime) {
        applyEventData(historyData[playbackIdx])
        events.value.push(historyData[playbackIdx])
        if (events.value.length > 200) events.value.shift()
        playbackIdx++
      }
      cursor.value = Math.min(targetTime, playbackEnd.value)
      if (cursor.value >= playbackEnd.value) {
        playing.value = false
        return
      }
      startPlaybackLoop()
    }, 100)
  }

  function stopPlayback() {
    if (playbackTimer) {
      clearTimeout(playbackTimer)
      playbackTimer = null
    }
  }

  // 时间轴跳转（test31 拖拽重构）：
  // 拖动中只移动游标做轻量预览（进度条 + runState 跟随），mouseup 或静止
  // 200ms 后才做一次全量重放重建 —— 此前 30ms 防抖到期即从第 0 条重放全部
  // 最多 2000 条 applyEventData，拖 1 秒 ≈ 33 次全量重放，是拖拽卡顿主因
  let seekDebounceTimer = null
  function seek(pct, dragging) {
    if (!historyData.length) return

    // 跳转时暂停播放，避免自动开始播放
    if (playing.value) {
      playing.value = false
      stopPlayback()
    }

    const targetTime = playbackStart.value + pct * (playbackEnd.value - playbackStart.value)
    // 轻量预览：游标立即跟随
    cursor.value = targetTime

    if (dragging) {
      clearTimeout(seekDebounceTimer)
      seekDebounceTimer = setTimeout(() => commitSeek(targetTime), 200)
      return
    }
    clearTimeout(seekDebounceTimer)
    commitSeek(targetTime)
  }

  // 真正的跳转提交：重建目标时间点之前的全部事件状态（一次）
  function commitSeek(targetTime) {
    const idx = bisectLeft(historyData, targetTime, (e) => e._ts)
    playbackIdx = idx >= 0 ? idx : historyData.length

    // Motion2D 视图：回放 seek 后按新事件流重建状态
    motion2dRef.value?.resetReplayCursor?.()

    events.value = []

    const batchSize = 50
    let i = 0
    while (i < historyData.length && historyData[i]._ts <= targetTime) {
      applyEventData(historyData[i])
      events.value.push(historyData[i])
      i++
      if (i % batchSize === 0) {
        if (events.value.length > 200) events.value = events.value.slice(-200)
      }
    }
    if (events.value.length > 200) events.value = events.value.slice(-200)
    playbackIdx = i
  }

  function bisectLeft(arr, target, getKey) {
    let low = 0, high = arr.length
    while (low < high) {
      const mid = (low + high) >> 1
      if (getKey(arr[mid]) < target) {
        low = mid + 1
      } else {
        high = mid
      }
    }
    return low
  }

  // 探测指定日期的数据时间跨度（返回该日升序事件的首尾时间戳）
  // 用途：默认区段是「当前时刻往前 1 小时」，切到历史日期后该区段通常与
  // 当日数据没有交集，会表现为「只有当天能查到数据，前几天都查不到」
  async function probeDayRange(dateStr) {
    try {
      const resp = await api.getHistory(machineId.value, {
        start_time: `${dateStr}T00:00:00`,
        end_time: `${dateStr}T23:59:59`,
        limit: PLAYBACK_EVENT_LIMIT,
      })
      const list = mapEventList(resp)
      if (!list.length) return null
      return { start: list[0]._ts, end: list[list.length - 1]._ts }
    } catch {
      return null
    }
  }

  // 把时间区段设为覆盖给定数据跨度（首尾各留 1 分钟余量，并限制在所选日期内）。
  // 超过 12h 上限时保留结束端、向前收，与 normalizeRange 的处理保持一致
  function applyRangeToSpan(span) {
    const dayStart = new Date(`${playbackDate.value}T00:00:00`).getTime()
    const dayEnd = dayStart + 86400000 - 1
    let s = Math.max(dayStart, span.start - 60000)
    let e = Math.min(dayEnd, span.end + 60000)
    if (e - s > MAX_RANGE_MS) s = e - MAX_RANGE_MS
    if (s < dayStart) s = dayStart
    playbackStartHM.value = msToHM(s - dayStart)
    playbackEndHM.value = msToHM(e - dayStart)
  }

  // 日期变化：切换日期后重新加载。
  // 换到别的日期时先探测该日数据跨度并自动适配时间区段，避免沿用
  // 「最近 1 小时」区段导致查不到历史数据；同日期刷新（刷新按钮）则保持区段不变
  async function onDateChange(newDate) {
    if (!newDate) return
    const dateChanged = newDate !== playbackDate.value
    playbackDate.value = newDate
    if (dateChanged) {
      const span = await probeDayRange(newDate)
      if (span) applyRangeToSpan(span)
    }
    await switchToPlayback()
  }

  // 时间区段变化（开始/结束），最大跨度12小时
  function onStartTimeChange(v) {
    if (!v) return
    normalizeRange(v, playbackEndHM.value)
    switchToPlayback()
  }
  function onEndTimeChange(v) {
    if (!v) return
    normalizeRange(playbackStartHM.value, v)
    switchToPlayback()
  }

  // 倍速变化
  function onSpeedChange(s) {
    speed.value = s
  }

  // 跳转到指定时间：在当前区段内直接跳，否则调整区段后重新加载
  async function jumpToTime(payload) {
    if (!payload) return
    // T4 统一契约：AiAssistant 与悬浮球均传对象 { machine_id, timestamp }，兼容旧裸时间戳
    const ts = (typeof payload === 'object') ? payload.timestamp : payload
    if (!ts) return
    const target = parseTs(ts)
    if (!target) return
    const targetDate = fmtDateMs(target)
    const inRange = mode.value === 'playback' && targetDate === playbackDate.value &&
      playbackStart.value > 0 && playbackEnd.value > 0 &&
      target >= playbackStart.value && target <= playbackEnd.value
    if (inRange) {
      doJump(ts)
      return
    }
    if (targetDate !== playbackDate.value) {
      playbackDate.value = targetDate
    }
    setRangeAround(target)
    pendingJumpTs.value = String(ts)
    await switchToPlayback()
  }

  function doJump(ts) {
    if (!historyData.length) return
    const target = parseTs(ts)
    if (!target) return
    const clamped = Math.max(playbackStart.value, Math.min(playbackEnd.value, target))
    const pct = (clamped - playbackStart.value) / (playbackEnd.value - playbackStart.value)
    // 跳转前确保暂停
    playing.value = false
    stopPlayback()
    seek(pct)
  }

  // 回放历史事件（从历史回放面板触发）
  function onReplayEvent(ev) {
    if (!ev || !ev.timestamp) return
    // 切换到回放模式
    if (mode.value !== 'playback') {
      switchToPlayback().then(() => {
        doJump(ev.timestamp)
      })
    } else {
      doJump(ev.timestamp)
    }
  }

  // 泄漏修复（test31）：本引擎持有的定时器与未完成请求在卸载时统一清理。
  // （rAF 循环归 run 货状态机，由组件自身的 onUnmounted 负责）
  onUnmounted(() => {
    stopPlayback()
    if (seekDebounceTimer) {
      clearTimeout(seekDebounceTimer)
      seekDebounceTimer = null
    }
    // 取消未完成的历史请求，避免卸载后响应回来写已销毁的状态
    if (historyAbort) {
      historyAbort.abort()
      historyAbort = null
    }
  })

  return {
    fetchRangeEvents,
    fetchLatestEvents,
    switchToPlayback,
    switchToRealtime,
    onModeChange,
    onPlayingChange,
    seek,
    commitSeek,
    probeDayRange,
    onDateChange,
    onStartTimeChange,
    onEndTimeChange,
    onSpeedChange,
    jumpToTime,
    stopPlayback,
    onReplayEvent,
  }
}
