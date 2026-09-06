import type { UiText } from '../i18n'
import { resolveWebSocketBaseUrl } from '../network/ws-url'

/**
 * 会话历史台账 API 客户端（ROADMAP Phase 10 数据生命周期）。
 *
 * 与后端 REST 端点同源（复用 WebSocket host/port），仅本机回环可访问。
 */

export interface SessionQualityMetrics {
  asr_segments: number
  translation_segments: number
  revision_segments: number
  audio_chunks_received: number
  audio_chunks_dropped: number
  audio_queue_max_depth: number
  audio_queue_capacity: number
  reconnect_count: number
  latency: Record<string, { count: number; avg_ms: number; max_ms: number }>
  api_call_counts: Record<string, number>
}

export interface SessionHistoryRecord {
  session_id: string
  started_at: number
  updated_at: number
  segment_count: number
  duration_ms: number
  /** 阶段 10 可观测性补全：会话质量指标（旧记录可能缺失）。 */
  quality?: SessionQualityMetrics | null
}

export interface SessionHistoryStats {
  total_sessions: number
  total_segments: number
  retention_seconds: number
}

export interface SessionHistoryResponse {
  success: boolean
  reason?: string
  sessions?: SessionHistoryRecord[]
  stats?: SessionHistoryStats
}

export interface SessionHistoryDeleteResponse {
  success: boolean
  reason?: string
  cleared?: number
  purged?: number
}

const HISTORY_PATH = '/api/v1/session-history'

function getHistoryBaseUrl(): string {
  // 与 WebSocket 同源推导后端地址（桌面启动器注入随机端口也能正确访问）
  const wsBase = resolveWebSocketBaseUrl()
  const scheme = wsBase.startsWith('wss://') ? 'https://' : 'http://'
  const hostPort = wsBase.replace(/^wss?:\/\//, '').split('/')[0]
  return `${scheme}${hostPort}`
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${getHistoryBaseUrl()}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    throw new Error(`Session history request failed: ${response.status}`)
  }
  return (await response.json()) as T
}

/** 获取会话历史台账。 */
export async function fetchSessionHistory(limit = 100): Promise<SessionHistoryResponse> {
  return requestJson<SessionHistoryResponse>(`${HISTORY_PATH}?limit=${limit}`)
}

/** 删除单个会话记录。 */
export async function deleteSessionHistory(sessionId: string): Promise<SessionHistoryDeleteResponse> {
  return requestJson<SessionHistoryDeleteResponse>(
    `${HISTORY_PATH}/${encodeURIComponent(sessionId)}`,
    { method: 'DELETE' },
  )
}

/** 清空全部会话记录（隐私控制）。 */
export async function clearSessionHistory(): Promise<SessionHistoryDeleteResponse> {
  return requestJson<SessionHistoryDeleteResponse>(HISTORY_PATH, { method: 'DELETE' })
}

/** 手动触发过期会话清理。 */
export async function purgeSessionHistory(): Promise<SessionHistoryDeleteResponse> {
  return requestJson<SessionHistoryDeleteResponse>(`${HISTORY_PATH}/purge`, { method: 'POST' })
}

/** 格式化会话时长（毫秒 → 可读文本）。 */
export function formatSessionDuration(durationMs: number, text: UiText): string {
  const seconds = Math.round(durationMs / 1000)
  if (seconds < 60) {
    return `${seconds}${text.history.sessionSeconds}`
  }
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return rest > 0 ? `${minutes}${text.history.sessionMinutes} ${rest}${text.history.sessionSeconds}` : `${minutes}${text.history.sessionMinutes}`
}

/** 格式化开始时间戳（本地时间）。 */
export function formatSessionStartedAt(timestamp: number): string {
  const date = new Date(timestamp * 1000)
  const pad = (value: number): string => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}
