// API models 域：机台型号配置与事件动作映射（批次3拆分）
import { request } from './core.js';

export const modelsApi = {
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
};
