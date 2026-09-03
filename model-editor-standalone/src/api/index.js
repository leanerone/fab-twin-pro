/**
 * Mock API 层 — 模拟 FabTwin 后端所有模型相关接口
 *
 * 数据存储：
 * - 模型配置 → localStorage（key: mock_models）
 * - 文件内容 → IndexedDB（store: model_files）
 * - 文件元数据 → localStorage（key: mock_model_files）
 *
 * 所有接口返回格式与真实后端一致，合并回主项目时只需替换 api 导入路径即可。
 */

// ========== IndexedDB 文件存储 ==========
const DB_NAME = 'fabtwin_mock'
const DB_VERSION = 1
const STORE_FILES = 'model_files'

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE_FILES)) {
        db.createObjectStore(STORE_FILES)
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function idbSet(key, value) {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_FILES, 'readwrite')
    tx.objectStore(STORE_FILES).put(value, key)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

async function idbGet(key) {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_FILES, 'readonly')
    const req = tx.objectStore(STORE_FILES).get(key)
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function idbDelete(key) {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_FILES, 'readwrite')
    tx.objectStore(STORE_FILES).delete(key)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

// ========== localStorage 模型配置 ==========
const MODELS_KEY = 'mock_models'
const FILES_KEY = 'mock_model_files'

function _loadModels() {
  try {
    return JSON.parse(localStorage.getItem(MODELS_KEY) || '[]')
  } catch { return [] }
}
function __saveModels(list) {
  localStorage.setItem(MODELS_KEY, JSON.stringify(list))
}
function _loadFiles() {
  try {
    return JSON.parse(localStorage.getItem(FILES_KEY) || '[]')
  } catch { return [] }
}
function __saveFiles(list) {
  localStorage.setItem(FILES_KEY, JSON.stringify(list))
}

// ========== 工具函数 ==========
function genId() {
  return Math.random().toString(36).slice(2, 10)
}
function now() {
  return new Date().toISOString().replace('T', ' ').slice(0, 19)
}
function fileExt(name) {
  const i = name.lastIndexOf('.')
  return i >= 0 ? name.slice(i).toLowerCase() : ''
}
function slotKey(ext) {
  if (ext === '.svg') return 'current_svg'
  if (ext === '.json') return 'current_json'
  if (['.glb', '.gltf'].includes(ext)) return 'current_glb'
  if (ext === '.html') return 'current_html'
  return 'current_other'
}

function nextVersion(modelId) {
  const m = _loadModels().find(m => m.model_id === modelId)
  if (!m || !m.version) return 'v1'
  const num = parseInt(m.version.replace(/[v.]/g, '')) || 1
  return `v${num + 1}`
}

// ========== 模型 CRUD ==========
async function getModels() {
  return _loadModels()
}
async function getModel(modelId) {
  const m = _loadModels().find(m => m.model_id === modelId)
  if (!m) throw new Error(`机型 ${modelId} 不存在`)
  return m
}
async function createModel(data) {
  const list = _loadModels()
  if (list.some(m => m.model_id === data.model_id)) {
    throw new Error(`机型 ${data.model_id} 已存在`)
  }
  const model = {
    model_id: data.model_id,
    model_name: data.model_name || data.model_id,
    vendor: data.vendor || '',
    process_type: data.process_type || 'ETCH',
    version: 'v1',
    view_mode: data.view_mode || 'svg',
    description: data.description || '',
    views_config: {},
    parts_config: [],
    state_mapping: [],
    hotspots_config: [],
    animation_config: {},
    source_files: {},
    event_actions: [],
    created_at: now(),
    updated_at: now(),
  }
  list.push(model)
  _saveModels(list)
  return model
}
async function updateModel(modelId, data) {
  const list = _loadModels()
  const idx = list.findIndex(m => m.model_id === modelId)
  if (idx < 0) throw new Error(`机型 ${modelId} 不存在`)
  list[idx] = { ...list[idx], ...data, updated_at: now() }
  _saveModels(list)
  return list[idx]
}
async function deleteModel(modelId) {
  const list = _loadModels().filter(m => m.model_id !== modelId)
  _saveModels(list)
  // 同时清理文件
  const files = _loadFiles().filter(f => f.model_id !== modelId)
  _saveFiles(files)
  return { status: 'success' }
}
async function duplicateModel(modelId, data) {
  const src = _loadModels().find(m => m.model_id === modelId)
  if (!src) throw new Error(`机型 ${modelId} 不存在`)
  return createModel({ ...src, ...data, model_id: data.model_id })
}

// ========== 事件动作映射 ==========
async function getEventActions(modelId) {
  const m = _loadModels().find(m => m.model_id === modelId)
  return m?.event_actions || []
}
async function createEventAction(modelId, data) {
  const list = _loadModels()
  const m = list.find(m => m.model_id === modelId)
  if (!m) throw new Error(`机型 ${modelId} 不存在`)
  const action = { ...data, id: genId(), model_id: modelId, created_at: now(), updated_at: now() }
  m.event_actions = m.event_actions || []
  m.event_actions.push(action)
  _saveModels(list)
  return action
}
async function updateEventAction(modelId, mappingId, data) {
  const list = _loadModels()
  const m = list.find(m => m.model_id === modelId)
  if (!m) return
  const idx = (m.event_actions || []).findIndex(a => a.id === mappingId)
  if (idx >= 0) {
    m.event_actions[idx] = { ...m.event_actions[idx], ...data, updated_at: now() }
    _saveModels(list)
    return m.event_actions[idx]
  }
}
async function deleteEventAction(modelId, mappingId) {
  const list = _loadModels()
  const m = list.find(m => m.model_id === modelId)
  if (!m) return
  m.event_actions = (m.event_actions || []).filter(a => a.id !== mappingId)
  _saveModels(list)
  return { status: 'success' }
}

// ========== 文件上传/管理 ==========
async function uploadModelFile(file, modelId, uploadedBy = 'dev') {
  const models = _loadModels()
  const m = models.find(m => m.model_id === modelId)
  if (!m) throw new Error(`机型 ${modelId} 不存在`)

  const ext = fileExt(file.name)
  const version = nextVersion(modelId)
  const fileId = genId()
  const fileUrl = `/uploads/models/${modelId}_${version}_${fileId}${ext}`

  // 文件内容存 IndexedDB（text 文件存字符串，binary 存 ArrayBuffer）
  let content
  if (['.svg', '.json', '.html'].includes(ext)) {
    content = await file.text()
  } else {
    content = await file.arrayBuffer()
  }
  await idbSet(fileUrl, content)

  // 文件元数据存 localStorage
  const files = _loadFiles()
  const fileMeta = {
    file_id: fileId,
    file_name: file.name,
    file_url: fileUrl,
    file_type: ext,
    file_size: file.size,
    model_id: modelId,
    version,
    uploaded_by: uploadedBy,
    created_at: now(),
  }
  files.push(fileMeta)
  _saveFiles(files)

  // 更新模型 source_files（分槽存储）
  if (!m.source_files) m.source_files = {}
  const sk = slotKey(ext)
  m.source_files[sk] = fileMeta
  m.source_files.current_file = fileMeta
  if (!m.source_files.history) m.source_files.history = []
  m.source_files.history.push(fileMeta)
  m.version = version
  m.updated_at = now()
  _saveModels(models)

  // 更新 views_config
  if (!m.views_config) m.views_config = {}
  if (ext === '.svg') {
    if (!m.views_config.view_2d) m.views_config.view_2d = {}
    m.views_config.view_2d.svg_source = fileUrl
  } else if (['.glb', '.gltf', '.json'].includes(ext)) {
    if (!m.views_config.view_3d) m.views_config.view_3d = {}
    m.views_config.view_3d.model_source = fileUrl
  }
  _saveModels(models)

  // JSON 含 schema_version → 存 animation_config
  if (ext === '.json') {
    try {
      const json = JSON.parse(content)
      if (json.schema_version) {
        m.animation_config = json
        m.updated_at = now()
        _saveModels(models)
      }
    } catch {}
  }

  return fileMeta
}

async function getModelFiles(modelId) {
  const files = _loadFiles().filter(f => f.model_id === modelId)
  // 去重：同 file_url 只保留最新版本
  const seen = new Map()
  for (const f of files) {
    const existing = seen.get(f.file_url)
    if (!existing || f.created_at > existing.created_at) {
      seen.set(f.file_url, f)
    }
  }
  return { files: Array.from(seen.values()), total: seen.size }
}

async function deleteModelFile(fileId, modelId) {
  const files = _loadFiles()
  const idx = files.findIndex(f => f.file_id === fileId && f.model_id === modelId)
  if (idx < 0) throw new Error('文件不存在')
  const fileUrl = files[idx].file_url
  await idbDelete(fileUrl)
  files.splice(idx, 1)
  _saveFiles(files)

  // 清理模型 source_files
  const models = _loadModels()
  const m = models.find(m => m.model_id === modelId)
  if (m && m.source_files) {
    const sk = slotKey(files[idx]?.file_type || '')
    if (sk && m.source_files[sk]?.file_id === fileId) {
      delete m.source_files[sk]
    }
    if (m.source_files.current_file?.file_id === fileId) {
      delete m.source_files.current_file
    }
    m.source_files.history = (m.source_files.history || []).filter(h => h.file_id !== fileId)
    _saveModels(models)
  }
  return { status: 'success', message: `文件 ${fileId} 已删除` }
}

async function extractSvgParts(modelId) {
  const models = _loadModels()
  const m = models.find(m => m.model_id === modelId)
  if (!m) throw new Error(`机型 ${modelId} 不存在`)

  const sf = m.source_files || {}
  const svgMeta = sf.current_svg || sf.current_file
  if (!svgMeta || svgMeta.file_type !== '.svg') {
    throw new Error('该机型没有已上传的 SVG 文件，请先上传 SVG')
  }

  const content = await idbGet(svgMeta.file_url)
  if (!content) throw new Error('SVG 文件内容不存在')

  // 客户端解析 SVG（用 DOMParser 代替后端的 xml.etree）
  const parser = new DOMParser()
  const doc = parser.parseFromString(content, 'image/svg+xml')
  const parts = []
  const skipTags = ['style', 'defs', 'metadata', 'title', 'desc']

  function walk(node) {
    if (node.nodeType !== 1) return
    const id = node.getAttribute('id')
    if (id) {
      const tag = node.tagName.toLowerCase()
      if (!skipTags.includes(tag)) {
        parts.push({ element_id: id, tag, part_name: id })
      }
    }
    for (const child of node.children) walk(child)
  }
  walk(doc.documentElement)

  return { model_id: modelId, parts, total: parts.length }
}

// ========== 文件内容读取（供 SVG 预览用）==========
async function getFileContent(fileUrl) {
  return await idbGet(fileUrl)
}

// ========== 导出 ==========
export const api = {
  // 模型 CRUD
  getModels,
  getModel,
  createModel,
  updateModel,
  deleteModel,
  duplicateModel,
  // 事件动作映射
  getEventActions,
  createEventAction,
  updateEventAction,
  deleteEventAction,
  // 文件上传/管理
  uploadModelFile,
  getModelFiles,
  deleteModelFile,
  extractSvgParts,
  // 文件内容（预览用）
  getFileContent,
}
