// API auth 域：认证 / 用户 / 角色 / 权限（批次3拆分，平台内核）
import { request } from './core.js';

export const authApi = {
  // 认证API
  login: () => request('POST', '/auth/login', null, false),
  loginWithPassword: (username, password) => request('POST', '/auth/login-password', { username, password }, false),
  // Windows 身份由受信 IIS 在服务端注入，前端不提交或预取用户名
  loginWindows: () => request('POST', '/auth/login-windows', null, false),
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
