// 所有请求的统一出口：超时、错误信封、网络错误都转成 ApiError。
const DEFAULT_TIMEOUT = 20000

export class ApiError extends Error {
  constructor(message, code = 'internal', status = 0) {
    super(message || '请求失败')
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

function buildUrl(path, query) {
  if (!query) return path
  const params = new URLSearchParams()
  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    params.set(key, String(value))
  })
  const qs = params.toString()
  if (!qs) return path
  return path + (path.includes('?') ? '&' : '?') + qs
}

async function parseEnvelope(resp) {
  const text = await resp.text()
  let payload = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch (e) {
    throw new ApiError('服务返回异常（HTTP ' + resp.status + '）', 'internal', resp.status)
  }
  if (!payload || payload.ok !== true) {
    const raw = payload && payload.error
    const message =
      typeof raw === 'string' ? raw : (raw && raw.message) || '请求失败（HTTP ' + resp.status + '）'
    const code = raw && typeof raw === 'object' ? raw.code || 'internal' : 'internal'
    throw new ApiError(message, code, resp.status)
  }
  return payload.data
}

export async function requestJSON(path, options = {}) {
  const { method = 'GET', query, body, timeout = DEFAULT_TIMEOUT } = options
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  const headers = {}
  let payload
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  try {
    let resp
    try {
      resp = await fetch(buildUrl(path, query), {
        method,
        headers,
        body: payload,
        cache: 'no-store',
        signal: controller.signal,
      })
    } catch (e) {
      if (e && e.name === 'AbortError') {
        throw new ApiError('请求超时，请稍后重试', 'timeout', 0)
      }
      throw new ApiError('无法连接本机服务，请确认系统正在运行', 'network', 0)
    }
    return await parseEnvelope(resp)
  } finally {
    clearTimeout(timer)
  }
}

export function getJSON(path, options = {}) {
  return requestJSON(path, options)
}

export function postJSON(path, body, options = {}) {
  return requestJSON(path, { ...options, method: 'POST', body: body === undefined ? {} : body })
}

export function deleteJSON(path, options = {}) {
  return requestJSON(path, { ...options, method: 'DELETE' })
}

// 原始字节上传（数据包恢复）
export async function postBinary(path, data, options = {}) {
  const { timeout = 180000 } = options
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    let resp
    try {
      resp = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: data,
        cache: 'no-store',
        signal: controller.signal,
      })
    } catch (e) {
      if (e && e.name === 'AbortError') {
        throw new ApiError('上传超时，请检查文件大小后重试', 'timeout', 0)
      }
      throw new ApiError('无法连接本机服务，请确认系统正在运行', 'network', 0)
    }
    return await parseEnvelope(resp)
  } finally {
    clearTimeout(timer)
  }
}
