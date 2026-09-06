/**
 * 多人协作翻译 REST 客户端（ROADMAP V5.2）。
 *
 * 对应后端端点：
 * - GET    /api/v1/collaboration/rooms              列出协作房间
 * - POST   /api/v1/collaboration/rooms              创建协作房间
 * - GET    /api/v1/collaboration/rooms/{id}         获取房间详情（成员+协作修正）
 * - POST   /api/v1/collaboration/rooms/{id}/join    加入房间
 * - POST   /api/v1/collaboration/rooms/{id}/leave   离开房间（房主离开即销毁）
 * - POST   /api/v1/collaboration/rooms/{id}/revisions   提交协作修正
 * - DELETE /api/v1/collaboration/rooms/{id}/revisions   清空协作修正（仅房主）
 * - DELETE /api/v1/collaboration/rooms/{id}         销毁房间（仅房主）
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


export interface CollaborationMember {
  session_id: string
  name: string
  is_owner: boolean
  joined_at: number
  last_seen_at: number
}


export interface CollaborativeRevisionItem {
  room_id: string
  revision_id: number
  member_session_id: string
  member_name: string
  segment_id: string
  source_text: string
  new_text: string
  created_at: number
}


export interface CollaborationRoom {
  room_id: string
  owner_session_id: string
  title: string
  created_at: number
  last_active_at: number
  member_count: number
  members: CollaborationMember[]
  revision_count?: number
  revisions?: CollaborativeRevisionItem[]
}


export interface CollaborationPayload {
  success: boolean
  reason: string
  rooms?: CollaborationRoom[]
  room?: CollaborationRoom
  revision?: CollaborativeRevisionItem
  cleared?: number
}


const API_BASE_PATH = '/api/v1'


/** 解析协作 REST 端点（与 WebSocket 同源，仅本机回环）。 */
export function resolveCollaborationEndpoint(path: string, search?: string): string {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`
  const locationSearch = search ?? (typeof window === 'undefined' ? '' : window.location.search)
  const runtimeUrl = getRuntimeWebSocketUrlFromSearch(locationSearch)
  const runtimeApiUrl = createCollaborationApiUrlFromWebSocketUrl(runtimeUrl, normalizedPath)
  if (runtimeApiUrl) {
    return runtimeApiUrl
  }

  const base = resolveWebSocketBaseUrl()
  const { hostname, port } = parseWsBaseUrl(base)
  return `http://${hostname}:${port ?? DEFAULT_BACKEND_PORT}${API_BASE_PATH}${normalizedPath}`
}


/**
 * 由运行时 WebSocket URL 推导协作 REST 端点（仅接受本机回环主机）。
 */
export function createCollaborationApiUrlFromWebSocketUrl(
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
): Promise<CollaborationPayload | null> {
  const fetcher = options.fetcher ?? getDefaultFetcher()
  if (!fetcher) {
    return null
  }

  const endpoint = options.endpoint ?? resolveCollaborationEndpoint(path)
  try {
    const response = await fetcher(endpoint, {
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      ...init,
    })
    if (!response.ok) {
      return null
    }
    return (await response.json()) as CollaborationPayload
  } catch {
    return null
  }
}


/** 列出协作房间。 */
export async function fetchCollaborationRooms(
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<CollaborationRoom[] | null> {
  const payload = await requestJson('/collaboration/rooms', { method: 'GET' }, options)
  return payload?.success ? (payload.rooms ?? null) : null
}


/** 创建协作房间。 */
export async function createCollaborationRoom(
  ownerSessionId: string,
  title: string,
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<CollaborationRoom | null> {
  const payload = await requestJson('/collaboration/rooms', {
    method: 'POST',
    body: JSON.stringify({ ownerSessionId, title }),
  }, options)
  return payload?.success ? (payload.room ?? null) : null
}


/** 获取房间详情（含成员与协作修正）。 */
export async function fetchCollaborationRoom(
  roomId: string,
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<CollaborationRoom | null> {
  const payload = await requestJson(
    `/collaboration/rooms/${encodeURIComponent(roomId)}`,
    { method: 'GET' },
    options,
  )
  return payload?.success ? (payload.room ?? null) : null
}


/** 加入协作房间。 */
export async function joinCollaborationRoom(
  roomId: string,
  sessionId: string,
  name: string,
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<CollaborationRoom | null> {
  const payload = await requestJson(
    `/collaboration/rooms/${encodeURIComponent(roomId)}/join`,
    { method: 'POST', body: JSON.stringify({ sessionId, name }) },
    options,
  )
  return payload?.success ? (payload.room ?? null) : null
}


/** 离开协作房间（房主离开即销毁房间）。 */
export async function leaveCollaborationRoom(
  roomId: string,
  sessionId: string,
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<boolean> {
  const payload = await requestJson(
    `/collaboration/rooms/${encodeURIComponent(roomId)}/leave`,
    { method: 'POST', body: JSON.stringify({ sessionId, name: '' }) },
    options,
  )
  return payload?.success ?? false
}


/** 提交协作修正（提交后房间内全员可见）。 */
export async function submitCollaborationRevision(
  roomId: string,
  revision: { sessionId: string; segmentId: string; newText: string; sourceText?: string },
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<CollaborativeRevisionItem | null> {
  const payload = await requestJson(
    `/collaboration/rooms/${encodeURIComponent(roomId)}/revisions`,
    {
      method: 'POST',
      body: JSON.stringify({
        sessionId: revision.sessionId,
        segmentId: revision.segmentId,
        newText: revision.newText,
        sourceText: revision.sourceText ?? '',
      }),
    },
    options,
  )
  return payload?.success ? (payload.revision ?? null) : null
}


/** 清空协作修正（仅房主）。 */
export async function clearCollaborationRevisions(
  roomId: string,
  sessionId: string,
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<number> {
  const payload = await requestJson(
    `/collaboration/rooms/${encodeURIComponent(roomId)}/revisions?sessionId=${encodeURIComponent(sessionId)}`,
    { method: 'DELETE' },
    options,
  )
  return payload?.cleared ?? 0
}


/** 销毁协作房间（仅房主）。 */
export async function destroyCollaborationRoom(
  roomId: string,
  sessionId: string,
  options: { fetcher?: (input: string, init?: RequestInit) => Promise<Response>; endpoint?: string } = {},
): Promise<boolean> {
  const payload = await requestJson(
    `/collaboration/rooms/${encodeURIComponent(roomId)}?sessionId=${encodeURIComponent(sessionId)}`,
    { method: 'DELETE' },
    options,
  )
  return payload?.success ?? false
}
