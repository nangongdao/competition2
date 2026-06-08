export const DEFAULT_BACKEND_HOST = '127.0.0.1'
export const DEFAULT_BACKEND_PORT = 8000
export const RUNTIME_WS_URL_QUERY_PARAM = 'wsUrl'


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


function normalizeWebSocketUrl(value: string | null | undefined): string | null {
  const trimmed = value?.trim() ?? ''
  if (trimmed.length === 0) {
    return null
  }
  return trimmed.replace(/\/+$/, '')
}


function normalizeHostname(value: string | null | undefined): string | null {
  const trimmed = value?.trim() ?? ''
  return trimmed.length > 0 ? trimmed : null
}
