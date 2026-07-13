<script setup>
import { ref, watch, nextTick } from 'vue'
import { api } from '../api'

// AI 助手聊天：发送问题、显示回答、SQL、跳转按钮
const props = defineProps({
  machineId: { type: String, default: '' },
})

const emit = defineEmits(['jump'])

const messages = ref([])
const input = ref('')
const chatLogRef = ref(null)
const loading = ref(false)

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

// 发送查询
async function ask(questionText) {
  const q = (questionText || input.value || '').trim()
  if (!q || loading.value) return
  input.value = ''
  loading.value = true

  // 调用后端 AI 接口
  const resp = await api.aiQuery(q, props.machineId)
  loading.value = false

  messages.value.push({
    q,
    a: resp?.answer || '抱歉，查询失败或服务不可用。',
    sql: resp?.sql || '',
    jumpTs: resp?.jump_timestamp || null,
  })

  // 自动滚动到底部
  await nextTick()
  if (chatLogRef.value) {
    chatLogRef.value.scrollTop = chatLogRef.value.scrollHeight
  }
}

// 跳转到回放时间
function jumpToTime(ts) {
  emit('jump', ts)
}

// 监听机台变化，清空对话
watch(() => props.machineId, () => {
  messages.value = []
})
</script>

<template>
  <div class="ai-assistant">
    <div class="section-title">AI 助手</div>
    <div ref="chatLogRef" class="chat-log">
      <div class="chat-msg ai">
        您好，我是机台 AI 助手。可以问我机台状态、报警、温度趋势、产量、异常检测、Lot 追踪等。
      </div>
      <template v-for="(m, i) in messages" :key="i">
        <div class="chat-msg user">{{ m.q }}</div>
        <div class="chat-msg ai">
          {{ m.a }}
          <div v-if="m.sql" class="sql">{{ m.sql }}</div>
          <button v-if="m.jumpTs" class="ai-jump-btn" @click="jumpToTime(m.jumpTs)">→ 跳转到回放时间</button>
        </div>
      </template>
      <div v-if="loading" class="chat-msg ai">查询中...</div>
    </div>
    <div class="chat-suggestions">
      <button v-for="s in suggestions" :key="s" @click="ask(s)">{{ s }}</button>
    </div>
    <div class="chat-input-bar">
      <input
        v-model="input"
        @keyup.enter="ask(input)"
        placeholder="如：LOT00123 什么时间加工的？"
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
}
.chat-input-bar input {
  flex: 1;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 7px 11px;
  border-radius: 7px;
  font-size: 12.5px;
  outline: none;
}
.chat-input-bar input:focus {
  border-color: var(--accent);
}
.chat-input-bar button {
  background: var(--accent);
  color: #000;
  border: none;
  padding: 0 14px;
  border-radius: 7px;
  font-weight: 700;
  font-size: 12px;
}
.chat-input-bar button:hover {
  opacity: 0.85;
}
</style>
