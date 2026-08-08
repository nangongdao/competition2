export const DEFAULT_BACKEND_HOST = '127.0.0.1'
export const DEFAULT_BACKEND_PORT = 8000
export const RUNTIME_WS_URL_QUERY_PARAM = 'wsUrl'

/** 允许的 WebSocket 主机（仅本机回环）。 */
const ALLOWED_WS_HOSTNAMES = new Set(['127.0.0.1', 'localhost', '::1'])


export interface WebSocketUrlOptions {
  runtimeUrl?: string | null
  configuredUrl?: string | null
  hostname?: string | null
}


export function resolveWebSocketBaseUrl(options: WebSocketUrlOptions = {}): string {
  const runtimeUrl = normalizeWebSocketUrl(options.runtimeUrl)
  if (runtimeUrl) {
    return runtimeUrl
  }

  const configuredUrl = normalizeWebSocketUrl(options.configuredUrl)
  if (configuredUrl) {
    return configuredUrl
  }

  const hostname = normalizeHostname(options.hostname) ?? DEFAULT_BACKEND_HOST
  return `ws://${hostname}:${DEFAULT_BACKEND_PORT}/api/v1/ws/translate`
}


export function getRuntimeWebSocketUrlFromSearch(search: string): string | null {
  const value = new URLSearchParams(search).get(RUNTIME_WS_URL_QUERY_PARAM)
  return normalizeWebSocketUrl(value)
}


/**
 * 归一化并校验 WebSocket URL。
 *
 * 运行时 URL 可能来自查询参数（不可信输入），必须限制协议为 ws/wss
 * 且主机为本机回环，否则可被诱导将音频流发送到攻击者服务器。
 *
 * @param value 待校验的 URL
 * @returns 合法时返回归一化 URL，否则返回 null
 */
function normalizeWebSocketUrl(value: string | null | undefined): string | null {
  const trimmed = value?.trim() ?? ''
  if (trimmed.length === 0) {
    return null
  }

  let parsed: URL
  try {
    parsed = new URL(trimmed)
  } catch {
    return null
  }

  if (parsed.protocol !== 'ws:' && parsed.protocol !== 'wss:') {
    return null
  }

  // 去掉 IPv6 字面量的方括号后比较
  const hostname = parsed.hostname.replace(/^\[|\]$/g, '').toLowerCase()
  if (!ALLOWED_WS_HOSTNAMES.has(hostname)) {
    return null
  }

  return trimmed.replace(/\/+$/, '')
}


function normalizeHostname(value: string | null | undefined): string | null {
  const trimmed = value?.trim() ?? ''
  return trimmed.length > 0 ? trimmed : null
}
