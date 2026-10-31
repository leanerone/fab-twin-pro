// API 请求入口（批次3重组：request 封装在 core.js，端点按域拆分；本文件保持 { api } 默认导出不变，
// 全部消费方 import { api } from '@/api' 无需任何改动）
import { machinesApi } from './machines.js';
import { historyApi } from './history.js';
import { aiApi } from './ai.js';
import { floorsApi } from './floors.js';
import { modelsApi } from './models.js';
import { uploadsApi } from './uploads.js';
import { authApi } from './auth.js';

export const api = {
  ...machinesApi,
  ...historyApi,
  ...aiApi,
  ...floorsApi,
  ...modelsApi,
  ...uploadsApi,
  ...authApi,
};

export default api;
export { request, getToken, BASE } from './core.js';
