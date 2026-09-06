import type { RevisionEvent, RevisionMessage } from '../types'


/** 修正历史时间线的事件数量上限。 */
export const REVISION_HISTORY_LIMIT = 200


/**
 * 阶段 4：把一条后端修正消息转换为时间线事件。
 *
 * 后端消息使用 snake_case 字段，前端事件使用 camelCase。
 * 时间戳在事件产生时记录（本地时钟）。
 */
export function revisionEventFromMessage(
  message: RevisionMessage,
  timestamp = Date.now(),
): RevisionEvent {
  return {
    id: `${message.segment_id}-${timestamp}-${Math.random().toString(36).slice(2, 8)}`,
    segmentId: message.segment_id,
    segmentIndex: segmentIndexFromId(message.segment_id),
    newText: message.new_text,
    sourceText: message.source_text,
    oldText: message.old_text,
    oldSourceText: message.old_source_text,
    reason: message.reason,
    correctionSource: message.correction_source,
    trigger: message.trigger,
    latencyMs: message.latency_ms,
    confidence: message.confidence,
    timestamp,
  }
}


/**
 * 把新事件插入修正历史（最新在前），并裁剪到上限。
 */
export function pushRevisionEvent(
  history: RevisionEvent[],
  event: RevisionEvent,
): RevisionEvent[] {
  return [event, ...history].slice(0, REVISION_HISTORY_LIMIT)
}


/**
 * 从 segmentId 解析片段序号。
 *
 * segmentId 形如 "{session_id}_{index}"，序号恒为末段。
 * 解析失败返回 undefined，调用方按 undefined 处理。
 */
function segmentIndexFromId(segmentId: string): number | undefined {
  const index = segmentId.lastIndexOf('_')
  if (index === -1) {
    return undefined
  }
  const parsed = Number(segmentId.slice(index + 1))
  return Number.isFinite(parsed) ? parsed : undefined
}
