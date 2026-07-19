<script setup>
import { ref, computed, onUnmounted } from 'vue'
import { api } from '../api'

const props = defineProps({
  mode: { type: String, default: 'input' },
  text: { type: String, default: '' },
  size: { type: Number, default: 20 },
})

const emit = defineEmits([
  'speechResult',
  'speechInterim',
  'speechStart',
  'speechEnd',
  'speechError',
])

const isRecording = ref(false)
const isProcessing = ref(false)
const isSpeaking = ref(false)
const synthesis = window.speechSynthesis
const errorMsg = ref('')
const mediaRecorder = ref(null)
const audioChunks = ref([])
const streamRef = ref(null)

const supported = computed(() => {
  if (props.mode === 'input') {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder)
  }
  return 'speechSynthesis' in window
})

const icon = computed(() => {
  if (props.mode === 'input') {
    if (isProcessing.value) return '⋯'
    return isRecording.value ? '⏹' : '🎤'
  }
  return isSpeaking.value ? '🔊' : '🔈'
})

// ==================== 语音输入：MediaRecorder + 后端 Whisper ====================

async function toggleRecording() {
  if (!supported.value) {
    showMsg('error', '当前浏览器不支持录音，请使用 Chrome 或 Edge')
    return
  }
  if (isProcessing.value) return

  if (isRecording.value) {
    stopRecording()
  } else {
    await startRecording()
  }
}

async function startRecording() {
  errorMsg.value = ''
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    })
    streamRef.value = stream

    // 选择浏览器支持的 mime
    const mimeTypes = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4',
    ]
    let mimeType = ''
    for (const mt of mimeTypes) {
      if (MediaRecorder.isTypeSupported(mt)) {
        mimeType = mt
        break
      }
    }

    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    audioChunks.value = []

    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        audioChunks.value.push(e.data)
      }
    }

    recorder.onstop = async () => {
      // 合并音频片段
      const blob = new Blob(audioChunks.value, { type: mimeType || 'audio/webm' })
      audioChunks.value = []

      // 停止所有音轨
      if (streamRef.value) {
        streamRef.value.getTracks().forEach(t => t.stop())
        streamRef.value = null
      }

      // 录音太短，忽略
      if (blob.size < 500) {
        showMsg('info', '录音太短，请重试')
        emit('speechEnd')
        return
      }

      // 上传到后端识别
      isProcessing.value = true
      try {
        emit('speechInterim', '识别中...')
        const result = await api.aiSpeechToText(blob, 'zh')
        const text = (result.text || '').trim()
        if (text) {
          emit('speechResult', text)
        } else {
          showMsg('info', '未识别到语音内容')
        }
      } catch (e) {
        console.error('[语音] 识别失败:', e)
        const errMsg = e.message || '识别失败'
        if (errMsg.includes('ffmpeg') || errMsg.includes('model') || errMsg.includes('download')) {
          showMsg('error', '后端模型加载中或下载失败，请查看后端日志')
        } else {
          showMsg('error', '识别失败：' + errMsg)
        }
        emit('speechError', errMsg)
      } finally {
        isProcessing.value = false
        emit('speechEnd')
      }
    }

    recorder.start()
    mediaRecorder.value = recorder
    isRecording.value = true
    emit('speechStart')
  } catch (e) {
    console.error('[语音] 启动录音失败:', e)
    const errMap = {
      NotAllowedError: '麦克风权限被拒绝，请在浏览器设置中允许',
      NotFoundError: '未检测到麦克风设备',
      NotReadableError: '麦克风被其他程序占用',
      SecurityError: '需要 HTTPS 环境才能使用麦克风',
    }
    const msg = errMap[e.name] || `录音启动失败：${e.message || e.name}`
    showMsg('error', msg)
    emit('speechError', msg)
  }
}

function stopRecording() {
  if (mediaRecorder.value && mediaRecorder.value.state !== 'inactive') {
    mediaRecorder.value.stop()
  }
  isRecording.value = false
}

function showMsg(type, msg) {
  errorMsg.value = msg
  setTimeout(() => { errorMsg.value = '' }, 3500)
}

onUnmounted(() => {
  if (isRecording.value) {
    stopRecording()
  }
  if (streamRef.value) {
    streamRef.value.getTracks().forEach(t => t.stop())
  }
})

// ==================== 语音播报（浏览器原生 speechSynthesis，离线可用） ====================

function speak(text) {
  if (!synthesis) {
    showMsg('error', '浏览器不支持语音播报')
    return
  }
  if (isSpeaking.value) {
    synthesis.cancel()
    isSpeaking.value = false
    return
  }
  synthesis.cancel()
  const utter = new SpeechSynthesisUtterance(text)
  utter.lang = 'zh-CN'
  utter.rate = 1.0
  utter.onstart = () => { isSpeaking.value = true }
  utter.onend = () => { isSpeaking.value = false }
  utter.onerror = () => { isSpeaking.value = false }
  synthesis.speak(utter)
}

function toggleSpeak() {
  if (props.mode === 'output') {
    speak(props.text)
  }
}

defineExpose({
  isRecording,
  isProcessing,
  isSpeaking,
})
</script>

<template>
  <div class="voice-wrapper">
    <button
      class="voice-btn"
      :class="{
        active: isRecording || isSpeaking,
        processing: isProcessing,
        'not-supported': !supported,
      }"
      :style="{ width: size + 'px', height: size + 'px', fontSize: (size * 0.5) + 'px' }"
      @click="mode === 'input' ? toggleRecording() : toggleSpeak()"
      :title="mode === 'input'
        ? (isProcessing ? '识别中...' : (isRecording ? '停止录音' : '语音输入'))
        : (isSpeaking ? '停止播报' : '语音播报')"
    >
      <span class="icon">{{ icon }}</span>
      <span v-if="isRecording" class="pulse"></span>
    </button>
    <transition name="fade">
      <div v-if="errorMsg" class="voice-error-tip">{{ errorMsg }}</div>
    </transition>
  </div>
</template>

<style scoped>
.voice-wrapper {
  position: relative;
  display: inline-flex;
  flex-shrink: 0;
}

.voice-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: var(--bg, #0f1419);
  border: 1px solid var(--border, #2a3142);
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
  flex-shrink: 0;
  color: var(--text, #e0e6ed);
}

.voice-btn:hover:not(.not-supported) {
  border-color: var(--accent, #00d4ff);
  background: rgba(0, 212, 255, 0.1);
}

.voice-btn.active {
  background: rgba(255, 71, 87, 0.15);
  border-color: #ff4757;
  color: #ff4757;
}

.voice-btn.processing {
  background: rgba(0, 212, 255, 0.15);
  border-color: var(--accent, #00d4ff);
  color: var(--accent, #00d4ff);
  animation: processing-spin 1s linear infinite;
}

@keyframes processing-spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

.voice-btn.not-supported {
  opacity: 0.4;
  cursor: not-allowed;
}

.icon {
  line-height: 1;
}

.pulse {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 100%;
  height: 100%;
  border-radius: 50%;
  border: 2px solid #ff4757;
  animation: pulse-ring 1.2s cubic-bezier(0.215, 0.61, 0.355, 1) infinite;
  pointer-events: none;
}

@keyframes pulse-ring {
  0% {
    transform: translate(-50%, -50%) scale(0.8);
    opacity: 1;
  }
  80%, 100% {
    transform: translate(-50%, -50%) scale(1.4);
    opacity: 0;
  }
}

.voice-error-tip {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  white-space: nowrap;
  max-width: 280px;
  white-space: normal;
  text-align: center;
  background: rgba(231, 76, 60, 0.95);
  color: #fff;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  z-index: 100;
  pointer-events: none;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}

.voice-error-tip::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
  border-top-color: rgba(231, 76, 60, 0.95);
}

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.2s, transform 0.2s;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(4px);
}
</style>
