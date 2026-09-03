/**
 * 初始假数据 — 首次运行时自动注入 localStorage
 * 让开发者打开就有 3 个示例机型可以编辑
 */
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

export function seedIfEmpty() {
  const existing = localStorage.getItem('mock_models')
  if (!existing || JSON.parse(existing).length === 0) {
    localStorage.setItem('mock_models', JSON.stringify(SEED_MODELS))
    console.log('[SEED] 已注入 3 个示例机型数据')
  }
}
