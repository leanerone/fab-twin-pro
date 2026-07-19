<script setup>
/**
 * 事件-动画时间轴调试面板
 *
 * 功能区域：
 *   A. 时间轴轨道（事件轨/阶段轨/动画轨）
 *   B. 事件列表（实时/回放中收到的事件 + 期望阶段）
 *   C. 阶段高亮（当前阶段在轨道上高亮）
 *   D. 偏差检测（事件→动画触发是否对齐）
 *   E. 手动触发（点击事件按钮立即触发动画）
 *   F. 配置热编辑（修改 duration_ms / 事件映射，实时生效）
 *   G. 动画录制器（手动拖拽部件 → 生成 JSON 配置）
 *   H. 导出配置（下载 podopener.json 覆盖到 configs/）
 *
 * 用法：在 MachineDetail.vue 中作为调试标签页挂载
 */
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useAnimationConfig } from '../composables/useAnimationConfig.js'

const props = defineProps({
  machineType: { type: String, default: 'podopener' },
  events: { type: Array, default: () => [] },
  currentPhase: { type: String, default: '' },
  currentFlow: { type: String, default: 'PACKING' },
  // 是否处于实时模式（影响事件来源）
  mode: { type: String, default: 'realtime' },
})

const emit = defineEmits([
  'trigger-event',      // 手动触发事件 → 父组件执行
  'jump-to-phase',      // 跳转阶段 → 父组件执行
  'config-updated',     // 配置热更新 → 父组件传递给 2D/3D 视图
])

const animConfig = useAnimationConfig(props.machineType)
const activeTab = ref('timeline')  // timeline | events | manual | config | recorder

// ============ A. 时间轴轨道 ============
const timelineEvents = ref([])  // [{ ts, event_name, phase, anim, status }]
const timelineMaxItems = 30
const driftThresholdMs = 500  // 偏差检测阈值

// ============ B. 事件列表 ============
const eventLog = ref([])  // 完整事件日志
const eventLogMaxItems = 100

// ============ C. 阶段高亮 ============
const phases = computed(() => animConfig.getPhases(currentFlowSelected.value))
const currentFlowSelected = ref(props.currentFlow || 'PACKING')

// ============ D. 偏差检测 ============
const drifts = ref([])  // [{ eventTs, eventName, expectedPhase, actualPhase, delayMs }]

// ============ F. 配置热编辑 ============
const editableConfig = ref(null)  // 热编辑中的配置副本
const editDirty = ref(false)

// ============ G. 动画录制器 ============
const recorder = ref({
  active: false,
  startTime: 0,
  currentTarget: '',
  keyframes: [],  // [{ t, target, axis, value }]
})

// ============ 监听事件流 ============
let lastEventTs = ''
watch(() => props.events, (evs) => {
  if (!Array.isArray(evs) || evs.length === 0) return
  const latest = evs[0]
  const ts = latest?.timestamp || latest?.event_ts_utc || ''
  if (ts === lastEventTs) return
  lastEventTs = ts

  const eventName = (latest?.event_code || latest?.event_name || '').toUpperCase()
  if (!eventName) return

  // 查找事件映射
  const phaseInfo = animConfig.getPhaseByEvent(eventName, currentFlowSelected.value)
  const expectedPhase = phaseInfo?.phase || '(未映射)'
  const expectedAnim = phaseInfo?.anim || ''

  // 添加到时间轴
  timelineEvents.value.unshift({
    ts,
    event_name: eventName,
    phase: expectedPhase,
    anim: expectedAnim,
    status: phaseInfo ? 'mapped' : 'unmapped',
  })
  if (timelineEvents.value.length > timelineMaxItems) {
    timelineEvents.value = timelineEvents.value.slice(0, timelineMaxItems)
  }

  // 添加到事件日志
  eventLog.value.unshift({
    ts,
    event_name: eventName,
    expected_phase: expectedPhase,
    expected_anim: expectedAnim,
    actual_phase: props.currentPhase,
    flow: currentFlowSelected.value,
    note: latest?.alarm_text || '',
  })
  if (eventLog.value.length > eventLogMaxItems) {
    eventLog.value = eventLog.value.slice(0, eventLogMaxItems)
  }

  // 偏差检测：如果期望阶段与实际阶段不匹配
  if (phaseInfo && props.currentPhase && expectedPhase !== props.currentPhase) {
    drifts.value.unshift({
      ts,
      eventName,
      expectedPhase,
      actualPhase: props.currentPhase,
      delayMs: 0,  // TODO: 后续可结合动画触发时间精确测量
    })
    if (drifts.value.length > 20) drifts.value = drifts.value.slice(0, 20)
  }
}, { deep: true })

watch(() => props.currentPhase, (newPhase) => {
  // 当前阶段变化时，更新时间轴上最近一条记录的 actualPhase
  if (timelineEvents.value.length > 0) {
    timelineEvents.value[0].actualPhase = newPhase
  }
})

// ============ E. 手动触发 ============
const manualEvents = computed(() => {
  const eventMap = animConfig.getEventMap(currentFlowSelected.value)
  return Object.entries(eventMap).map(([evt, def]) => ({
    event: evt,
    phase: def.phase,
    anim: def.anim,
    note: def.note || '',
  }))
})

function manualTrigger(evt) {
  emit('trigger-event', evt)
  // 记录到时间轴
  const now = new Date().toISOString()
  const phaseInfo = animConfig.getPhaseByEvent(evt, currentFlowSelected.value)
  timelineEvents.value.unshift({
    ts: now,
    event_name: evt,
    phase: phaseInfo?.phase || '(未映射)',
    anim: phaseInfo?.anim || '',
    status: phaseInfo ? 'manual' : 'unmapped',
    isManual: true,
  })
  if (timelineEvents.value.length > timelineMaxItems) {
    timelineEvents.value = timelineEvents.value.slice(0, timelineMaxItems)
  }
}

function jumpToPhase(phaseKey) {
  emit('jump-to-phase', { flow: currentFlowSelected.value, phase: phaseKey })
}

// ============ F. 配置热编辑 ============
function startEditConfig() {
  // 深拷贝当前配置作为编辑副本
  const cfg = animConfig.config.value
  if (!cfg) return
  editableConfig.value = JSON.parse(JSON.stringify(cfg))
  editDirty.value = false
}

function applyEditConfig() {
  if (!editableConfig.value) return
  try {
    animConfig.updateConfig(editableConfig.value)
    emit('config-updated', editableConfig.value)
    editDirty.value = false
    toast('配置已应用（仅本次会话生效）', 'success')
  } catch (e) {
    toast(`应用失败: ${e.message}`, 'error')
  }
}

function exportConfig() {
  const cfg = editableConfig.value || animConfig.config.value
  if (!cfg) return
  const text = JSON.stringify(cfg, null, 2)
  const blob = new Blob([text], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${props.machineType.toLowerCase()}.json`
  a.click()
  URL.revokeObjectURL(url)
  toast('配置已导出，请覆盖到 frontend/src/configs/machine-animations/ 目录', 'success')
}

// 编辑字段变更
function onPhaseDurationChange(flowKey, idx, value) {
  if (!editableConfig.value) return
  editableConfig.value.flows[flowKey].phases[idx].duration_ms = parseInt(value) || 100
  editDirty.value = true
}

function onEventPhaseChange(flowKey, evt, newPhase) {
  if (!editableConfig.value) return
  editableConfig.value.flows[flowKey].event_to_phase[evt].phase = newPhase
  editDirty.value = true
}

// ============ G. 动画录制器 ============
const recorderTargets = computed(() => {
  const cfg = editableConfig.value || animConfig.config.value
  return cfg ? Object.keys(cfg.targets) : []
})

function startRecording(target) {
  recorder.value.active = true
  recorder.value.startTime = performance.now()
  recorder.value.currentTarget = target
  recorder.value.keyframes = []
  toast(`录制中：拖拽 ${target} 部件，每帧会自动记录`, 'info')
}

function addKeyframe(axis, value) {
  if (!recorder.value.active) return
  const t = performance.now() - recorder.value.startTime
  recorder.value.keyframes.push({
    t: Math.round(t),
    target: recorder.value.currentTarget,
    axis,
    value: Math.round(value * 100) / 100,
  })
}

function stopRecording() {
  if (!recorder.value.active) return
  recorder.value.active = false
  if ( recorder.value.keyframes.length < 2) {
    toast('关键帧太少，无法生成动画', 'warn')
    return
  }
  // 从关键帧推断动画原语
  const first = recorder.value.keyframes[0]
  const last = recorder.value.keyframes[recorder.value.keyframes.length - 1]
  const duration = last.t - first.t
  const target = first.target
  const axis = first.axis
  const from = first.value
  const to = last.value

  const animKey = `${target}.recorded_${Date.now()}`
  const newAnim = {
    target,
    action: 'translate',
    axis,
    from,
    to,
    duration_ms: Math.max(100, duration),
    easing: 'mechanical',
    note: `录制生成 ${new Date().toLocaleString()}`,
  }
  if (editableConfig.value) {
    editableConfig.value.animations[animKey] = newAnim
    editDirty.value = true
    toast(`已生成动画原语: ${animKey}`, 'success')
  } else {
    toast('请先开启配置编辑模式', 'warn')
  }
}

// ============ 通用 toast ============
const toasts = ref([])
function toast(msg, type = 'info') {
  const id = Date.now() + Math.random()
  toasts.value.push({ id, msg, type })
  setTimeout(() => {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }, 3000)
}

// ============ 时间轴可视化计算 ============
const timelineBars = computed(() => {
  // 把最近的事件转成时间轴条
  if (timelineEvents.value.length === 0) return []
  const now = Date.now()
  const oldest = new Date(timelineEvents.value[timelineEvents.value.length - 1].ts).getTime()
  const span = Math.max(1000, now - oldest)
  return timelineEvents.value.map(e => {
    const t = new Date(e.ts).getTime()
    const left = ((t - oldest) / span) * 100
    return { ...e, leftPercent: Math.max(0, Math.min(100, left)) }
  })
})

// ============ 生命周期 ============
onMounted(async () => {
  await animConfig.loadConfig()
})

onUnmounted(() => {
  // 清理
})
</script>

<template>
  <div class="debugger-panel">
    <!-- 顶部 Tab 切换 -->
    <div class="debugger-tabs">
      <button :class="{ active: activeTab === 'timeline' }" @click="activeTab = 'timeline'">时间轴</button>
      <button :class="{ active: activeTab === 'events' }" @click="activeTab = 'events'">事件列表</button>
      <button :class="{ active: activeTab === 'manual' }" @click="activeTab = 'manual'">手动触发</button>
      <button :class="{ active: activeTab === 'config' }" @click="activeTab = 'config'">配置编辑</button>
      <button :class="{ active: activeTab === 'recorder' }" @click="activeTab = 'recorder'">动画录制</button>
      <div class="tab-spacer"></div>
      <select v-model="currentFlowSelected" class="flow-select">
        <option value="PACKING">PACKING (穿入)</option>
        <option value="UNPACKING">UNPACKING (脱出)</option>
      </select>
    </div>

    <!-- A. 时间轴轨道 -->
    <div v-if="activeTab === 'timeline'" class="tab-content">
      <div class="section-title">A. 事件-阶段-动画时间轴</div>
      <div class="timeline-container">
        <div class="timeline-track">
          <div class="track-label">事件</div>
          <div class="track-line">
            <div v-for="(bar, idx) in timelineBars" :key="idx"
                 class="track-marker event-marker"
                 :class="bar.status"
                 :style="{ left: bar.leftPercent + '%' }"
                 :title="`${bar.event_name} @ ${bar.ts}`">
              <span class="marker-dot"></span>
              <span class="marker-label">{{ bar.event_name }}</span>
            </div>
          </div>
        </div>
        <div class="timeline-track">
          <div class="track-label">阶段</div>
          <div class="track-line">
            <div v-for="(bar, idx) in timelineBars" :key="'p' + idx"
                 class="track-marker phase-marker"
                 :class="{ current: idx === 0 }"
                 :style="{ left: bar.leftPercent + '%' }">
              <span class="marker-dot"></span>
              <span class="marker-label">{{ bar.phase }}</span>
            </div>
          </div>
        </div>
        <div class="timeline-track">
          <div class="track-label">动画</div>
          <div class="track-line">
            <div v-for="(bar, idx) in timelineBars" :key="'a' + idx"
                 class="track-marker anim-marker"
                 :style="{ left: bar.leftPercent + '%' }">
              <span class="marker-dot"></span>
              <span class="marker-label">{{ bar.anim || '-' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- D. 偏差检测 -->
      <div class="section-title" style="margin-top: 16px;">D. 偏差检测</div>
      <div v-if="drifts.length === 0" class="empty-hint">暂无偏差</div>
      <div v-else class="drift-list">
        <div v-for="(d, idx) in drifts" :key="idx" class="drift-item">
          <span class="drift-ts">{{ d.ts.slice(11, 19) }}</span>
          <span class="drift-event">{{ d.eventName }}</span>
          <span class="drift-arrow">→</span>
          <span class="drift-expected">期望: {{ d.expectedPhase }}</span>
          <span class="drift-arrow">≠</span>
          <span class="drift-actual">实际: {{ d.actualPhase }}</span>
        </div>
      </div>
    </div>

    <!-- B. 事件列表 -->
    <div v-if="activeTab === 'events'" class="tab-content">
      <div class="section-title">B. 事件日志（最近 {{ eventLog.length }} 条）</div>
      <div v-if="eventLog.length === 0" class="empty-hint">等待事件中...</div>
      <table v-else class="event-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>事件</th>
            <th>流程</th>
            <th>期望阶段</th>
            <th>实际阶段</th>
            <th>动画</th>
            <th>备注</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(e, idx) in eventLog" :key="idx" :class="{ drift: e.expected_phase !== e.actual_phase }">
            <td>{{ e.ts.slice(11, 19) }}</td>
            <td class="event-name">{{ e.event_name }}</td>
            <td>{{ e.flow }}</td>
            <td>{{ e.expected_phase }}</td>
            <td :class="{ 'actual-drift': e.expected_phase !== e.actual_phase }">{{ e.actual_phase || '-' }}</td>
            <td class="anim-name">{{ e.expected_anim || '-' }}</td>
            <td>{{ e.note }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- E. 手动触发 -->
    <div v-if="activeTab === 'manual'" class="tab-content">
      <div class="section-title">E. 手动触发事件（{{ currentFlowSelected }} 流程）</div>
      <div class="manual-grid">
        <button v-for="m in manualEvents" :key="m.event"
                class="manual-btn"
                @click="manualTrigger(m.event)">
          <div class="btn-event">{{ m.event }}</div>
          <div class="btn-phase">→ {{ m.phase }}</div>
          <div v-if="m.note" class="btn-note">{{ m.note }}</div>
        </button>
      </div>
      <div class="section-title" style="margin-top: 16px;">直接跳转阶段</div>
      <div class="phase-jump">
        <button v-for="(p, idx) in phases" :key="p.key"
                class="phase-btn"
                @click="jumpToPhase(p.key)">
          {{ idx + 1 }}. {{ p.label }}
        </button>
      </div>
    </div>

    <!-- F. 配置热编辑 -->
    <div v-if="activeTab === 'config'" class="tab-content">
      <div class="section-title">F. 配置热编辑</div>
      <div class="config-actions">
        <button @click="startEditConfig" :disabled="!animConfig.config.value">开始编辑</button>
        <button @click="applyEditConfig" :disabled="!editDirty">应用变更</button>
        <button @click="exportConfig">导出 JSON</button>
        <span v-if="editDirty" class="dirty-flag">有未保存变更</span>
      </div>

      <div v-if="editableConfig" class="config-editor">
        <!-- 阶段时长编辑 -->
        <div v-for="flowKey in ['PACKING', 'UNPACKING']" :key="flowKey" class="config-flow">
          <h4>{{ flowKey }} 阶段时长</h4>
          <div v-for="(p, idx) in editableConfig.flows[flowKey].phases" :key="p.key" class="phase-edit-row">
            <span class="phase-key">{{ p.key }}</span>
            <span class="phase-label">{{ p.label }}</span>
            <input type="number" v-model.number="p.duration_ms" min="100" step="100"
                   @change="onPhaseDurationChange(flowKey, idx, $event.target.value)" />
            <span class="unit">ms</span>
          </div>
        </div>
        <!-- 事件映射编辑（仅当前选中流程） -->
        <div class="config-flow">
          <h4>{{ currentFlowSelected }} 事件映射</h4>
          <div v-for="(def, evt) in editableConfig.flows[currentFlowSelected].event_to_phase"
               :key="evt" class="event-edit-row">
            <span class="event-key">{{ evt }}</span>
            <span class="arrow">→</span>
            <select v-model="def.phase"
                    @change="onEventPhaseChange(currentFlowSelected, evt, $event.target.value)">
              <option v-for="p in editableConfig.flows[currentFlowSelected].phases"
                      :key="p.key" :value="p.key">{{ p.key }} ({{ p.label }})</option>
            </select>
            <span class="anim-tag">{{ def.anim }}</span>
          </div>
        </div>
      </div>
      <div v-else class="empty-hint">点击"开始编辑"加载当前配置</div>
    </div>

    <!-- G. 动画录制器 -->
    <div v-if="activeTab === 'recorder'" class="tab-content">
      <div class="section-title">G. 动画录制器</div>
      <div class="recorder-hint">
        功能：选择部件 → 点"开始录制" → 在 2D/3D 视图中拖拽该部件 → 点"停止录制"
        系统会自动生成动画原语配置（from/to/duration），添加到配置编辑器中。
      </div>
      <div class="recorder-controls">
        <select v-model="recorder.currentTarget">
          <option v-for="t in recorderTargets" :key="t" :value="t">{{ t }}</option>
        </select>
        <button @click="startRecording(recorder.currentTarget)" :disabled="!recorder.currentTarget || recorder.active">
          开始录制
        </button>
        <button @click="stopRecording" :disabled="!recorder.active">停止录制</button>
        <span v-if="recorder.active" class="recording-badge">● 录制中 ({{ recorder.keyframes.length }} 帧)</span>
      </div>
      <div v-if="recorder.keyframes.length > 0" class="keyframe-list">
        <div class="section-title">已录制关键帧</div>
        <div v-for="(kf, idx) in recorder.keyframes" :key="idx" class="keyframe-row">
          <span>t={{ kf.t }}ms</span>
          <span>{{ kf.target }}.{{ kf.axis }} = {{ kf.value }}</span>
        </div>
      </div>
      <div class="recorder-tip">
        提示：本录制器目前需要父组件（MachineDetail）配合监听 2D/3D 部件拖拽事件，
        调用 addKeyframe(axis, value) 添加关键帧。完整集成在 M3 后续迭代中完善。
      </div>
    </div>

    <!-- Toast 消息 -->
    <div class="toast-container">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="t.type">{{ t.msg }}</div>
    </div>
  </div>
</template>

<style scoped>
.debugger-panel {
  background: #1e1e2e;
  color: #e0e0e8;
  padding: 12px;
  font-family: 'Segoe UI', system-ui, sans-serif;
  font-size: 13px;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.debugger-tabs {
  display: flex;
  gap: 4px;
  padding-bottom: 8px;
  border-bottom: 1px solid #3a3a4a;
  margin-bottom: 12px;
  align-items: center;
}
.debugger-tabs button {
  background: #2a2a3a;
  color: #b0b0c0;
  border: 1px solid #3a3a4a;
  padding: 6px 12px;
  border-radius: 4px 4px 0 0;
  cursor: pointer;
  font-size: 13px;
}
.debugger-tabs button.active {
  background: #3b82f6;
  color: #fff;
  border-color: #3b82f6;
}
.debugger-tabs .tab-spacer { flex: 1; }
.flow-select {
  background: #2a2a3a;
  color: #e0e0e8;
  border: 1px solid #4a4a5a;
  padding: 4px 8px;
  border-radius: 4px;
}

.tab-content {
  flex: 1;
  overflow-y: auto;
  padding-right: 4px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #a0c4ff;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid #3a3a4a;
}

.empty-hint {
  color: #707080;
  font-style: italic;
  padding: 12px 0;
}

/* 时间轴 */
.timeline-container {
  background: #15151f;
  border: 1px solid #2a2a3a;
  border-radius: 4px;
  padding: 12px;
}
.timeline-track {
  display: flex;
  align-items: center;
  height: 48px;
  margin-bottom: 8px;
  position: relative;
}
.track-label {
  width: 60px;
  color: #9090a0;
  font-size: 12px;
  flex-shrink: 0;
}
.track-line {
  flex: 1;
  height: 100%;
  position: relative;
  background: linear-gradient(to right, transparent 0%, #2a2a3a 1%, #2a2a3a 99%, transparent 100%);
}
.track-marker {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
}
.marker-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #3b82f6;
}
.marker-label {
  font-size: 10px;
  color: #b0b0c0;
  white-space: nowrap;
  margin-top: 2px;
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.event-marker .marker-dot { background: #f59e0b; }
.event-marker.unmapped .marker-dot { background: #ef4444; }
.event-marker.manual .marker-dot { background: #10b981; }
.phase-marker .marker-dot { background: #a78bfa; }
.phase-marker.current .marker-dot { background: #fff; box-shadow: 0 0 6px #fff; }
.anim-marker .marker-dot { background: #06b6d4; }

/* 偏差检测 */
.drift-list { display: flex; flex-direction: column; gap: 4px; }
.drift-item {
  display: flex;
  gap: 8px;
  padding: 6px 8px;
  background: #3a1a1a;
  border-left: 3px solid #ef4444;
  border-radius: 2px;
  font-size: 12px;
}
.drift-ts { color: #9090a0; }
.drift-event { color: #f59e0b; font-weight: 600; }
.drift-expected { color: #a0c4ff; }
.drift-actual { color: #ef4444; }
.drift-arrow { color: #707080; }

/* 事件表格 */
.event-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.event-table th, .event-table td {
  padding: 6px 8px;
  text-align: left;
  border-bottom: 1px solid #2a2a3a;
}
.event-table th {
  background: #2a2a3a;
  color: #a0c4ff;
  font-weight: 600;
}
.event-table tr.drift { background: rgba(239, 68, 68, 0.1); }
.event-name { color: #f59e0b; font-weight: 600; }
.anim-name { color: #06b6d4; }
.actual-drift { color: #ef4444; }

/* 手动触发 */
.manual-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}
.manual-btn {
  background: #2a2a3a;
  color: #e0e0e8;
  border: 1px solid #4a4a5a;
  border-radius: 4px;
  padding: 8px;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s;
}
.manual-btn:hover {
  background: #3a3a4a;
  border-color: #3b82f6;
}
.btn-event { font-weight: 600; color: #f59e0b; font-size: 12px; }
.btn-phase { color: #a0c4ff; font-size: 11px; margin-top: 2px; }
.btn-note { color: #808090; font-size: 10px; margin-top: 2px; }

.phase-jump {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.phase-btn {
  background: #2a2a3a;
  color: #b0b0c0;
  border: 1px solid #4a4a5a;
  padding: 4px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
}
.phase-btn:hover { background: #3a3a4a; }

/* 配置编辑 */
.config-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.config-actions button {
  background: #3b82f6;
  color: #fff;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
}
.config-actions button:disabled {
  background: #4a4a5a;
  cursor: not-allowed;
}
.dirty-flag { color: #f59e0b; font-size: 12px; }

.config-editor { display: flex; flex-direction: column; gap: 16px; }
.config-flow h4 { color: #a0c4ff; margin-bottom: 8px; }
.phase-edit-row, .event-edit-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid #2a2a3a;
}
.phase-key { color: #a78bfa; min-width: 180px; font-family: monospace; }
.phase-label { color: #b0b0c0; min-width: 100px; }
.event-key { color: #f59e0b; min-width: 200px; font-family: monospace; }
.arrow { color: #707080; }
.anim-tag { color: #06b6d4; font-size: 11px; }
.unit { color: #808090; font-size: 11px; }
input[type="number"], select {
  background: #15151f;
  color: #e0e0e8;
  border: 1px solid #4a4a5a;
  padding: 2px 6px;
  border-radius: 3px;
}

/* 动画录制器 */
.recorder-hint {
  background: #2a2a3a;
  padding: 8px;
  border-radius: 4px;
  color: #b0b0c0;
  margin-bottom: 12px;
  font-size: 12px;
  line-height: 1.5;
}
.recorder-controls {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.recorder-controls button {
  background: #ef4444;
  color: #fff;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
}
.recorder-controls button:disabled { background: #4a4a5a; cursor: not-allowed; }
.recording-badge {
  color: #ef4444;
  font-weight: 600;
  animation: blink 1s infinite;
}
@keyframes blink { 50% { opacity: 0.5; } }
.keyframe-list { margin-top: 12px; }
.keyframe-row {
  display: flex;
  gap: 16px;
  padding: 4px 0;
  border-bottom: 1px solid #2a2a3a;
  font-family: monospace;
  font-size: 11px;
  color: #b0b0c0;
}
.recorder-tip {
  margin-top: 16px;
  padding: 8px;
  background: #3a3a1a;
  border-left: 3px solid #f59e0b;
  font-size: 11px;
  color: #c0c0a0;
}

/* Toast */
.toast-container {
  position: fixed;
  bottom: 12px;
  right: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  z-index: 9999;
}
.toast {
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 12px;
  color: #fff;
  animation: slideIn 0.2s;
}
.toast.success { background: #10b981; }
.toast.error { background: #ef4444; }
.toast.info { background: #3b82f6; }
.toast.warn { background: #f59e0b; }
@keyframes slideIn { from { transform: translateX(20px); opacity: 0; } }
</style>
