// API floors 域：楼层布局 / 区域 / 轨道 / 天车（批次3拆分）
import { request } from './core.js';

export const floorsApi = {
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
  updateFloorMachine: (floorId, machineId, data) => request('PUT', `/floors/${floorId}/machines/${machineId}`, data),
  importFloorPlan: (data) => request('POST', '/floors/import', data),
  exportFloorPlan: (floorId) => request('GET', `/floors/export/${floorId}`),
  // 平面图层级操作（D 批）
  cloneFloorAreas: (floorId, areaIds, offset = { x: 3, y: 3 }) => request('POST', `/floors/${floorId}/areas/batch-clone`, { area_ids: areaIds, offset_x: offset.x, offset_y: offset.y }),
  cloneFloorMachines: (floorId, machineIds, offset = { x: 3, y: 3 }) => request('POST', `/floors/${floorId}/machines/batch-clone`, { machine_ids: machineIds, offset_x: offset.x, offset_y: offset.y }),
  reorderFloorArea: (floorId, areaId, action) => request('POST', `/floors/${floorId}/areas/reorder`, { area_id: areaId, action }),
  reorderFloorMachine: (floorId, machineId, action) => request('POST', `/floors/${floorId}/machines/reorder`, { machine_id: machineId, action }),
  // 天车轨迹
  addTrack: (floorId, data) => request('POST', `/floors/${floorId}/tracks`, data),
  updateTrack: (floorId, trackId, data) => request('PUT', `/floors/${floorId}/tracks/${trackId}`, data),
  deleteTrack: (floorId, trackId) => request('DELETE', `/floors/${floorId}/tracks/${trackId}`),
  // 天车
  addVehicle: (floorId, data) => request('POST', `/floors/${floorId}/vehicles`, data),
  updateVehicle: (floorId, vehicleId, data) => request('PUT', `/floors/${floorId}/vehicles/${vehicleId}`, data),
  deleteVehicle: (floorId, vehicleId) => request('DELETE', `/floors/${floorId}/vehicles/${vehicleId}`),
};
