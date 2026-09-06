/**
 * 付费订阅与配额 REST 客户端（ROADMAP V5.5）。
 *
 * 对应后端端点：
 * - GET  /api/v1/subscription            获取订阅状态 + 套餐清单
 * - PUT  /api/v1/subscription            切换套餐（本地演示/评审）
 * - POST /api/v1/subscription/reset      重置当天配额用量
 *
 * 端点地址与 WebSocket 同源推导（复用运行时 wsUrl 的 host/port）。
 */

import {
  DEFAULT_BACKEND_HOST,
  DEFAULT_BACKEND_PORT,
  getRuntimeWebSocketUrlFromSearch,
  resolveWebSocketBaseUrl,
} from '../network/ws-url'


export interface SubscriptionPlan {
  key: string
  name: string
  name_en: string
  price: string
  daily_limit: number | null
  features: string[]
}


export interface SubscriptionSnapshot {
  plan: string
  plan_name: string
  plan_name_en: string
  price: string
  features: string[]
  daily_used: number
  daily_limit: number | null
  daily_remaining: number | null
  day_key: string
  updated_at: number
}


export interface SubscriptionPayload {
  success: boolean
  reason: string
  subscription?: SubscriptionSnapshot
  plans?: SubscriptionPlan[]
}


const API_BASE_PATH = '/api/v1'


/** 解析订阅 REST 端点（与 WebSocket 同源，仅本机回环）。 */
export function resolveSubscriptionEndpoint(path: string, search?: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const locationSearch = search ?? (typeof window === 'undefined' ? '' : window.location.search)
  const runtimeUrl = getRuntimeWebSocketUrlFromSearch(locationSearch)
  const runtimeApiUrl = createSubscriptionApiUrlFromWebSocketUrl(runtimeUrl, normalizedPath)
  if (runtimeApiUrl) {
    return runtimeApiUrl
  }

  const base = resolveWebSocketBaseUrl()
  const { hostname, port } = parseWsBaseUrl(base)
  return `http://${hostname}:${port ?? DEFAULT_BACKEND_PORT}${API_BASE_PATH}${normalizedPath}`
}


/**
 * 由运行时 WebSocket URL 推导订阅 REST 端点（仅接受本机回环主机）。
 */
export function createSubscriptionApiUrlFromWebSocketUrl(
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
): Promise<SubscriptionPayload | null> {
  const fetcher = options.fetcher ?? getDefaultFetcher()
  if (!fetcher) {
    return null
  }

  const endpoint = options.endpoint ?? resolveSubscriptionEndpoint(path)
  try {
    const response = await fetcher(endpoint, {
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      ...init,
    })
    if (!response.ok) {
      return null
    }
    return (await response.json()) as SubscriptionPayload
  } catch {
    return null
  }
}


/** 获取订阅状态与套餐清单。 */
export async function fetchSubscription(
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<{ subscription: SubscriptionSnapshot | null; plans: SubscriptionPlan[] } | null> {
  const payload = await requestJson('/subscription', { method: 'GET' }, options)
  if (!payload?.success) {
    return null
  }
  return {
    subscription: payload.subscription ?? null,
    plans: payload.plans ?? [],
  }
}


/** 切换套餐（本地演示/评审用）。 */
export async function updateSubscriptionPlan(
  plan: string,
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<SubscriptionSnapshot | null> {
  const payload = await requestJson('/subscription', {
    method: 'PUT',
    body: JSON.stringify({ plan }),
  }, options)
  return payload?.success ? (payload.subscription ?? null) : null
}


/** 重置当天配额用量。 */
export async function resetSubscriptionUsage(
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<SubscriptionSnapshot | null> {
  const payload = await requestJson('/subscription/reset', { method: 'POST' }, options)
  return payload?.success ? (payload.subscription ?? null) : null
}
