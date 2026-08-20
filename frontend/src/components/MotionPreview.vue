<script setup>
/**
 * MotionPreview.vue — 通用 Motion JSON 动画预览组件
 *
 * 功能：
 * 1. 内联渲染 SVG（fetch → v-html，可直接操作 DOM）
 * 2. 自动从 motions 中提取所有 step 作为触发按钮
 * 3. 自动从 when 表达式中提取参数生成输入面板
 * 4. 触发事件 → 匹配 rule → 应用 action 到 SVG 元素
 * 5. 支持 offset/rotate/scale/opacity/visibility/flash/color 动作类型
 * 6. 重置按钮恢复所有部件到初始状态
 */
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { evalWhen, extractParamKeys } from '../composables/useExprEval'

const props = defineProps({
  /** SVG 文件 URL */
  svgUrl: { type: String, default: '' },
  /** Motion JSON 配置对象 */
  motionConfig: { type: Object, default: null },
})

const svgContainer = ref(null)
const svgInline = ref('')
const loading = ref(false)
const errorMsg = ref('')
const eventLog = ref([])

// 参数面板
const paramValues = ref({})

// 缓存每个部件的初始 transform（用于 reset）
const initialTransforms = new Map()

// === 加载 SVG ===
async function loadSvg() {
  if (!props.svgUrl) {
    errorMsg.value = '未设置 SVG URL'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    const resp = await fetch(props.svgUrl)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    svgInline.value = await resp.text()
    // 等待 DOM 更新后缓存初始 transform
    await nextTick()
    cacheInitialTransforms()
  } catch (e) {
    errorMsg.value = `加载 SVG 失败: ${e.message}`
  } finally {
    loading.value = false
  }
}

function cacheInitialTransforms() {
  if (!svgContainer.value) return
  const els = svgContainer.value.querySelectorAll('[id]')
  for (const el of els) {
    const id = el.getAttribute('id')
    const computed = window.getComputedStyle(el)
    const transform = computed.transform
    initialTransforms.set(id, transform !== 'none' ? transform : '')
    // 确保有 transform-origin
    if (!el.style.transformOrigin) {
      el.style.transformOrigin = 'center'
    }
  }
}

// === Motion 数据计算 ===
const isMotionFormat = computed(() => {
  return props.motionConfig && props.motionConfig.schema_version
})

const motions = computed(() => {
  if (!isMotionFormat.value) return []
  return props.motionConfig.motions || []
})

const parts = computed(() => {
  if (!isMotionFormat.value) return []
  return props.motionConfig.parts || []
})

// 提取所有 step 名称
const stepList = computed(() => {
  return motions.value.map(m => m.step).filter(Boolean)
})

// 提取所有 when 表达式中的参数名
const paramKeys = computed(() => {
  const whenList = []
  for (const m of motions.value) {
    for (const r of m.rules || []) {
      if (r.when) whenList.push(r.when)
    }
  }
  return extractParamKeys(whenList)
})

// 初始化参数默认值
watch(paramKeys, (keys) => {
  for (const k of keys) {
    if (!(k in paramValues.value)) {
      paramValues.value[k] = ''
    }
  }
}, { immediate: true })

// === 触发事件 ===
function triggerStep(stepName) {
  const motion = motions.value.find(m => m.step === stepName)
  if (!motion) {
    logEvent(stepName, '未找到 step', 'error')
    return
  }

  // 按顺序匹配 rules
  let matched = false
  for (const rule of motion.rules || []) {
    if (evalWhen(rule.when, paramValues.value)) {
      const targetId = rule.target_part_id || motion.target_part_id
      const actions = rule.actions || []
      // 预先在目标元素上设置 transition：取所有 action 中的最大 duration
      // 避免后续 action（如 duration=0 的 offset）覆盖前一个 action 的过渡设置
      const targetEl = svgContainer.value?.querySelector(`#${targetId}`)
      if (targetEl) {
        const maxDuration = actions.reduce((m, a) => Math.max(m, a.duration || 0), 0)
        // 取第一个有 easing 的 action 的 easing 作为整体过渡曲线
        const easingAction = actions.find(a => a.easing)
        const easing = easingToCss(easingAction?.easing)
        targetEl.style.transition = maxDuration > 0
          ? `transform ${maxDuration}ms ${easing}, opacity ${maxDuration}ms ${easing}`
          : 'none'
      }
      for (const action of actions) {
        executeAction(targetId, action)
      }
      logEvent(stepName, `命中: ${rule.when} → ${targetId} ${actions.length}个动作`, 'success')
      matched = true
      break
    }
  }

  if (!matched) {
    logEvent(stepName, '无匹配 rule', 'warn')
  }
}

// === 执行动作 ===
// 每个部件维护独立的 translate / rotate / scale 状态，组合后写入 style.transform
// 避免多个 action 互相覆盖（旧版 bug：applyOffset 会清掉 applyRotate 设置的旋转）
const partTransformState = new Map()

function getPartState(el) {
  const id = el.getAttribute('id') || el
  if (!partTransformState.has(id)) {
    partTransformState.set(id, { translate: '', rotate: '', scale: '', origin: '' })
  }
  return partTransformState.get(id)
}

function applyCombinedTransform(el) {
  const s = getPartState(el)
  const parts = [s.translate, s.rotate, s.scale].filter(Boolean)
  el.style.transform = parts.join(' ')
  if (s.origin) el.style.transformOrigin = s.origin
}

function executeAction(partId, action) {
  const el = svgContainer.value?.querySelector(`#${partId}`)
  if (!el) {
    console.warn(`[MotionPreview] 部件 #${partId} 未找到`)
    return
  }

  // 注意：transition 由 triggerStep 在调用前预先设置（取 rule 内所有 action 的最大 duration）
  // 这里不再为单个 action 设置 transition，避免后续 action（如 duration=0）覆盖前者

  switch (action.type) {
    case 'offset':
      applyOffset(el, action)
      break
    case 'rotate':
      applyRotate(el, action)
      break
    case 'scale':
      applyScale(el, action)
      break
    case 'opacity':
      el.style.opacity = String(action.to ?? 1)
      break
    case 'visibility':
      el.style.opacity = action.to ? '1' : '0'
      break
    case 'flash':
      applyFlash(el, action)
      break
    case 'color':
      applyColor(el, action)
      break
    default:
      console.log(`[MotionPreview] 未知动作类型: ${action.type}`)
  }
}

function applyOffset(el, action) {
  // 逻辑坐标 Y 向上 → SVG 浏览器坐标 Y 向下，需翻转
  const offsetX = action.offset_x || 0
  const offsetY = -(action.offset_y || 0) // Y 轴翻转
  // 2D 场景只用 x/y，z 忽略
  const s = getPartState(el)
  s.translate = `translate(${offsetX}px, ${offsetY}px)`
  applyCombinedTransform(el)
}

function applyRotate(el, action) {
  const angle = action.angle || 0
  // pivot 逻辑坐标转 SVG 坐标
  let pivotX = 0, pivotY = 0
  if (action.pivot) {
    pivotX = action.pivot.x || 0
    // Y 轴翻转
    const viewBoxH = getViewBoxHeight()
    pivotY = viewBoxH - (action.pivot.y || 0)
  } else {
    // 查找 parts 中的 anchor
    const part = parts.value.find(p => p.part_id === el.getAttribute('id'))
    if (part?.anchors?.[0]) {
      pivotX = part.anchors[0].x || 0
      const viewBoxH = getViewBoxHeight()
      pivotY = viewBoxH - (part.anchors[0].y || 0)
    }
  }
  const s = getPartState(el)
  s.origin = `${pivotX}px ${pivotY}px`
  s.rotate = `rotate(${angle}deg)`
  applyCombinedTransform(el)
}

function applyScale(el, action) {
  const sx = action.scale_x ?? 1
  const sy = action.scale_y ?? 1
  const s = getPartState(el)
  s.scale = `scale(${sx}, ${sy})`
  applyCombinedTransform(el)
}

function applyFlash(el, action) {
  const color = action.color || '#ef4444'
  const duration = action.duration || 500
  const originalFill = el.style.fill || ''
  el.style.fill = color
  setTimeout(() => {
    el.style.fill = originalFill
  }, duration)
}

function applyColor(el, action) {
  const target = action.to || '#16a34a'
  el.style.fill = target
}

function easingToCss(easing) {
  const map = {
    'linear': 'linear',
    'mechanical': 'cubic-bezier(0.34, 1.56, 0.64, 1)',
    'ease-in': 'ease-in',
    'ease-out': 'ease-out',
    'ease-in-out': 'ease-in-out',
  }
  return map[easing] || 'linear'
}

function getViewBoxHeight() {
  if (!props.motionConfig?.document?.coord?.viewBox) return 900
  return props.motionConfig.document.coord.viewBox[3] || 900
}

// === 重置 ===
function resetAll() {
  if (!svgContainer.value) return
  // 清空累积的 transform 状态
  partTransformState.clear()
  for (const [id, transform] of initialTransforms) {
    const el = svgContainer.value.querySelector(`#${id}`)
    if (el) {
      el.style.transform = transform || ''
      el.style.transformOrigin = ''
      el.style.opacity = ''
      el.style.transition = ''
      delete el.dataset.transform
    }
  }
  logEvent('RESET', '所有部件已重置', 'info')
}

// === 事件日志 ===
function logEvent(step, msg, type = 'info') {
  const time = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  eventLog.value.unshift({ time, step, msg, type })
  if (eventLog.value.length > 50) eventLog.value.pop()
}

// === 监听 ===
watch(() => props.svgUrl, () => {
  if (props.svgUrl) loadSvg()
})

watch(() => props.motionConfig, () => {
  // 配置变更时重置
  resetAll()
  eventLog.value = []
}, { deep: true })

onMounted(() => {
  if (props.svgUrl) loadSvg()
})
</script>

<template>
  <div class="motion-preview">
    <!-- 顶部工具栏 -->
    <div class="preview-toolbar">
      <div class="toolbar-left">
        <span v-if="isMotionFormat" class="format-badge motion">
          Motion JSON v{{ motionConfig.schema_version }}
        </span>
        <span v-else class="format-badge old">旧格式 / 无配置</span>
        <span v-if="svgUrl" class="svg-status" :class="{ ok: svgInline }">
          {{ svgInline ? 'SVG 已加载' : 'SVG 加载中...' }}
        </span>
      </div>
      <div class="toolbar-right">
        <button class="btn-reset" @click="resetAll" :disabled="!svgInline">↻ 重置</button>
      </div>
    </div>

    <div class="preview-body">
      <!-- 左侧：SVG 预览区 -->
      <div class="svg-area">
        <div v-if="errorMsg" class="error-msg">⚠️ {{ errorMsg }}</div>
        <div
          ref="svgContainer"
          class="svg-container"
          v-html="svgInline"
        ></div>
        <div v-if="!svgUrl" class="empty-hint">
          请先上传 SVG 文件
        </div>
      </div>

      <!-- 右侧：控制面板 -->
      <div class="control-panel">
        <!-- 参数输入 -->
        <div v-if="paramKeys.length > 0" class="param-section">
          <h4>参数</h4>
          <div class="param-grid">
            <div v-for="key in paramKeys" :key="key" class="param-item">
              <label>{{ key }}</label>
              <input
                v-model="paramValues[key]"
                :placeholder="`如: 1`"
                @keyup.enter="paramValues[key] = paramValues[key]"
              />
            </div>
          </div>
        </div>

        <!-- 事件触发按钮 -->
        <div class="trigger-section">
          <h4>事件触发</h4>
          <div v-if="stepList.length === 0" class="empty-row">无可用 step</div>
          <div v-else class="trigger-grid">
            <button
              v-for="step in stepList"
              :key="step"
              class="trigger-btn"
              @click="triggerStep(step)"
            >
              <div class="btn-step">{{ step }}</div>
              <div class="btn-desc">
                {{ motions.find(m => m.step === step)?.rules?.length || 0 }} 条规则
              </div>
            </button>
          </div>
        </div>

        <!-- 部件列表 -->
        <div v-if="parts.length > 0" class="parts-section">
          <h4>部件 ({{ parts.length }})</h4>
          <div class="parts-list">
            <div v-for="p in parts" :key="p.part_id" class="part-row">
              <span class="part-id">{{ p.part_id }}</span>
              <span class="part-name">{{ p.part_name }}</span>
            </div>
          </div>
        </div>

        <!-- 事件日志 -->
        <div class="log-section">
          <h4>事件日志 ({{ eventLog.length }})</h4>
          <div v-if="eventLog.length === 0" class="empty-row">暂无事件</div>
          <div v-else class="log-list">
            <div
              v-for="(log, idx) in eventLog"
              :key="idx"
              class="log-item"
              :class="log.type"
            >
              <span class="log-time">{{ log.time }}</span>
              <span class="log-step">{{ log.step }}</span>
              <span class="log-msg">{{ log.msg }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.motion-preview {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--panel);
  border-radius: 8px;
  overflow: hidden;
}

.preview-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.format-badge {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.format-badge.motion {
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent);
}
.format-badge.old {
  background: rgba(245, 158, 11, 0.15);
  color: var(--yellow);
}
.svg-status {
  font-size: 11px;
  color: var(--text-dim);
}
.svg-status.ok { color: var(--green); }

.btn-reset {
  background: var(--panel-2);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 4px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
.btn-reset:hover { border-color: var(--accent); }
.btn-reset:disabled { opacity: 0.5; cursor: not-allowed; }

.preview-body {
  display: grid;
  grid-template-columns: 1fr 320px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
@media (max-width: 900px) {
  .preview-body { grid-template-columns: 1fr; }
}

.svg-area {
  background: var(--bg);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: auto;
  position: relative;
  padding: 16px;
}
.svg-container {
  max-width: 100%;
  max-height: 100%;
}
.svg-container :deep(svg) {
  max-width: 100%;
  height: auto;
  display: block;
}
.error-msg {
  color: var(--red);
  font-size: 13px;
  padding: 8px 12px;
  background: rgba(244, 67, 54, 0.1);
  border-radius: 4px;
  margin-bottom: 8px;
}
.empty-hint {
  color: var(--text-dim);
  font-size: 14px;
  font-style: italic;
}

.control-panel {
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  background: var(--panel-2);
}
.control-panel h4 {
  font-size: 12px;
  color: var(--accent);
  margin: 0 0 8px 0;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.param-section,
.trigger-section,
.parts-section,
.log-section {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}

.param-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.param-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.param-item label {
  font-size: 12px;
  color: var(--text-dim);
  min-width: 70px;
  flex-shrink: 0;
}
.param-item input {
  flex: 1;
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  padding: 4px 8px;
  border-radius: 3px;
  font-size: 12px;
  outline: none;
  min-width: 0;
}
.param-item input:focus { border-color: var(--accent); }

.trigger-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.trigger-btn {
  background: var(--bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 8px;
  cursor: pointer;
  text-align: center;
  transition: all 0.15s;
}
.trigger-btn:hover {
  background: var(--panel);
  border-color: var(--accent);
}
.btn-step {
  font-weight: 600;
  color: var(--yellow);
  font-size: 11px;
}
.btn-desc {
  color: var(--text-dim);
  font-size: 10px;
  margin-top: 2px;
}

.parts-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-height: 150px;
  overflow-y: auto;
}
.part-row {
  display: flex;
  gap: 8px;
  font-size: 11px;
  padding: 3px 6px;
}
.part-id {
  font-family: monospace;
  color: var(--accent);
  min-width: 100px;
}
.part-name {
  color: var(--text-dim);
}

.log-list {
  max-height: 200px;
  overflow-y: auto;
}
.log-item {
  display: flex;
  gap: 6px;
  padding: 4px 6px;
  border-bottom: 1px solid var(--border);
  font-size: 11px;
  align-items: center;
}
.log-item:last-child { border-bottom: none; }
.log-item.success { background: rgba(34, 197, 94, 0.05); }
.log-item.error { background: rgba(244, 67, 54, 0.05); }
.log-item.warn { background: rgba(245, 158, 11, 0.05); }
.log-time {
  color: var(--text-dim);
  font-family: monospace;
  flex-shrink: 0;
}
.log-step {
  color: var(--yellow);
  font-weight: 600;
  flex-shrink: 0;
  min-width: 80px;
}
.log-msg {
  color: var(--text);
  flex: 1;
  min-width: 0;
  word-break: break-all;
}

.empty-row {
  color: var(--text-dim);
  font-size: 11px;
  font-style: italic;
  text-align: center;
  padding: 8px;
}
</style>
