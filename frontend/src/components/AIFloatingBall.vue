<script setup>
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import VoiceInput from './VoiceInput.vue'

const STORAGE_KEY = 'fabtwin_ai_floating_session'
const POSITION_KEY = 'fabtwin_ai_floating_pos'
const SIZE_KEY = 'fabtwin_ai_floating_size'

const emit = defineEmits(['jump'])
const route = useRoute()

// 状态
const chatOpen = ref(false)
const minimized = ref(false)

// 当前路由对应的机台ID（用于AI跳转时定位）
const currentMachineId = ref('')
watch(
  () => route,
  (r) => {
    // 兼容 /machine/:id 和 /floor/:floor/machine/:id 等
    const params = r.params || {}
    currentMachineId.value = params.id || params.machineId || ''
  },
  { immediate: true, deep: true }
)

// 位置和尺寸
const ballPos = ref({ x: 20, y: 100 })
const chatPos = ref({ x: 0, y: 0 })
const chatSize = ref({ w: 420, h: 580 })

// 聊天
const messages = ref([])
const input = ref('')
const chatLogRef = ref(null)
const loading = ref(false)
const sessionId = ref(null)
const voiceInputRef = ref(null)
const voiceOutputRef = ref(null)
const isRecording = ref(false)
const interimText = ref('')

// 当前AI配置与模型切换
const currentConfig = ref({ name: '本地规则引擎', provider_name: '本地规则引擎', model: '', config_id: null })
const showModelSelector = ref(false)
const availableConfigs = ref([])

// 拖拽
const isDragging = ref(false)
const dragTarget = ref(null) // 'ball' | 'header' | 'resize'
const dragStart = ref({ x: 0, y: 0, posX: 0, posY: 0, w: 0, h: 0 })

// 快捷问题
const suggestions = [
  '当前厂线状态',
  '今日报警统计',
  '产量是多少',
  'PODOPENER-1状态',
  '查询LOT12345',
]

// ==================== 生命周期 ====================

onMounted(() => {
  // 恢复位置
  const savedPos = localStorage.getItem(POSITION_KEY)
  if (savedPos) {
    try {
      const pos = JSON.parse(savedPos)
      ballPos.value = pos
    } catch (e) {}
  } else {
    // 默认右下角
    ballPos.value = {
      x: window.innerWidth - 80,
      y: window.innerHeight - 120,
    }
  }

  // 恢复尺寸
  const savedSize = localStorage.getItem(SIZE_KEY)
  if (savedSize) {
    try {
      chatSize.value = JSON.parse(savedSize)
    } catch (e) {}
  }

  // 恢复会话
  const savedSession = localStorage.getItem(STORAGE_KEY)
  if (savedSession) {
    try {
      const data = JSON.parse(savedSession)
      messages.value = data.messages || []
      sessionId.value = data.sessionId || null
    } catch (e) {}
  }

  // 加载当前AI配置
  loadCurrentConfig()

  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
})

onUnmounted(() => {
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
})

// ==================== AI配置管理 ====================

async function loadCurrentConfig() {
  try {
    const res = await api.aiGetProviders()
    currentConfig.value = {
      name: res.current_name || '本地规则引擎',
      provider_name: res.current_name || '本地规则引擎',
      model: res.current || '',
      config_id: res.current_config_id || null,
    }
  } catch (e) {
    console.error('加载当前AI配置失败', e)
  }
}

async function loadAvailableConfigs() {
  try {
    const res = await api.aiGetModelConfigs()
    availableConfigs.value = res.configs || []
  } catch (e) {
    console.error('加载AI配置列表失败', e)
  }
}

async function selectConfig(configId) {
  try {
    await api.aiSwitchModelConfig(configId)
    await loadCurrentConfig()
    await loadAvailableConfigs()
    showModelSelector.value = false
  } catch (e) {
    console.error('切换配置失败', e)
  }
}

function toggleModelSelector() {
  showModelSelector.value = !showModelSelector.value
  if (showModelSelector.value) {
    loadAvailableConfigs()
  }
}

// ==================== 会话持久化 ====================

watch([messages, sessionId], () => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({
    messages: messages.value,
    sessionId: sessionId.value,
  }))
}, { deep: true })

// ==================== 拖拽逻辑 ====================

function startDrag(e, target) {
  isDragging.value = true
  dragTarget.value = target
  dragStart.value = {
    x: e.clientX,
    y: e.clientY,
    posX: target === 'ball' ? ballPos.value.x : chatPos.value.x,
    posY: target === 'ball' ? ballPos.value.y : chatPos.value.y,
    w: chatSize.value.w,
    h: chatSize.value.h,
  }
  e.preventDefault()
}

function onMouseMove(e) {
  if (!isDragging.value) return

  const dx = e.clientX - dragStart.value.x
  const dy = e.clientY - dragStart.value.y

  if (dragTarget.value === 'ball') {
    ballPos.value = {
      x: Math.max(10, Math.min(window.innerWidth - 60, dragStart.value.posX + dx)),
      y: Math.max(10, Math.min(window.innerHeight - 60, dragStart.value.posY + dy)),
    }
    localStorage.setItem(POSITION_KEY, JSON.stringify(ballPos.value))
  } else if (dragTarget.value === 'header') {
    chatPos.value = {
      x: Math.max(0, Math.min(window.innerWidth - 200, dragStart.value.posX + dx)),
      y: Math.max(0, Math.min(window.innerHeight - 100, dragStart.value.posY + dy)),
    }
  } else if (dragTarget.value === 'resize') {
    chatSize.value = {
      w: Math.max(320, Math.min(800, dragStart.value.w + dx)),
      h: Math.max(400, Math.min(900, dragStart.value.h + dy)),
    }
    localStorage.setItem(SIZE_KEY, JSON.stringify(chatSize.value))
  }
}

function onMouseUp() {
  isDragging.value = false
  dragTarget.value = null
}

// ==================== 聊天逻辑 ====================

function toggleChat() {
  chatOpen.value = !chatOpen.value
  if (chatOpen.value) {
    minimized.value = false
    // 聊天窗口位置在AI球旁边
    chatPos.value = {
      x: Math.max(10, Math.min(window.innerWidth - chatSize.value.w - 10, ballPos.value.x - chatSize.value.w - 10)),
      y: Math.max(10, Math.min(window.innerHeight - chatSize.value.h - 10, ballPos.value.y - chatSize.value.h + 30)),
    }
    // 每次打开聊天窗口时刷新当前配置
    loadCurrentConfig()
    nextTick(() => {
      scrollToBottom()
    })
  }
}

function minimizeChat() {
  minimized.value = true
}

function restoreChat() {
  minimized.value = false
  nextTick(() => scrollToBottom())
}

function closeChat() {
  chatOpen.value = false
  minimized.value = false
}

async function sendMessage(text) {
  const q = (text || input.value || '').trim()
  if (!q || loading.value) return
  input.value = ''

  messages.value.push({
    role: 'user',
    content: q,
    time: new Date().toLocaleTimeString(),
  })

  await nextTick()
  scrollToBottom()

  loading.value = true
  try {
    const resp = await api.aiChat({
      question: q,
      session_id: sessionId.value,
      user_role: 'user',
      config_id: currentConfig.value.config_id,
      machine_id: currentMachineId.value || null,
    })

    sessionId.value = resp.session_id || sessionId.value

    messages.value.push({
      role: 'assistant',
      content: resp.answer,
      sql: resp.sql,
      jump_timestamp: resp.jump_timestamp,
      jump_machine_id: resp.jump_machine_id,
      machine_online: resp.machine_online,
      table_data: resp.table_data,
      tool_calls: resp.tool_calls,
      sources: resp.sources,
      provider_name: resp.provider_name,
      model: resp.model,
      config_id: resp.config_id,
      usage: resp.usage,
      time: new Date().toLocaleTimeString(),
    })
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: '抱歉，请求失败：' + (e.message || '未知错误'),
      provider_name: '系统',
      time: new Date().toLocaleTimeString(),
    })
  } finally {
    loading.value = false
    await nextTick()
    scrollToBottom()
  }
}

function onSpeechResult(text) {
  input.value = text
  interimText.value = ''
}

function onSpeechInterim(text) {
  interimText.value = text
}

function onSpeechStart() {
  isRecording.value = true
  interimText.value = ''
}

function onSpeechEnd() {
  isRecording.value = false
}

function onSpeechError(msg) {
  isRecording.value = false
  interimText.value = ''
  console.warn('[语音] 错误:', msg)
}

function scrollToBottom() {
  if (chatLogRef.value) {
    chatLogRef.value.scrollTop = chatLogRef.value.scrollHeight
  }
}

function clearChat() {
  if (confirm('确定要清空对话记录吗？')) {
    messages.value = []
    sessionId.value = null
    localStorage.removeItem(STORAGE_KEY)
  }
}

function jumpToTime(payload, machineOnline = null) {
  // payload: { machine_id, timestamp } 或 兼容纯字符串时间戳
  if (!payload) return
  const enriched = typeof payload === 'string'
    ? { machine_id: currentMachineId.value, timestamp: payload, machine_online: machineOnline }
    : { ...payload, machine_online: machineOnline }
  emit('jump', enriched)
}
</script>

<template>
  <!-- AI 悬浮球（聊天窗口关闭或最小化时显示） -->
  <div
    v-if="!chatOpen || minimized"
    class="ai-floating-ball"
    :style="{ left: ballPos.x + 'px', top: ballPos.y + 'px' }"
    @mousedown="startDrag($event, 'ball')"
    @click="minimized ? restoreChat() : toggleChat()"
  >
    <div class="ball-inner">
      <span class="ball-icon">🤖</span>
      <span class="ball-pulse"></span>
    </div>
    <div class="ball-tooltip">AI 助手</div>
  </div>

  <!-- 聊天窗口 -->
  <Teleport to="body">
    <div
      v-if="chatOpen && !minimized"
      class="ai-chat-window"
      :style="{
        left: chatPos.x + 'px',
        top: chatPos.y + 'px',
        width: chatSize.w + 'px',
        height: chatSize.h + 'px',
      }"
    >
      <!-- 顶部标题栏（可拖拽） -->
      <div class="chat-header" @mousedown="startDrag($event, 'header')">
        <span class="chat-title">
          <span class="title-icon">🤖</span>
          FabTwin AI 助手
          <span class="model-badge" @click.stop="toggleModelSelector" :title="'当前模型: ' + (currentConfig.provider_name || '本地规则引擎') + (currentConfig.model ? ' (' + currentConfig.model + ')' : '')">
            {{ currentConfig.provider_name || '本地规则引擎' }}
          </span>
          <!-- 模型选择下拉 -->
          <div v-if="showModelSelector" class="model-dropdown">
            <div
              v-for="cfg in availableConfigs.filter(c => c.is_enabled)"
              :key="cfg.id"
              class="model-option"
              :class="{ active: cfg.id === currentConfig.config_id }"
              @click.stop="selectConfig(cfg.id)"
            >
              {{ cfg.name }} <span class="model-tag">{{ cfg.model }}</span>
            </div>
            <div v-if="availableConfigs.filter(c => c.is_enabled).length === 0" class="model-option disabled">
              暂无可用配置
            </div>
          </div>
        </span>
        <div class="header-actions">
          <span class="header-btn" title="清空对话" @click.stop="clearChat">🗑️</span>
          <span class="header-btn" title="最小化" @click.stop="minimizeChat">─</span>
          <span class="header-btn" title="关闭" @click.stop="closeChat">✕</span>
        </div>
      </div>

      <!-- 聊天内容区 -->
      <div ref="chatLogRef" class="chat-log">
        <div class="chat-msg ai welcome">
          <div class="msg-content">
            您好，我是 FabTwin AI 数字孪生助手。<br/>
            我可以帮您查询：
            <ul>
              <li>机台实时状态与工艺参数</li>
              <li>报警统计与异常分析</li>
              <li>产量与 Lot 批次追踪</li>
              <li>温度趋势与历史数据</li>
            </ul>
            （所有数据均来自生产数据库实时同步）
          </div>
        </div>

        <template v-for="(msg, i) in messages" :key="i">
          <!-- 用户消息 -->
          <div v-if="msg.role === 'user'" class="chat-msg user">
            <div class="msg-content">{{ msg.content }}</div>
          </div>
          <!-- AI消息 -->
          <div v-else class="chat-msg ai">
            <div class="msg-content">
              <div class="msg-text">{{ msg.content }}</div>
              <!-- SQL展示 -->
              <div v-if="msg.sql" class="msg-sql">{{ msg.sql }}</div>
              <!-- 表格数据 -->
              <div v-if="msg.table_data && msg.table_data.rows && msg.table_data.rows.length" class="msg-table">
                <table>
                  <thead>
                    <tr>
                      <th v-for="h in msg.table_data.headers" :key="h">{{ h }}</th>
                      <th v-if="msg.jump_machine_id" class="col-action">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, ri) in msg.table_data.rows" :key="ri"
                        :class="{ 'row-clickable': msg.jump_machine_id }">
                      <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
                      <td v-if="msg.jump_machine_id" class="col-action">
                        <button
                          v-if="msg.table_data.headers.includes('机台') || ri === 0"
                          class="row-jump-btn"
                          :class="{ disabled: msg.machine_online === false }"
                          @click="jumpToTime({
                            machine_id: row[msg.table_data.headers.indexOf('机台')] || msg.jump_machine_id,
                            timestamp: row[msg.table_data.headers.indexOf('时间')] || msg.jump_timestamp
                          }, msg.machine_online)"
                          :title="msg.machine_online === false ? '该机台暂未上线平台' : ''"
                        >📍 跳转</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <!-- 跳转按钮 -->
              <button
                v-if="msg.jump_timestamp || msg.jump_machine_id"
                class="msg-jump-btn"
                :class="{ disabled: msg.machine_online === false }"
                @click="jumpToTime({ machine_id: msg.jump_machine_id || currentMachineId, timestamp: msg.jump_timestamp }, msg.machine_online)"
                :title="msg.machine_online === false ? '该机台暂未上线平台' : ''"
              >
                {{ msg.machine_online === false ? '⚠️ 机台暂未上线' : `📍 跳转到${msg.jump_machine_id && msg.jump_machine_id !== currentMachineId ? msg.jump_machine_id : '历史回放'}` }}
              </button>
              <!-- 工具调用 -->
              <div v-if="msg.tool_calls && msg.tool_calls.length" class="msg-tools">
                <span class="tool-tag" v-for="(t, ti) in msg.tool_calls" :key="ti" :class="t.status">
                  🔧 {{ t.tool }}: {{ t.status }}
                </span>
              </div>
              <!-- Provider与Token信息 -->
              <div v-if="msg.provider_name" class="msg-meta">
                <span class="provider-badge">{{ msg.provider_name }}{{ msg.model ? ' · ' + msg.model : '' }}</span>
                <span v-if="msg.usage && msg.usage.total_tokens" class="token-badge" title="输入/输出/总Token">
                  {{ msg.usage.prompt_tokens || 0 }} / {{ msg.usage.completion_tokens || 0 }} / {{ msg.usage.total_tokens }} token
                </span>
              </div>
            </div>
          </div>
        </template>

        <div v-if="loading" class="chat-msg ai loading-msg">
          <div class="msg-content">
            <span class="loading-dots">
              <span></span><span></span><span></span>
            </span>
            正在思考中...
          </div>
        </div>
      </div>

      <!-- 快捷问题 -->
      <div class="chat-suggestions">
        <button v-for="s in suggestions" :key="s" @click="sendMessage(s)">{{ s }}</button>
      </div>

      <!-- 输入栏 -->
      <div class="chat-input-bar">
        <VoiceInput
          ref="voiceInputRef"
          mode="input"
          :size="32"
          @speech-result="onSpeechResult"
          @speech-interim="onSpeechInterim"
          @speech-start="onSpeechStart"
          @speech-end="onSpeechEnd"
          @speech-error="onSpeechError"
        />
        <div class="input-wrapper">
          <input
            v-model="input"
            @keyup.enter="sendMessage()"
            :placeholder="isRecording ? '正在聆听中...请说话' : '请输入问题，按回车发送...'"
          />
          <div v-if="isRecording && interimText" class="interim-text">
            <span class="rec-dot">●</span>
            {{ interimText }}
          </div>
        </div>
        <VoiceInput
          v-if="messages.length > 0"
          ref="voiceOutputRef"
          mode="output"
          :text="messages[messages.length - 1]?.content || ''"
          :size="28"
        />
        <button class="send-btn" @click="sendMessage()" :disabled="loading">
          发送
        </button>
      </div>

      <!-- 调整大小手柄 -->
      <div class="resize-handle" @mousedown="startDrag($event, 'resize')"></div>
    </div>
  </Teleport>
</template>

<style scoped>
/* 悬浮球 */
.ai-floating-ball {
  position: fixed;
  z-index: 9999;
  width: 56px;
  height: 56px;
  cursor: grab;
  user-select: none;
}

.ai-floating-ball:active {
  cursor: grabbing;
}

.ball-inner {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: linear-gradient(135deg, #00d4ff, #0066ff);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 20px rgba(0, 212, 255, 0.4);
  position: relative;
  transition: transform 0.2s, box-shadow 0.2s;
}

.ball-inner:hover {
  transform: scale(1.1);
  box-shadow: 0 6px 25px rgba(0, 212, 255, 0.6);
}

.ball-icon {
  font-size: 26px;
  z-index: 1;
}

.ball-pulse {
  position: absolute;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  border: 2px solid #00d4ff;
  animation: ball-pulse 2s infinite;
}

@keyframes ball-pulse {
  0% { transform: scale(1); opacity: 1; }
  100% { transform: scale(1.6); opacity: 0; }
}

.ball-tooltip {
  position: absolute;
  right: calc(100% + 10px);
  top: 50%;
  transform: translateY(-50%);
  background: rgba(0,0,0,0.8);
  color: #fff;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s;
}

.ai-floating-ball:hover .ball-tooltip {
  opacity: 1;
}

/* 聊天窗口 */
.ai-chat-window {
  position: fixed;
  z-index: 9998;
  background: var(--bg-card, #1a1f2e);
  border: 1px solid var(--border, #2a3142);
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0,0,0,0.5);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: linear-gradient(90deg, rgba(0,212,255,0.1), rgba(0,102,255,0.1));
  border-bottom: 1px solid var(--border, #2a3142);
  cursor: move;
  user-select: none;
}

.chat-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text, #e0e6ed);
  display: flex;
  align-items: center;
  gap: 8px;
}

.title-icon {
  font-size: 18px;
}

.header-actions {
  display: flex;
  gap: 4px;
}

.header-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  cursor: pointer;
  color: var(--text-dim, #8a94a6);
  font-size: 13px;
  transition: all 0.15s;
}

.header-btn:hover {
  background: rgba(255,255,255,0.1);
  color: var(--text, #e0e6ed);
}

/* 聊天内容 */
.chat-log {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--bg, #0f1419);
}

.chat-msg {
  max-width: 90%;
  display: flex;
}

.chat-msg.user {
  align-self: flex-end;
}

.chat-msg.ai {
  align-self: flex-start;
}

.msg-content {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.6;
}

.chat-msg.user .msg-content {
  background: linear-gradient(135deg, #00d4ff, #0066ff);
  color: #000;
  font-weight: 500;
  border-radius: 12px 12px 2px 12px;
}

.chat-msg.ai .msg-content {
  background: var(--bg-card, #1a1f2e);
  border: 1px solid var(--border, #2a3142);
  color: var(--text, #e0e6ed);
  border-radius: 12px 12px 12px 2px;
}

.chat-msg.ai.welcome .msg-content {
  background: transparent;
  border: 1px dashed var(--border, #2a3142);
}

.chat-msg.ai.welcome ul {
  margin: 6px 0 0 0;
  padding-left: 18px;
}

.chat-msg.ai.welcome li {
  margin: 2px 0;
  font-size: 12.5px;
  color: var(--text-dim, #8a94a6);
}

.msg-text {
  white-space: pre-wrap;
  word-break: break-word;
}

.msg-sql {
  margin-top: 8px;
  padding: 8px 10px;
  background: rgba(0, 212, 255, 0.06);
  border-radius: 6px;
  font-family: 'Consolas', monospace;
  font-size: 11px;
  color: var(--accent, #00d4ff);
  word-break: break-all;
}

.msg-table {
  margin-top: 8px;
  overflow-x: auto;
  border: 1px solid var(--border, #2a3142);
  border-radius: 6px;
}

.msg-table table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
}

.msg-table th {
  background: rgba(0,212,255,0.1);
  color: var(--accent, #00d4ff);
  padding: 6px 8px;
  text-align: left;
  font-weight: 600;
  border-bottom: 1px solid var(--border, #2a3142);
}

.msg-table td {
  padding: 5px 8px;
  border-bottom: 1px solid var(--border, #2a3142);
  color: var(--text-dim, #8a94a6);
}

.msg-table tr:last-child td {
  border-bottom: none;
}

.msg-table tr.row-clickable {
  cursor: pointer;
  transition: background 0.15s;
}
.msg-table tr.row-clickable:hover {
  background: rgba(0, 212, 255, 0.08);
}
.msg-table .col-action {
  text-align: center;
  width: 60px;
}
.row-jump-btn {
  padding: 3px 8px;
  background: rgba(0, 212, 255, 0.15);
  color: #00d4ff;
  border: 1px solid rgba(0, 212, 255, 0.3);
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
}
.row-jump-btn:hover {
  background: rgba(0, 212, 255, 0.25);
}
.row-jump-btn.disabled {
  background: rgba(156, 163, 175, 0.15);
  color: #9ca3af;
  border-color: rgba(156, 163, 175, 0.3);
  cursor: not-allowed;
}
.row-jump-btn.disabled:hover {
  background: rgba(156, 163, 175, 0.15);
}

.msg-jump-btn {
  margin-top: 8px;
  padding: 5px 12px;
  background: var(--accent, #00d4ff);
  color: #000;
  border: none;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.msg-jump-btn:hover {
  opacity: 0.9;
}
.msg-jump-btn.disabled {
  background: #6b7280;
  color: #fff;
  cursor: not-allowed;
}
.msg-jump-btn.disabled:hover {
  opacity: 1;
}

.msg-tools {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tool-tag {
  padding: 2px 8px;
  background: rgba(0,212,255,0.1);
  color: var(--accent, #00d4ff);
  border-radius: 10px;
  font-size: 10.5px;
}

.tool-tag.success {
  background: rgba(0,255,128,0.1);
  color: #00ff80;
}

.tool-tag.failed {
  background: rgba(255,71,87,0.1);
  color: #ff4757;
}

.loading-msg .msg-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.loading-dots {
  display: inline-flex;
  gap: 3px;
}

.loading-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent, #00d4ff);
  animation: loading-bounce 1.4s infinite ease-in-out both;
}

.loading-dots span:nth-child(1) { animation-delay: -0.32s; }
.loading-dots span:nth-child(2) { animation-delay: -0.16s; }

@keyframes loading-bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1); }
}

/* 快捷问题 */
.chat-suggestions {
  padding: 8px 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  border-top: 1px solid var(--border, #2a3142);
  background: rgba(0,0,0,0.1);
}

.chat-suggestions button {
  padding: 4px 10px;
  background: transparent;
  border: 1px solid var(--border, #2a3142);
  color: var(--text-dim, #8a94a6);
  border-radius: 12px;
  font-size: 11.5px;
  cursor: pointer;
  transition: all 0.15s;
}

.chat-suggestions button:hover {
  border-color: var(--accent, #00d4ff);
  color: var(--accent, #00d4ff);
}

/* 输入栏 */
.chat-input-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-top: 1px solid var(--border, #2a3142);
  background: var(--bg-card, #1a1f2e);
}

.input-wrapper {
  flex: 1;
  position: relative;
}
.input-wrapper input {
  width: 100%;
  background: var(--bg, #0f1419);
  border: 1px solid var(--border, #2a3142);
  color: var(--text, #e0e6ed);
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 13px;
  outline: none;
  transition: border-color 0.2s;
  box-sizing: border-box;
}
.input-wrapper input:focus {
  border-color: var(--accent, #00d4ff);
}
.interim-text {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  right: 0;
  background: rgba(0, 212, 255, 0.12);
  border: 1px solid var(--accent, #00d4ff);
  color: var(--accent, #00d4ff);
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 12.5px;
  line-height: 1.5;
  z-index: 20;
  pointer-events: none;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}
.interim-text .rec-dot {
  color: #ff4757;
  margin-right: 8px;
  animation: rec-blink 1s infinite;
}
@keyframes rec-blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0.3; }
}

.send-btn {
  background: linear-gradient(135deg, #00d4ff, #0066ff);
  color: #000;
  border: none;
  padding: 8px 16px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  transition: opacity 0.2s;
}

.send-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 调整大小手柄 */
.resize-handle {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 16px;
  height: 16px;
  cursor: nwse-resize;
  background: linear-gradient(135deg, transparent 50%, var(--accent, #00d4ff) 50%);
  opacity: 0.5;
  border-radius: 0 0 12px 0;
}

.resize-handle:hover {
  opacity: 1;
}

/* 最小化状态 */
.ai-chat-minimized {
  position: fixed;
  z-index: 9998;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: var(--bg-card, #1a1f2e);
  border: 1px solid var(--border, #2a3142);
  border-radius: 20px;
  box-shadow: 0 4px 15px rgba(0,0,0,0.4);
  cursor: pointer;
  user-select: none;
}

.min-icon {
  font-size: 18px;
}

.min-text {
  font-size: 13px;
  color: var(--text, #e0e6ed);
  font-weight: 500;
}

.min-close {
  margin-left: 4px;
  color: var(--text-dim, #8a94a6);
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 4px;
}

.min-close:hover {
  background: rgba(255,255,255,0.1);
  color: var(--text, #e0e6ed);
}

/* 模型徽章与下拉 */
.model-badge {
  display: inline-block;
  margin-left: 8px;
  padding: 2px 8px;
  border-radius: 10px;
  background: rgba(0, 212, 255, 0.12);
  color: #00d4ff;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  vertical-align: middle;
}
.model-badge:hover {
  background: rgba(0, 212, 255, 0.22);
}
.model-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  min-width: 220px;
  background: #1a1f2e;
  border: 1px solid #2a3142;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  z-index: 100;
  padding: 6px 0;
}
.model-option {
  padding: 8px 14px;
  font-size: 12px;
  color: #e0e6ed;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.model-option:hover {
  background: rgba(0, 212, 255, 0.08);
}
.model-option.active {
  color: #00d4ff;
  background: rgba(0, 212, 255, 0.12);
}
.model-option.disabled {
  color: #555;
  cursor: default;
}
.model-tag {
  font-size: 10px;
  color: #8a94a6;
  margin-left: 6px;
}
.chat-title {
  position: relative;
}

/* 消息元信息 */
.msg-meta {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.provider-badge {
  font-size: 10px;
  color: #8a94a6;
  background: rgba(255,255,255,0.05);
  padding: 2px 6px;
  border-radius: 4px;
}
.token-badge {
  font-size: 10px;
  color: #00d4ff;
  background: rgba(0, 212, 255, 0.06);
  padding: 2px 6px;
  border-radius: 4px;
}
</style>
