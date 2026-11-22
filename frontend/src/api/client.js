const API_BASE = '/api';
export async function api(path, options = {}) {
  const token = localStorage.getItem('campusToken');
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || '请求失败');
    error.status = response.status;
    throw error;
  }
  return data;
}
export const get = (path) => api(path);
export const post = (path, body) => api(path, { method: 'POST', body: JSON.stringify(body) });
export function postWithHeaders(path, body, headers) {
  return api(path, { method: 'POST', body: JSON.stringify(body), headers });
}

/**
 * 裁决回执丢失时按同一幂等键重试：后端不会重复记账，也不会覆盖后来作出的裁决。
 * 4xx 属于明确拒绝，直接抛出；网络中断、5xx 才进入重试。
 */
export async function postIdempotent(path, body, key, attempts = 3) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await postWithHeaders(path, body, { 'Idempotency-Key': key });
    } catch (error) {
      lastError = error;
      if (error.status && error.status < 500) throw error;
      if (attempt < attempts) await new Promise((resolve) => setTimeout(resolve, 150 * attempt));
    }
  }
  throw lastError;
}
