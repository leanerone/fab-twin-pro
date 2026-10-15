/**
 * 初始假数据 — 首次运行时自动注入 localStorage
 * v2: 追加 AMAT-METSPUT 机型（动画配置来自 src/data/amat_metsput.json，
 *     SVG 内容写入 IndexedDB，与 api/index.js 同一库表）
 */
import svgRaw from '../assets/amat_metsput.svg?raw'
import motionJson from '../data/amat_metsput.json'

const SEED_VERSION = '2'
const SEED_VERSION_KEY = 'mock_seed_version'
const AMAT_SVG_URL = '/uploads/models/AMAT-METSPUT_v1_seed.svg'
const SEED_TIME = '2026-10-15 10:00:00'

const SEED_MODELS = [
  {
    model_id: 'OXE-01',
    model_name: 'OXE 刻蚀机',
    vendor: 'Lam Research',
    process_type: 'ETCH',
    version: 'v1',
    view_mode: 'svg',
    description: 'OXE 系列刻蚀设备，支持 line1（无SMIF）和 line2（有SMIF）',
    views_config: {
      view_2d: { svg_source: '' },
      view_3d: { model_source: '' },
    },
    parts_config: [],
    state_mapping: [],
    hotspots_config: [],
    animation_config: {},
    source_files: {},
    event_actions: [],
    created_at: '2026-08-01 10:00:00',
    updated_at: '2026-08-01 10:00:00',
  },
  {
    model_id: 'PODOPENER',
    model_name: 'Pod Opener',
    vendor: 'Brooks',
    process_type: 'OPEN',
    version: 'v1',
    view_mode: 'svg',
    description: 'Pod 开盖设备，用于开启 FOUP',
    views_config: {},
    parts_config: [],
    state_mapping: [],
    hotspots_config: [],
    animation_config: {},
    source_files: {},
    event_actions: [],
    created_at: '2026-08-01 10:00:00',
    updated_at: '2026-08-01 10:00:00',
  },
  {
    model_id: 'VPO',
    model_name: 'VPO 机台',
    vendor: 'Applied Materials',
    process_type: 'ETCH',
    version: 'v1',
    view_mode: 'html',
    description: 'VPO 刻蚀设备，需要专用的按钮布局和视图切换',
    views_config: {},
    parts_config: [],
    state_mapping: [],
    hotspots_config: [],
    animation_config: {},
    source_files: {},
    event_actions: [],
    created_at: '2026-08-01 10:00:00',
    updated_at: '2026-08-01 10:00:00',
  },
]

function buildAmatSvgMeta() {
  return {
    file_id: 'seed_svg_amat',
    file_name: 'amat_metsput.svg',
    file_url: AMAT_SVG_URL,
    file_type: '.svg',
    file_size: svgRaw.length,
    model_id: 'AMAT-METSPUT',
    version: 'v1',
    uploaded_by: 'seed',
    created_at: SEED_TIME,
  }
}

function buildAmatModel() {
  const svgMeta = buildAmatSvgMeta()
  return {
    model_id: 'AMAT-METSPUT',
    model_name: 'AMAT MET/SPUT',
    vendor: 'Applied Materials',
    process_type: 'PVD',
    version: 'v1',
    view_mode: 'svg',
    description: 'AMAT MET/SPUT 平台（种子数据：含动画配置与 SVG）',
    views_config: {
      view_2d: { svg_source: AMAT_SVG_URL },
      view_3d: { model_source: '' },
    },
    parts_config: [],
    state_mapping: [],
    hotspots_config: [],
    animation_config: motionJson,
    source_files: { current_svg: svgMeta, current_file: svgMeta, history: [svgMeta] },
    event_actions: [],
    created_at: SEED_TIME,
    updated_at: SEED_TIME,
  }
}

// ========== IndexedDB 写入（与 api/index.js 同一库/表） ==========
function idbSet(key, value) {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open('fabtwin_mock', 1)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains('model_files')) {
        db.createObjectStore('model_files')
      }
    }
    req.onsuccess = () => {
      const db = req.result
      const tx = db.transaction('model_files', 'readwrite')
      tx.objectStore('model_files').put(value, key)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    }
    req.onerror = () => reject(req.error)
  })
}

function _loadModels() {
  try {
    return JSON.parse(localStorage.getItem('mock_models') || '[]')
  } catch { return [] }
}

async function ensureAmatSeeded(force) {
  const list = _loadModels()
  const idx = list.findIndex(m => m.model_id === 'AMAT-METSPUT')
  if (idx < 0) {
    list.push(buildAmatModel())
  } else if (force) {
    // 版本升级：整体重置为种子配置（保留创建时间）
    list[idx] = { ...buildAmatModel(), created_at: list[idx].created_at || SEED_TIME }
  } else {
    // 兼容旧数据：缺动画配置 / SVG 绑定则补齐，保留用户其他改动
    const m = list[idx]
    const patch = {}
    if (!m.animation_config || !Object.keys(m.animation_config).length) {
      patch.animation_config = motionJson
    }
    if (!m.views_config?.view_2d?.svg_source) {
      patch.views_config = { ...(m.views_config || {}), view_2d: { svg_source: AMAT_SVG_URL } }
    }
    if (!m.source_files?.current_svg) {
      const svgMeta = buildAmatSvgMeta()
      patch.source_files = { ...(m.source_files || {}), current_svg: svgMeta, current_file: svgMeta }
    }
    if (Object.keys(patch).length) list[idx] = { ...m, ...patch }
  }
  localStorage.setItem('mock_models', JSON.stringify(list))

  // 文件元数据补齐
  try {
    const files = JSON.parse(localStorage.getItem('mock_model_files') || '[]')
    if (!files.some(f => f.file_id === 'seed_svg_amat')) {
      files.push(buildAmatSvgMeta())
      localStorage.setItem('mock_model_files', JSON.stringify(files))
    }
  } catch { /* 忽略 */ }

  // SVG 内容写 IndexedDB（幂等，保证 MotionPreview fetch 失败后的回退读取）
  await idbSet(AMAT_SVG_URL, svgRaw)
}

export function seedIfEmpty() {
  const existing = localStorage.getItem('mock_models')
  if (!existing || JSON.parse(existing).length === 0) {
    localStorage.setItem('mock_models', JSON.stringify(SEED_MODELS))
    console.log('[SEED] 已注入 3 个示例机型数据')
  }
  const ver = localStorage.getItem(SEED_VERSION_KEY)
  ensureAmatSeeded(ver !== SEED_VERSION)
    .then(() => {
      localStorage.setItem(SEED_VERSION_KEY, SEED_VERSION)
      console.log('[SEED] AMAT-METSPUT 种子数据就绪')
    })
    .catch(e => console.warn('[SEED] AMAT-METSPUT 注入失败', e))
}
