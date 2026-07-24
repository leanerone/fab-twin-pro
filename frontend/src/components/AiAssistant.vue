<script setup>
import { ref, watch, nextTick, onMounted } from 'vue'
import { api } from '../api'
import VoiceInput from './VoiceInput.vue'

// AI 助手聊天：发送问题、显示回答、SQL、表格、跳转按钮
const props = defineProps({
  machineId: { type: String, default: '' },
  // 会话类型：用于本地存储key，确保多窗口会话独立
  sessionType: { type: String, default: 'detail' },
  // 是否显示语音功能
  showVoice: { type: Boolean, default: true },
})

const emit = defineEmits(['jump'])

const messages = ref([])
const input = ref('')
const chatLogRef = ref(null)
const loading = ref(false)
const sessionId = ref(null)
const voiceInputRef = ref(null)
const voiceOutputRef = ref(null)
const isRecording = ref(false)
const interimText = ref('')

const STORAGE_KEY = `fabtwin_ai_${props.sessionType}`

// 快捷问题
const suggestions = [
  '当前机台状态',
  '今天有多少报警',
  '温度趋势如何',
  '已加工多少晶圆',
  '异常检测结果',
  '工艺步骤详情',
  '查询 Lot',
]

// ==================== 会话持久化 ====================

onMounted(() => {
  // 恢复会话
  const saved = localStorage.getItem(STORAGE_KEY + '_' + (props.machineId || 'global'))
  if (saved) {
    try {
      const data = JSON.parse(saved)
      messages.value = data.messages || []
      sessionId.value = data.sessionId || null
    } catch (e) {}
  }
})

watch([messages, sessionId, () => props.machineId], () => {
  const key = STORAGE_KEY + '_' + (props.machineId || 'global')
  localStorage.setItem(key, JSON.stringify({
    messages: messages.value,
    sessionId: sessionId.value,
  }))
}, { deep: true })

// 监听机台变化，切换会话
watch(() => props.machineId, (newId, oldId) => {
  if (newId !== oldId) {
    // 保存当前会话
    const oldKey = STORAGE_KEY + '_' + (oldId || 'global')
    localStorage.setItem(oldKey, JSON.stringify({
      messages: messages.value,
      sessionId: sessionId.value,
    }))
    // 加载新机台会话
    const newKey = STORAGE_KEY + '_' + (newId || 'global')
    const saved = localStorage.getItem(newKey)
    if (saved) {
      try {
        const data = JSON.parse(saved)
        messages.value = data.messages || []
        sessionId.value = data.sessionId || null
      } catch (e) {
        messages.value = []
        sessionId.value = null
      }
    } else {
      messages.value = []
      sessionId.value = null
    }
  }
})

// ==================== 聊天逻辑 ====================

async function ask(questionText) {
  const q = (questionText || input.value || '').trim()
  if (!q || loading.value) return
  input.value = ''

  // 用户消息
  messages.value.push({
    role: 'user',
    content: q,
    time: new Date().toLocaleTimeString(),
  })

  await nextTick()
  scrollToBottom()

  loading.value = true
  try {
    // 使用统一的AI聊天接口
    const resp = await api.aiChat({
      question: q,
      session_id: sessionId.value,
      machine_id: props.machineId,
      user_role: 'user',
    })

    sessionId.value = resp.session_id || sessionId.value

    const msg = {
      role: 'assistant',
      content: resp.answer,
      sql: resp.sql,
      jump_timestamp: resp.jump_timestamp,
      table_data: resp.table_data,
      tool_calls: resp.tool_calls,
      sources: resp.sources,
      provider_name: resp.provider_name,
      model: resp.model,
      config_id: resp.config_id,
      usage: resp.usage,
      time: new Date().toLocaleTimeString(),
    }
    messages.value.push(msg)

    // 语音播报AI回复
    if (voiceOutputRef.value && resp.answer) {
      // 可选：自动播报（默认不自动，用户点击按钮播报）
    }
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: '抱歉，查询失败：' + (e.message || '服务不可用'),
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

// 跳转到回放时间
function jumpToTime(ts) {
  emit('jump', ts)
}

function scrollToBottom() {
  if (chatLogRef.value) {
    chatLogRef.value.scrollTop = chatLogRef.value.scrollHeight
  }
}
</script>

<template>
  <div class="ai-assistant">
    <div class="section-title">AI 助手</div>
    <div ref="chatLogRef" class="chat-log">
      <div class="chat-msg ai welcome">
        您好，我是机台 AI 助手。可以问我机台状态、报警、温度趋势、产量、异常检测、Lot 追踪等。
      </div>
      <template v-for="(m, i) in messages" :key="i">
        <div class="chat-msg user">{{ m.content }}</div>
        <div class="chat-msg ai">
          <div class="msg-text">{{ m.content }}</div>
          <!-- SQL展示 -->
          <div v-if="m.sql" class="sql">{{ m.sql }}</div>
          <!-- 表格数据 -->
          <div v-if="m.table_data && m.table_data.rows && m.table_data.rows.length" class="msg-table">
            <table>
              <thead>
                <tr>
                  <th v-for="h in m.table_data.headers" :key="h">{{ h }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, ri) in m.table_data.rows" :key="ri">
                  <td v-for="(cell, ci) in row" :key="ci">{{ cell }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <button v-if="m.jump_timestamp" class="ai-jump-btn" @click="jumpToTime(m.jump_timestamp)">
            → 跳转到回放时间
          </button>
          <!-- Provider与Token信息 -->
          <div v-if="m.provider_name" class="msg-meta">
            <span class="provider-badge">{{ m.provider_name }}{{ m.model ? ' · ' + m.model : '' }}</span>
            <span v-if="m.usage && m.usage.total_tokens" class="token-badge" title="输入/输出/总Token">
              {{ m.usage.prompt_tokens || 0 }} / {{ m.usage.completion_tokens || 0 }} / {{ m.usage.total_tokens }} token
            </span>
          </div>
        </div>
      </template>
      <div v-if="loading" class="chat-msg ai">查询中...</div>
    </div>
    <div class="chat-suggestions">
      <button v-for="s in suggestions" :key="s" @click="ask(s)">{{ s }}</button>
    </div>
    <div class="chat-input-bar">
      <VoiceInput
        v-if="showVoice"
        ref="voiceInputRef"
        mode="input"
        :size="28"
        @speech-result="onSpeechResult"
        @speech-interim="onSpeechInterim"
        @speech-start="onSpeechStart"
        @speech-end="onSpeechEnd"
        @speech-error="onSpeechError"
      />
      <div class="input-wrapper">
        <input
          v-model="input"
          @keyup.enter="ask(input)"
          :placeholder="isRecording ? '正在聆听中...' : '如：LOT00123 什么时间加工的？'"
        />
        <div v-if="isRecording && interimText" class="interim-text">
          <span class="rec-dot">●</span>
          {{ interimText }}
        </div>
      </div>
      <VoiceInput
        v-if="showVoice && messages.length > 0"
        ref="voiceOutputRef"
        mode="output"
        :text="messages[messages.length - 1]?.content || ''"
        :size="26"
      />
      <button @click="ask(input)">发送</button>
    </div>
  </div>
</template>

<style scoped>
.ai-assistant {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}
.chat-log {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.chat-msg {
  font-size: 12.5px;
  line-height: 1.5;
  max-width: 92%;
  white-space: pre-wrap;
}
.chat-msg.user {
  align-self: flex-end;
  background: var(--accent);
  color: #000;
  padding: 8px 12px;
  border-radius: 12px 12px 2px 12px;
  font-weight: 500;
}
.chat-msg.ai {
  align-self: flex-start;
  background: var(--bg);
  border: 1px solid var(--border);
  padding: 8px 12px;
  border-radius: 12px 12px 12px 2px;
}
.chat-msg.ai.welcome {
  background: transparent;
  border: 1px dashed var(--border);
  color: var(--text-dim);
}
.msg-text {
  word-break: break-word;
}
.chat-msg.ai .sql {
  font-family: 'Consolas', monospace;
  font-size: 10.5px;
  color: var(--accent);
  margin-top: 6px;
  padding: 6px 8px;
  background: rgba(0, 212, 255, 0.05);
  border-radius: 4px;
  word-break: break-all;
}
.msg-table {
  margin-top: 8px;
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 4px;
}
.msg-table table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.msg-table th {
  background: rgba(0,212,255,0.1);
  color: var(--accent);
  padding: 5px 7px;
  text-align: left;
  font-weight: 600;
  border-bottom: 1px solid var(--border);
}
.msg-table td {
  padding: 4px 7px;
  border-bottom: 1px solid var(--border);
  color: var(--text-dim);
}
.msg-table tr:last-child td {
  border-bottom: none;
}
.ai-jump-btn {
  background: var(--accent);
  color: #000;
  border: none;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 10.5px;
  font-weight: 700;
  margin-top: 6px;
}
.ai-jump-btn:hover {
  opacity: 0.85;
}
.chat-suggestions {
  padding: 0 14px 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.chat-suggestions button {
  padding: 4px 10px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-dim);
  border-radius: 12px;
  font-size: 11px;
}
.chat-suggestions button:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.chat-input-bar {
  display: flex;
  gap: 8px;
  padding: 10px 14px;
  border-top: 1px solid var(--border);
  align-items: center;
}
.input-wrapper {
  flex: 1;
  position: relative;
}
.input-wrapper input {
  width: 100%;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 7px 11px;
  border-radius: 7px;
  font-size: 12.5px;
  outline: none;
  box-sizing: border-box;
}
.input-wrapper input:focus {
  border-color: var(--accent);
}
.interim-text {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  right: 0;
  background: rgba(0, 212, 255, 0.12);
  border: 1px solid var(--accent);
  color: var(--accent);
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.4;
  z-index: 10;
  pointer-events: none;
}
.interim-text .rec-dot {
  color: #ff4757;
  margin-right: 6px;
  animation: blink 1s infinite;
}
@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0.3; }
}
.chat-input-bar button {
  background: var(--accent);
  color: #000;
  border: none;
  padding: 0 14px;
  height: 32px;
  border-radius: 7px;
  font-weight: 700;
  font-size: 12px;
}
.chat-input-bar button:hover {
  opacity: 0.85;
}
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
