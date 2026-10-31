// API 请求核心封装（批次3自 api/index.js 拆出，属平台公共文件）
const BASE = '/api';

function getToken() {
  return localStorage.getItem('fabtwin_token');
}

async function request(method, path, data = null, requireAuth = true, options = {}) {
  // test31 强化：
  // - 默认超时（GET 15s / 其他 120s）：此前裸 fetch 无超时，慢接口下 UI 永远 loading
  // - options.signal：调用方可用 AbortController 取消（快速切换机台/日期时旧请求
  //   不再乱序返回覆盖新数据）
  // - GET in-flight 去重：相同 GET 进行中时复用同一 Promise，重复点击不叠加请求
  const { signal = null } = options;
  const timeoutMs = options.timeoutMs != null ? options.timeoutMs
    : (method === 'GET' ? 15000 : 120000);
  const dedupeKey = method === 'GET' && !signal ? `GET ${path}` : null;
  if (dedupeKey && inflightGets.has(dedupeKey)) {
    return inflightGets.get(dedupeKey);
  }

  const exec = (async () => {
    const opts = {
      method,
      headers: { 'Content-Type': 'application/json' },
    };
    // 超时与外部 signal 合并到同一个控制器
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(new DOMException('request timeout', 'TimeoutError')), timeoutMs);
    const onOuterAbort = () => ctrl.abort(signal.reason);
    if (signal) {
      if (signal.aborted) ctrl.abort(signal.reason);
      else signal.addEventListener('abort', onOuterAbort);
    }
    opts.signal = ctrl.signal;

    try {
      if (requireAuth) {
        const token = getToken();
        if (token) {
          opts.headers.Authorization = `Bearer ${token}`;
        } else {
          const currentHash = window.location.hash;
          if (!currentHash.includes('/login')) {
            window.location.hash = '#/login';
          }
          throw new Error('No token available');
        }
      }
      if (data && method !== 'GET' && method !== 'DELETE') opts.body = JSON.stringify(data);
      const res = await fetch(BASE + path, opts);
      if (!res.ok) {
        if (res.status === 401) {
          const token = getToken();
          if (token) {
            localStorage.removeItem('fabtwin_token');
          }
          const currentHash = window.location.hash;
          if (!currentHash.includes('/login')) {
            window.location.hash = '#/login';
          }
        }
        // 尝试从响应体提取 detail 消息（FastAPI 错误格式 {detail: "..."}）
        let detail = '';
        try {
          const errBody = await res.json();
          detail = errBody.detail || errBody.message || errBody.error || '';
        } catch (_) {
          try { detail = await res.text(); } catch (_) {}
        }
        throw new Error(detail ? `${detail}` : `API error: ${res.status}`);
      }
      return res.json();
    } finally {
      clearTimeout(timer);
      if (signal) signal.removeEventListener('abort', onOuterAbort);
    }
  })();

  if (dedupeKey) {
    inflightGets.set(dedupeKey, exec);
    exec.catch(() => {}).finally(() => inflightGets.delete(dedupeKey));
  }
  return exec;
}

// GET 进行中请求表（同 URL 复用）
const inflightGets = new Map();

export { request, getToken, BASE };
