/**
 * 会话完整产物包（ROADMAP 阶段 9 深化 / 第二梯队-方向 7）。
 *
 * 把一次会话的全部可导出产物打进一个 ZIP：
 * - SRT / VTT 字幕
 * - 纯文本转写（TXT）
 * - 学习笔记（Markdown）
 * - 会话诊断（TXT）
 * - 会话摘要（Markdown，可选）
 * - manifest.json（元数据：生成时间、各产物统计）
 *
 * 纯函数 + 标准库，便于本地单测验证。
 */
import type { SubtitleEntry } from '../types'
import {
  formatLearningNotesMarkdown,
  formatPlainTranscript,
  formatSrtSubtitles,
  formatVttSubtitles,
} from '../subtitle/subtitle-export'
import { createZipBlob, type ZipEntry } from './zip-writer'


export interface SessionBundleOptions {
  entries: SubtitleEntry[]
  diagnosticsText?: string
  /** 会话摘要（Markdown），可选；没有则产物包不包含 summary.md。 */
  summaryMarkdown?: string
  /** 附加说明文本（可选），写入 info.txt。 */
  infoText?: string
  /** 会话标签/备注（可选），写入 manifest。 */
  sessionLabel?: string
}

export interface SessionBundleManifest {
  generatedAt: string
  subtitleCount: number
  sourceCount: number
  translatedCount: number
  revisedCount: number
  hasDiagnostics: boolean
  hasSummary: boolean
  sessionLabel: string
  files: string[]
}

/**
 * 计算用于产物包命名的时戳（本地可读 + 文件名安全）。
 */
export function bundleTimestamp(date = new Date()): string {
  const pad = (value: number): string => String(value).padStart(2, '0')
  return (
    `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}` +
    `-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`
  )
}

/**
 * 构建一次会话的完整产物 ZIP。
 *
 * @returns 可直接下载的 `application/zip` Blob 与产物清单。
 */
export function buildSessionBundle(options: SessionBundleOptions): {
  blob: Blob
  manifest: SessionBundleManifest
} {
  const files: ZipEntry[] = []

  files.push({ name: 'subtitles.srt', content: formatSrtSubtitles(options.entries) })
  files.push({ name: 'subtitles.vtt', content: formatVttSubtitles(options.entries) })
  files.push({ name: 'transcript.txt', content: formatPlainTranscript(options.entries) })
  files.push({ name: 'notes.md', content: formatLearningNotesMarkdown(options.entries) })

  const diagnostics = options.diagnosticsText?.trim() ?? ''
  if (diagnostics) {
    files.push({ name: 'diagnostics.txt', content: diagnostics })
  }

  const summary = options.summaryMarkdown?.trim() ?? ''
  if (summary) {
    files.push({ name: 'summary.md', content: summary })
  }

  if (options.infoText?.trim()) {
    files.push({ name: 'info.txt', content: options.infoText.trim() })
  }

  const exportable = options.entries.filter(
    (entry) => entry.sourceText.trim().length > 0 || entry.translatedText.trim().length > 0,
  )
  const manifest: SessionBundleManifest = {
    generatedAt: new Date().toISOString(),
    subtitleCount: exportable.length,
    sourceCount: exportable.filter((entry) => entry.sourceText.trim().length > 0).length,
    translatedCount: exportable.filter((entry) => entry.translatedText.trim().length > 0).length,
    revisedCount: exportable.filter((entry) => entry.isRevised).length,
    hasDiagnostics: Boolean(diagnostics),
    hasSummary: Boolean(summary),
    sessionLabel: options.sessionLabel ?? '',
    files: [...files.map((file) => file.name), 'manifest.json'],
  }
  files.push({
    name: 'manifest.json',
    content: JSON.stringify(manifest, null, 2),
  })

  return { blob: createZipBlob(files), manifest }
}
