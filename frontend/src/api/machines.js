// API machines 域：机台 / 事件 / Lot / 告警 / OHT / 配方 / 消息调试（批次3拆分）
import { request } from './core.js';

export const machinesApi = {
  // 机台API
  getMachines: () => request('GET', '/machines'),
  getMachine: (id) => request('GET', `/machines/${id}`),
  getMachineStats: () => request('GET', '/machines/stats'),
  updateMachine: (id, payload) => request('PATCH', `/machines/${id}`, payload),
  deleteMachine: (id) => request('DELETE', `/machines/${id}`),
  updateMachineExternalLink: (id, payload) => request('PATCH', `/machines/${id}/external-link`, payload),

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

  // OHT API
  getOHTPositions: () => request('GET', '/oht'),
  getOHTHistory: (ohtId) => request('GET', `/oht/${ohtId}`),

  // 配方API
  getRecipes: (machineId) => request('GET', `/recipes?machine_id=${machineId}`),
  getRecipe: (recipeId) => request('GET', `/recipes/${recipeId}`),

  // 消息调试API（Motion2D 调试台：注入事件走真实轮询链路驱动动画）
  debugSendEvent: (data) => request('POST', '/debug/event', data),
};
