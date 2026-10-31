// API ai 域：AI 对话 / 流式 / 配置 / 机台Dify路由 / 用量 / 语音（批次3拆分）
import { request, getToken, BASE } from './core.js';

export const aiApi = {
  // AI API
  aiQuery: (question, machineId) => request('POST', '/ai/query', { question, machine_id: machineId }),
  // AI 统一聊天接口
  aiChat: (data) => request('POST', '/ai/chat', data),
  // AI 流式聊天（SSE，T4）：fetch + ReadableStream 解析（EventSource 不支持 POST/自定义头）
  // handlers: { onChunk(text), onThought(evt), onFinal(evt), onError(err) }
  aiChatStream: async (data, handlers = {}) => {
    const token = getToken();
    if (!token) {
      const currentHash = window.location.hash;
      if (!currentHash.includes('/login')) window.location.hash = '#/login';
      throw new Error('No token available');
    }
    const res = await fetch(BASE + '/ai/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      if (res.status === 401) {
        localStorage.removeItem('fabtwin_token');
        const currentHash = window.location.hash;
        if (!currentHash.includes('/login')) window.location.hash = '#/login';
      }
      let detail = '';
      try {
        const errBody = await res.json();
        detail = errBody.detail || errBody.message || errBody.error || '';
      } catch (_) {
        try { detail = await res.text(); } catch (_) {}
      }
      throw new Error(detail ? `${detail}` : `API error: ${res.status}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buf = '';
    // 终端帧追踪：流结束（done）时若没收到过 final/error/[DONE]，
    // 说明后端生成器异常中断（或反代悬死），必须主动 onError 让 UI 复位，
    // 否则前端永远卡在"思考中"。
    let gotTerminal = false;
    // 读超时兜底：最后一次收到数据后超过 READ_TIMEOUT_MS 仍无新数据，
    // 判定连接悬死（IIS ARR 保持连接等超时的场景），主动 cancel + onError。
    const READ_TIMEOUT_MS = 180000;
    let readTimer = null;
    const resetReadTimer = () => {
      if (readTimer) clearTimeout(readTimer);
      readTimer = setTimeout(() => {
        try { reader.cancel(); } catch (_) {}
      }, READ_TIMEOUT_MS);
    };
    resetReadTimer();
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        resetReadTimer();
        buf += decoder.decode(value, { stream: true });
        let sep;
        while ((sep = buf.indexOf('\n\n')) >= 0) {
          const rawEvt = buf.slice(0, sep);
          buf = buf.slice(sep + 2);
          for (const line of rawEvt.split('\n')) {
            if (!line.startsWith('data:')) continue;
            const payload = line.slice(5).trim();
            if (!payload) continue;
            if (payload === '[DONE]') { gotTerminal = true; return; }
            let evt;
            try { evt = JSON.parse(payload); } catch (_) { continue; }
            const name = evt.event || '';
            if (name === 'agent_message' || name === 'message' || name === 'message_replace') {
              if (evt.answer) handlers.onChunk?.(evt.answer);
            } else if (name === 'agent_thought') {
              handlers.onThought?.(evt);
            } else if (name === 'final') {
              gotTerminal = true;
              handlers.onFinal?.(evt);
            } else if (name === 'error') {
              gotTerminal = true;
              handlers.onError?.(new Error(evt.message || '流式调用失败'));
            }
          }
        }
      }
      // 连接被异常取消（读超时）或服务器中断，且没收到任何终端帧
      if (!gotTerminal) {
        handlers.onError?.(new Error('流式响应中断（未收到结束帧），请重试'));
      }
    } catch (e) {
      if (!gotTerminal) {
        handlers.onError?.(new Error(e.message || '流式连接异常中断'));
      }
    } finally {
      if (readTimer) { clearTimeout(readTimer); readTimer = null; }
    }
  },
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

  // MCP Server (N8N) 配置（管理面板已登录，但不要求强鉴权跳转，保持与原裸 fetch 一致的行为）
  aiGetMcpConfig: () => request('GET', '/ai/mcp/config', null, false),
  aiSaveMcpConfig: (payload) => request('PUT', '/ai/mcp/config', payload, false),
  aiTestMcpConnection: () => request('POST', '/ai/mcp/test', null, false),
  // 机台专属 Dify 配置管理
  aiGetMachineDifyConfigs: () => request('GET', '/ai/machine-dify'),
  aiCreateMachineDifyConfig: (data) => request('POST', '/ai/machine-dify', data),
  aiUpdateMachineDifyConfig: (id, data) => request('PUT', `/ai/machine-dify/${id}`, data),
  aiDeleteMachineDifyConfig: (id) => request('DELETE', `/ai/machine-dify/${id}`),
  // 机台级AI路由诊断（前端显示AI来源用）
  aiGetMachineAiRouting: (machineId) => request('GET', `/ai/machine-routing/${encodeURIComponent(machineId)}`),
  // 切换全局AI（'dify' | 'llm_default'）—— 浮动球模型切换Dify全局入口
  aiSwitchGlobalAI: (target) => request('POST', '/ai/switch-global', { target }),
  // 机台专属Dify连接测试
  aiTestMachineDify: (config) => request('POST', '/ai/config/test', {
    provider_type: 'dify',
    config: {
      dify_enabled: true,
      dify_base_url: config.dify_base_url,
      dify_api_key: config.dify_api_key,
    },
  }),
  // AI 使用量统计
  aiGetUsageStats: (days = 30) => request('GET', `/ai/usage/stats?days=${days}`),
  aiGetUsageLogs: (params = {}) => {
    const qs = new URLSearchParams({ limit: params.limit || 100, offset: params.offset || 0 });
    if (params.start_date) qs.append('start_date', params.start_date);
    if (params.end_date) qs.append('end_date', params.end_date);
    if (params.provider) qs.append('provider', params.provider);
    if (params.success !== undefined && params.success !== null) qs.append('success', params.success);
    return request('GET', `/ai/usage/logs?${qs.toString()}`);
  },
  aiGetUsageLogDetail: (logId) => request('GET', `/ai/usage/logs/${logId}`),
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
};
