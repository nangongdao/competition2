/**
 * 极简 ZIP 打包器（Store 方式，不压缩）。
 *
 * 生成一个符合 ZIP 规范（APPNOTE.TXT）的归档：
 * - 每个文件以 `0x00` 压缩方式（STORE）原样写入，不依赖任何压缩库，纯标准库可测试。
 * - 文件内容按 UTF-8 编码，文件名使用 UTF-8（不设置 UTF-8 标志位时，多数解压器仍按
 *   本地代码页解析；此处设置 UTF-8 语言编码标志位以确保中文文件名安全）。
 * - 仅支持「文件 + 目录分隔符」基础场景，足够用于把 SRT/VTT/MD/TXT 等文本产物打进一个包。
 *
 * 用法：
 * ```ts
 * const blob = createZipBlob([
 *   { name: 'subtitles.srt', content: '...' },
 *   { name: 'notes.md', content: '...' },
 * ])
 * ```
 */

export interface ZipEntry {
  name: string
  content: string
}

/** ZIP 版本号（Windows NT）。 */
const VERSION_NEEDED = 20
const VERSION_MADE_BY = 20

/** 本地文件头 + 中央目录头 + 中央目录结束记录 的固定结构常量。 */
const LOCAL_HEADER_SIGNATURE = 0x04034b50
const CENTRAL_HEADER_SIGNATURE = 0x02014b50
const EOCD_SIGNATURE = 0x06054b50

const UTF8_FLAG = 0x0800
const STORE_METHOD = 0

/**
 * 生成一个完整的 ZIP 归档 Blob。
 *
 * @param entries 待归档文件列表（按给定顺序写入）。
 * @returns 可直接用于下载的 `application/zip` Blob。
 */
export function createZipBlob(entries: ZipEntry[]): Blob {
  const bytes = buildZip(entries)
  return new Blob([bytes.buffer as ArrayBuffer], { type: 'application/zip' })
}

/**
 * 生成 ZIP 归档的字节序列（Uint8Array），纯函数便于测试。
 */
export function buildZip(entries: ZipEntry[]): Uint8Array {
  const localParts: Uint8Array[] = []
  const centralParts: Uint8Array[] = []
  let localOffset = 0

  for (const entry of entries) {
    const nameBytes = encodeUtf8(entry.name)
    const contentBytes = encodeUtf8(entry.content)
    const crc32 = computeCrc32(contentBytes)

    // 本地文件头
    const local = new Uint8Array(30 + nameBytes.length + contentBytes.length)
    const localView = new DataView(local.buffer)
    writeU32(localView, 0, LOCAL_HEADER_SIGNATURE)
    writeU16(localView, 4, VERSION_NEEDED)
    writeU16(localView, 6, UTF8_FLAG)
    writeU16(localView, 8, STORE_METHOD)
    writeU16(localView, 10, 0) // 时间
    writeU16(localView, 12, 0) // 日期
    writeU32(localView, 14, crc32)
    writeU32(localView, 18, contentBytes.length) // 压缩后大小 = 原大小（store）
    writeU32(localView, 22, contentBytes.length) // 原大小
    writeU16(localView, 26, nameBytes.length)
    writeU16(localView, 28, 0) // 扩展字段长度
    local.set(nameBytes, 30)
    local.set(contentBytes, 30 + nameBytes.length)
    localParts.push(local)

    // 中央目录记录
    const central = new Uint8Array(46 + nameBytes.length)
    const centralView = new DataView(central.buffer)
    writeU32(centralView, 0, CENTRAL_HEADER_SIGNATURE)
    writeU16(centralView, 4, VERSION_MADE_BY)
    writeU16(centralView, 6, VERSION_NEEDED)
    writeU16(centralView, 8, UTF8_FLAG)
    writeU16(centralView, 10, STORE_METHOD)
    writeU16(centralView, 12, 0)
    writeU16(centralView, 14, 0)
    writeU32(centralView, 16, crc32)
    writeU32(centralView, 20, contentBytes.length)
    writeU32(centralView, 24, contentBytes.length)
    writeU16(centralView, 28, nameBytes.length)
    writeU16(centralView, 30, 0)
    writeU16(centralView, 32, 0)
    writeU16(centralView, 34, 0)
    writeU16(centralView, 36, 0)
    writeU32(centralView, 38, 0) // 外部属性
    writeU32(centralView, 42, localOffset)
    central.set(nameBytes, 46)
    centralParts.push(central)

    localOffset += local.length
  }

  // 中央目录结束记录（EOCD）
  const centralDirectorySize = centralParts.reduce((sum, part) => sum + part.length, 0)
  const centralDirectoryOffset = localParts.reduce((sum, part) => sum + part.length, 0)
  const eocd = new Uint8Array(22)
  const eocdView = new DataView(eocd.buffer)
  writeU32(eocdView, 0, EOCD_SIGNATURE)
  writeU16(eocdView, 4, 0) // 磁盘号
  writeU16(eocdView, 6, 0)
  writeU16(eocdView, 8, entries.length)
  writeU16(eocdView, 10, entries.length)
  writeU32(eocdView, 12, centralDirectorySize)
  writeU32(eocdView, 16, centralDirectoryOffset)
  writeU16(eocdView, 20, 0) // 注释长度

  const totalLength =
    localParts.reduce((sum, part) => sum + part.length, 0) +
    centralDirectorySize +
    eocd.length
  const result = new Uint8Array(totalLength)
  let cursor = 0
  for (const part of localParts) {
    result.set(part, cursor)
    cursor += part.length
  }
  for (const part of centralParts) {
    result.set(part, cursor)
    cursor += part.length
  }
  result.set(eocd, cursor)

  return result
}

function encodeUtf8(text: string): Uint8Array {
  const encoder = new TextEncoder()
  return encoder.encode(text)
}

function writeU16(view: DataView, offset: number, value: number): void {
  view.setUint16(offset, value, true)
}

function writeU32(view: DataView, offset: number, value: number): void {
  view.setUint32(offset, value >>> 0, true)
}

/**
 * 标准 CRC-32（IEEE 802.3 / zip 规范），查表法。
 */
const CRC32_TABLE: Uint32Array = (() => {
  const table = new Uint32Array(256)
  for (let index = 0; index < 256; index += 1) {
    let current = index
    for (let bit = 0; bit < 8; bit += 1) {
      current = current & 1 ? 0xedb88320 ^ (current >>> 1) : current >>> 1
    }
    table[index] = current >>> 0
  }
  return table
})()

export function computeCrc32(data: Uint8Array): number {
  let crc = 0xffffffff
  for (let index = 0; index < data.length; index += 1) {
    crc = (crc >>> 8) ^ CRC32_TABLE[(crc ^ data[index]) & 0xff]
  }
  return (crc ^ 0xffffffff) >>> 0
}
