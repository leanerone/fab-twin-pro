<template>
  <div class="ai-floating-container">
    <button
      v-if="isMinimized"
      type="button"
      class="float-ball"
      :style="ballStyle"
      aria-label="打开 FabTwin AI 助手，也可拖拽移动"
      @pointerdown="onPointerDown"
      @click="handleClick"
    >
      <svg class="ball-icon" viewBox="0 0 32 32" fill="none" aria-hidden="true">
        <rect x="5" y="8" width="22" height="18" rx="5" stroke="currentColor" stroke-width="1.8"/>
        <path d="M16 8V4m-3 0h6M10 16h.01M22 16h.01M11 21c2.8 2 7.2 2 10 0" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
      <span class="ball-pulse"></span>
      <!-- R8：未读告警徽标 -->
      <span v-if="alarmUnread > 0" class="ball-alarm-badge">{{ alarmUnread > 99 ? '99+' : alarmUnread }}</span>
    </button>

    <div
      v-else
      class="float-panel"
      :class="{ 'is-fullscreen': isFullscreen }"
      :style="isFullscreen ? fullscreenStyle : panelStyle"
      role="dialog"
      aria-label="FabTwin AI 助手"
      @keydown.esc="close"
    >
      <div class="panel-header">
        <div class="panel-title">
          <svg class="panel-title-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <rect x="4" y="6" width="16" height="14" rx="4" stroke="currentColor" stroke-width="1.6"/>
            <path d="M12 6V3M8 12h.01M16 12h.01M8.5 16h7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
          </svg>
          <span>FabTwin AI</span>
        </div>
        <div class="panel-actions">
          <button type="button" class="action-btn" :title="isFullscreen ? '还原窗口' : '全屏'" :aria-label="isFullscreen ? '还原窗口' : '全屏'" @click="toggleFullscreen">
            <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M7 3H3v4m10-4h4v4M3 13v4h4m10-4v4h-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <button type="button" class="action-btn" title="最小化" aria-label="最小化" @click="minimize">
            <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M5 10h10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
          </button>
          <button type="button" class="action-btn close-btn" title="关闭" aria-label="关闭" @click="close">
            <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="m6 6 8 8m0-8-8 8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
          </button>
        </div>
      </div>
      <div class="panel-body">
        <AiAssistant ref="assistantRef" />
      </div>
    </div>

    <!-- R8：主动告警轻提示（右下角，8秒自散，点击打开 AI 面板） -->
    <Teleport to="body">
      <div class="alarm-toast-stack">
        <div
          v-for="t in alarmToasts"
          :key="t.id"
          class="alarm-toast"
          @click="openChatFromAlarm"
        >
          <span class="alarm-toast-icon">⚠️</span>
          <span class="alarm-toast-text">{{ t.text }}</span>
          <span class="alarm-toast-action">问 AI →</span>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import AiAssistant from './AiAssistant.vue'
import { useWebSocket } from '@/platform/frontend/core/composables/useWebSocket'

const ws = useWebSocket()

const isMinimized = ref(true)
const isFullscreen = ref(false)
const position = ref({ x: window.innerWidth - 90, y: window.innerHeight - 100 })
const assistantRef = ref(null)

const ballStyle = ref({ left: position.value.x + 'px', top: position.value.y + 'px' })
const panelStyle = ref({
  left: (position.value.x - 350) + 'px',
  top: (position.value.y - 420) + 'px',
  width: 'min(360px, calc(100vw - 24px))',
  height: 'min(480px, calc(100vh - 24px))'
})
const fullscreenStyle = {
  left: '50%',
  top: '50%',
  transform: 'translate(-50%, -50%)',
  width: 'min(640px, calc(100vw - 24px))',
  height: 'min(720px, calc(100vh - 24px))'
}

const isDragging = ref(false)
const dragStart = ref({ x: 0, y: 0 })
const ballStart = ref({ x: 0, y: 0 })
const dragDistance = ref(0)

function handleClick() {
  if (dragDistance.value > 5) { dragDistance.value = 0; return }
  isMinimized.value = false
  updatePanelPosition()
}
function minimize() { isMinimized.value = true }
function close() { isMinimized.value = true; isFullscreen.value = false }
function toggleFullscreen() { isFullscreen.value = !isFullscreen.value }
function updatePanelPosition() {
  const width = Math.min(360, window.innerWidth - 24)
  const height = Math.min(480, window.innerHeight - 24)
  const x = Math.max(12, Math.min(position.value.x - width + 48, window.innerWidth - width - 12))
  const y = Math.max(12, Math.min(position.value.y - height + 48, window.innerHeight - height - 12))
  panelStyle.value = { left: x + 'px', top: y + 'px', width: width + 'px', height: height + 'px' }
}
function onPointerDown(e) {
  if (e.button !== 0) return
  isDragging.value = true
  dragDistance.value = 0
  dragStart.value = { x: e.clientX, y: e.clientY }
  ballStart.value = { x: position.value.x, y: position.value.y }
  document.addEventListener('pointermove', onPointerMove)
  document.addEventListener('pointerup', onPointerUp)
}
function onPointerMove(e) {
  if (!isDragging.value) return
  const dx = e.clientX - dragStart.value.x
  const dy = e.clientY - dragStart.value.y
  dragDistance.value = Math.sqrt(dx * dx + dy * dy)
  position.value = {
    x: Math.max(12, Math.min(window.innerWidth - 68, ballStart.value.x + dx)),
    y: Math.max(12, Math.min(window.innerHeight - 68, ballStart.value.y + dy))
  }
  ballStyle.value = { left: position.value.x + 'px', top: position.value.y + 'px' }
}
function onPointerUp() {
  isDragging.value = false
  document.removeEventListener('pointermove', onPointerMove)
  document.removeEventListener('pointerup', onPointerUp)
}

// ==================== 主动告警通知（R8 2026-11-06） ====================
// 订阅 WS 原始事件流：告警发生且面板未展开时，球上挂未读徽标 + 右下角轻提示
//（从"人问 AI 答"向"AI 主动报"迈第一步）。ver3 合并：状态模型从 chatOpen/minimized
// 映射为本组件的 isMinimized（球=最小化，面板=展开）。

const alarmUnread = ref(0)
const alarmToasts = ref([])
let _alarmToastSeq = 0

function onRawAlarmEvent(evt) {
  if (!evt || !evt.is_alarm) return
  // 面板展开中：用户正在看 AI，不打扰（消息流里能看到）
  if (!isMinimized.value) return
  alarmUnread.value++
  const id = ++_alarmToastSeq
  const mid = evt.machine_id || evt.tool_id || ''
  const text = evt.alarm_text || evt.alarm_id || '告警'
  alarmToasts.value.push({ id, mid, text: `${mid} ${String(text).slice(0, 40)}` })
  if (alarmToasts.value.length > 3) alarmToasts.value.shift()
  setTimeout(() => {
    alarmToasts.value = alarmToasts.value.filter(t => t.id !== id)
  }, 8000)
}

function openChatFromAlarm() {
  alarmUnread.value = 0
  isMinimized.value = false
  updatePanelPosition()
}

onMounted(() => {
  ws.subscribeRawEvent(onRawAlarmEvent)
})

onUnmounted(() => {
  ws.unsubscribeRawEvent(onRawAlarmEvent)
  document.removeEventListener('pointermove', onPointerMove)
  document.removeEventListener('pointerup', onPointerUp)
})
</script>

<style scoped>
.ai-floating-container { position: fixed; z-index: var(--z-overlay); }
.float-ball {
  position: fixed;
  display: grid;
  place-items: center;
  width: 56px;
  height: 56px;
  padding: 0;
  background: #122337;
  border: 1px solid rgba(0, 212, 255, 0.45);
  border-radius: 50%;
  cursor: grab;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.36);
  touch-action: none;
  user-select: none;
}
.float-ball:active { cursor: grabbing; }
.float-ball:hover { background: #172b42; border-color: var(--accent); box-shadow: 0 8px 26px rgba(0, 0, 0, 0.4), 0 0 0 4px rgba(0, 212, 255, 0.06); }
.ball-icon { width: 31px; height: 31px; color: var(--accent); }
.ball-pulse { position: absolute; right: 3px; bottom: 3px; width: 10px; height: 10px; background: var(--green); border: 2px solid #122337; border-radius: 50%; }
/* R8：未读告警徽标 + 主动告警轻提示 */
.ball-alarm-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  min-width: 18px;
  height: 18px;
  line-height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: #ff4757;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  text-align: center;
  box-shadow: 0 2px 6px rgba(255, 71, 87, 0.5);
  animation: alarm-badge-pulse 1.6s ease-in-out infinite;
}
@keyframes alarm-badge-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.15); }
}
.alarm-toast-stack {
  position: fixed;
  right: 16px;
  bottom: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 9999;
}
.alarm-toast {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(30, 34, 44, 0.96);
  border: 1px solid #ff4757;
  border-radius: 8px;
  padding: 8px 12px;
  color: var(--text, #e8e8e8);
  font-size: 12px;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4);
  animation: alarm-toast-in 0.25s ease-out;
  max-width: 340px;
}
.alarm-toast:hover { border-color: #ff6b81; }
@keyframes alarm-toast-in {
  from { transform: translateX(24px); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}
.alarm-toast-icon { flex-shrink: 0; }
.alarm-toast-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.alarm-toast-action {
  flex-shrink: 0;
  color: var(--accent);
  font-size: 11px;
  font-weight: 600;
}
.float-panel {
  position: fixed;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--panel);
  border: 1px solid var(--border-2);
  border-radius: var(--radius-md);
  box-shadow: 0 18px 54px rgba(0, 0, 0, 0.48);
}
.float-panel.is-fullscreen { z-index: var(--z-overlay); }
.panel-header { display: flex; align-items: center; justify-content: space-between; min-height: 46px; padding: 0 10px 0 14px; background: #101d2c; border-bottom: 1px solid var(--border); }
.panel-title { display: flex; align-items: center; gap: 8px; color: var(--text); font-size: 13px; font-weight: 600; }
.panel-title-icon { width: 21px; height: 21px; color: var(--accent); }
.panel-actions { display: flex; align-items: center; gap: 2px; }
.action-btn { display: grid; place-items: center; width: 30px; height: 30px; padding: 0; color: var(--text-mute); background: transparent; border: 0; border-radius: var(--radius-sm); }
.action-btn svg { width: 17px; height: 17px; }
.action-btn:hover { color: var(--text); background: rgba(255, 255, 255, 0.06); }
.close-btn:hover { color: #fff; background: #dc2626; }
.panel-body { flex: 1; min-height: 0; overflow: hidden; }
@media (max-height: 600px) {
  .panel-header { min-height: 40px; }
}
</style>
