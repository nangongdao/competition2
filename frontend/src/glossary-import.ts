/**
 * 术语表文件导入解析。
 *
 * 支持 JSON（数组或 {"entries": [...]}）与 CSV（source,target[,keep_original]）。
 */

export interface GlossaryImportItem {
  source: string
  target: string
  keep_original?: boolean
}


/**
 * 解析术语表文件内容。
 *
 * @param filename 文件名（按扩展名决定解析方式）。
 * @param text 文件文本。
 * @returns 解析出的术语表条目；解析失败返回空数组。
 */
export function parseGlossaryFile(filename: string, text: string): GlossaryImportItem[] {
  const normalized = filename.trim().toLowerCase()
  if (normalized.endsWith('.json')) {
    return parseGlossaryJson(text)
  }
  if (normalized.endsWith('.csv')) {
    return parseGlossaryCsv(text)
  }
  return []
}


function parseGlossaryJson(text: string): GlossaryImportItem[] {
  let raw: unknown
  try {
    raw = JSON.parse(text)
  } catch {
    return []
  }

  const candidates = Array.isArray(raw)
    ? raw
    : isRecord(raw) && Array.isArray(raw.entries)
      ? raw.entries
      : []

  const items: GlossaryImportItem[] = []
  for (const entry of candidates) {
    if (!isRecord(entry) || typeof entry.source !== 'string' || !entry.source.trim()) {
      continue
    }
    items.push({
      source: entry.source.trim(),
      target: typeof entry.target === 'string' ? entry.target.trim() : '',
      keep_original: entry.keep_original === true,
    })
  }
  return items
}


function parseGlossaryCsv(text: string): GlossaryImportItem[] {
  const items: GlossaryImportItem[] = []
  for (const rawLine of text.split(/\r?\n/)) {
    const trimmedLine = rawLine.trim()
    if (!trimmedLine || trimmedLine.startsWith('#')) {
      continue
    }
    const columns = trimmedLine.split(',').map((cell) => cell.trim())
    if (!columns[0]) {
      continue
    }
    items.push({
      source: columns[0],
      target: columns[1] ?? '',
      keep_original: (columns[2] ?? '').toLowerCase() === 'true',
    })
  }
  return items
}


function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
