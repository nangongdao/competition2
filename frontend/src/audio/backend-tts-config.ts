/**
 * 后端 TTS 语音/语速配置化。
 *
 * 前端通过 WebSocket config 消息把用户选择的语音与语速下发到后端
 * TTSService（edge-tts / OpenAI），实现「控制面板选语音、后端合成」。
 *
 * 语音列表为 edge-tts 常用中文语音精选，值即 edge-tts 的 voice 参数。
 */

/** 一条可选的后端 TTS 语音。 */
export interface BackendTtsVoice {
  /** edge-tts voice 值，作为 config 消息的 tts_voice 下发。 */
  value: string
  /** 展示名（中文）。 */
  label: string
  /** 语音性别/风格提示（男/女声）。 */
  tone: 'female' | 'male' | 'other'
}

/** 后端 TTS 语速档位（edge-tts rate 参数，正/负百分比）。 */
export interface BackendTtsRatePreset {
  value: string
  label: string
}

/** edge-tts 音量档位（volume 参数，正/负百分比）。 */
export interface BackendTtsVolumePreset {
  value: string
  label: string
}

/**
 * 播报延迟档位（毫秒）。
 *
 * 控制后端 TTS 每段音频在开始播放前额外等待的时间，以及相邻两段之间的最小间隔，
 * 用于调节「跟随度」：值越小语音越紧跟字幕（适合实时跟读），值越大间隔越宽松
 * （避免连续多段听起来急促、重叠）。
 */
export interface BackendTtsDelayPreset {
  /** 延迟毫秒数（0 表示不额外延迟）。 */
  value: number
  label: string
}

/** 用户当前选中的后端 TTS 配置。 */
export interface BackendTtsConfig {
  /** edge-tts voice 值（如 zh-CN-XiaoxiaoNeural）。 */
  voice: string
  /** edge-tts rate 值（如 +0%）。 */
  rate: string
  /** edge-tts volume 值（如 +0%）。 */
  volume: string
  /** 播报延迟（毫秒），0 表示紧跟字幕播放。 */
  delay: number
}

/** edge-tts 中文语音精选列表。 */
export const BACKEND_TTS_VOICES: readonly BackendTtsVoice[] = [
  { value: 'zh-CN-XiaoxiaoNeural', label: '晓晓（普通话女声）', tone: 'female' },
  { value: 'zh-CN-XiaoyiNeural', label: '晓伊（普通话女声）', tone: 'female' },
  { value: 'zh-CN-YunxiNeural', label: '云希（普通话男声）', tone: 'male' },
  { value: 'zh-CN-YunjianNeural', label: '云健（普通话男声）', tone: 'male' },
  { value: 'zh-CN-YunyangNeural', label: '云扬（新闻男声）', tone: 'male' },
  { value: 'zh-CN-YunxiaNeural', label: '云夏（少年男声）', tone: 'male' },
  { value: 'zh-CN-liaoning-XiaobeiNeural', label: '晓北（东北女声）', tone: 'female' },
  { value: 'zh-TW-HsiaoChenNeural', label: '曉臻（台湾女声）', tone: 'female' },
  { value: 'zh-HK-HiuMaanNeural', label: '曉曼（粤语女声）', tone: 'female' },
]

/** 后端 TTS 语速档位（edge-tts rate 参数）。 */
export const BACKEND_TTS_RATE_PRESETS: readonly BackendTtsRatePreset[] = [
  { value: '-25%', label: '0.75x 慢速' },
  { value: '-10%', label: '0.9x 略慢' },
  { value: '+0%', label: '1.0x 正常' },
  { value: '+10%', label: '1.1x 略快' },
  { value: '+25%', label: '1.25x 快速' },
]

/** 后端 TTS 音量档位（edge-tts volume 参数）。 */
export const BACKEND_TTS_VOLUME_PRESETS: readonly BackendTtsVolumePreset[] = [
  { value: '-50%', label: '低音量' },
  { value: '-25%', label: '较小' },
  { value: '+0%', label: '正常' },
  { value: '+25%', label: '较大' },
  { value: '+50%', label: '高音量' },
]

/** 播报延迟档位（毫秒）。 */
export const BACKEND_TTS_DELAY_PRESETS: readonly BackendTtsDelayPreset[] = [
  { value: 0, label: '紧跟字幕' },
  { value: 300, label: '0.3s' },
  { value: 600, label: '0.6s' },
  { value: 1000, label: '1.0s' },
  { value: 1500, label: '1.5s' },
]

export const DEFAULT_BACKEND_TTS_CONFIG: BackendTtsConfig = {
  voice: 'zh-CN-XiaoxiaoNeural',
  rate: '+0%',
  volume: '+0%',
  delay: 0,
}

/**
 * 判断给定语音值是否在可选列表中；不在则回退到默认语音。
 * 防止后端配置了列表外的语音时前端下拉显示空值。
 */
export function normalizeBackendTtsVoice(voice: string): string {
  return BACKEND_TTS_VOICES.some((entry) => entry.value === voice)
    ? voice
    : DEFAULT_BACKEND_TTS_CONFIG.voice
}

/**
 * 判断给定语速值是否为合法档位；不是则回退到默认语速。
 */
export function normalizeBackendTtsRate(rate: string): string {
  return BACKEND_TTS_RATE_PRESETS.some((entry) => entry.value === rate)
    ? rate
    : DEFAULT_BACKEND_TTS_CONFIG.rate
}

/**
 * 判断给定音量值是否为合法档位；不是则回退到默认音量。
 */
export function normalizeBackendTtsVolume(volume: string): string {
  return BACKEND_TTS_VOLUME_PRESETS.some((entry) => entry.value === volume)
    ? volume
    : DEFAULT_BACKEND_TTS_CONFIG.volume
}

/**
 * 判断给定播报延迟（毫秒）是否为合法档位；不是（含非法/负值/非数字）则回退到默认延迟。
 */
export function normalizeBackendTtsDelay(delay: number): number {
  return BACKEND_TTS_DELAY_PRESETS.some((entry) => entry.value === delay)
    ? delay
    : DEFAULT_BACKEND_TTS_CONFIG.delay
}

/**
 * 把 edge-tts 音量字符串（如 "+0%" / "-50%" / "+50%"）映射为前端播放音量系数（0.0~1.0）。
 *
 * 后端音量影响合成出的音频本身；本地播放音量系数再乘上一档响度，供用户在不重新
 * 合成的情况下快速调节听感。非法或不可解析的值回退为 1.0（不放大不衰减）。
 */
export function backendTtsVolumeToPlayback(volume: string): number {
  const match = /^([+-]?\d+)%$/.exec(volume)
  if (!match) {
    return 1
  }
  const pct = Number.parseInt(match[1], 10)
  if (!Number.isFinite(pct)) {
    return 1
  }
  // 以 +0% = 1.0 为基准：每 -10% 音量对应约 -0.1 播放系数，最低 0.2 防止完全无声
  return Math.min(1, Math.max(0.2, 1 + pct / 100))
}
