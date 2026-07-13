// API请求封装
const BASE = '/api';

async function request(method, path, data = null) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (data && method !== 'GET' && method !== 'DELETE') opts.body = JSON.stringify(data);
  const res = await fetch(BASE + path, opts);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
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
};

export default api;
