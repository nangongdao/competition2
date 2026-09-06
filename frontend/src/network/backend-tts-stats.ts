/**
 * 后端 TTS 合成/缓存统计客户端。
 *
 * 前端通过 REST 端点 /api/v1/tts/stats 读取共享 TTS 服务的合成统计（内存缓存命中、
 * 磁盘缓存命中、合成数、失败数、磁盘缓存文件数等），用于在控制面板展示后端
 * 语音产物的成本与缓存收益，无需真机即可本地验证。
 */

export interface BackendTtsStats {
  /** 引擎（edge/openai/off）。 */
  engine: string
  /** 是否启用后端合成。 */
  enabled: boolean
  /** 当前语音。 */
  voice: string
  /** 当前语速。 */
  rate: string
  /** 内存缓存条目数。 */
  cacheSize: number
  /** 内存缓存命中次数。 */
  cacheHits: number
  /** 磁盘缓存命中次数。 */
  diskHits: number
  /** 磁盘缓存文件数。 */
  diskCacheFiles: number
  /** 实际合成次数。 */
  synthesized: number
  /** 失败次数。 */
  failed: number
  /** 当前活跃会话数。 */
  active: number
}

export interface BackendTtsStatsResponse {
  success: boolean
  stats?: BackendTtsStats
}

/** 缓存未命中时的占位统计（空状态）。 */
export const EMPTY_BACKEND_TTS_STATS: BackendTtsStats = {
  engine: 'off',
  enabled: false,
  voice: '',
  rate: '',
  cacheSize: 0,
  cacheHits: 0,
  diskHits: 0,
  diskCacheFiles: 0,
  synthesized: 0,
  failed: 0,
  active: 0,
}

/**
 * 归一化后端返回的统计对象，保证所有字段为数字/字符串且缺失字段回退 0，
 * 避免脏数据渲染出 NaN/undefined。
 */
export function normalizeBackendTtsStats(raw: unknown): BackendTtsStats {
  if (!raw || typeof raw !== 'object') {
    return { ...EMPTY_BACKEND_TTS_STATS }
  }
  const record = raw as Record<string, unknown>
  const numberOr = (value: unknown): number =>
    typeof value === 'number' && Number.isFinite(value) ? value : 0
  const stringOr = (value: unknown): string =>
    typeof value === 'string' ? value : ''
  const booleanOr = (value: unknown): boolean => typeof value === 'boolean' && value

  return {
    engine: stringOr(record.engine) || 'off',
    enabled: booleanOr(record.enabled),
    voice: stringOr(record.voice),
    rate: stringOr(record.rate),
    cacheSize: numberOr(record.cacheSize),
    cacheHits: numberOr(record.cacheHits),
    diskHits: numberOr(record.diskHits),
    diskCacheFiles: numberOr(record.diskCacheFiles),
    synthesized: numberOr(record.synthesized),
    failed: numberOr(record.failed),
    active: numberOr(record.active),
  }
}

/** 从运行时 wsUrl 推导同源 REST 基础地址。 */
export function resolveTtsStatsEndpoint(): string {
  const base = resolveRuntimeWsBase()
  return `${base}/api/v1/tts/stats`
}

function resolveRuntimeWsBase(): string {
  if (typeof window === 'undefined') {
    return ''
  }
  const params = new URLSearchParams(window.location.search)
  const wsUrl = params.get('wsUrl')
  if (wsUrl) {
    try {
      const parsed = new URL(wsUrl)
      return `${parsed.protocol === 'https:' ? 'https' : 'http'}://${parsed.host}`
    } catch {
      // fall through
    }
  }
  const { protocol, host } = window.location
  return `${protocol}//${host}`
}

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

/**
 * 拉取后端 TTS 统计。任何网络/解析异常都返回空统计并标注成功与否，
 * 绝不向上抛异常中断 UI。
 */
export async function fetchBackendTtsStats(
  fetcher: Fetcher = globalThis.fetch?.bind(globalThis),
): Promise<{ success: boolean; stats: BackendTtsStats }> {
  if (!fetcher) {
    return { success: false, stats: { ...EMPTY_BACKEND_TTS_STATS } }
  }
  try {
    const response = await fetcher(resolveTtsStatsEndpoint(), {
      method: 'GET',
      headers: { Accept: 'application/json' },
    })
    if (!response.ok) {
      return { success: false, stats: { ...EMPTY_BACKEND_TTS_STATS } }
    }
    const payload = (await response.json()) as BackendTtsStatsResponse
    return {
      success: payload.success !== false,
      stats: normalizeBackendTtsStats(payload.stats),
    }
  } catch (error) {
    console.warn('[backend-tts-stats] failed to fetch stats', error)
    return { success: false, stats: { ...EMPTY_BACKEND_TTS_STATS } }
  }
}

/**
 * 计算磁盘缓存命中率（0-100）。分母为磁盘命中 + 实际合成；无样本时返回 0。
 */
export function diskCacheHitRatePct(stats: BackendTtsStats): number {
  const denominator = stats.diskHits + stats.synthesized
  if (denominator <= 0) {
    return 0
  }
  return Math.round((stats.diskHits / denominator) * 100)
}
