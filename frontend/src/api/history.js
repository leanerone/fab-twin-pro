// API history 域：历史回放（批次3拆分）
import { request } from './core.js';

export const historyApi = {
  // 历史回放API
  getHistory: (toolId, params = {}, signal = null) => {
    const qs = new URLSearchParams(params).toString();
    return request('GET', `/history/${toolId}?${qs}`, null, true, { signal });
  },
  getHistoryTimeline: (toolId, date) => request('GET', `/history/${toolId}/timeline?date=${date}`),
  getAlarmHistory: (toolId, params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request('GET', `/history/${toolId}/alarms?${qs}`);
  },
  getEventDetail: (toolId, rawId) => request('GET', `/history/${toolId}/events/${rawId}`),
};
