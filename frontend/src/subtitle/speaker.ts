/**
 * 说话人标签的显示辅助：为不同说话人分配稳定颜色。
 */

export const SPEAKER_COLORS = ['#4aa3ff', '#58b06a', '#f4c84c', '#ff8c42', '#c77dff', '#ff5e8a']


/**
 * 按说话人标识（"speaker_N"）取稳定颜色。
 *
 * @param speaker 说话人标识，如 "speaker_1"。
 * @returns 色板中的十六进制颜色。
 */
export function speakerColor(speaker: string): string {
  const match = /speaker_(\d+)/.exec(speaker)
  const index = match ? parseInt(match[1], 10) - 1 : 0
  return SPEAKER_COLORS[((index % SPEAKER_COLORS.length) + SPEAKER_COLORS.length) % SPEAKER_COLORS.length]
}
