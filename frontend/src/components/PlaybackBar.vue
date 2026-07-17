<script setup>
import { ref, computed } from 'vue'

// 回放控制条：实时/回放切换 + 日期 + 播放 + 倍速 + 时间轴
const props = defineProps({
  // realtime / playback
  mode: { type: String, default: 'realtime' },
  // 是否正在播放
  playing: { type: Boolean, default: false },
  // 倍速
  speed: { type: Number, default: 1 },
  // 回放日期
  date: { type: String, default: '' },
  // 当前游标时间戳
  cursor: { type: Number, default: 0 },
  // 回放开始时间
  start: { type: Number, default: 0 },
  // 回放结束时间
  end: { type: Number, default: 0 },
})

const emit = defineEmits(['update:mode', 'update:playing', 'update:speed', 'update:date', 'seek'])

const speeds = [0.5, 1, 2, 4, 8, 16]

// 进度百分比
const progress = computed(() => {
  if (!props.end || props.end <= props.start) return 0
  const pct = ((props.cursor - props.start) / (props.end - props.start)) * 100
  return Math.max(0, Math.min(100, pct))
})

// 切换模式
function switchMode(newMode) {
  emit('update:mode', newMode)
}

// 切换播放/暂停
function togglePlay() {
  emit('update:playing', !props.playing)
}

// 选择倍速
function selectSpeed(s) {
  emit('update:speed', s)
}

// 日期变化
function onDateChange(e) {
  emit('update:date', e.target.value)
}

// 时间轴点击跳转
function onTrackClick(e) {
  const rect = e.currentTarget.getBoundingClientRect()
  const pct = (e.clientX - rect.left) / rect.width
  emit('seek', pct)
}

// 时间轴拖拽
function onTrackDrag(e) {
  if (e.buttons !== 1) return
  onTrackClick(e)
}

// 格式化时间显示
function formatTime(ts) {
  if (!ts) return '--:--:--'
  try {
    const d = new Date(ts)
    return d.toTimeString().slice(0, 8)
  } catch {
    return '--:--:--'
  }
}
</script>

<template>
  <div class="playback-bar" :class="{ show: mode === 'playback' }">
    <div class="pb-mode-switch">
      <button class="pb-mode-btn" :class="{ active: mode === 'realtime' }" @click="switchMode('realtime')">实时</button>
      <button class="pb-mode-btn" :class="{ active: mode === 'playback' }" @click="switchMode('playback')">回放</button>
    </div>
    <input type="date" class="pb-date" :value="date" @change="onDateChange" />
    <button v-if="mode === 'playback'" class="pb-play" @click="togglePlay">{{ playing ? '⏸' : '▶' }}</button>
    <div v-if="mode === 'playback'" class="pb-speeds">
      <button v-for="s in speeds" :key="s" :class="{ active: speed === s }" @click="selectSpeed(s)">{{ s }}x</button>
    </div>
    <div v-if="mode === 'playback'" class="pb-track" @click="onTrackClick" @mousemove="onTrackDrag">
      <div class="fill" :style="{ width: progress + '%' }"></div>
      <div class="knob" :style="{ left: progress + '%' }"></div>
    </div>
    <div v-if="mode === 'playback'" class="pb-time">{{ formatTime(cursor) }} / {{ formatTime(end) }}</div>
  </div>
</template>

<style scoped>
.playback-bar {
  position: absolute;
  bottom: 14px;
  left: 14px;
  right: 14px;
  background: rgba(13, 20, 36, 0.92);
  backdrop-filter: blur(10px);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 16px;
  display: none;
  align-items: center;
  gap: 14px;
  z-index: 10;
}
.playback-bar.show {
  display: flex;
}
.pb-mode-switch {
  display: flex;
  gap: 4px;
  background: var(--bg);
  border-radius: 6px;
  padding: 2px;
}
.pb-mode-btn {
  padding: 4px 10px;
  border: none;
  background: transparent;
  color: var(--text-dim);
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}
.pb-mode-btn.active {
  background: var(--accent);
  color: #000;
}
.pb-date {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 4px 8px;
  border-radius: 5px;
  font-size: 11px;
  font-family: monospace;
}
.pb-date:focus {
  border-color: var(--accent);
  outline: none;
}
.pb-play {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: none;
  background: var(--accent);
  color: #000;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
}
.pb-play:hover {
  opacity: 0.85;
}
.pb-speeds {
  display: flex;
  gap: 4px;
}
.pb-speeds button {
  padding: 3px 9px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-dim);
  border-radius: 4px;
  font-size: 11px;
}
.pb-speeds button.active {
  background: var(--accent);
  color: #000;
  border-color: var(--accent);
}
.pb-track {
  flex: 1;
  height: 5px;
  background: var(--bg);
  border-radius: 3px;
  position: relative;
  cursor: pointer;
}
.pb-track .fill {
  height: 100%;
  background: var(--accent);
  border-radius: 3px;
  width: 0%;
}
.pb-track .knob {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--accent);
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  left: 0%;
  box-shadow: 0 0 8px var(--accent);
}
.pb-time {
  font-size: 11px;
  color: var(--text-dim);
  font-family: monospace;
  min-width: 110px;
  text-align: right;
}
</style>
