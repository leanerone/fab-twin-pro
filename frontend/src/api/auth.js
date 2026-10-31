// API auth 域：认证 / 用户 / 角色 / 权限（批次3拆分，平台内核）
import { request } from './core.js';

export const authApi = {
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
