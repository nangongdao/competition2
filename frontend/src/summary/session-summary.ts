/**
 * 会话学习摘要客户端。
 *
 * 对应后端 GET /api/v1/sessions/{session_id}/summary（ROADMAP 阶段 9 / AC-G7）。
 * 端点地址与 WebSocket 同源推导（复用运行时 wsUrl 的 host/port），
 * 保证桌面启动器注入的随机端口也能正确访问。
 */

import {
  DEFAULT_BACKEND_HOST,
  DEFAULT_BACKEND_PORT,
  getRuntimeWebSocketUrlFromSearch,
  resolveWebSocketBaseUrl,
} from '../network/ws-url'


export interface SessionKeyword {
  term: string
  count: number
  examples: string[]
}


export interface SessionSummary {
  session_id: string
  /** local：本地统计摘要；llm：LLM 增强摘要（要点 + 行动项）。 */
  mode: 'local' | 'llm'
  generated_at: number
  duration_seconds: number
  segment_count: number
  revision_count: number
  speaker_count: number
  keywords: SessionKeyword[]
  bullets: string[]
  action_items: string[]
}


export interface SummaryPayload {
  success: boolean
  reason: string
  summary: SessionSummary | null
}


const SUMMARY_API_PATH = '/api/v1/sessions'


/**
 * 解析会话摘要 REST 端点地址。
 *
 * @param sessionId 会话 ID（与 WebSocket 路径中的会话 ID 一致）。
 * @param search 可选的运行时 URL 查询串（桌面启动器注入 wsUrl）。
 * @returns 形如 http://127.0.0.1:8000/api/v1/sessions/{id}/summary 的端点。
 */
export function resolveSummaryEndpoint(sessionId: string, search?: string): string {
  const encoded = encodeURIComponent(sessionId)
  const locationSearch = search ?? (typeof window === 'undefined' ? '' : window.location.search)
  const runtimeWebSocketUrl = getRuntimeWebSocketUrlFromSearch(locationSearch)
  const runtimeApiUrl = createSummaryApiUrlFromWebSocketUrl(runtimeWebSocketUrl, encoded)
  if (runtimeApiUrl) {
    return runtimeApiUrl
  }

  // 无运行时 URL：回落到默认后端 host/port（与 WebSocket 默认一致）。
  const base = resolveWebSocketBaseUrl()
  const { hostname, port } = parseWsBaseUrl(base)
  return `http://${hostname}:${port ?? DEFAULT_BACKEND_PORT}${SUMMARY_API_PATH}/${encoded}/summary`
}


/**
 * 由运行时 WebSocket URL 推导摘要端点（仅接受本机回环主机）。
 *
 * @param value 运行时 WebSocket URL（如 ws://127.0.0.1:49321/api/v1/ws/translate/{id}）。
 * @param encodedSessionId 已编码的会话 ID。
 * @returns 合法的摘要端点；输入非法或主机不在白名单时返回 null。
 */
export function createSummaryApiUrlFromWebSocketUrl(
  value: string | null | undefined,
  encodedSessionId: string,
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
    const hostname = url.hostname.toLowerCase()
    if (hostname !== '127.0.0.1' && hostname !== 'localhost' && hostname !== '::1') {
      return null
    }

    url.protocol = url.protocol === 'wss:' ? 'https:' : 'http:'
    url.pathname = `${SUMMARY_API_PATH}/${encodedSessionId}/summary`
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


export interface FetchSummaryOptions {
  /** 是否尝试 LLM 增强摘要（默认 false，使用本地统计摘要）。 */
  useLlm?: boolean
  fetcher?: (input: string, init?: RequestInit) => Promise<Response>
  endpoint?: string
}


/**
 * 拉取会话学习摘要。
 *
 * @param sessionId 会话 ID。
 * @param options 可选配置。
 * @returns 会话摘要；会话不存在/服务不可用时返回 null。
 */
export async function fetchSessionSummary(
  sessionId: string,
  options: FetchSummaryOptions = {},
): Promise<SessionSummary | null> {
  if (!sessionId) {
    return null
  }

  const fetcher = options.fetcher ?? getDefaultFetcher()
  if (!fetcher) {
    return null
  }

  const endpoint = options.endpoint ?? resolveSummaryEndpoint(sessionId)
  const query = options.useLlm ? '?use_llm=true' : ''
  try {
    const response = await fetcher(`${endpoint}${query}`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) {
      return null
    }
    const payload = (await response.json()) as SummaryPayload
    return payload.success ? (payload.summary ?? null) : null
  } catch {
    return null
  }
}


function getDefaultFetcher(): ((input: string, init?: RequestInit) => Promise<Response>) | null {
  if (typeof globalThis.fetch !== 'function') {
    return null
  }
  return globalThis.fetch.bind(globalThis)
}


/**
 * 将摘要渲染为可复制的 Markdown 文本。
 *
 * @param summary 会话摘要。
 * @returns Markdown 文本。
 */
export function formatSummaryMarkdown(summary: SessionSummary): string {
  const lines = [
    '# AI Interpreter Session Summary',
    '',
    `Generated: ${new Date(summary.generated_at * 1000).toLocaleString()}`,
    `Session: ${summary.session_id}`,
    `Mode: ${summary.mode === 'llm' ? 'LLM enhanced' : 'local statistics'}`,
    `Duration: ${formatDuration(summary.duration_seconds)}`,
    `Segments: ${summary.segment_count}`,
    `Revisions: ${summary.revision_count}`,
    `Speakers: ${summary.speaker_count}`,
  ]

  if (summary.bullets.length > 0) {
    lines.push('', '## Key points', '')
    for (const bullet of summary.bullets) {
      lines.push(`- ${bullet}`)
    }
  }

  if (summary.action_items.length > 0) {
    lines.push('', '## Action items', '')
    for (const item of summary.action_items) {
      lines.push(`- [ ] ${item}`)
    }
  }

  if (summary.keywords.length > 0) {
    lines.push('', '## Keywords', '')
    for (const keyword of summary.keywords) {
      const examples = keyword.examples.length > 0
        ? ` — ${keyword.examples[0]}`
        : ''
      lines.push(`- **${keyword.term}** (${keyword.count})${examples}`)
    }
  }

  return lines.join('\n')
}


export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds))
  const minutes = Math.floor(total / 60)
  const secs = total % 60
  if (minutes === 0) {
    return `${secs}s`
  }
  return `${minutes}m ${secs}s`
}
