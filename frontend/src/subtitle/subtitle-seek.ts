/**
 * 字幕时间轴对齐与回看跳转（第二梯队-方向 5）。
 *
 * 纯函数：把一条字幕条目映射为文件音频源中的采样偏移，供「点击历史字幕 →
 * 跳到对应音频位置回听」使用。
 *
 * 映射假设：字幕是在文件按实时节奏播放时逐句产生的，因此字幕时间戳区间
 * （首条 → 末条）与文件音频时长按比例对齐。对首/末条做边界夹紧，避免越界。
 */
import type { SubtitleEntry } from '../types'

/** 后端管线采样率（与 FileAudioSource 一致）。 */
export const PIPELINE_SAMPLE_RATE = 16000

/**
 * 计算一条字幕对应的文件音频采样偏移。
 *
 * @param entry 目标字幕条目。
 * @param entries 全量字幕历史（用于求时间轴起止点）。
 * @param totalSamples 文件音频总采样数（0 表示无音频）。
 * @returns 采样偏移（0 ~ totalSamples-1），无可用音频或时间轴不可用时返回 null。
 */
export function subtitleToSeekSample(
  entry: SubtitleEntry,
  entries: SubtitleEntry[],
  totalSamples: number,
): number | null {
  if (totalSamples <= 0) {
    return null
  }

  const exportable = entries.filter(
    (item) => item.sourceText.trim().length > 0 || item.translatedText.trim().length > 0,
  )
  if (exportable.length < 2) {
    // 单条字幕无法构成时间轴，回退到文件开头。
    return 0
  }

  const firstTimestamp = exportable[0].timestamp
  const lastTimestamp = exportable[exportable.length - 1].timestamp
  const span = lastTimestamp - firstTimestamp
  if (!Number.isFinite(span) || span <= 0) {
    return 0
  }

  const fraction = (entry.timestamp - firstTimestamp) / span
  const clampedFraction = Math.max(0, Math.min(1, fraction))
  const sample = Math.floor(clampedFraction * totalSamples)
  return Math.max(0, Math.min(sample, totalSamples - 1))
}

/**
 * 把采样偏移格式化为「分:秒」时间轴标签（用于历史条目展示）。
 */
export function formatSampleClock(sampleOffset: number, sampleRate = PIPELINE_SAMPLE_RATE): string {
  const seconds = Math.max(0, Math.floor(sampleOffset / sampleRate))
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`
}
