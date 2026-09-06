/**
 * 术语库 + 翻译记忆库 REST 客户端。
 *
 * 对应后端端点：
 * - GET    /api/v1/glossary              读取术语库
 * - POST   /api/v1/glossary              新增术语条目
 * - DELETE /api/v1/glossary/{id}         删除术语条目
 * - DELETE /api/v1/glossary              清空术语库
 * - POST   /api/v1/glossary/import       导入（JSON 数组 / CSV 文本）
 * - GET    /api/v1/translation-memory    翻译记忆库统计（V5.3）
 * - POST   /api/v1/translation-memory/clear  清空翻译记忆库
 *
 * 端点地址与 WebSocket 同源推导（复用运行时 wsUrl 的 host/port），
 * 保证桌面启动器注入的随机端口也能正确访问。
 */

import {
  DEFAULT_BACKEND_HOST,
  DEFAULT_BACKEND_PORT,
  getRuntimeWebSocketUrlFromSearch,
  resolveWebSocketBaseUrl,
} from '../network/ws-url'


export interface GlossaryEntryItem {
  id: string
  source: string
  target: string
  keep_original: boolean
}


export interface GlossarySnapshot {
  path: string
  size: number
  entries: GlossaryEntryItem[]
}


export interface GlossaryPayload {
  success: boolean
  reason: string
  glossary?: GlossarySnapshot
  entry?: GlossaryEntryItem
  imported?: number
  cleared?: number
}


export interface TranslationMemoryStats {
  size: number
  hits: number
  misses: number
  written: number
  sessions: string[]
  threshold: number
  /** V5.3 生产化：跨会话持久化存储统计（persisted=false 表示未初始化）。 */
  store?: {
    persisted: boolean
    size: number
    pairs: number
    by_pair: Record<string, number>
  }
}


export interface TranslationMemoryEntry {
  source: string
  translated: string
  language_pair: string
  created_at: number
}


export interface TranslationMemoryPayload {
  success: boolean
  reason: string
  stats?: TranslationMemoryStats | null
  cleared?: number
  store_cleared?: number
  entries?: TranslationMemoryEntry[]
  size?: number
}


const API_BASE_PATH = '/api/v1'


/**
 * 解析 REST 端点地址（与 WebSocket 同源，仅本机回环）。
 *
 * @param path 端点路径（如 /glossary）。
 * @param search 可选的运行时 URL 查询串（桌面启动器注入 wsUrl）。
 * @returns 形如 http://127.0.0.1:8000/api/v1/glossary 的端点。
 */
export function resolveApiEndpoint(path: string, search?: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const locationSearch = search ?? (typeof window === 'undefined' ? '' : window.location.search)
  const runtimeUrl = getRuntimeWebSocketUrlFromSearch(locationSearch)
  const runtimeApiUrl = createApiUrlFromWebSocketUrl(runtimeUrl, normalizedPath)
  if (runtimeApiUrl) {
    return runtimeApiUrl
  }

  const base = resolveWebSocketBaseUrl()
  const { hostname, port } = parseWsBaseUrl(base)
  return `http://${hostname}:${port ?? DEFAULT_BACKEND_PORT}${API_BASE_PATH}${normalizedPath}`
}


/**
 * 由运行时 WebSocket URL 推导 REST 端点（仅接受本机回环主机）。
 *
 * @param value 运行时 WebSocket URL（如 ws://127.0.0.1:49321/api/v1/ws/translate/{id}）。
 * @param path 端点路径（如 /glossary）。
 * @returns 合法的 REST 端点；输入非法或主机不在白名单时返回 null。
 */
export function createApiUrlFromWebSocketUrl(
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
): Promise<GlossaryPayload | TranslationMemoryPayload | null> {
  const fetcher = options.fetcher ?? getDefaultFetcher()
  if (!fetcher) {
    return null
  }

  const endpoint = options.endpoint ?? resolveApiEndpoint(path)
  try {
    const response = await fetcher(endpoint, {
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      ...init,
    })
    if (!response.ok) {
      return null
    }
    return (await response.json()) as GlossaryPayload | TranslationMemoryPayload
  } catch {
    return null
  }
}


/** 读取术语库。 */
export async function fetchGlossary(
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<GlossarySnapshot | null> {
  const payload = await requestJson('/glossary', { method: 'GET' }, options) as GlossaryPayload | null
  return payload?.success ? (payload.glossary ?? null) : null
}


/** 新增术语条目。 */
export async function addGlossaryEntry(
  entry: { source: string; target: string; keep_original?: boolean },
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<GlossaryEntryItem | null> {
  const payload = await requestJson('/glossary', {
    method: 'POST',
    body: JSON.stringify(entry),
  }, options) as GlossaryPayload | null
  return payload?.success ? (payload.entry ?? null) : null
}


/** 删除术语条目。 */
export async function deleteGlossaryEntry(
  entryId: string,
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<boolean> {
  const payload = await requestJson(`/glossary/${encodeURIComponent(entryId)}`, {
    method: 'DELETE',
  }, options) as GlossaryPayload | null
  return payload?.success ?? false
}


/** 清空术语库。 */
export async function clearGlossary(
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<number> {
  const payload = await requestJson('/glossary', {
    method: 'DELETE',
  }, options) as GlossaryPayload | null
  return payload?.cleared ?? 0
}


/**
 * 导入术语表。
 *
 * @param content 文件内容（JSON 数组 / {"entries": [...]} / CSV 文本）。
 * @param filename 文件名（按扩展名选择 JSON/CSV 解析）。
 */
export async function importGlossary(
  filename: string,
  content: string,
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<number> {
  const normalized = filename.trim().toLowerCase()
  const isCsv = normalized.endsWith('.csv')
  const body = isCsv ? { csv: content } : { entries: tryParseGlossaryJson(content) }
  const payload = await requestJson('/glossary/import', {
    method: 'POST',
    body: JSON.stringify(body),
  }, options) as GlossaryPayload | null
  return payload?.imported ?? 0
}


/** 读取翻译记忆库统计。 */
export async function fetchTranslationMemoryStats(
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<TranslationMemoryStats | null> {
  const payload = await requestJson('/translation-memory', { method: 'GET' }, options) as TranslationMemoryPayload | null
  return payload?.success ? (payload.stats ?? null) : null
}


/** 清空翻译记忆库（活跃会话 + 跨会话持久化存储）。 */
export async function clearTranslationMemory(
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<number> {
  const payload = await requestJson('/translation-memory/clear', {
    method: 'POST',
  }, options) as TranslationMemoryPayload | null
  return payload?.cleared ?? 0
}


/** 读取跨会话持久化翻译记忆库句对列表（V5.3 生产化）。 */
export async function fetchTranslationMemoryEntries(
  options: {
    fetcher?: (input: string, init?: RequestInit) => Promise<Response>
    endpoint?: string
    languagePair?: string
  } = {},
): Promise<TranslationMemoryEntry[] | null> {
  const query = options.languagePair
    ? `?language_pair=${encodeURIComponent(options.languagePair)}`
    : ''
  const payload = await requestJson(
    `/translation-memory/entries${query}`,
    { method: 'GET' },
    options,
  ) as TranslationMemoryPayload | null
  return payload?.success ? (payload.entries ?? null) : null
}


/** 尝试把文本解析为 JSON 术语表；失败返回空数组（服务端会给出错误）。 */
function tryParseGlossaryJson(content: string): Array<Record<string, unknown>> {
  try {
    const raw = JSON.parse(content) as unknown
    const candidates = Array.isArray(raw)
      ? raw
      : typeof raw === 'object' && raw !== null && Array.isArray((raw as { entries?: unknown }).entries)
        ? (raw as { entries: Array<Record<string, unknown>> }).entries
        : []
    return Array.isArray(candidates) ? candidates as Array<Record<string, unknown>> : []
  } catch {
    return []
  }
}
