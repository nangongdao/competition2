/**
 * 商用成本模型 REST 客户端（成本估算 + 用量计量 + 熔断建议）。
 *
 * 对应后端端点：
 * - GET  /api/v1/cost          获取成本概览
 * - POST /api/v1/cost/reset    清空累计用量
 *
 * 端点地址与 WebSocket 同源推导（复用运行时 wsUrl 的 host/port）。
 */

import {
  DEFAULT_BACKEND_HOST,
  DEFAULT_BACKEND_PORT,
  getRuntimeWebSocketUrlFromSearch,
  resolveWebSocketBaseUrl,
} from '../network/ws-url'


export interface CostUsageSnapshot {
  nmt_input_tokens: number
  nmt_output_tokens: number
  asr_seconds: number
  tts_chars: number
}


export interface CostOverview {
  success: boolean
  reason: string
  total_sessions: number
  usage: CostUsageSnapshot
  today: CostUsageSnapshot
  total_cost_usd: number
  total_cost_cny: number
  today_cost_usd: number
  today_cost_cny: number
  daily_cost_limit_usd: number
  daily_nmt_call_limit: number
  suggestions: string[]
  prices: {
    nmt_input_per_m: number
    nmt_output_per_m: number
    asr_per_minute: number
    tts_per_k_chars: number
  }
  token_estimate_note: string
}


const API_BASE_PATH = '/api/v1'


/** 解析成本 REST 端点（与 WebSocket 同源，仅本机回环）。 */
export function resolveCostEndpoint(path: string, search?: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const locationSearch = search ?? (typeof window === 'undefined' ? '' : window.location.search)
  const runtimeUrl = getRuntimeWebSocketUrlFromSearch(locationSearch)
  const runtimeApiUrl = createCostApiUrlFromWebSocketUrl(runtimeUrl, normalizedPath)
  if (runtimeApiUrl) {
    return runtimeApiUrl
  }

  const base = resolveWebSocketBaseUrl()
  const { hostname, port } = parseWsBaseUrl(base)
  return `http://${hostname}:${port ?? DEFAULT_BACKEND_PORT}${API_BASE_PATH}${normalizedPath}`
}


/**
 * 由运行时 WebSocket URL 推导成本 REST 端点（仅接受本机回环主机）。
 */
export function createCostApiUrlFromWebSocketUrl(
  value: string | null | undefined,
  path: string,
): string | null {
  const trimmedValue = value?.trim() ?? ''
  if (!trimmedValue) {
    return null
  }

  try {
    const url = new URL(trimmedValue)
    if (url.protocol !== 'ws:' && url.protocol !== 'wss:') {
      return null
    }
    const hostname = url.hostname.replace(/^\[|\]$/g, '').toLowerCase()
    if (hostname !== '127.0.0.1' && hostname !== 'localhost' && hostname !== '::1') {
      return null
    }

    url.protocol = url.protocol === 'wss:' ? 'https:' : 'http:'
    url.pathname = `${API_BASE_PATH}${path.startsWith('/') ? path : `/${path}`}`
    url.search = ''
    url.hash = ''
    return url.toString()
  } catch {
    return null
  }
}


function parseWsBaseUrl(base: string): { hostname: string; port: string | null } {
  try {
    const url = new URL(base)
    return { hostname: url.hostname, port: url.port || null }
  } catch {
    return { hostname: DEFAULT_BACKEND_HOST, port: String(DEFAULT_BACKEND_PORT) }
  }
}


function getDefaultFetcher(): ((input: string, init?: RequestInit) => Promise<Response>) | null {
  if (typeof globalThis.fetch !== 'function') {
    return null
  }
  return globalThis.fetch.bind(globalThis)
}


async function requestJson(
  path: string,
  init: RequestInit,
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<CostOverview | null> {
  const fetcher = options.fetcher ?? getDefaultFetcher()
  if (!fetcher) {
    return null
  }

  const endpoint = options.endpoint ?? resolveCostEndpoint(path)
  try {
    const response = await fetcher(endpoint, {
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      ...init,
    })
    if (!response.ok) {
      return null
    }
    return (await response.json()) as CostOverview
  } catch {
    return null
  }
}


/** 获取成本概览。 */
export async function fetchCostOverview(
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<CostOverview | null> {
  const payload = await requestJson('/cost', { method: 'GET' }, options)
  return payload?.success ? payload : null
}


/** 清空累计用量。 */
export async function resetCostUsage(
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<CostOverview | null> {
  const payload = await requestJson('/cost/reset', { method: 'POST' }, options)
  return payload?.success ? payload : null
}
