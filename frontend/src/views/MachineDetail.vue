<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAppStore } from '../stores/app'
import { useModelStore } from '../stores/model'
import { api } from '../api'
import { stateLabels } from '../composables/useThree'
import MachineModel3D from '../components/MachineModel3D.vue'
import MachineModel2D from '../components/MachineModel2D.vue'
import MachineIsoView from '../components/MachineIsoView.vue'
import MachineOxeView from '../components/MachineOxeView.vue'
import MachineVpoView from '../components/MachineVpoView.vue'
import MachineVpo3DView from '../components/MachineVpo3DView.vue'
import PlaybackBar from '../components/PlaybackBar.vue'
import AlarmStats from '../components/AlarmStats.vue'
import EventList from '../components/EventList.vue'
import LotList from '../components/LotList.vue'
import AiAssistant from '../components/AiAssistant.vue'
import HistoryReplay from '../components/HistoryReplay.vue'
import { parseEventAction } from '../composables/useEventActionMapping'

// 时间戳解析：统一处理东八区时间
// 后端返回的时间戳已去掉Z后缀，但需兼容历史数据可能带Z的情况
// 带Z的时间戳实际上是东八区时间被误标为UTC，需要去掉Z后按本地时间解析
function parseTs(ts) {
  if (!ts) return 0
  const str = String(ts).trim()
  // 去掉Z后缀和时区偏移，按本地时间（东八区）解析
  const localStr = str.replace(/Z$/, '').replace(/[+-]\d{2}:\d{2}$/, '')
  const d = new Date(localStr)
  return isNaN(d.getTime()) ? 0 : d.getTime()
}

// 机台详情：3D 模型 + 2D原理图 + 回放 + 右侧 Tab（告警/事件/Lot/AI）
const props = defineProps({
  id: { type: String, default: '' },
})

// ============ 机台详情 AI Tab：专用Dify配置管理面板 ============
const machineDifyForm = ref({
  id: null,              // 已有记录的主键（null表示新建）
  config_name: '',
  model_id: '',          // 机台型号ID（匹配 MACHINE_DIFY_CONFIGS.model_id），如 OXE / PODOPENER
  dify_base_url: '',
  dify_api_key: '',      // 新输入时用真实值；加载后若 DB 已保存但用户没改，会显示为掩码预览，保存时判断是否仍含 **** 以决定不覆盖原有 key
  is_active: 1,
})
const machineDifyTestState = ref({ loading: false, message: '', level: '' })
const machineDifySaveState = ref({ loading: false, message: '', level: '' })
const machineDifyModelIdHint = ref('')   // 辅助提示（从machine.model推导）
const showMachineDifyPanel = ref(true)  // 折叠：默认展开

// AiAssistant ref -> 修改完配置后调用它的 reloadRouting()
const aiAssistantVueRef = ref(null)

function inferModelIdFromMachine(m) {
  // 与后端保持一致：优先 machine.model，否则取机台ID第一个 - 前缀
  if (m && m.model && String(m.model).trim()) return String(m.model).trim().toUpperCase()
  const mid = String(m ? (m.id || machineId.value) : (machineId.value || '')).trim().toUpperCase()
  if (!mid) return ''
  if (mid.includes('-')) return mid.split('-')[0]
  return mid
}

// 加载/刷新机台Dify配置（通过 /machine-routing），同时填充表单
async function loadMachineDifyConfig() {
  try {
    // 用新增的 machine-routing API 获取当前是否已有机台专属Dify
    const r = await api.aiGetMachineAiRouting(machineId.value)
    const modelIdHint = inferModelIdFromMachine(machine.value)
    machineDifyModelIdHint.value = modelIdHint
    // 初始化表单
    if (r.machine_dify) {
      // 有配置：回填（dify_api_key 填掩码预览）
      machineDifyForm.value = {
        id: r.machine_dify.id,
        config_name: r.machine_dify.config_name || `Dify · ${r.machine_dify.model_id || ''}`,
        model_id: r.machine_dify.model_id || modelIdHint,
        dify_base_url: r.machine_dify.dify_base_url || '',
        dify_api_key: r.machine_dify.dify_api_key_preview || '',   // 掩码预览
        is_active: r.machine_dify.is_active == 0 ? 0 : 1,
      }
    } else {
      machineDifyForm.value = {
        id: null,
        config_name: `Dify · ${modelIdHint || machineId.value}`,
        model_id: modelIdHint || machineId.value,
        dify_base_url: '',
        dify_api_key: '',
        is_active: 1,
      }
    }
    machineDifySaveState.value = { loading: false, message: '', level: '' }
    machineDifyTestState.value = { loading: false, message: '', level: '' }
  } catch (e) {
    console.warn('[MachineDetail] 加载机台Dify配置失败:', e)
  }
}

// 判断输入框当前的 api_key 值是否为掩码预览（不是用户实际新输入）
function isMaskedPreview(str) {
  return typeof str === 'string' && /\*{4,}/.test(str)
}

async function testMachineDify() {
  const form = machineDifyForm.value
  if (!form.dify_base_url) {
    machineDifyTestState.value = { loading: false, message: '请先填写 Dify API 地址', level: 'error' }
    return
  }
  let apiKey = form.dify_api_key
  // 若是掩码预览 → 说明 UI 上没改 key，这时候测试要用 DB 里的真实key。
  // 直接让后端调用 /ai/config/test 传入 "****" 这种掩码无法通过 dify 实际校验。
  // 因此前端这里提供明确提示：若已保存，请先保存或改用 aiTestConnection + 复用 saved DB key 逻辑
  if (isMaskedPreview(apiKey)) {
    // 如果已有id（=在DB里有记录），调用后端配置测试接口（后端 test_connection 逻辑会走 DB saved fallback）
    if (!form.id) {
      machineDifyTestState.value = { loading: false, message: '已保存的 API Key 显示为掩码；请先点"保存配置"再测试，或手动重新输入真实 API Key', level: 'warn' }
      return
    }
    machineDifyTestState.value = { loading: true, message: '使用已保存凭据测试中...', level: '' }
    try {
      // 用 masked 形式走 /ai/config/test → 后端 test_connection 中 Dify 分支已兼容 masked_preview 用 DB值
      const res = await api.aiTestConnection('dify', {
        dify_enabled: true,
        dify_base_url: form.dify_base_url,
        dify_api_key: apiKey,  // 掩码预览，后端会走 DB fallback
      })
      machineDifyTestState.value = {
        loading: false,
        message: res.success ? (res.message || '连接成功') : (res.message || '连接失败'),
        level: res.success ? 'success' : 'error',
      }
    } catch (e) {
      machineDifyTestState.value = { loading: false, message: '测试失败：' + (e.message || String(e)), level: 'error' }
    }
    return
  }
  // 用户输入了真实 key → 直接测试
  if (!apiKey) {
    machineDifyTestState.value = { loading: false, message: '请先输入 Dify API Key', level: 'error' }
    return
  }
  machineDifyTestState.value = { loading: true, message: '测试连接中...', level: '' }
  try {
    const res = await api.aiTestMachineDify({ dify_base_url: form.dify_base_url, dify_api_key: apiKey })
    machineDifyTestState.value = {
      loading: false,
      message: res.success ? (res.message || '连接成功') : (res.message || '连接失败'),
      level: res.success ? 'success' : 'error',
    }
  } catch (e) {
    machineDifyTestState.value = { loading: false, message: '测试失败：' + (e.message || String(e)), level: 'error' }
  }
}

async function saveMachineDify() {
  const form = machineDifyForm.value
  if (!form.model_id) {
    machineDifySaveState.value = { loading: false, message: '请填写 机台型号（model_id，如 OXE）', level: 'error' }
    return
  }
  if (!form.dify_base_url) {
    machineDifySaveState.value = { loading: false, message: '请填写 Dify API 地址', level: 'error' }
    return
  }
  // 如果是更新（已有 id）且 api_key 框仍是掩码预览，说明用户没改 key → 不传 dify_api_key，后端 update 会忽略这个字段，保留原值
  const payload = {
    config_name: form.config_name || `Dify · ${form.model_id}`,
    model_id: String(form.model_id).trim().toUpperCase(),
    dify_base_url: String(form.dify_base_url).trim().replace(/\/$/, ''),
    is_active: form.is_active ? 1 : 0,
  }
  const masked = isMaskedPreview(form.dify_api_key)
  if (form.id && masked) {
    // 更新但不改 key，不传 dify_api_key
  } else if (!form.dify_api_key || masked) {
    machineDifySaveState.value = { loading: false, message: '新建配置需要填写真实的 Dify API Key', level: 'error' }
    return
  } else {
    payload.dify_api_key = form.dify_api_key
  }

  machineDifySaveState.value = { loading: true, message: form.id ? '保存中...' : '创建中...', level: '' }
  try {
    if (form.id) {
      await api.aiUpdateMachineDifyConfig(form.id, payload)
      machineDifySaveState.value = { loading: false, message: '机台专属 Dify 已更新', level: 'success' }
    } else {
      const created = await api.aiCreateMachineDifyConfig(payload)
      machineDifyForm.value.id = created.id || null
      machineDifySaveState.value = { loading: false, message: '机台专属 Dify 已创建并生效', level: 'success' }
    }
    // 刷新 AiAssistant 的 Routing Bar（应变成 machine_dify）
    if (aiAssistantVueRef.value && typeof aiAssistantVueRef.value.reloadRouting === 'function') {
      await aiAssistantVueRef.value.reloadRouting()
    }
  } catch (e) {
    machineDifySaveState.value = { loading: false, message: '保存失败：' + (e.message || String(e)), level: 'error' }
  }
}

async function disableOrDeleteMachineDify() {
  const form = machineDifyForm.value
  if (!form.id) return
  // 先尝试「禁用」（is_active=0），若用户再点才删除
  if (form.is_active) {
    try {
      await api.aiUpdateMachineDifyConfig(form.id, { is_active: 0 })
      machineDifyForm.value.is_active = 0
      machineDifySaveState.value = { loading: false, message: '已禁用该机台型号的 Dify 配置（仍保留，可再次启用）', level: 'warn' }
      if (aiAssistantVueRef.value && typeof aiAssistantVueRef.value.reloadRouting === 'function') {
        await aiAssistantVueRef.value.reloadRouting()
      }
      return
    } catch (e) {
      machineDifySaveState.value = { loading: false, message: '禁用失败：' + (e.message || String(e)), level: 'error' }
      return
    }
  }
  if (!confirm(`确定要永久删除 型号 ${form.model_id} 的 Dify 专用配置吗？（删除后该型号会走 全局Dify/LLM/本地规则）`)) return
  try {
    await api.aiDeleteMachineDifyConfig(form.id)
    machineDifyForm.value.id = null
    machineDifyForm.value.is_active = 0
    machineDifySaveState.value = { loading: false, message: '已删除该机台型号 Dify 专用配置', level: 'success' }
    await loadMachineDifyConfig()
    if (aiAssistantVueRef.value && typeof aiAssistantVueRef.value.reloadRouting === 'function') {
      await aiAssistantVueRef.value.reloadRouting()
    }
  } catch (e) {
    machineDifySaveState.value = { loading: false, message: '删除失败：' + (e.message || String(e)), level: 'error' }
  }
}

// 加载机台基本信息 + 数据完成后，再加载机台Dify配置
watch(() => machine.value, (m) => {
  if (m) loadMachineDifyConfig()
}, { immediate: false })

const router = useRouter()
const route = useRoute()
const appStore = useAppStore()
const modelStore = useModelStore()

// === 状态 ===
const machine = ref(null)
// 是否使用外部跳转网站（iframe 嵌入）替代原生 2D/3D 视图
const useExternalView = computed(() => !!(machine.value?.use_external_url && machine.value?.external_url))
// 嵌入用 URL：自动补全协议前缀，避免被浏览器解析为相对路径
const externalFrameUrl = computed(() => {
  const raw = (machine.value?.external_url || '').trim()
  if (!raw) return ''
  return /^https?:\/\//i.test(raw) ? raw : 'https://' + raw
})
const mode = ref('realtime')              // realtime / playback
const playing = ref(true)
const speed = ref(2)
const today = new Date()
const playbackDate = ref(`${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`)
const cursor = ref(0)                     // 回放游标时间戳
const playbackStart = ref(0)
const playbackEnd = ref(0)
const rightTab = ref('alarms')
const aiAssistantRef = ref(null)
const aiPrefillQuestion = ref('')  // 从回放 Tab 传递过来的预填问题
const currentState = ref('idle')
const processStep = ref('待机')
const metrics = reactive({ temp: 22, pressure: 1, gas: 0, rf: 0, waferCount: 0 })
const events = ref([])
const alarms = ref([])
const lots = ref([])
const alarmStats = ref({ total: 0, crit: 0, warn: 0, temperature: 0, pressure: 0, rf_drift: 0, gas_leak: 0, resolved: 0, unresolved: 0 })
const selectedLotId = ref('')
const transferTrigger = ref(0)
const loading = ref(false)
const currentLotId = ref('')  // 当前正在run的Lot ID
const pendingJumpTs = ref('') // 等待数据加载完成后执行的跳转时间戳

// === 视图模式（根据机台型号自动选择） ===
const viewMode = ref('loading')           // loading / 3d / 2d / iso / vpo / vpo3d
const currentModelConfig = ref(null)
const modelConfigReady = ref(false)

function resolveViewMode(machineModel) {
  const vm = modelStore.getViewMode(machineModel)
  // OXE 机台：默认显示 Canvas 实时看板
  const machineIdVal = machine.value?.id || ''
  if (machineIdVal.toUpperCase().startsWith('OXE')) {
    return 'oxe'
  }
  // PODOPENER机台：如果view_3d.type=vpo则优先显示3D，否则显示2D
  if (vm === 'vpo' || vm === 'svg-vpo' || vm === 'vpo3d' || vm === 'vpo-3d') {
    // 默认优先展示 3D 视图（更具沉浸感）
    const cfg = modelStore.getModelById(modelStore.resolveModelId(machineModel))
    if (cfg?.views_config?.view_3d?.type === 'vpo') return 'vpo3d'
    return 'vpo'
  }
  if (vm === 'isometric' || vm === 'iso') return 'iso'
  if (vm === 'hybrid') return '2d'
  if (vm === 'svg') return '2d'
  return '3d'
}

const availableViews = computed(() => {
  const cfg = currentModelConfig.value
  if (!cfg) return []
  const views = []
  // OXE 机台：仅显示 Canvas 实时看板视图，不显示 3D/2.5D 等其他视图
  const machineIdVal = machine.value?.id || ''
  const isOxe = machineIdVal.toUpperCase().startsWith('OXE')
  if (isOxe) {
    views.push({ key: 'oxe', label: '📊 OXE看板' })
    return views
  }
  const isVpo = cfg.view_mode === 'vpo' || cfg.view_mode === 'vpo3d' || cfg.view_mode === 'vpo-3d' ||
                 cfg.views_config?.view_2d?.type === 'vpo' || cfg.views_config?.view_3d?.type === 'vpo'
  if (!isVpo && (cfg.views_config?.view_3d || cfg.view_mode === 'threejs' || cfg.view_mode === 'hybrid')) {
    views.push({ key: '3d', label: '🎯 3D模型' })
  }
  if (cfg.view_mode === 'isometric' || cfg.view_mode === 'iso' || cfg.views_config?.view_2d?.type === 'isometric') {
    views.push({ key: 'iso', label: '📐 2.5D等角' })
  }
  if (cfg.view_mode === 'vpo' || cfg.view_mode === 'svg-vpo' || cfg.views_config?.view_2d?.type === 'vpo') {
    views.push({ key: 'vpo', label: '📋 PODOPENER 2D' })
  }
  if (cfg.view_mode === 'vpo3d' || cfg.view_mode === 'vpo-3d' || cfg.views_config?.view_3d?.type === 'vpo') {
    views.push({ key: 'vpo3d', label: '🎯 PODOPENER 3D' })
  }
  if (!isVpo && (cfg.views_config?.view_2d?.type === 'svg' || cfg.view_mode === 'svg' || cfg.view_mode === 'hybrid')) {
    views.push({ key: '2d', label: '📋 2D视图' })
  }
  if (views.length === 0) views.push({ key: '3d', label: '🎯 3D模型' })
  return views
})

// ===== Run货动画状态（2D/3D共用） =====
const TOTAL_WAFERS = 25

// SVG坐标系中各模块相对ARM中心的角度（0=右, 90=下, 180=左, 270=上）
const TARGET_ANGLES = {
  port: 150,        // PORT1方向（左下）
  pa: 180,          // PA方向（左）
  chamberA: 250,    // Chamber A（左上）
  chamberB: 290,    // Chamber B（右上）
  chamberC: 0,      // Chamber C（右）
  idle: 90,         // 待机（向下）
}
const CHAMBER_KEYS = ['chamberA', 'chamberB', 'chamberC']

// 每片晶圆的完整run货流程（10步，每步含子阶段）
const RUN_STEPS = [
  { key: 'pick_port',     name: 'PORT取片',   duration: 2500 },
  { key: 'place_pa',      name: '放置PA',     duration: 2000 },
  { key: 'pa_align',      name: 'PA对准',     duration: 2500 },
  { key: 'pick_pa',       name: 'PA取片',     duration: 2000 },
  { key: 'place_chamber', name: '放入腔体',   duration: 2500 },
  { key: 'chamber_proc',  name: '腔体加工',   duration: 6000 },
  { key: 'pick_chamber',  name: '腔体取片',   duration: 2500 },
  { key: 'place_pa2',     name: 'PA放回',     duration: 2000 },
  { key: 'pick_pa2',      name: 'PA取回',     duration: 2000 },
  { key: 'place_port',    name: 'PORT放回',   duration: 2500 },
]
const SINGLE_WAFER_MS = RUN_STEPS.reduce((s, st) => s + st.duration, 0)
const TOTAL_RUN_MS = SINGLE_WAFER_MS * TOTAL_WAFERS

const runState = reactive({
  currentWafer: 0,
  currentStep: 0,
  stepProgress: 0,
  armAngle: 90,          // 当前角度
  armExtension: 0,       // 0=收回, 1=完全伸出
  gripperClosed: false,  // 夹爪是否闭合
  armHolding: null,      // 夹持的晶圆ID
  waferLocation: null,   // 晶圆所在位置: 'port'|'pa'|'chamberA'|'chamberB'|'chamberC'|'arm'|null
  chambers: [
    { id: 'A', state: 'idle', wafer: null, progress: 0 },
    { id: 'B', state: 'idle', wafer: null, progress: 0 },
    { id: 'C', state: 'idle', wafer: null, progress: 0 },
  ],
  waferStatuses: Array.from({ length: TOTAL_WAFERS }, (_, i) => ({
    id: `W${String(i + 1).padStart(2, '0')}`,
    status: 'pending',
  })),
})

function lerp(a, b, t) { return a + (b - a) * Math.max(0, Math.min(1, t)) }
function easeInOut(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2 }

// 根据时间偏移计算run货状态
function calcRunState(timeOffsetMs) {
  if (timeOffsetMs < 0) timeOffsetMs = 0
  const totalMs = timeOffsetMs % TOTAL_RUN_MS
  const waferIdx = Math.floor(totalMs / SINGLE_WAFER_MS)
  const waferTime = totalMs - waferIdx * SINGLE_WAFER_MS
  const waferId = `W${String(waferIdx + 1).padStart(2, '0')}`
  
  let stepIdx = 0
  let stepProgress = 0
  let acc = 0
  for (let i = 0; i < RUN_STEPS.length; i++) {
    if (waferTime < acc + RUN_STEPS[i].duration) {
      stepIdx = i
      stepProgress = (waferTime - acc) / RUN_STEPS[i].duration
      break
    }
    acc += RUN_STEPS[i].duration
    stepIdx = i
    stepProgress = 1
  }
  
  const chamberIdx = waferIdx % 3
  const chamberKey = CHAMBER_KEYS[chamberIdx]
  const chamberAngle = TARGET_ANGLES[chamberKey]
  const stepKey = RUN_STEPS[stepIdx].key
  const p = stepProgress
  
  // 默认值
  let armAngle = TARGET_ANGLES.idle
  let armExtension = 0
  let gripperClosed = false
  let armHolding = null
  let waferLocation = null
  
  const chambers = [
    { id: 'A', state: 'idle', wafer: null, progress: 0 },
    { id: 'B', state: 'idle', wafer: null, progress: 0 },
    { id: 'C', state: 'idle', wafer: null, progress: 0 },
  ]
  
  // 每步分4个子阶段: 旋转(0-0.25) → 伸出(0.25-0.5) → 夹爪动作(0.5-0.6) → 收回(0.6-1.0)
  const rotEnd = 0.25
  const extEnd = 0.5
  const gripEnd = 0.6
  const rotT = easeInOut(p / rotEnd)
  const extT = easeInOut((p - rotEnd) / (extEnd - rotEnd))
  const retT = easeInOut((p - gripEnd) / (1 - gripEnd))
  
  switch (stepKey) {
    case 'pick_port': // 从PORT取片
      if (p < rotEnd) {
        armAngle = lerp(TARGET_ANGLES.idle, TARGET_ANGLES.port, rotT)
      } else if (p < extEnd) {
        armAngle = TARGET_ANGLES.port
        armExtension = extT
      } else if (p < gripEnd) {
        armAngle = TARGET_ANGLES.port
        armExtension = 1
        gripperClosed = p > (gripEnd + extEnd) / 2
        if (gripperClosed) { armHolding = waferId; waferLocation = 'arm' }
        else { waferLocation = 'port' }
      } else {
        armAngle = TARGET_ANGLES.port
        armExtension = 1 - retT
        gripperClosed = true
        armHolding = waferId
        waferLocation = 'arm'
      }
      break
      
    case 'place_pa': // 放到PA上
      if (p < rotEnd) {
        armAngle = lerp(TARGET_ANGLES.port, TARGET_ANGLES.pa, rotT)
        armHolding = waferId
        waferLocation = 'arm'
      } else if (p < extEnd) {
        armAngle = TARGET_ANGLES.pa
        armExtension = extT
        armHolding = waferId
        waferLocation = 'arm'
      } else if (p < gripEnd) {
        armAngle = TARGET_ANGLES.pa
        armExtension = 1
        gripperClosed = p < (gripEnd + extEnd) / 2
        if (gripperClosed) { armHolding = waferId; waferLocation = 'arm' }
        else { armHolding = null; waferLocation = 'pa' }
      } else {
        armAngle = TARGET_ANGLES.pa
        armExtension = 1 - retT
        waferLocation = 'pa'
      }
      break
      
    case 'pa_align': // PA对准中，臂收回待机
      armAngle = TARGET_ANGLES.idle
      armExtension = 0
      waferLocation = 'pa'
      break
      
    case 'pick_pa': // 从PA取片
      if (p < rotEnd) {
        armAngle = lerp(TARGET_ANGLES.idle, TARGET_ANGLES.pa, rotT)
        waferLocation = 'pa'
      } else if (p < extEnd) {
        armAngle = TARGET_ANGLES.pa
        armExtension = extT
        waferLocation = 'pa'
      } else if (p < gripEnd) {
        armAngle = TARGET_ANGLES.pa
        armExtension = 1
        gripperClosed = p > (gripEnd + extEnd) / 2
        if (gripperClosed) { armHolding = waferId; waferLocation = 'arm' }
        else { waferLocation = 'pa' }
      } else {
        armAngle = lerp(TARGET_ANGLES.pa, chamberAngle, retT)
        armExtension = 1 - retT
        gripperClosed = true
        armHolding = waferId
        waferLocation = 'arm'
      }
      break
      
    case 'place_chamber': // 放入腔体
      if (p < rotEnd) {
        armAngle = lerp(TARGET_ANGLES.pa, chamberAngle, rotT)
        armHolding = waferId
        chambers[chamberIdx].state = 'loading'
        waferLocation = 'arm'
      } else if (p < extEnd) {
        armAngle = chamberAngle
        armExtension = extT
        armHolding = waferId
        chambers[chamberIdx].state = 'loading'
        waferLocation = 'arm'
      } else if (p < gripEnd) {
        armAngle = chamberAngle
        armExtension = 1
        gripperClosed = p < (gripEnd + extEnd) / 2
        if (gripperClosed) { armHolding = waferId; waferLocation = 'arm' }
        else { armHolding = null; waferLocation = chamberKey }
      } else {
        armAngle = chamberAngle
        armExtension = 1 - retT
        chambers[chamberIdx].state = 'run'
        waferLocation = chamberKey
      }
      break
      
    case 'chamber_proc': // 腔体加工中
      armAngle = TARGET_ANGLES.idle
      armExtension = 0
      chambers[chamberIdx].state = 'run'
      chambers[chamberIdx].wafer = waferId
      chambers[chamberIdx].progress = p
      waferLocation = chamberKey
      break
      
    case 'pick_chamber': // 从腔体取片
      if (p < rotEnd) {
        armAngle = lerp(TARGET_ANGLES.idle, chamberAngle, rotT)
        chambers[chamberIdx].state = 'unloading'
        waferLocation = chamberKey
      } else if (p < extEnd) {
        armAngle = chamberAngle
        armExtension = extT
        chambers[chamberIdx].state = 'unloading'
        waferLocation = chamberKey
      } else if (p < gripEnd) {
        armAngle = chamberAngle
        armExtension = 1
        gripperClosed = p > (gripEnd + extEnd) / 2
        if (gripperClosed) { armHolding = waferId; chambers[chamberIdx].wafer = null; waferLocation = 'arm' }
        else { waferLocation = chamberKey }
      } else {
        armAngle = chamberAngle
        armExtension = 1 - retT
        gripperClosed = true
        armHolding = waferId
        waferLocation = 'arm'
      }
      break
      
    case 'place_pa2': // 放回PA
      if (p < rotEnd) {
        armAngle = lerp(chamberAngle, TARGET_ANGLES.pa, rotT)
        armHolding = waferId
        waferLocation = 'arm'
      } else if (p < extEnd) {
        armAngle = TARGET_ANGLES.pa
        armExtension = extT
        armHolding = waferId
        waferLocation = 'arm'
      } else if (p < gripEnd) {
        armAngle = TARGET_ANGLES.pa
        armExtension = 1
        gripperClosed = p < (gripEnd + extEnd) / 2
        if (gripperClosed) { armHolding = waferId; waferLocation = 'arm' }
        else { armHolding = null; waferLocation = 'pa' }
      } else {
        armAngle = TARGET_ANGLES.pa
        armExtension = 1 - retT
        waferLocation = 'pa'
      }
      break
      
    case 'pick_pa2': // 从PA取回
      if (p < rotEnd) {
        armAngle = TARGET_ANGLES.pa
        waferLocation = 'pa'
      } else if (p < extEnd) {
        armAngle = TARGET_ANGLES.pa
        armExtension = extT
        waferLocation = 'pa'
      } else if (p < gripEnd) {
        armAngle = TARGET_ANGLES.pa
        armExtension = 1
        gripperClosed = p > (gripEnd + extEnd) / 2
        if (gripperClosed) { armHolding = waferId; waferLocation = 'arm' }
        else { waferLocation = 'pa' }
      } else {
        armAngle = lerp(TARGET_ANGLES.pa, TARGET_ANGLES.port, retT)
        armExtension = 1 - retT
        gripperClosed = true
        armHolding = waferId
        waferLocation = 'arm'
      }
      break
      
    case 'place_port': // 放回PORT
      if (p < rotEnd) {
        armAngle = lerp(TARGET_ANGLES.pa, TARGET_ANGLES.port, rotT)
        armHolding = waferId
        waferLocation = 'arm'
      } else if (p < extEnd) {
        armAngle = TARGET_ANGLES.port
        armExtension = extT
        armHolding = waferId
        waferLocation = 'arm'
      } else if (p < gripEnd) {
        armAngle = TARGET_ANGLES.port
        armExtension = 1
        gripperClosed = p < (gripEnd + extEnd) / 2
        if (gripperClosed) { armHolding = waferId; waferLocation = 'arm' }
        else { armHolding = null; waferLocation = 'port' }
      } else {
        armAngle = lerp(TARGET_ANGLES.port, TARGET_ANGLES.idle, retT)
        armExtension = 1 - retT
        waferLocation = 'port'
      }
      break
  }
  
  const waferStatuses = Array.from({ length: TOTAL_WAFERS }, (_, i) => {
    if (i < waferIdx) return { id: `W${String(i + 1).padStart(2, '0')}`, status: 'done' }
    if (i === waferIdx) return { id: `W${String(i + 1).padStart(2, '0')}`, status: 'processing' }
    return { id: `W${String(i + 1).padStart(2, '0')}`, status: 'pending' }
  })
  
  return {
    currentWafer: waferIdx,
    currentStep: stepIdx,
    stepProgress,
    armAngle,
    armExtension,
    gripperClosed,
    armHolding,
    waferLocation,
    chambers,
    waferStatuses,
  }
}

// 实时模式动画时间
let realtimeRunTime = 0
let runAnimFrame = null

function updateRunAnimation() {
  if (mode.value === 'realtime' && playing.value) {
    realtimeRunTime += 16 * speed.value
    const state = calcRunState(realtimeRunTime)
    Object.assign(runState, state)
  }
  runAnimFrame = requestAnimationFrame(updateRunAnimation)
}

// 监听回放游标，更新run货状态
watch(cursor, (val) => {
  if (mode.value === 'playback' && playbackEnd.value > playbackStart.value) {
    const offset = val - playbackStart.value
    const state = calcRunState(offset)
    Object.assign(runState, state)
  }
})

// 监听模式切换
watch(mode, (newMode) => {
  if (newMode === 'playback') {
    // 回放模式：根据cursor计算
    const offset = cursor.value - playbackStart.value
    const state = calcRunState(offset)
    Object.assign(runState, state)
  }
})

// 历史回放数据
let historyData = []
let playbackIdx = 0
let playbackTimer = null
let realtimeTimer = null

// 当前机台
const machineId = computed(() => props.id || appStore.selectedMachineId || 'OXE-01')

// 温度告警等级
const tempClass = computed(() => {
  if (metrics.temp > 80) return 'crit'
  if (metrics.temp > 70) return 'warn'
  return ''
})

// 进度百分比
const playProgress = computed(() => {
  if (!playbackEnd.value || playbackEnd.value <= playbackStart.value) return 0
  return Math.max(0, Math.min(100, ((cursor.value - playbackStart.value) / (playbackEnd.value - playbackStart.value)) * 100))
})

// 显示的事件（最新 60 条，倒序）
const displayEvents = computed(() => events.value.slice(-60).reverse())

// === 加载数据 ===
async function loadMachine() {
  // 加载时先清空视图，避免闪现ETCH模型
  modelConfigReady.value = false
  currentModelConfig.value = null
  viewMode.value = 'loading'

  machine.value = await api.getMachine(machineId.value)
  if (machine.value) {
    currentState.value = machine.value.state
    processStep.value = `步骤 ${machine.value.process_step}/6`
    metrics.temp = machine.value.temp
    metrics.pressure = machine.value.pressure
    metrics.gas = machine.value.gas_flow
    metrics.rf = machine.value.rf_power
    metrics.waferCount = machine.value.wafer_count
    appStore.selectMachine(machineId.value)

    // 外部跳转网站：用 iframe 嵌入，跳过原生 2D/3D 视图配置
    if (useExternalView.value) {
      viewMode.value = 'external'
      modelConfigReady.value = true
    } else {
      if (modelStore.models.length === 0) {
        await modelStore.loadModels()
      }
      const modelId = modelStore.resolveModelId(machine.value.model)
      const cfg = modelStore.getModelById(modelId)
      currentModelConfig.value = cfg
      const resolved = resolveViewMode(machine.value.model)
      viewMode.value = resolved
      modelConfigReady.value = !!cfg
    }
  }
  // 并行加载右侧面板数据
  loadAlarms()
  loadLots()
  loadLatestEvents()
}

// 加载告警（按选中日期过滤）
async function loadAlarms() {
  // 回放模式：从已加载的 historyData 中提取 alarms，避免重复查询
  if (mode.value === 'playback' && historyData.length) {
    const alarmList = historyData
      .filter(e => e.event_category === 'alarm' && e.alarm)
      .map(e => ({
        id: e.raw_id,
        description: e.alarm.alarm_text || e.description,
        level: e.alarm.severity || 'warn',
        timestamp: e.timestamp,
        alarm_code: e.alarm.alarm_id,
      }))
    alarms.value = alarmList
    alarmStats.value = {
      total: alarmList.length,
      crit: alarmList.filter(a => a.level === 'crit').length,
      warn: alarmList.filter(a => a.level === 'warn').length,
      info: alarmList.filter(a => a.level === 'info').length,
      resolved: 0,
      unresolved: alarmList.length,
    }
    return
  }
  // 实时模式：调用API获取
  const start = `${playbackDate.value}T00:00:00`
  const end = `${playbackDate.value}T23:59:59.999`
  const data = await api.getAlarmHistory(machineId.value, {
    start_time: start,
    end_time: end,
    limit: 100,
  })
  const alarmList = data?.alarms || []
  alarms.value = alarmList.map(a => ({
    id: a.raw_id,
    description: a.alarm_text,
    level: a.severity || 'warn',
    timestamp: a.timestamp,
    alarm_code: a.alarm_id,
  }))
  // 统计
  alarmStats.value = {
    total: alarmList.length,
    crit: alarmList.filter(a => a.severity === 'crit').length,
    warn: alarmList.filter(a => a.severity === 'warn').length,
    info: alarmList.filter(a => a.severity === 'info').length,
    resolved: 0,
    unresolved: alarmList.length,
  }
}

// 加载 Lot
async function loadLots() {
  lots.value = (await api.getLots(machineId.value, playbackDate.value)) || []
}

// 加载最新事件（从DT_EVENT_RAW表获取）
async function loadLatestEvents() {
  const resp = await api.getHistory(machineId.value, { limit: 60 })
  const data = (resp?.events || []).map(e => ({
    ...e,
    machine_id: e.tool_id || machineId.value,
    event_code: e.event_name,
    description: e.description || e.event_name,
  }))
  if (data.length) {
    if (mode.value === 'playback') {
      events.value = data
    }
    applyEventData(data[data.length - 1])
    // 记录初始最新时间戳，用于实时模式下判断新事件
    const latestTs = data[data.length - 1]?.timestamp || data[data.length - 1]?.event_ts_utc || ''
    if (latestTs && latestTs > lastProcessedRealtimeTs) {
      lastProcessedRealtimeTs = latestTs
    }
  }
}

// === 实时模式：从 store 接收事件 ===
let lastProcessedRealtimeTs = ''
let realtimeEventsInitialized = false
watch(() => appStore.recentEvents, (evs) => {
  if (mode.value !== 'realtime') return
  if (!evs.length) return
  const myEvents = evs.filter(e => e.machine_id === machineId.value)
  if (!myEvents.length) return
  // 首次接收事件时，只初始化时间戳，不处理历史事件
  if (!realtimeEventsInitialized) {
    realtimeEventsInitialized = true
    const latestTs = myEvents[0]?.timestamp || myEvents[0]?.event_ts_utc || ''
    if (latestTs && latestTs > lastProcessedRealtimeTs) {
      lastProcessedRealtimeTs = latestTs
    }
    console.log('[MachineDetail] 实时事件初始化, lastProcessedRealtimeTs=', lastProcessedRealtimeTs)
    return
  }
  // 只处理比上次更新的事件
  const newEvents = myEvents.filter(e => {
    const ts = e.timestamp || e.event_ts_utc || ''
    return ts > lastProcessedRealtimeTs
  })
  if (!newEvents.length) return
  console.log('[MachineDetail] 收到新实时事件:', newEvents.length, '个')
  newEvents.forEach(ev => {
    events.value.push(ev)
    if (events.value.length > 200) events.value.shift()
    applyEventData(ev)
    const ts = ev.timestamp || ev.event_ts_utc || ''
    if (ts > lastProcessedRealtimeTs) lastProcessedRealtimeTs = ts
  })
}, { deep: true })

// 应用事件数据到模型
function applyEventData(ev) {
  if (!ev) return
  const evtName = (ev.event_name || ev.event_code || '').toUpperCase()
  const evtType = (ev.event_type || '').toUpperCase()

  // 提取当前 Lot ID
  if (ev.lot_id && ev.lot_id !== 'null' && ev.lot_id !== 'NULL') {
    currentLotId.value = ev.lot_id
  }

  if (evtType === 'STATE') {
    currentState.value = ev.event_code || currentState.value
    processStep.value = ev.description || processStep.value
  } else if (evtType === 'SENSOR') {
    if (ev.metric === 'temperature') metrics.temp = ev.value
    if (ev.metric === 'pressure') metrics.pressure = ev.value
    if (ev.metric === 'gasflow') metrics.gas = ev.value
    if (ev.metric === 'rf') metrics.rf = ev.value
  } else if (evtType === 'ALARM' || evtName === 'EC_ALARM_REPORT') {
    // 加入告警列表
    const alarmId = ev.alarm_id || ev.event_code || ev.id
    if (!alarms.value.find(a => a.id === alarmId)) {
      alarms.value.unshift({
        id: alarmId,
        description: ev.alarm_text || ev.description || ev.event_name,
        level: ev.alarm_severity || ev.level || 'warn',
        timestamp: ev.timestamp,
        alarm_code: ev.alarm_id || ev.event_code,
      })
      if (alarms.value.length > 30) alarms.value.pop()
    }
  } else if (evtType === 'TRANSFER') {
    // 触发 3D 门/机械臂动画
    transferTrigger.value++
    if (/unload|卸载/i.test(ev.event_code + ev.description)) {
      metrics.waferCount++
    }
  } else if (evtType === 'VFEI' || evtType === 'HOST') {
    // PODOPENER 穿脱流程事件 - 更新状态（动画由3D组件通过watch events自动驱动）
    currentState.value = evtName
    processStep.value = ev.description || evtName
  }
}

// === 回放模式 ===
async function switchToPlayback() {
  mode.value = 'playback'
  stopPlayback()
  playing.value = false
  events.value = []
  alarms.value = []
  // 根据当前选择的日期加载该日历史事件
  const start = `${playbackDate.value}T00:00:00`
  const end = `${playbackDate.value}T23:59:59.999`
  const resp = await api.getHistory(machineId.value, { start_time: start, end_time: end, limit: 5000 })
  historyData = (resp?.events || []).map(e => ({
    ...e,
    machine_id: e.tool_id || machineId.value,
    event_code: e.event_name,
    description: e.description || e.event_name,
    _ts: parseTs(e.timestamp),
  }))
  if (!historyData.length) {
    console.warn('无历史数据')
    // 即使无事件数据，也要刷新告警和Lot（否则显示的是旧日期数据）
    loadAlarms()
    loadLots()
    return
  }
  playbackStart.value = historyData[0]._ts
  playbackEnd.value = historyData[historyData.length - 1]._ts
  cursor.value = playbackStart.value
  playbackIdx = 0
  playing.value = false
  // 并行加载告警与 Lot（不阻塞跳转）
  loadAlarms()
  loadLots()
  // 修复：加载历史数据后先初始化到起始位置，批量重建初始视觉状态
  // 避免用户刚切回放时看到空白画面以为没动，同时保证displayEvents正确传入MachineOxeView
  seek(0)
  // 如果有等待中的跳转，执行它（覆盖上面seek(0)的位置）
  if (pendingJumpTs.value) {
    const ts = pendingJumpTs.value
    pendingJumpTs.value = ''
    doJump(ts)
  }
}

function switchToRealtime() {
  mode.value = 'realtime'
  stopPlayback()
  playing.value = false
  events.value = []
  alarms.value = []
  // 重置回放状态
  cursor.value = 0
  playbackStart.value = 0
  playbackEnd.value = 0
  historyData = []
  playbackIdx = 0
  // 重置实时事件初始化标记
  realtimeEventsInitialized = false
  lastProcessedRealtimeTs = ''
  loadLatestEvents()
  loadAlarms()
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

// 时间轴跳转
let seekDebounceTimer = null
function seek(pct) {
  if (!historyData.length) return

  // 跳转时暂停播放，避免自动开始播放
  if (playing.value) {
    playing.value = false
    stopPlayback()
  }

  clearTimeout(seekDebounceTimer)
  seekDebounceTimer = setTimeout(() => {
    const targetTime = playbackStart.value + pct * (playbackEnd.value - playbackStart.value)
    cursor.value = targetTime

    const idx = bisectLeft(historyData, targetTime, (e) => e._ts)
    playbackIdx = idx >= 0 ? idx : historyData.length

    events.value = []
    alarms.value = []

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
  }, 30)
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

// 日期变化
async function onDateChange(newDate) {
  if (!newDate) return
  playbackDate.value = newDate
  loading.value = true
  try {
    // 选日期时自动切换到回放模式
    if (mode.value !== 'playback') {
      mode.value = 'playback'
      await switchToPlayback()
    } else {
      // 已在回放模式：重新加载历史事件
      await switchToPlayback()
    }
  } finally {
    loading.value = false
  }
}

// 告警点击跳转
function onAlarmClick(alarm) {
  if (alarm && alarm.timestamp) {
    jumpToTime(alarm.timestamp)
  }
}

// 倍速变化
function onSpeedChange(s) {
  speed.value = s
}

// 选择 Lot
async function selectLot(lot) {
  selectedLotId.value = lot.id
  const targetTs = lot.start_time || lot.timestamp
  if (!targetTs) return

  // 检查目标时间是否在当前回放日期范围内
  const targetDate = targetTs.slice(0, 10)
  if (mode.value !== 'playback') {
    // 需要先切换到回放模式
    if (targetDate !== playbackDate.value) {
      playbackDate.value = targetDate
    }
    pendingJumpTs.value = targetTs
    await switchToPlayback()
  } else if (targetDate !== playbackDate.value) {
    // 已在回放模式但日期不同，切换日期后跳转
    playbackDate.value = targetDate
    pendingJumpTs.value = targetTs
    await switchToPlayback()
  } else {
    // 同日期，直接跳转
    jumpToTime(targetTs)
  }
}

// 跳转到指定时间
async function jumpToTime(ts) {
  if (!ts) return
  // 检查目标时间是否在当前回放日期范围内
  const targetDate = String(ts).slice(0, 10)
  if (mode.value !== 'playback') {
    // 需要先切换到回放模式
    if (targetDate && targetDate !== playbackDate.value) {
      playbackDate.value = targetDate
    }
    pendingJumpTs.value = ts
    await switchToPlayback()
  } else if (targetDate && targetDate !== playbackDate.value) {
    // 已在回放模式但日期不同，切换日期后跳转
    playbackDate.value = targetDate
    pendingJumpTs.value = ts
    await switchToPlayback()
  } else {
    doJump(ts)
  }
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

// 回放 Tab 的"AI分析当前回放"：切换到 AI Tab 并预填问题
function onAiAnalyze(payload) {
  const tsStr = payload.timestamp ? String(payload.timestamp).slice(0, 19).replace('T', ' ') : ''
  const dateStr = payload.date || ''
  const machineStr = payload.machine_id || machineId.value || ''
  // 根据机台型号生成不同的预填问题
  if (machineStr.toUpperCase().startsWith('OXE')) {
    aiPrefillQuestion.value = `分析 ${machineStr} 在 ${tsStr} 附近的事件，当前第几片晶圆在加工？是否有异常？`
  } else {
    aiPrefillQuestion.value = `分析 ${machineStr} 在 ${dateStr} ${tsStr} 附近的事件，机台状态是否正常？有无异常告警？`
  }
  rightTab.value = 'ai'
}


// 返回看板
function goBack() {
  router.push('/')
}

// 监听机台 ID 变化
watch(() => props.id, () => {
  if (mode.value === 'playback') switchToRealtime()
  loadMachine()
})

// 监听 URL query 参数变化（date、mode）—— SPA 中切换 URL 不会重新挂载组件
watch(() => route.query, (q) => {
  if (!q) return
  const qDate = q.date ? String(q.date) : ''
  const qMode = q.mode ? String(q.mode) : ''
  // 仅处理合法日期格式
  if (qDate && /^\d{4}-\d{2}-\d{2}$/.test(qDate) && qDate !== playbackDate.value) {
    playbackDate.value = qDate
    switchToPlayback()
  } else if (qMode === 'playback' && mode.value !== 'playback') {
    switchToPlayback()
  } else if (qMode === 'realtime' && mode.value !== 'realtime') {
    switchToRealtime()
  }
})

// 处理AI跳转（query参数或全局store）
async function applyAIJump() {
  let ts = ''
  if (route.query && route.query.ts) {
    ts = String(route.query.ts)
    // 清理URL中的ts参数，避免刷新重复触发
    const q = { ...route.query }
    delete q.ts
    router.replace({ path: route.path, query: q })
  } else {
    const pending = appStore.consumePendingJump()
    if (pending && pending.timestamp) {
      // 仅当目标机台与当前机台一致（或未指定）时执行
      if (!pending.machine_id || pending.machine_id === props.id) {
        ts = pending.timestamp
      }
    }
  }
  if (!ts) return
  // 等待历史数据加载完成后跳转（不再用固定延时）
  await jumpToTime(ts)
}

onMounted(() => {
  loadMachine()
  updateRunAnimation()
  // 处理 URL 参数：date、mode
  const queryDate = route.query.date ? String(route.query.date) : ''
  const queryMode = route.query.mode ? String(route.query.mode) : ''
  // 在 loadMachine 完成后处理跳转和 URL 参数（loadMachine 内部异步加载数据）
  loadMachine().then(async () => {
    // 优先应用 URL 参数：date 和 mode
    if (queryDate && /^\d{4}-\d{2}-\d{2}$/.test(queryDate)) {
      playbackDate.value = queryDate
    }
    if (queryMode === 'playback' || queryDate) {
      // 有日期参数或明确指定 playback 模式时，自动切换到回放
      await switchToPlayback()
    }
    // 处理 AI 跳转（ts 参数）
    await applyAIJump()
  })
})
</script>

<template>
  <div class="detail-page">
    <!-- 左侧视图区 -->
    <div class="detail-viewer" :class="{ 'is-2d': viewMode === '2d' || viewMode === 'vpo' || viewMode === 'iso', 'is-vpo': viewMode === 'vpo', 'is-oxe': viewMode === 'oxe' }">
      <!-- 视图模式切换按钮（多于1个视图时才显示，避免单按钮遮挡内容） -->
      <div v-if="modelConfigReady && availableViews.length > 1" class="view-mode-switcher">
        <button
          v-for="v in availableViews"
          :key="v.key"
          class="vms-btn"
          :class="{ active: viewMode === v.key }"
          @click="viewMode = v.key"
        >
          {{ v.label }}
        </button>
      </div>

      <!-- 外部跳转网站：iframe 嵌入 -->
      <div v-if="useExternalView" class="ext-iframe-wrap">
        <iframe :src="externalFrameUrl" class="oxe-iframe" frameborder="0" allow="fullscreen; clipboard-read; clipboard-write" allowfullscreen></iframe>
      </div>

      <!-- 加载占位（避免闪现ETCH模型） -->
      <div v-else-if="!modelConfigReady" class="model-loading">
        <div class="loading-spinner"></div>
        <div class="loading-text">加载机台模型配置...</div>
      </div>

      <!-- 3D模型视图 -->
      <MachineModel3D
        v-else-if="viewMode === '3d'"
        :machine="machine"
        :current-state="currentState"
        :metrics="metrics"
        :process-step="processStep"
        :transfer-trigger="transferTrigger"
        :run-state="runState"
        :current-lot-id="currentLotId"
      />

      <!-- 2D原理图视图 -->
      <MachineModel2D
        v-else-if="viewMode === '2d'"
        :machine="machine"
        :current-state="currentState"
        :metrics="metrics"
        :process-step="processStep"
        :run-state="runState"
        :current-lot-id="currentLotId"
      />

      <!-- 2.5D等角视图（OXE/DRM专用） -->
      <MachineIsoView
        v-else-if="viewMode === 'iso'"
        :machine="machine"
        :model-config="currentModelConfig"
        :current-state="currentState"
        :metrics="metrics"
        :run-state="runState"
        :events="displayEvents"
      />

      <!-- PODOPENER 2D视图 -->
      <MachineVpoView
        v-else-if="viewMode === 'vpo'"
        :machine="machine"
        :model-config="currentModelConfig"
        :current-state="currentState"
        :metrics="metrics"
        :run-state="runState"
        :events="displayEvents"
        :paused="mode === 'playback' && !playing"
        :mode="mode"
      />

      <!-- PODOPENER 3D视图 -->
      <MachineVpo3DView
        v-else-if="viewMode === 'vpo3d'"
        :machine="machine"
        :model-config="currentModelConfig"
        :current-state="currentState"
        :metrics="metrics"
        :run-state="runState"
        :events="displayEvents"
        :paused="mode === 'playback' && !playing"
        :mode="mode"
      />

      <!-- OXE Canvas 看板（Vue 组件，支持回放驱动） -->
      <MachineOxeView
        v-else-if="viewMode === 'oxe'"
        :machine="machine"
        :model-config="currentModelConfig"
        :current-state="currentState"
        :metrics="metrics"
        :events="displayEvents"
        :paused="mode === 'playback' && !playing"
        :mode="mode"
        :speed="speed"
        :current-lot-id="currentLotId"
      />

      <button class="back-btn" @click="goBack">← 返回看板</button>

      <!-- 悬浮信息面板（2D模式下隐藏，避免遮挡） -->
      <div v-show="viewMode === '3d'" class="detail-left-panel glass-panel">
        <div class="detail-mid">{{ machineId }}</div>
        <div class="detail-model">{{ machine?.name || (machine?.model === 'TEL-DRM-UNIT' ? 'TEL DRM UNITY' : machine?.model) || 'TEL DRM UNITY' }} · 刻蚀机</div>
        <div class="state-badge" :class="currentState">{{ stateLabels[currentState] || currentState }}</div>
        <div class="detail-metrics">
          <div class="dm">
            <div class="dm-label">温度</div>
            <div class="dm-val" :class="tempClass">{{ metrics.temp.toFixed(1) }}°C</div>
          </div>
          <div class="dm">
            <div class="dm-label">压力</div>
            <div class="dm-val">{{ metrics.pressure.toFixed(3) }} Pa</div>
          </div>
          <div class="dm">
            <div class="dm-label">气体流量</div>
            <div class="dm-val">{{ metrics.gas.toFixed(0) }} sccm</div>
          </div>
          <div class="dm">
            <div class="dm-label">RF 功率</div>
            <div class="dm-val">{{ metrics.rf.toFixed(0) }} W</div>
          </div>
          <div class="dm">
            <div class="dm-label">晶圆计数</div>
            <div class="dm-val">{{ metrics.waferCount }}</div>
          </div>
          <div class="dm">
            <div class="dm-label">工艺步骤</div>
            <div class="dm-val small">{{ processStep }}</div>
          </div>
        </div>
      </div>

      <!-- 回放控制条（仅回放模式显示） -->
      <PlaybackBar
        v-show="mode === 'playback'"
        :mode="mode"
        :playing="playing"
        :speed="speed"
        :date="playbackDate"
        :cursor="cursor"
        :start="playbackStart"
        :end="playbackEnd"
        @update:mode="onModeChange"
        @update:playing="onPlayingChange"
        @update:speed="onSpeedChange"
        @update:date="onDateChange"
        @seek="seek"
      />
    </div>

    <!-- 右侧面板 -->
    <div class="detail-right">
      <!-- 全局日期选择器（实时/回放都可见） -->
      <div class="dr-date-bar">
        <span class="dr-date-label">数据日期</span>
        <input
          type="date"
          class="dr-date-input"
          :value="playbackDate"
          @change="onDateChange($event.target.value)"
        />
        <button class="dr-date-refresh" @click="onDateChange(playbackDate)" title="刷新数据">↻</button>
      </div>

      <div class="dr-tabs">
        <button class="dr-tab" :class="{ active: rightTab === 'alarms' }" @click="rightTab = 'alarms'">告警</button>
        <button class="dr-tab" :class="{ active: rightTab === 'events' }" @click="rightTab = 'events'">事件</button>
        <button class="dr-tab" :class="{ active: rightTab === 'replay' }" @click="rightTab = 'replay'">回放</button>
        <button class="dr-tab" :class="{ active: rightTab === 'lots' }" @click="rightTab = 'lots'">Lot</button>
        <button class="dr-tab" :class="{ active: rightTab === 'ai' }" @click="rightTab = 'ai'">AI</button>

      </div>

      <!-- 告警 Tab -->
      <div v-show="rightTab === 'alarms'" class="dr-section">
        <AlarmStats :stats="alarmStats" :alarms="alarms" @click-alarm="onAlarmClick" />
      </div>

      <!-- 事件 Tab -->
      <div v-show="rightTab === 'events'" class="dr-section">
        <EventList :events="displayEvents" />
      </div>

      <!-- 回放 Tab -->
      <div v-show="rightTab === 'replay'" class="dr-section">
        <HistoryReplay
          :machine-id="machineId"
          :machine-state="machine?.state"
          :external-date="playbackDate"
          :jump-timestamp="cursor ? new Date(cursor).toISOString().slice(0, 19) : ''"
          @jump="jumpToTime"
          @replay-event="onReplayEvent"
          @date-change="onDateChange"
          @ai-analyze="onAiAnalyze"
        />
      </div>

      <!-- Lot Tab -->
      <div v-show="rightTab === 'lots'" class="dr-section">
        <LotList :lots="lots" :selected-lot-id="selectedLotId" @select="selectLot" />
      </div>

      <!-- AI Tab -->
      <div v-show="rightTab === 'ai'" class="dr-section ai-tab-wrap">
        <!-- 机台专属 Dify 配置面板 -->
        <div class="machine-dify-panel">
          <div class="mdp-header" @click="showMachineDifyPanel = !showMachineDifyPanel">
            <span class="mdp-title">⚙️ 机台专属 Dify 配置</span>
            <span class="mdp-toggle">{{ showMachineDifyPanel ? '▲ 收起' : '▼ 展开' }}</span>
          </div>
          <div v-show="showMachineDifyPanel" class="mdp-body">
            <div class="mdp-form-grid">
              <label>
                <span>配置名称</span>
                <input v-model="machineDifyForm.config_name" placeholder="如：OXE专用刻蚀Dify" />
              </label>
              <label>
                <span>机台型号 model_id <em>(决定哪些机台命中此配置，匹配machine.model)</em></span>
                <input
                  v-model="machineDifyForm.model_id"
                  :placeholder="'例：OXE （当前识别到: ' + (machineDifyModelIdHint || '未知') + '）'"
                />
              </label>
              <label>
                <span>Dify API 地址</span>
                <input v-model="machineDifyForm.dify_base_url" placeholder="例：http://192.168.1.100/v1" />
              </label>
              <label>
                <span>Dify API Key <em>(app-xxxxxxx)</em></span>
                <input
                  v-model="machineDifyForm.dify_api_key"
                  type="password"
                  :placeholder="machineDifyForm.id ? '（已保存，输入新值才会覆盖）' : '请输入 app- 开头的 Dify API Key'"
                />
              </label>
              <label class="inline-label">
                <input type="checkbox" v-model="machineDifyForm.is_active" :true-value="1" :false-value="0" />
                <span>启用此配置（未启用时，该型号机台回退到全局Dify/LLM/本地规则）</span>
              </label>
            </div>
            <div class="mdp-actions">
              <button class="mdp-btn test" :disabled="machineDifyTestState.loading" @click="testMachineDify()">
                {{ machineDifyTestState.loading ? '测试中...' : '🧪 测试连接' }}
              </button>
              <button class="mdp-btn save" :disabled="machineDifySaveState.loading" @click="saveMachineDify()">
                {{ machineDifySaveState.loading ? '保存中...' : (machineDifyForm.id ? '💾 保存配置' : '➕ 创建配置') }}
              </button>
              <button
                v-if="machineDifyForm.id"
                class="mdp-btn danger"
                :disabled="machineDifySaveState.loading"
                @click="disableOrDeleteMachineDify()"
              >
                {{ machineDifyForm.is_active ? '⛔ 禁用' : '🗑️ 删除' }}
              </button>
            </div>
            <!-- 测试/保存消息 -->
            <div v-if="machineDifyTestState.message" class="mdp-msg" :class="'msg-' + machineDifyTestState.level">
              [测试] {{ machineDifyTestState.message }}
            </div>
            <div v-if="machineDifySaveState.message" class="mdp-msg" :class="'msg-' + machineDifySaveState.level">
              [配置] {{ machineDifySaveState.message }}
            </div>
            <div class="mdp-hint">
              💡 说明：同型号（model_id）的机台共用一个 Dify 配置。优先级「机台专属 Dify > 全局Dify/LLM」。
            </div>
          </div>
        </div>
        <AiAssistant
          ref="aiAssistantVueRef"
          :machine-id="machineId"
          :prefill-question="aiPrefillQuestion"
          @jump="jumpToTime"
        />
      </div>


      <!-- 全局加载遮罩 -->
      <div v-if="loading" class="dr-loading-overlay">
        <div class="dr-loading-spinner"></div>
        <div class="dr-loading-text">数据加载中...</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail-page {
  display: flex;
  height: 100%;
}
.detail-viewer {
  flex: 1;
  position: relative;
  background: #040712;
  overflow: hidden;
}

/* 加载占位 */
.model-loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  z-index: 5;
  color: #94a3b8;
  font-size: 13px;
  pointer-events: none;
}
.loading-spinner {
  width: 36px;
  height: 36px;
  border: 3px solid rgba(0, 212, 255, 0.2);
  border-top-color: #00d4ff;
  border-radius: 50%;
  animation: loading-spin 0.8s linear infinite;
}
@keyframes loading-spin {
  to { transform: rotate(360deg); }
}

/* 新增：视图模式切换按钮 */
.view-mode-switcher {
  position: absolute;
  top: 14px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 8px;
  z-index: 15;
}

/* 2D模式下，切换按钮移到右下角，避免遮挡PORT1/PORT2看板 */
.detail-viewer.is-2d .view-mode-switcher {
  left: auto;
  right: 14px;
  bottom: 14px;
  top: auto;
  transform: none;
  flex-direction: column;
  gap: 6px;
}

.detail-viewer.is-2d .vms-btn {
  padding: 6px 12px;
  font-size: 11px;
}

/* VPO视图专用样式：按钮移到顶部两侧，避免遮挡PORT2和机台主体 */
.detail-viewer.is-vpo .view-mode-switcher {
  left: 14px;
  right: auto;
  transform: none;
  top: 14px;
  z-index: 20;
}

.detail-viewer.is-vpo .vms-btn {
  padding: 6px 12px;
  font-size: 11px;
  background: rgba(13, 20, 36, 0.9);
}

.detail-viewer.is-vpo .back-btn {
  top: 14px;
  right: 14px;
  padding: 6px 12px;
  font-size: 11px;
  z-index: 20;
  background: rgba(13, 20, 36, 0.9);
}

.vms-btn {
  padding: 8px 16px;
  border: 1px solid var(--border);
  background: rgba(13, 20, 36, 0.9);
  backdrop-filter: blur(8px);
  color: var(--text-dim);
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.vms-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.vms-btn.active {
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent);
  border-color: var(--accent);
  box-shadow: 0 0 12px rgba(0, 212, 255, 0.3);
}

.back-btn {
  position: absolute;
  top: 14px;
  right: 14px;
  background: rgba(13, 20, 36, 0.9);
  backdrop-filter: blur(8px);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  z-index: 10;
}
/* OXE Canvas 模式：为避免遮挡左侧 PORT1 Wafer Map 面板，back-btn 固定右上角；
   同时为顶部切换按钮区 / 底部播放条预留 padding，确保 Canvas 不画在遮挡区域下 */
.detail-viewer.is-oxe {
  padding: 58px 0 84px 0;
  box-sizing: border-box;
}
.detail-viewer.is-oxe .back-btn {
  left: auto;
  right: 14px;
  top: 14px;
  padding: 6px 12px;
  font-size: 11px;
  z-index: 60;
}
/* OXE 模式：视图模式切换按钮移到左上角（与返回按钮左右对称，避开顶部中心及左右两侧 Wafer Map 面板） */
.detail-viewer.is-oxe .view-mode-switcher {
  left: 14px;
  top: 14px;
  right: auto;
  transform: none;
  flex-direction: column;
  gap: 6px;
  z-index: 60;
}
.detail-viewer.is-oxe .vms-btn {
  padding: 6px 12px;
  font-size: 11px;
  background: rgba(13, 20, 36, 0.92);
}

/* 2D模式下，返回按钮紧凑显示 */
.detail-viewer.is-2d .back-btn {
  top: 10px;
  right: 14px;
  padding: 6px 12px;
  font-size: 11px;
}

/* 外部跳转网站 iframe 容器（铺满详情视图区） */
.ext-iframe-wrap {
  position: absolute;
  inset: 0;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: #fff;
}
.ext-iframe-wrap .oxe-iframe {
  width: 100%;
  height: 100%;
  border: none;
}

/* OXE Canvas 看板 iframe 样式 */
.oxe-iframe {
  width: 100%;
  height: 100%;
  border: none;
  display: block;
}
.back-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.detail-left-panel {
  position: absolute;
  top: 14px;
  left: 14px;
  padding: 14px 18px;
  min-width: 280px;
  z-index: 5;
}
.detail-mid {
  font-size: 22px;
  font-weight: 800;
}
.detail-model {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 2px;
  letter-spacing: 0.5px;
}
.detail-metrics {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 14px;
}
.dm {
  background: rgba(0, 0, 0, 0.25);
  padding: 8px 10px;
  border-radius: 6px;
}
.dm-label {
  font-size: 10px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.dm-val {
  font-size: 16px;
  font-weight: 700;
  margin-top: 3px;
}
.dm-val.small {
  font-size: 13px;
}
.dm-val.warn {
  color: var(--yellow);
}
.dm-val.crit {
  color: var(--red);
}
.detail-right {
  width: 340px;
  background: var(--panel);
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  position: relative;
}
.dr-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
}

/* 全局日期选择器 */
.dr-date-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: rgba(0, 0, 0, 0.15);
}
.dr-date-label {
  font-size: 11px;
  color: var(--text-dim);
  white-space: nowrap;
}
.dr-date-input {
  flex: 1;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 5px 8px;
  border-radius: 5px;
  font-size: 12px;
  font-family: monospace;
  color-scheme: dark;
}
.dr-date-input:focus {
  border-color: var(--accent);
  outline: none;
}
.dr-date-refresh {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text-dim);
  width: 28px;
  height: 28px;
  border-radius: 5px;
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.dr-date-refresh:hover {
  color: var(--accent);
  border-color: var(--accent);
}
.dr-tab {
  flex: 1;
  padding: 8px 10px;
  background: none;
  border: none;
  color: var(--text-dim);
  font-size: 11px;
  font-weight: 600;
  border-bottom: 2px solid transparent;
}
.dr-tab:hover {
  color: var(--text);
}
.dr-tab.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  background: rgba(0, 212, 255, 0.05);
}
.dr-section {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

/* 加载遮罩 */
.dr-loading-overlay {
  position: absolute;
  inset: 0;
  background: rgba(4, 7, 18, 0.85);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  z-index: 50;
  pointer-events: none;
}
.dr-loading-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid rgba(0, 212, 255, 0.2);
  border-top-color: #00d4ff;
  border-radius: 50%;
  animation: loading-spin 0.8s linear infinite;
}
.dr-loading-text {
  font-size: 12px;
  color: #94a3b8;
}

/* ===== AI Tab：机台专属 Dify 配置面板 ===== */
.ai-tab-wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ai-tab-wrap .dr-section { min-height: 0; }
.machine-dify-panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(0,0,0,0.18);
  overflow: hidden;
  flex-shrink: 0;
}
.mdp-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  background: rgba(0, 212, 255, 0.05);
  border-bottom: 1px solid var(--border);
}
.mdp-title { font-size: 12px; font-weight: 700; letter-spacing: 0.3px; color: var(--accent); }
.mdp-toggle { font-size: 10.5px; color: var(--text-dim); }
.mdp-body { padding: 10px 12px 12px; }
.mdp-form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 12px;
}
.mdp-form-grid label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
  color: var(--text-dim);
}
.mdp-form-grid label em {
  font-style: normal;
  color: #64748b;
  font-weight: 400;
  margin-left: 4px;
}
.mdp-form-grid label.inline-label {
  grid-column: 1 / -1;
  flex-direction: row;
  align-items: center;
  gap: 6px;
  color: var(--text-dim);
}
.mdp-form-grid input[type="text"],
.mdp-form-grid input[type="password"],
.mdp-form-grid input:not([type]) {
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 6px 8px;
  border-radius: 5px;
  font-size: 12px;
  outline: none;
  font-family: inherit;
  box-sizing: border-box;
  width: 100%;
}
.mdp-form-grid input:focus { border-color: var(--accent); }
.mdp-actions {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.mdp-btn {
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  padding: 6px 12px;
  font-size: 11.5px;
  font-weight: 600;
  border-radius: 6px;
  cursor: pointer;
}
.mdp-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.mdp-btn.test { border-color: rgba(250, 204, 21, 0.35); color: #facc15; background: rgba(250, 204, 21, 0.06); }
.mdp-btn.test:hover:not(:disabled) { background: rgba(250, 204, 21, 0.12); }
.mdp-btn.save { border-color: rgba(0, 212, 255, 0.4); color: #00d4ff; background: rgba(0,212,255,0.08); }
.mdp-btn.save:hover:not(:disabled) { background: rgba(0,212,255,0.15); }
.mdp-btn.danger { border-color: rgba(255, 71, 87, 0.4); color: #ff4757; background: rgba(255,71,87,0.06); }
.mdp-btn.danger:hover:not(:disabled) { background: rgba(255,71,87,0.12); }
.mdp-msg {
  margin-top: 8px;
  padding: 6px 10px;
  font-size: 11.5px;
  border-radius: 5px;
  line-height: 1.5;
}
.mdp-msg.msg-success { color: #10b981; background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.25); }
.mdp-msg.msg-error   { color: #ff4757; background: rgba(255,71,87,0.08); border: 1px solid rgba(255,71,87,0.25); }
.mdp-msg.msg-warn    { color: #f59e0b; background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.25); }
.mdp-hint {
  margin-top: 8px;
  font-size: 10.5px;
  color: #64748b;
  line-height: 1.5;
}
@media (max-width: 520px) {
  .mdp-form-grid { grid-template-columns: 1fr; }
}
</style>
