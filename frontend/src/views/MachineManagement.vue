<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { useAppStore } from '../stores/app'

const router = useRouter()
const appStore = useAppStore()

// ============== 状态 ==============
const loading = ref(false)
const error = ref('')
const success = ref('')

const machines = ref([])

// 机台专属 Dify 配置列表（按型号 model_id 匹配，用于在列表中展示每台机台命中的专属 Dify）
const machineDifyConfigs = ref([])

// 搜索/筛选
const searchKeyword = ref('')
const filterLine = ref('')
const filterState = ref('')

// 编辑弹窗
const showEditDialog = ref(false)
const editingMachine = reactive({
  id: '',
  name: '',
  model: '',
  line: 1,
  process_type: '',
  chamber_count: 1,
  state: '',
  external_url: '',
  use_external_url: 0,
})

// 删除确认弹窗
const showDeleteDialog = ref(false)
const deletingMachine = ref(null)
const deleteConfirmId = ref('') // 二次确认：输入机台ID

// ============== 计算属性 ==============
const filteredMachines = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  return machines.value.filter((m) => {
    const matchKw =
      !kw ||
      (m.id && m.id.toLowerCase().includes(kw)) ||
      (m.name && m.name.toLowerCase().includes(kw)) ||
      (m.model && m.model.toLowerCase().includes(kw))
    const matchLine = !filterLine.value || String(m.line) === filterLine.value
    const matchState = !filterState.value || m.state === filterState.value
    return matchKw && matchLine && matchState
  })
})

const lineOptions = computed(() => {
  const set = new Set(machines.value.map((m) => m.line).filter((l) => l != null))
  return Array.from(set).sort()
})

const stateOptions = [
  { value: '', label: '全部状态' },
  { value: 'run', label: '运行中' },
  { value: 'idle', label: '空闲' },
  { value: 'error', label: '故障' },
  { value: 'maint', label: '维护' },
  { value: 'setup', label: '设置' },
]

const stateLabel = (s) => stateOptions.find((o) => o.value === s)?.label || s || '-'

const stateBadgeClass = (s) => `state-${s || 'unknown'}`

// ============== 方法 ==============
function showError(msg) {
  error.value = msg
  setTimeout(() => { error.value = '' }, 4000)
}

function showSuccess(msg) {
  success.value = msg
  setTimeout(() => { success.value = '' }, 3000)
}

async function loadMachines() {
  loading.value = true
  try {
    const data = await api.getMachines()
    machines.value = Array.isArray(data) ? data : data.machines || []
  } catch (e) {
    showError('加载机台列表失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

// 加载全部机台专属 Dify 配置（用于列表展示每台机台命中的配置名）
async function loadMachineDifyConfigs() {
  try {
    const data = await api.aiGetMachineDifyConfigs()
    machineDifyConfigs.value = Array.isArray(data) ? data : (data?.items || [])
  } catch (e) {
    console.warn('[MachineManagement] 加载机台专属 Dify 配置失败:', e)
    machineDifyConfigs.value = []
  }
}

// 按机台型号匹配命中的「专属 Dify」配置（与后端 _get_machine_dify_config 一致：machine.model 匹配 model_id，且 is_active）
function machineDifyOf(m) {
  const model = String(m?.model || '').trim().toUpperCase()
  if (!model) return null
  return machineDifyConfigs.value.find(
    (c) => c.is_active && String(c.model_id || '').trim().toUpperCase() === model
  ) || null
}

// 点击「专属 Dify」单元格跳转到 AI 配置管理页（带上 model 便于定位）
function goAiConfig(m) {
  const cfg = machineDifyOf(m)
  router.push({ path: '/ai-config', query: { tab: 'machine-dify', model: cfg ? cfg.model_id : (m?.model || '') } })
}

// ============== 编辑 ==============
function openEditDialog(m) {
  Object.assign(editingMachine, {
    id: m.id,
    name: m.name || '',
    model: m.model || '',
    line: m.line ?? 1,
    process_type: m.process_type || '',
    chamber_count: m.chamber_count ?? 1,
    state: m.state || '',
    external_url: m.external_url || '',
    use_external_url: m.use_external_url ? 1 : 0,
  })
  showEditDialog.value = true
}

async function saveMachine() {
  if (!editingMachine.id) {
    showError('机台ID缺失')
    return
  }
  try {
    const payload = {
      name: editingMachine.name,
      model: editingMachine.model,
      line: Number(editingMachine.line),
      process_type: editingMachine.process_type,
      chamber_count: Number(editingMachine.chamber_count),
    }
    await api.updateMachine(editingMachine.id, payload)

    // 同步更新外部链接配置
    await api.updateMachineExternalLink(editingMachine.id, {
      external_url: editingMachine.external_url,
      use_external_url: editingMachine.use_external_url ? 1 : 0,
    })

    showSuccess(`机台 ${editingMachine.id} 更新成功`)
    showEditDialog.value = false
    await loadMachines()
    // 同步到全局 store
    appStore.refreshMachines?.()
  } catch (e) {
    showError('保存失败: ' + e.message)
  }
}

// ============== 删除 ==============
function openDeleteDialog(m) {
  deletingMachine.value = m
  deleteConfirmId.value = ''
  showDeleteDialog.value = true
}

const canConfirmDelete = computed(
  () => deleteConfirmId.value.trim() === (deletingMachine.value?.id || '')
)

async function confirmDelete() {
  if (!canConfirmDelete.value) {
    showError('输入的机台ID不匹配，无法删除')
    return
  }
  const m = deletingMachine.value
  try {
    await api.deleteMachine(m.id)
    showSuccess(`机台 ${m.id} 已彻底删除`)
    showDeleteDialog.value = false
    deletingMachine.value = null
    deleteConfirmId.value = ''
    await loadMachines()
    appStore.refreshMachines?.()
  } catch (e) {
    showError('删除失败: ' + e.message)
  }
}

// ============== 详情跳转 ==============
function goDetail(m) {
  router.push(`/machine/${m.id}`)
}

// ============== 生命周期 ==============
onMounted(() => {
  loadMachines()
  loadMachineDifyConfigs()
})
</script>

<template>
  <div class="machine-mgmt">
    <div class="page-header">
      <h2>🏭 机台管理</h2>
      <div class="header-actions">
        <button class="btn btn-primary" @click="loadMachines">🔄 刷新</button>
      </div>
    </div>

    <div class="page-tip">
      💡 此页面用于<b>机台基础信息维护</b>（改名/型号/产线/工艺/外部链接）和<b>彻底删除机台</b>。
      删除会同时从平面图移除机台，且不可恢复；DT量产表数据不动。
    </div>

    <div v-if="error" class="alert alert-error">{{ error }}</div>
    <div v-if="success" class="alert alert-success">{{ success }}</div>

    <!-- 筛选条 -->
    <div class="filter-bar">
      <input
        v-model="searchKeyword"
        class="input"
        placeholder="搜索机台ID/名称/型号..."
      />
      <select v-model="filterLine" class="input select">
        <option value="">全部产线</option>
        <option v-for="l in lineOptions" :key="l" :value="String(l)">Line {{ l }}</option>
      </select>
      <select v-model="filterState" class="input select">
        <option v-for="o in stateOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
      <div class="count-tag">共 {{ filteredMachines.length }} / {{ machines.length }} 台</div>
    </div>

    <!-- 列表 -->
    <div v-if="loading" class="loading">加载中...</div>

    <div v-if="!loading" class="table-wrapper">
      <table class="data-table">
        <thead>
          <tr>
            <th>机台ID</th>
            <th>名称</th>
            <th>型号</th>
            <th>产线</th>
            <th>工艺</th>
            <th>状态</th>
            <th>告警</th>
            <th>外部链接</th>
            <th>专属 Dify</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in filteredMachines" :key="m.id">
            <td class="mono">{{ m.id }}</td>
            <td>{{ m.name || '-' }}</td>
            <td>{{ m.model || '-' }}</td>
            <td>Line {{ m.line ?? '-' }}</td>
            <td>{{ m.process_type || '-' }}</td>
            <td>
              <span class="state-badge" :class="stateBadgeClass(m.state)">
                {{ stateLabel(m.state) }}
              </span>
            </td>
            <td>
              <span v-if="m.alarm_count" class="alarm-badge">{{ m.alarm_count }}</span>
              <span v-else>-</span>
            </td>
            <td>
              <span v-if="m.use_external_url && m.external_url" class="link-on" :title="m.external_url">已启用</span>
              <span v-else class="link-off">未启用</span>
            </td>
            <td>
              <span
                v-if="machineDifyOf(m)"
                class="dify-tag dify-on"
                :title="`型号 ${m.model} 命中专属 Dify，点击跳转配置页`"
                @click="goAiConfig(m)"
              >{{ machineDifyOf(m).config_name }}</span>
              <span v-else class="dify-tag dify-off" :title="`型号 ${m.model || '—'} 无专属 Dify，点击去配置页新增`" @click="goAiConfig(m)">—</span>
            </td>
            <td class="actions">
              <button class="btn btn-sm" @click="goDetail(m)">查看</button>
              <button class="btn btn-sm" @click="openEditDialog(m)">编辑</button>
              <button class="btn btn-sm btn-danger" @click="openDeleteDialog(m)">删除</button>
            </td>
          </tr>
          <tr v-if="filteredMachines.length === 0">
            <td colspan="10" class="empty">暂无数据</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 编辑弹窗 -->
    <div v-if="showEditDialog" class="modal-overlay" @click.self="showEditDialog = false">
      <div class="modal">
        <div class="modal-header">
          <h3>编辑机台 - {{ editingMachine.id }}</h3>
          <button class="close-btn" @click="showEditDialog = false">×</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label>机台ID</label>
            <input class="input" :value="editingMachine.id" disabled />
          </div>
          <div class="form-group">
            <label>名称 *</label>
            <input v-model="editingMachine.name" class="input" placeholder="机台显示名称" />
          </div>
          <div class="form-group">
            <label>型号</label>
            <input v-model="editingMachine.model" class="input" placeholder="如 OXE / VPO / PODOPENER" />
          </div>
          <div class="form-row">
            <div class="form-group half">
              <label>产线</label>
              <input v-model.number="editingMachine.line" type="number" min="1" class="input" />
            </div>
            <div class="form-group half">
              <label>工艺类型</label>
              <input v-model="editingMachine.process_type" class="input" placeholder="如 ETCH / DEP / LITHO" />
            </div>
          </div>
          <div class="form-divider"></div>
          <div class="form-group">
            <label>外部跳转链接</label>
            <input v-model="editingMachine.external_url" class="input" placeholder="如 http://10.30.6.6/oxe-view" />
          </div>
          <div class="form-group checkbox-row">
            <label>
              <input type="checkbox" v-model="editingMachine.use_external_url" :true-value="1" :false-value="0" />
              启用外部链接（机台详情页点"查看"会跳转到该链接）
            </label>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn" @click="showEditDialog = false">取消</button>
          <button class="btn btn-primary" @click="saveMachine">保存</button>
        </div>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="showDeleteDialog" class="modal-overlay" @click.self="showDeleteDialog = false">
      <div class="modal modal-danger">
        <div class="modal-header danger">
          <h3>⚠️ 彻底删除机台</h3>
          <button class="close-btn" @click="showDeleteDialog = false">×</button>
        </div>
        <div class="modal-body">
          <div class="warn-box">
            <div class="warn-line"><b>机台ID：</b>{{ deletingMachine?.id }}</div>
            <div class="warn-line"><b>名称：</b>{{ deletingMachine?.name || '-' }}</div>
            <div class="warn-line"><b>型号：</b>{{ deletingMachine?.model || '-' }}</div>
          </div>
          <p class="warn-text">
            此操作将<b>彻底删除该机台记录</b>，同时会从所有平面图中移除该机台，且<b>不可恢复</b>。
            DT量产表数据不受影响。
          </p>
          <p v-if="deletingMachine?.alarm_count || deletingMachine?.wafer_count" class="warn-text">
            ⚠️ 该机台当前有告警或晶圆数据，可能存在关联记录，删除可能因外键约束失败，请先清理关联数据。
          </p>
          <div class="form-group">
            <label>请输入机台ID <code>{{ deletingMachine?.id }}</code> 以确认：</label>
            <input v-model="deleteConfirmId" class="input danger-input" :placeholder="deletingMachine?.id" />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn" @click="showDeleteDialog = false">取消</button>
          <button class="btn btn-danger" :disabled="!canConfirmDelete" @click="confirmDelete">
            确认删除
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.machine-mgmt {
  padding: 16px;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.page-header h2 {
  margin: 0;
  font-size: 18px;
  color: var(--text);
}

.page-tip {
  font-size: 12px;
  color: var(--text-dim);
  padding: 8px 12px;
  background: rgba(0, 212, 255, 0.06);
  border: 1px solid rgba(0, 212, 255, 0.2);
  border-radius: 6px;
  line-height: 1.6;
}
.page-tip b { color: var(--accent); }

.alert {
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
}
.alert-error { background: rgba(239, 68, 68, 0.15); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.3); }
.alert-success { background: rgba(34, 197, 94, 0.15); color: #22c55e; border: 1px solid rgba(34, 197, 94, 0.3); }

.filter-bar {
  display: flex;
  gap: 10px;
  align-items: center;
}
.input {
  flex: 1;
  padding: 8px 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-size: 13px;
  outline: none;
}
.input:focus { border-color: var(--accent); }
.input:disabled { opacity: 0.5; cursor: not-allowed; }
.select { flex: 0 0 160px; }
.count-tag {
  font-size: 12px;
  color: var(--text-dim);
  padding: 6px 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  white-space: nowrap;
}

.table-wrapper {
  flex: 1;
  overflow: auto;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.data-table thead th {
  position: sticky;
  top: 0;
  background: var(--panel);
  text-align: left;
  padding: 10px 12px;
  color: var(--text-dim);
  font-weight: 600;
  border-bottom: 1px solid var(--border);
  z-index: 1;
}
.data-table tbody td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  color: var(--text);
}
.data-table tbody tr:hover { background: rgba(0, 212, 255, 0.05); }
.mono { font-family: 'Consolas', monospace; font-size: 12px; }
.empty { text-align: center; color: var(--text-dim); padding: 20px; }

.state-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}
.state-badge.state-run { background: rgba(34, 197, 94, 0.15); color: #22c55e; }
.state-badge.state-idle { background: rgba(148, 163, 184, 0.15); color: #94a3b8; }
.state-badge.state-error { background: rgba(239, 68, 68, 0.15); color: #ef4444; }
.state-badge.state-maint { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.state-badge.state-setup { background: rgba(59, 130, 246, 0.15); color: #3b82f6; }
.state-badge.state-unknown { background: rgba(148, 163, 184, 0.1); color: var(--text-dim); }

.alarm-badge {
  display: inline-block;
  min-width: 20px;
  padding: 2px 6px;
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  text-align: center;
}
.link-on { color: #22c55e; font-size: 12px; }
.link-off { color: var(--text-dim); font-size: 12px; }
.dify-tag {
  display: inline-block;
  font-size: 11.5px;
  padding: 2px 8px;
  border-radius: 10px;
  cursor: pointer;
  user-select: none;
  border: 1px solid transparent;
  white-space: nowrap;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: middle;
}
.dify-on {
  color: #00d4ff;
  background: rgba(0, 212, 255, 0.12);
  border-color: rgba(0, 212, 255, 0.3);
}
.dify-on:hover { background: rgba(0, 212, 255, 0.2); }
.dify-off { color: var(--text-dim); }
.dify-off:hover { color: var(--text); }

.actions { white-space: nowrap; }
.btn {
  padding: 6px 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text);
  cursor: pointer;
  font-size: 12px;
  margin-right: 4px;
}
.btn:hover { border-color: var(--accent); color: var(--accent); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-sm { padding: 4px 8px; font-size: 11px; }
.btn-primary { background: rgba(0, 212, 255, 0.15); color: var(--accent); border-color: var(--accent); }
.btn-danger { color: #ef4444; border-color: rgba(239, 68, 68, 0.3); }
.btn-danger:hover { background: rgba(239, 68, 68, 0.1); border-color: #ef4444; }

.loading { padding: 20px; text-align: center; color: var(--text-dim); }

/* 弹窗 */
.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  width: 520px;
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}
.modal-danger { border-color: rgba(239, 68, 68, 0.4); }
.modal-header {
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.modal-header.danger { border-bottom-color: rgba(239, 68, 68, 0.3); }
.modal-header h3 { margin: 0; font-size: 15px; color: var(--text); }
.modal-header.danger h3 { color: #ef4444; }
.close-btn {
  background: transparent;
  border: none;
  color: var(--text-dim);
  font-size: 20px;
  cursor: pointer;
  padding: 0 8px;
}
.close-btn:hover { color: var(--text); }
.modal-body { padding: 16px 18px; overflow: auto; }
.modal-footer {
  padding: 12px 18px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.form-group { margin-bottom: 12px; }
.form-group label {
  display: block;
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--text-dim);
}
.form-row { display: flex; gap: 12px; }
.form-group.half { flex: 1; }
.form-divider {
  height: 1px;
  background: var(--border);
  margin: 14px 0;
}
.checkbox-row label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
}
.checkbox-row input[type="checkbox"] { margin: 0; }

.warn-box {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 12px;
}
.warn-line { font-size: 13px; color: var(--text); margin-bottom: 4px; }
.warn-text {
  font-size: 13px;
  color: var(--text-dim);
  line-height: 1.6;
  margin: 8px 0;
}
.warn-text b { color: #ef4444; }
.danger-input { border-color: rgba(239, 68, 68, 0.4); }
.danger-input:focus { border-color: #ef4444; }
code {
  background: var(--bg);
  padding: 2px 6px;
  border-radius: 3px;
  color: var(--accent);
  font-family: monospace;
}
</style>
