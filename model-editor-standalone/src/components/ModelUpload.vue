<script setup>
import { ref, onMounted, watch } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'

const props = defineProps({
  modelId: { type: String, default: '' },
  modelName: { type: String, default: '' },
})

const emit = defineEmits(['uploaded', 'deleted', 'svgPartsExtracted'])

const authStore = useAuthStore()

const loading = ref(false)
const uploading = ref(false)
const extracting = ref(false)
const fileList = ref([])
const dragActive = ref(false)
const errorMsg = ref('')
const successMsg = ref('')
const svgParts = ref([])

const ALLOWED_EXTS = ['.svg', '.glb', '.gltf', '.json', '.html']
const MAX_SIZE = 50 * 1024 * 1024

const extColor = {
  '.svg': '#4CAF50',
  '.glb': '#2196F3',
  '.gltf': '#2196F3',
  '.json': '#FF9800',
  '.html': '#9C27B0',
}

function fileExt(name) {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i).toLowerCase() : ''
}

function fileIcon(name) {
  return fileExt(name).replace('.', '').toUpperCase()
}

function extStyle(name) {
  return { background: extColor[fileExt(name)] || '#607D8B' }
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

async function loadFiles() {
  if (!props.modelId) return
  loading.value = true
  errorMsg.value = ''
  try {
    const resp = await api.getModelFiles(props.modelId)
    fileList.value = resp.files || []
  } catch (e) {
    errorMsg.value = e.message || '加载文件列表失败'
  } finally {
    loading.value = false
  }
}

async function handleFiles(files) {
  const list = Array.from(files)
  errorMsg.value = ''
  successMsg.value = ''

  if (!props.modelId) {
    errorMsg.value = '请先选择机型'
    return
  }

  // 前置校验：格式 + 大小
  const invalid = []
  for (const f of list) {
    const ext = fileExt(f.name)
    if (!ALLOWED_EXTS.includes(ext)) {
      invalid.push(`${f.name} (不支持 ${ext})`)
    } else if (f.size > MAX_SIZE) {
      invalid.push(`${f.name} (${formatSize(f.size)} 超 ${formatSize(MAX_SIZE)})`)
    }
  }
  if (invalid.length) {
    errorMsg.value = `已忽略：${invalid.join('，')}。支持: ${ALLOWED_EXTS.join(', ')}，最大 ${formatSize(MAX_SIZE)}`
    return
  }

  // v2.5.3：SVG 排前面先传，确保 extractParts 在所有文件传完后能立即拿到 current_svg
  // （后端已分槽存储顺序无关，此排序仅作保险）
  list.sort((a, b) => {
    const aSvg = fileExt(a.name) === '.svg' ? 0 : 1
    const bSvg = fileExt(b.name) === '.svg' ? 0 : 1
    return aSvg - bSvg
  })

  uploading.value = true
  const user = authStore.user?.username || 'admin'
  const okFiles = []
  const failedFiles = []
  for (const f of list) {
    try {
      await api.uploadModelFile(f, props.modelId, user)
      okFiles.push(f.name)
    } catch (e) {
      failedFiles.push(`${f.name}: ${e.message || '上传失败'}`)
    }
  }

  // 汇总反馈
  const msgs = []
  if (okFiles.length) msgs.push(`✅ 成功 ${okFiles.length} 个：${okFiles.join('、')}`)
  if (failedFiles.length) msgs.push(`❌ 失败 ${failedFiles.length} 个：${failedFiles.join('；')}`)
  successMsg.value = msgs.length ? msgs.join(' | ') : ''

  // 只要有任意一个成功，就触发父组件刷新 + 重新加载文件列表
  if (okFiles.length) {
    emit('uploaded')
    await loadFiles()
    // 如果本次上传了 SVG，自动提取部件
    if (okFiles.some(n => fileExt(n) === '.svg')) {
      await extractParts()
    }
  }
  uploading.value = false
}

async function extractParts() {
  if (!props.modelId) return
  extracting.value = true
  errorMsg.value = ''
  try {
    const resp = await api.extractSvgParts(props.modelId)
    svgParts.value = resp.parts || []
    emit('svgPartsExtracted', svgParts.value)
    successMsg.value = `从 SVG 中提取了 ${svgParts.value.length} 个部件`
  } catch (e) {
    errorMsg.value = e.message || '提取部件失败'
  } finally {
    extracting.value = false
  }
}

function onFileChange(e) {
  handleFiles(e.target.files)
  e.target.value = ''
}

function onDragEnter(e) { e.preventDefault(); dragActive.value = true }
function onDragLeave(e) { e.preventDefault(); dragActive.value = false }
function onDragOver(e) { e.preventDefault() }
function onDrop(e) {
  e.preventDefault()
  dragActive.value = false
  handleFiles(e.dataTransfer.files)
}

async function deleteFile(file) {
  if (!confirm(`确定删除文件 "${file.file_name}" (${file.version})？`)) return
  try {
    await api.deleteModelFile(file.file_id, file.model_id)
    successMsg.value = `文件 ${file.file_name} 已删除`
    emit('deleted')
    await loadFiles()
    svgParts.value = []
    emit('svgPartsExtracted', [])
  } catch (e) {
    errorMsg.value = e.message || '删除失败'
  }
}

function openFileUrl(url) {
  if (url) window.open(url, '_blank')
}

watch(() => props.modelId, () => {
  if (props.modelId) {
    loadFiles()
    svgParts.value = []
  }
})

onMounted(() => {
  if (props.modelId) loadFiles()
})
</script>

<template>
  <div class="model-upload">
    <div class="upload-header">
      <div class="uh-left">
        <span class="uh-icon">📁</span>
        <span class="uh-title">模型文件管理</span>
        <span v-if="modelName" class="uh-model-name">— {{ modelName }}</span>
      </div>
      <div class="uh-right">
        <span v-if="fileList.length" class="file-count">{{ fileList.length }} 个文件</span>
        <button class="btn-refresh" :disabled="loading" @click="loadFiles" title="刷新">
          {{ loading ? '...' : '🔄' }}
        </button>
        <button v-if="fileList.some(f => f.file_type === '.svg')"
                class="btn-extract" :disabled="extracting"
                @click="extractParts" title="提取SVG部件">
          {{ extracting ? '⏳' : '🔍' }}
        </button>
      </div>
    </div>

    <div
      class="drop-zone"
      :class="{ active: dragActive }"
      @dragenter="onDragEnter"
      @dragleave="onDragLeave"
      @dragover="onDragOver"
      @drop="onDrop"
    >
      <div class="dz-inner">
        <div class="dz-icon">⬆️</div>
        <div class="dz-text">拖拽文件到此处，或</div>
        <label class="dz-btn">
          <input type="file" multiple accept=".svg,.glb,.gltf,.json,.html" @change="onFileChange" />
          <span>点击选择文件</span>
        </label>
        <div class="dz-hint">
          支持: {{ ALLOWED_EXTS.join(', ') }} · 最大 {{ formatSize(MAX_SIZE) }}
        </div>
      </div>
    </div>

    <div v-if="errorMsg" class="msg error">⚠️ {{ errorMsg }}</div>
    <div v-if="successMsg" class="msg success">✅ {{ successMsg }}</div>

    <div class="file-list">
      <div v-if="loading && fileList.length === 0" class="empty-state">加载中...</div>
      <div v-else-if="!fileList.length" class="empty-state">
        <div class="empty-icon">📂</div>
        <div class="empty-text">暂无模型文件</div>
        <div class="empty-hint">上传 SVG / GLB / JSON / HTML 文件来管理机型的 2D/3D 模型</div>
      </div>
      <div v-else class="file-grid">
        <div v-for="f in fileList" :key="f.file_id" class="file-card">
          <div class="file-ext" :style="extStyle(f.file_name)">{{ fileIcon(f.file_name) }}</div>
          <div class="file-info">
            <div class="file-name" :title="f.file_name">{{ f.file_name }}</div>
            <div class="file-meta">
              <span class="version">{{ f.version }}</span>
              <span class="dot">·</span>
              <span>{{ formatSize(f.file_size) }}</span>
              <span class="dot">·</span>
              <span class="time">{{ f.created_at }}</span>
            </div>
            <div class="file-url" :title="f.file_url" @click="openFileUrl(f.file_url)">
              🔗 {{ f.file_url }}
            </div>
          </div>
          <div class="file-actions">
            <button class="btn-preview" title="预览" @click="openFileUrl(f.file_url)">👁️</button>
            <button class="btn-del" title="删除" @click="deleteFile(f)">🗑️</button>
          </div>
        </div>
      </div>
    </div>

    <!-- SVG 部件提取结果 -->
    <div v-if="svgParts.length" class="svg-parts-section">
      <div class="parts-header">
        <span>🔍 SVG 部件提取结果（{{ svgParts.length }} 个）</span>
      </div>
      <div class="parts-list">
        <div v-for="p in svgParts" :key="p.element_id" class="part-item">
          <span class="part-id">{{ p.element_id }}</span>
          <span class="part-tag">{{ p.tag }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.model-upload {
  padding: 16px;
  background: var(--bg-card, #1a1f2e);
  border-radius: 10px;
  border: 1px solid var(--border, #2a3142);
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.upload-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.uh-left { display: flex; align-items: center; gap: 8px; }
.uh-icon { font-size: 18px; }
.uh-title { font-size: 15px; font-weight: 600; color: var(--text, #e0e6ed); }
.uh-model-name { color: var(--text-dim, #8a94a6); font-size: 13px; }

.uh-right { display: flex; align-items: center; gap: 8px; }
.file-count { font-size: 12px; color: var(--text-dim, #8a94a6); }
.btn-refresh, .btn-extract {
  background: none; border: 1px solid var(--border, #2a3142);
  color: var(--text, #e0e6ed); border-radius: 6px;
  width: 32px; height: 32px; cursor: pointer; font-size: 14px;
}
.btn-refresh:hover, .btn-extract:hover { background: var(--bg-hover, #252b3b); }

.drop-zone {
  border: 2px dashed var(--border, #2a3142);
  border-radius: 10px;
  padding: 24px;
  text-align: center;
  transition: all 0.2s;
  cursor: pointer;
  flex-shrink: 0;
  background: var(--bg-secondary, #151a28);
}
.drop-zone.active {
  border-color: var(--primary, #4a9eff);
  background: rgba(74, 158, 255, 0.05);
}
.dz-inner { display: flex; flex-direction: column; align-items: center; gap: 8px; }
.dz-icon { font-size: 32px; }
.dz-text { font-size: 14px; color: var(--text, #e0e6ed); }
.dz-btn {
  display: inline-block; padding: 8px 20px;
  background: var(--primary, #4a9eff); color: #fff;
  border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500;
}
.dz-btn input { display: none; }
.dz-hint { font-size: 12px; color: var(--text-dim, #8a94a6); }

.msg {
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
  margin-top: 10px;
  flex-shrink: 0;
}
.msg.error { background: rgba(244, 67, 54, 0.15); color: #f44336; }
.msg.success { background: rgba(76, 175, 80, 0.15); color: #4caf50; }

.file-list {
  margin-top: 12px;
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-dim, #8a94a6);
}
.empty-icon { font-size: 40px; margin-bottom: 12px; }
.empty-text { font-size: 15px; color: var(--text, #e0e6ed); margin-bottom: 4px; }
.empty-hint { font-size: 12px; }

.file-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--bg-secondary, #151a28);
  border: 1px solid var(--border, #2a3142);
  border-radius: 8px;
  transition: border-color 0.2s;
}
.file-card:hover { border-color: var(--primary, #4a9eff); }

.file-ext {
  width: 48px; height: 48px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 11px; font-weight: 700;
  flex-shrink: 0;
}

.file-info { flex: 1; min-width: 0; }
.file-name {
  font-size: 14px; color: var(--text, #e0e6ed);
  font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.file-meta {
  font-size: 12px; color: var(--text-dim, #8a94a6);
  margin-top: 4px;
  display: flex; align-items: center; gap: 6px;
}
.file-meta .version {
  background: rgba(74, 158, 255, 0.15); color: var(--primary, #4a9eff);
  padding: 2px 6px; border-radius: 4px; font-weight: 600;
}
.file-meta .dot { opacity: 0.5; }
.file-url {
  font-size: 11px; color: var(--primary, #4a9eff);
  margin-top: 3px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  font-family: monospace;
  cursor: pointer;
}
.file-url:hover { text-decoration: underline; }

.file-actions { flex-shrink: 0; display: flex; gap: 4px; }
.btn-preview, .btn-del {
  background: none; border: none; cursor: pointer;
  font-size: 16px; padding: 6px; border-radius: 4px;
  opacity: 0.6; transition: opacity 0.2s;
}
.btn-preview:hover { opacity: 1; background: rgba(74, 158, 255, 0.15); }
.btn-del:hover { opacity: 1; background: rgba(244, 67, 54, 0.15); }

/* SVG 部件提取结果 */
.svg-parts-section {
  margin-top: 12px;
  padding: 12px;
  background: var(--bg-secondary, #151a28);
  border: 1px solid var(--border, #2a3142);
  border-radius: 8px;
  flex-shrink: 0;
  max-height: 200px;
  overflow-y: auto;
}
.parts-header {
  font-size: 13px; font-weight: 600;
  color: var(--primary, #4a9eff);
  margin-bottom: 8px;
}
.parts-list {
  display: flex; flex-wrap: wrap; gap: 6px;
}
.part-item {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 8px;
  background: var(--bg-card, #1a1f2e);
  border: 1px solid var(--border, #2a3142);
  border-radius: 4px;
  font-size: 12px;
}
.part-id { font-family: monospace; color: var(--text, #e0e6ed); }
.part-tag {
  font-size: 10px; padding: 1px 6px;
  background: rgba(74, 158, 255, 0.15); color: var(--primary, #4a9eff);
  border-radius: 10px;
}
</style>
