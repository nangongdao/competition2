/**
 * 按句末标点把连续文本切分为句子。
 *
 * 用于流式 TTS：翻译 token 到达时，遇到句末标点立即把完整句子送去合成，
 * 不必等整个 segment 翻译完。
 *
 * 连续标点（如 "？？？。"）视为同一个句末标点组，不逐字符切分。
 * 注意：英文分号 ";" 不表示句子结束（连接分句），不参与切分。
 */

const SENTENCE_END_PATTERN = /([。！？；.!?]+)\s*/u


/**
 * 将文本按句末标点切分为句子序列。
 *
 * @param text 待切分的连续文本（可能包含未完成的末尾句）。
 * @returns 句子数组，末尾可能包含一个尚未收尾的片段。
 */
export function splitSentences(text: string): string[] {
  const parts = text.split(SENTENCE_END_PATTERN)
  const sentences: string[] = []

  // split 带捕获组 → [文本, 标点, 文本, 标点, ...]，末尾可能多一个无标点片段
  for (let index = 0; index < parts.length; index += 2) {
    const textPart = parts[index] ?? ''
    const punctuation = parts[index + 1]
    if (punctuation !== undefined) {
      const sentence = `${textPart}${punctuation}`.trim()
      if (sentence) {
        sentences.push(sentence)
      }
    } else if (textPart.trim()) {
      // 末尾未完成片段
      sentences.push(textPart.trim())
    }
  }

  return sentences
}
