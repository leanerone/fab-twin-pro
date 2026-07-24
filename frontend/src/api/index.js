// API请求封装
const BASE = '/api';

function getToken() {
  return localStorage.getItem('fabtwin_token');
}

async function request(method, path, data = null, requireAuth = true) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (requireAuth) {
    const token = getToken();
    if (token) {
      opts.headers.Authorization = `Bearer ${token}`;
    } else if (requireAuth) {
      const currentHash = window.location.hash;
      if (!currentHash.includes('/login')) {
        window.location.hash = '#/login';
      }
      throw new Error('No token available');
    }
  }
  if (data && method !== 'GET' && method !== 'DELETE') opts.body = JSON.stringify(data);
  const res = await fetch(BASE + path, opts);
  if (!res.ok) {
    if (res.status === 401) {
      const token = getToken();
      if (token) {
        localStorage.removeItem('fabtwin_token');
      }
      const currentHash = window.location.hash;
      if (!currentHash.includes('/login')) {
        window.location.hash = '#/login';
      }
    }
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

export const api = {
  // 机台API
  getMachines: () => request('GET', '/machines'),
  getMachine: (id) => request('GET', `/machines/${id}`),
  getMachineStats: () => request('GET', '/machines/stats'),

  // 事件API
  getEvents: (machineId, date) => request('GET', `/events/${machineId}?date=${date}`),
  getLatestEvents: (machineId, limit = 60) => request('GET', `/events/${machineId}/latest?limit=${limit}`),
  getTimeline: (machineId, date) => request('GET', `/events/${machineId}/timeline?date=${date}`),

  // Lot API
  getLots: (machineId, date) => request('GET', `/lots?machine_id=${machineId}&date=${date}`),
  getLot: (lotId) => request('GET', `/lots/${lotId}`),
  getLotEvents: (lotId) => request('GET', `/lots/${lotId}/events`),

  // 告警API
  getAlarms: (machineId, date) => request('GET', `/alarms?machine_id=${machineId}&date=${date}`),
  getAlarmStats: (machineId, date) => request('GET', `/alarms/stats?machine_id=${machineId}&date=${date}`),

  // AI API
  aiQuery: (question, machineId) => request('POST', '/ai/query', { question, machine_id: machineId }),
  // AI 统一聊天接口
  aiChat: (data) => request('POST', '/ai/chat', data),
  // AI 配置管理（Dify/N8N）
  aiGetConfig: () => request('GET', '/ai/config'),
  aiUpdateConfig: (config) => request('PUT', '/ai/config', config),
  aiTestConnection: (providerType, config) => request('POST', '/ai/config/test', { provider_type: providerType, config }),
  aiGetProviders: () => request('GET', '/ai/providers'),
  // AI LLM 多配置管理
  aiGetModelConfigs: () => request('GET', '/ai/model-configs'),
  aiCreateModelConfig: (data) => request('POST', '/ai/model-configs', data),
  aiUpdateModelConfig: (id, data) => request('PUT', `/ai/model-configs/${id}`, data),
  aiDeleteModelConfig: (id) => request('DELETE', `/ai/model-configs/${id}`),
  aiSetDefaultModelConfig: (id) => request('PUT', `/ai/model-configs/${id}/default`),
  aiToggleModelConfig: (id) => request('PUT', `/ai/model-configs/${id}/toggle`),
  aiSwitchModelConfig: (id) => request('POST', `/ai/model-configs/switch?config_id=${id}`),
  // AI 使用量统计
  aiGetUsageStats: (days = 30) => request('GET', `/ai/usage/stats?days=${days}`),
  aiGetUsageLogs: (limit = 100, offset = 0) => request('GET', `/ai/usage/logs?limit=${limit}&offset=${offset}`),
  // AI 会话管理
  aiListSessions: (limit = 20) => request('GET', `/ai/sessions?limit=${limit}`),
  aiGetSession: (sessionId) => request('GET', `/ai/sessions/${sessionId}`),
  aiClearSession: (sessionId) => request('DELETE', `/ai/sessions/${sessionId}`),
  // AI 语音识别（本地 Whisper，上传音频返回文本）
  aiSpeechToText: async (audioBlob, language = 'zh') => {
    const formData = new FormData();
    formData.append('audio', audioBlob, 'speech.webm');
    formData.append('language', language);
    const token = getToken();
    const res = await fetch(BASE + '/ai/speech-to-text', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || err.error || `HTTP ${res.status}`);
    }
    return res.json();
  },
  aiSpeechStatus: () => request('GET', '/ai/speech/status'),

  // OHT API
  getOHTPositions: () => request('GET', '/oht'),
  getOHTHistory: (ohtId) => request('GET', `/oht/${ohtId}`),

  // 配方API
  getRecipes: (machineId) => request('GET', `/recipes?machine_id=${machineId}`),
  getRecipe: (recipeId) => request('GET', `/recipes/${recipeId}`),

  // 楼层API
  getFloors: () => request('GET', '/floors'),
  getFloor: (floorId) => request('GET', `/floors/${floorId}`),
  getFloorMachines: (floorId) => request('GET', `/floors/${floorId}/machines`),
  addFloorMachine: (floorId, data) => request('POST', `/floors/${floorId}/machines`, data),
  addFloorArea: (floorId, data) => request('POST', `/floors/${floorId}/areas`, data),
  updateFloorArea: (floorId, areaId, data) => request('PUT', `/floors/${floorId}/areas/${areaId}`, data),
  deleteFloorArea: (floorId, areaId) => request('DELETE', `/floors/${floorId}/areas/${areaId}`),
  deleteFloorMachine: (floorId, machineId) => request('DELETE', `/floors/${floorId}/machines/${machineId}`),
  updateMachinePosition: (floorId, machineId, position) => request('PUT', `/floors/${floorId}/machines/${machineId}/position`, position),
  importFloorPlan: (data) => request('POST', '/floors/import', data),
  exportFloorPlan: (floorId) => request('GET', `/floors/export/${floorId}`),
  // 天车轨迹
  addTrack: (floorId, data) => request('POST', `/floors/${floorId}/tracks`, data),
  updateTrack: (floorId, trackId, data) => request('PUT', `/floors/${floorId}/tracks/${trackId}`, data),
  deleteTrack: (floorId, trackId) => request('DELETE', `/floors/${floorId}/tracks/${trackId}`),
  // 天车
  addVehicle: (floorId, data) => request('POST', `/floors/${floorId}/vehicles`, data),
  updateVehicle: (floorId, vehicleId, data) => request('PUT', `/floors/${floorId}/vehicles/${vehicleId}`, data),
  deleteVehicle: (floorId, vehicleId) => request('DELETE', `/floors/${floorId}/vehicles/${vehicleId}`),

  // 机台型号配置API
  getModels: () => request('GET', '/models'),
  getModel: (modelId) => request('GET', `/models/${modelId}`),
  createModel: (data) => request('POST', '/models', data),
  updateModel: (modelId, data) => request('PUT', `/models/${modelId}`, data),
  deleteModel: (modelId) => request('DELETE', `/models/${modelId}`),
  duplicateModel: (modelId, data) => request('POST', `/models/${modelId}/duplicate`, data),
  // 事件动作映射
  getEventActions: (modelId) => request('GET', `/models/${modelId}/event-actions`),
  createEventAction: (modelId, data) => request('POST', `/models/${modelId}/event-actions`, data),
  updateEventAction: (modelId, mappingId, data) => request('PUT', `/models/${modelId}/event-actions/${mappingId}`, data),
  deleteEventAction: (modelId, mappingId) => request('DELETE', `/models/${modelId}/event-actions/${mappingId}`),

  // 历史回放API
  getHistory: (toolId, params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request('GET', `/history/${toolId}?${qs}`);
  },
  getHistoryTimeline: (toolId, date) => request('GET', `/history/${toolId}/timeline?date=${date}`),
  getAlarmHistory: (toolId, params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request('GET', `/history/${toolId}/alarms?${qs}`);
  },
  getEventDetail: (toolId, rawId) => request('GET', `/history/${toolId}/events/${rawId}`),

  // 认证API
  login: () => request('POST', '/auth/login', null, false),
  loginWithPassword: (username, password) => request('POST', '/auth/login-password', { username, password }, false),
  loginWindows: (username) => request('POST', '/auth/login-windows', { username }, false),
  // 通过ASP获取Windows用户名（仅IIS模式有效；直连模式返回fallback让前端走密码登录）
  getWindowsUser: async () => {
    try {
      const res = await fetch('/get_user.asp', { method: 'GET', credentials: 'include' });
      if (!res.ok) throw new Error(`ASP error: ${res.status}`);
      const ct = res.headers.get('content-type') || '';
      if (!ct.includes('application/json')) {
        throw new Error('ASP returned non-JSON (likely HTML 404 in direct mode)');
      }
      return res.json();
    } catch (e) {
      // 直连模式无 ASP/JSON，提示用户使用密码登录
      return { success: false, username: '', error: e.message };
    }
  },
  getUserInfo: () => request('GET', '/auth/user'),
  getPermissions: () => request('GET', '/auth/permissions'),
  checkPermission: (permId) => request('GET', `/auth/check/${permId}`),
  getMachineMapping: (machineId) => request('GET', `/auth/machine/${machineId}`),

  // 用户管理API（admin专用）
  getUsers: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request('GET', `/users?${qs}`);
  },
  createUser: (data) => request('POST', '/users', data),
  getUserDetail: (id) => request('GET', `/users/${id}`),
  updateUser: (id, data) => request('PUT', `/users/${id}`, data),
  deleteUser: (id) => request('DELETE', `/users/${id}`),
  resetUserPassword: (id, data) => request('PUT', `/users/${id}/password`, data),

  // 角色管理API
  getRoles: () => request('GET', '/roles'),
  createRole: (data) => request('POST', '/roles', data),
  updateRole: (id, data) => request('PUT', `/roles/${id}`, data),
  deleteRole: (id) => request('DELETE', `/roles/${id}`),
  getRolePermissions: (id) => request('GET', `/roles/${id}/permissions`),
  updateRolePermissions: (id, permIds) => request('PUT', `/roles/${id}/permissions`, { permission_ids: permIds }),

  // 权限管理API
  getAllPermissions: () => request('GET', '/permissions'),
};

export default api;
