// API uploads 域：模型文件上传管理（批次3拆分）
import { request, getToken, BASE } from './core.js';

export const uploadsApi = {
  // 模型文件上传API
  uploadModelFile: async (file, modelId, uploadedBy = 'admin') => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('model_id', modelId);
    formData.append('uploaded_by', uploadedBy);
    const token = getToken();
    const res = await fetch(BASE + '/uploads/models', {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  },
  getModelFiles: (modelId) => request('GET', `/uploads/models?model_id=${modelId || ''}`),
  deleteModelFile: (fileId, modelId) => request('DELETE', `/uploads/models/${fileId}?model_id=${modelId}`),
  extractSvgParts: (modelId) => request('POST', `/uploads/models/${modelId}/extract-svg-parts`),
  validateModelDraft: (data) => request('POST', '/uploads/models/validate-draft', data),
};
