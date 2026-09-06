import type { SubtitleEntry } from '../types'


export interface HighlightPart {
  text: string
  matched: boolean
}


/**
 * 阶段 5：按查询词过滤字幕历史。
 *
 * 大小写不敏感；查询按空白拆分为多个关键词，要求**全部**关键词
 * 都出现在原文或译文中（AND 语义），便于逐步缩小范围。
 */
export function filterSubtitlesByQuery(
  entries: SubtitleEntry[],
  query: string,
): SubtitleEntry[] {
  const trimmed = query.trim()
  if (!trimmed) {
    return entries
  }
  const keywords = trimmed.split(/\s+/).filter(Boolean)
  if (keywords.length === 0) {
    return entries
  }
  return entries.filter((entry) => {
    const haystack = `${entry.sourceText} ${entry.translatedText}`.toLowerCase()
    return keywords.every((keyword) => haystack.includes(keyword.toLowerCase()))
  })
}


/**
 * 阶段 5：把文本按查询词拆成「命中/未命中」片段，供 UI 高亮渲染。
 *
 * 大小写不敏感；支持空格分隔的多个关键词（任一词命中即高亮）。
 * 无查询时返回整段未命中，避免无谓拆分。
 */
export function splitHighlightedText(text: string, query: string): HighlightPart[] {
  const trimmed = query.trim()
  if (!trimmed) {
    return [{ text, matched: false }]
  }
  const keywords = trimmed.split(/\s+/).filter(Boolean)
  if (keywords.length === 0) {
    return [{ text, matched: false }]
  }

  const pattern = keywords
    .map((keyword) => keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
    .join('|')
  const regex = new RegExp(`(${pattern})`, 'gi')
  const parts = text.split(regex)
  const matchedSet = new Set(
    parts.filter((part) =>
      keywords.some((keyword) => part.toLowerCase() === keyword.toLowerCase()),
    ),
  )
  return parts.map((part) => ({ text: part, matched: matchedSet.has(part) }))
}
