/**
 * 会话产物导入解析。
 *
 * 支持把已导出的字幕产物重新导入，恢复字幕历史。
 *
 * 支持的格式：
 * - SRT：标准序号 + 时间轴 + 文本块（`formatSrtSubtitles` 产物）
 * - VTT：`WEBVTT` + cue 块（`formatVttSubtitles` 产物）
 * - JSON：`SubtitleEntry[]` 数组（前端内部产物，最完整，保留修订/说话人信息）
 * - TXT：`formatPlainTranscript` 产物（`1. 时间` + `EN:` / `ZH:` 行）
 */

import type { RevisionReason, SubtitleEntry } from '../types'


export interface SessionImportResult {
  entries: SubtitleEntry[]
  /** 被跳过的非法/空条目数。 */
  skipped: number
}


/**
 * 根据文件名/内容解析会话产物为字幕历史。
 *
 * @param filename 文件名（决定解析策略；未知扩展名尝试 JSON）。
 * @param text 文件文本内容。
 * @returns 解析出的字幕条目（含跳过计数）；解析失败返回空结果。
 */
export function parseSessionArtifact(filename: string, text: string): SessionImportResult {
  const normalized = filename.trim().toLowerCase()

  if (normalized.endsWith('.srt')) {
    return parseSrt(text)
  }
  if (normalized.endsWith('.vtt')) {
    return parseVtt(text)
  }
  if (normalized.endsWith('.json')) {
    return parseJson(text)
  }
  // TXT 与未知扩展名都尝试转录文本格式
  return parsePlainTranscript(text)
}


/**
 * 把字幕后端产物统一转成 SubtitleEntry。
 */
function toEntry(
  segmentId: string,
  sourceText: string,
  translatedText: string,
  timestamp: number,
  extras?: Partial<SubtitleEntry>,
): SubtitleEntry {
  return {
    segmentId,
    sourceText,
    translatedText,
    isPartial: false,
    isRevised: extras?.isRevised ?? false,
    revisionReason: extras?.revisionReason,
    revisedAt: extras?.revisedAt,
    timestamp,
    seq: extras?.seq,
    speaker: extras?.speaker,
  }
}


/** 解析 SRT：多个以空行分隔的块，每块含序号、时间轴、文本。 */
export function parseSrt(text: string): SessionImportResult {
  const blocks = splitBlocks(text)
  const entries: SubtitleEntry[] = []
  let skipped = 0

  for (const block of blocks) {
    const lines = block.split('\n')
    // 跳过第一行序号，取时间轴行定位
    const timelineIndex = lines.findIndex((line) => /\d{1,2}:\d{2}:\d{2}[,.]\d{3}/.test(line))
    if (timelineIndex === -1 || timelineIndex === lines.length - 1) {
      skipped += 1
      continue
    }
    const contentLines = lines.slice(timelineIndex + 1).map((l) => l.trim()).filter(Boolean)
    if (contentLines.length === 0) {
      skipped += 1
      continue
    }

    const startMs = parseTimeToMs(lines[timelineIndex].split('-->')[0] ?? '')
    const { sourceText, translatedText } = splitBilingualLines(contentLines)
    entries.push(toEntry(`import_${entries.length}`, sourceText, translatedText, startMs))
  }

  return { entries, skipped }
}


/** 解析 VTT：WEBVTT 头 + 空行分隔的 cue 块（含时间轴行）。 */
export function parseVtt(text: string): SessionImportResult {
  const body = text.replace(/^\uFEFF/, '').replace(/^WEBVTT.*$/m, '')
  const blocks = splitBlocks(body)
  const entries: SubtitleEntry[] = []
  let skipped = 0

  for (const block of blocks) {
    const lines = block.split('\n')
    const timelineIndex = lines.findIndex((line) =>
      /\d{1,2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[.,]\d{3}/.test(line),
    )
    if (timelineIndex === -1 || timelineIndex === lines.length - 1) {
      skipped += 1
      continue
    }
    const contentLines = lines.slice(timelineIndex + 1).map((l) => l.trim()).filter(Boolean)
    if (contentLines.length === 0) {
      skipped += 1
      continue
    }

    const startMs = parseTimeToMs(lines[timelineIndex].split('-->')[0] ?? '')
    const { sourceText, translatedText } = splitBilingualLines(contentLines)
    entries.push(toEntry(`import_${entries.length}`, sourceText, translatedText, startMs))
  }

  return { entries, skipped }
}


/** 解析 JSON：SubtitleEntry[] 或 { entries: SubtitleEntry[] }。 */
export function parseJson(text: string): SessionImportResult {
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    return { entries: [], skipped: 0 }
  }

  const list = Array.isArray(raw)
    ? raw
    : isRecord(raw) && Array.isArray(raw.entries)
      ? raw.entries
      : []
  const entries: SubtitleEntry[] = []
  let skipped = 0

  for (const item of list) {
    if (!isRecord(item) || typeof item.segmentId !== 'string' || !item.segmentId.trim()) {
      skipped += 1
      continue
    }
    const sourceText = typeof item.sourceText === 'string' ? item.sourceText : ''
    const translatedText = typeof item.translatedText === 'string' ? item.translatedText : ''
    if (!sourceText && !translatedText) {
      skipped += 1
      continue
    }
    const reason = isRevisionReason(item.revisionReason) ? item.revisionReason : undefined
    entries.push(toEntry(
      item.segmentId,
      sourceText,
      translatedText,
      typeof item.timestamp === 'number' ? item.timestamp : Date.now(),
      {
        isRevised: item.isRevised === true,
        revisionReason: reason,
        revisedAt: typeof item.revisedAt === 'number' ? item.revisedAt : undefined,
        seq: typeof item.seq === 'number' ? item.seq : undefined,
        speaker: typeof item.speaker === 'string' ? item.speaker : undefined,
      },
    ))
  }

  return { entries, skipped }
}


/** 解析纯文本转录（`1. 时间` + `EN:` / `ZH:` 行）。 */
export function parsePlainTranscript(text: string): SessionImportResult {
  const lines = text.split('\n')
  const entries: SubtitleEntry[] = []
  let skipped = 0

  let currentIndex = 0
  while (currentIndex < lines.length) {
    const header = /^\s*\d+\.\s+(\S.*)$/.exec(lines[currentIndex])
    if (!header) {
      currentIndex += 1
      continue
    }
    const timeStr = header[1].trim()
    let sourceText = ''
    let translatedText = ''
    let cursor = currentIndex + 1
    while (cursor < lines.length) {
      const line = lines[cursor].trim()
      if (!line) {
        break
      }
      if (/^EN:\s*/.test(line)) {
        sourceText = line.replace(/^EN:\s*/, '').replace(/ \[revised:[^\]]+\]$/, '')
      } else if (/^ZH:\s*/.test(line)) {
        translatedText = line.replace(/^ZH:\s*/, '')
      } else {
        break
      }
      cursor += 1
    }
    if (sourceText || translatedText) {
      entries.push(toEntry(`import_${entries.length}`, sourceText, translatedText, parseTimeToMs(timeStr)))
    } else {
      skipped += 1
    }
    currentIndex = cursor
  }

  return { entries, skipped }
}


/** 按空行切分文本块。 */
function splitBlocks(text: string): string[] {
  return text
    .replace(/\r\n?/g, '\n')
    .split(/\n\s*\n/)
    .map((block) => block.trim())
    .filter(Boolean)
}


/** 把 "HH:MM:SS,mmm" / "MM:SS.mmm" 转成毫秒。 */
function parseTimeToMs(raw: string): number {
  const match = /(\d{1,2}):(\d{2}):(\d{2})[.,](\d{3})/.exec(raw)
  if (match) {
    const [, h, m, s, ms] = match
    return Number(h) * 3_600_000 + Number(m) * 60_000 + Number(s) * 1000 + Number(ms)
  }
  const short = /(\d{1,2}):(\d{2})[.,](\d{3})/.exec(raw)
  if (short) {
    const [, m, s, ms] = short
    return Number(m) * 60_000 + Number(s) * 1000 + Number(ms)
  }
  return Date.now()
}


/**
 * 拆分双语内容行。
 *
 * 兼容两种结构：
 * - 分行的 "EN: ..." / "ZH: ..."（subtitle-export 产物）
 * - 单行 "原文 / 译文" 斜杠分隔
 */
function splitBilingualLines(lines: string[]): { sourceText: string; translatedText: string } {
  let sourceText = ''
  let translatedText = ''

  for (const line of lines) {
    const enMatch = /^EN:\s*(.+)$/i.exec(line)
    const zhMatch = /^ZH:\s*(.+)$/i.exec(line)
    if (enMatch) {
      sourceText = enMatch[1].replace(/ \[revised:[^\]]+\]$/, '')
    } else if (zhMatch) {
      translatedText = zhMatch[1]
    } else if (line.includes(' / ')) {
      const [s, t] = line.split(' / ')
      sourceText = (s ?? '').trim()
      translatedText = (t ?? '').trim()
    } else if (!sourceText) {
      sourceText = line
    } else if (!translatedText) {
      translatedText = line
    }
  }

  return { sourceText, translatedText }
}


function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}


function isRevisionReason(value: unknown): value is RevisionReason {
  return value === 'asr_correction' || value === 'translation_correction'
}
