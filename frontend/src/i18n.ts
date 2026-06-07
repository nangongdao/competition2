import type {
  AppStatus,
  DesktopAsrProfile,
  RevisionReason,
  SourceLanguage,
  SubtitleMode,
  TranslationEngine,
  UiLanguage,
} from './types'


export interface UiText {
  appName: string
  idleTitle: string
  idleDescription: string
  idleSettingsButton: string
  startError: string
  control: ControlPanelText
  history: HistoryPanelText
  settings: SettingsPanelText
}


export interface ControlPanelText {
  ariaLabel: string
  statusLabels: Record<AppStatus, string>
  websocket: string
  settingsButton: string
  source: string
  sourceAriaLabel: string
  sourceOptions: Record<SourceLanguage, string>
  translationFixes: string
  asrFixes: string
  lastFix: string
  none: string
  revisionLabels: Record<RevisionReason, string>
  startTranslation: string
  stopTranslation: string
  reviseNow: string
  historyAndExport: (count: number) => string
  floatingSubtitlesOn: string
  floatingSubtitlesOff: string
  voiceOn: string
  voiceOff: string
  voiceUnavailable: string
  volume: string
  rate: string
  voiceStatus: (status: string, queueLength: number) => string
  voiceStates: {
    unsupported: string
    off: string
    speaking: string
    ready: string
    idle: string
  }
  modeOptions: Array<{ label: string; value: SubtitleMode }>
  showDetails: string
  hideDetails: string
  details: Record<string, string>
  captureBackends: {
    audioWorklet: string
    scriptProcessor: string
    unknown: string
  }
}


export interface HistoryPanelText {
  ariaLabel: string
  title: string
  latestSummary: (visibleCount: number, totalCount: number) => string
  close: string
  closeAriaLabel: string
  source: string
  translated: string
  revised: string
  empty: string
  asrRevised: string
  translationRevised: string
  copied: string
  copyFailed: string
  copyTxt: string
  downloadTxt: string
  downloadSrt: string
  downloadVtt: string
  notesMd: string
  downloadDiagnostics: string
}


export interface SettingsPanelText {
  ariaLabel: string
  title: string
  subtitle: string
  unavailableTitle: string
  unavailableBody: string
  interfaceLanguage: string
  translationEngine: string
  translationEngineOptions: Record<TranslationEngine, string>
  model: string
  openaiBaseUrl: string
  openaiApiKey: string
  anthropicApiKey: string
  keyConfigured: string
  keyMissing: string
  keyPlaceholder: string
  clearOpenaiKey: string
  clearAnthropicKey: string
  asrProfile: string
  asrProfileOptions: Record<DesktopAsrProfile, string>
  asrModel: string
  asrOpenaiBaseUrl: string
  asrOpenaiApiKey: string
  clearAsrOpenaiKey: string
  defaultSourceLanguage: string
  localFile: string
  restartNotice: string
  save: string
  saving: string
  close: string
  saved: string
  saveFailed: string
}


export const UI_LANGUAGE_OPTIONS: Array<{ label: string; value: UiLanguage }> = [
  { label: '中文', value: 'zh-CN' },
  { label: 'English', value: 'en-US' },
]


const CONTROL_DETAILS_ZH: Record<string, string> = {
  session: '会话',
  capture: '采集',
  voice: '语音',
  voiceQueue: '语音队列',
  voiceErrors: '语音错误',
  sentChunks: '已发送音频块',
  clientDrops: '客户端丢弃',
  serverDrops: '服务端丢弃',
  reconnects: '重连次数',
  asrLatency: 'ASR 延迟',
  firstToken: '首字延迟',
  finalText: '终稿延迟',
  apiCalls: 'API 调用',
}


const CONTROL_DETAILS_EN: Record<string, string> = {
  session: 'Session',
  capture: 'Capture',
  voice: 'Voice',
  voiceQueue: 'Voice queue',
  voiceErrors: 'Voice errors',
  sentChunks: 'Sent chunks',
  clientDrops: 'Client drops',
  serverDrops: 'Server drops',
  reconnects: 'Reconnects',
  asrLatency: 'ASR latency',
  firstToken: 'First token',
  finalText: 'Final text',
  apiCalls: 'API calls',
}


const SOURCE_OPTIONS_ZH: Record<SourceLanguage, string> = {
  auto: '自动检测',
  en: '英语',
  ja: '日语',
  ko: '韩语',
  es: '西班牙语',
  fr: '法语',
  de: '德语',
}


const SOURCE_OPTIONS_EN: Record<SourceLanguage, string> = {
  auto: 'Auto detect',
  en: 'English',
  ja: 'Japanese',
  ko: 'Korean',
  es: 'Spanish',
  fr: 'French',
  de: 'German',
}


const UI_TEXT: Record<UiLanguage, UiText> = {
  'zh-CN': {
    appName: 'AI 同声传译助手',
    idleTitle: 'Live Interpreter',
    idleDescription: '从控制面板开始翻译。停顿时会自动修正识别和翻译，历史记录可随时导出。',
    idleSettingsButton: '打开设置',
    startError: '启动失败。请检查麦克风、标签页音频或系统音频权限。',
    control: {
      ariaLabel: '实时翻译控制',
      statusLabels: {
        idle: '就绪',
        capturing: '正在采集音频',
        translating: '正在实时翻译',
        error: '需要处理',
      },
      websocket: 'WebSocket',
      settingsButton: '设置',
      source: '源语言',
      sourceAriaLabel: '源语言',
      sourceOptions: SOURCE_OPTIONS_ZH,
      translationFixes: '翻译修正',
      asrFixes: '识别修正',
      lastFix: '最近修正',
      none: '无',
      revisionLabels: {
        asr_correction: '识别',
        translation_correction: '翻译',
      },
      startTranslation: '开始翻译',
      stopTranslation: '停止翻译',
      reviseNow: '立即修正',
      historyAndExport: (count) => `历史与导出 (${count})`,
      floatingSubtitlesOn: '悬浮字幕已开启',
      floatingSubtitlesOff: '悬浮字幕已关闭',
      voiceOn: '语音已开启',
      voiceOff: '语音已关闭',
      voiceUnavailable: '语音不可用',
      volume: '音量',
      rate: '语速',
      voiceStatus: (status, queueLength) => `语音: ${status} / 队列 ${queueLength}`,
      voiceStates: {
        unsupported: '不支持',
        off: '关闭',
        speaking: '朗读中',
        ready: '就绪',
        idle: '空闲',
      },
      modeOptions: [
        { label: '双语', value: 'bilingual' },
        { label: '译文', value: 'translation_only' },
        { label: '原文', value: 'source_only' },
      ],
      showDetails: '显示详情',
      hideDetails: '隐藏详情',
      details: CONTROL_DETAILS_ZH,
      captureBackends: {
        audioWorklet: 'AudioWorklet',
        scriptProcessor: 'ScriptProcessor 兼容模式',
        unknown: '-',
      },
    },
    history: {
      ariaLabel: '字幕历史',
      title: '字幕历史',
      latestSummary: (visibleCount, totalCount) => `最近 ${visibleCount} 条 / 共 ${totalCount} 条`,
      close: '关闭',
      closeAriaLabel: '关闭字幕历史',
      source: '原文',
      translated: '译文',
      revised: '修正',
      empty: '还没有字幕。',
      asrRevised: '识别已修正',
      translationRevised: '翻译已修正',
      copied: '已复制',
      copyFailed: '复制失败',
      copyTxt: '复制 TXT',
      downloadTxt: '下载 TXT',
      downloadSrt: '下载 SRT',
      downloadVtt: '下载 VTT',
      notesMd: '笔记 MD',
      downloadDiagnostics: '下载诊断',
    },
    settings: {
      ariaLabel: '应用设置',
      title: '设置',
      subtitle: '本地配置会写入已忽略的 desktop-settings.local.json。',
      unavailableTitle: '本地设置不可用',
      unavailableBody: '请通过 start-web 启动本项目；网页会连接本机后端来读写本地密钥文件。',
      interfaceLanguage: '界面语言',
      translationEngine: '翻译引擎',
      translationEngineOptions: {
        openai: 'OpenAI 兼容',
        claude: 'Claude',
      },
      model: '模型',
      openaiBaseUrl: 'OpenAI Base URL',
      openaiApiKey: 'OpenAI API Key',
      anthropicApiKey: 'Anthropic API Key',
      keyConfigured: '已配置',
      keyMissing: '未配置',
      keyPlaceholder: '留空则保留已保存的 key',
      clearOpenaiKey: '清空 OpenAI key',
      clearAnthropicKey: '清空 Anthropic key',
      asrProfile: 'ASR 资源模式',
      asrProfileOptions: {
        remote: 'Remote API',
        light: '轻量 CPU',
        cpu: 'CPU',
        gpu: 'GPU 高精度',
        env: '使用环境文件',
      },
      asrModel: 'ASR 转写模型',
      asrOpenaiBaseUrl: 'ASR Base URL',
      asrOpenaiApiKey: 'ASR API Key',
      clearAsrOpenaiKey: '清空 ASR key',
      defaultSourceLanguage: '默认源语言',
      localFile: '本地文件',
      restartNotice: '翻译引擎、模型、API key、ASR 配置和 ASR 模式保存后，需要重启网页启动器或后端后生效。',
      save: '保存设置',
      saving: '保存中',
      close: '关闭',
      saved: '设置已保存',
      saveFailed: '保存失败',
    },
  },
  'en-US': {
    appName: 'AI Interpreter',
    idleTitle: 'Live Interpreter',
    idleDescription: 'Start translation from the control panel. Pauses in audio trigger automatic ASR and translation revisions, and history stays exportable.',
    idleSettingsButton: 'Open settings',
    startError: 'Start failed. Check microphone, tab audio, or system audio permissions.',
    control: {
      ariaLabel: 'Live translation controls',
      statusLabels: {
        idle: 'Ready',
        capturing: 'Capturing audio',
        translating: 'Live translation',
        error: 'Action needed',
      },
      websocket: 'WebSocket',
      settingsButton: 'Settings',
      source: 'Source',
      sourceAriaLabel: 'Source language',
      sourceOptions: SOURCE_OPTIONS_EN,
      translationFixes: 'Translation fixes',
      asrFixes: 'ASR fixes',
      lastFix: 'Last fix',
      none: 'None',
      revisionLabels: {
        asr_correction: 'ASR',
        translation_correction: 'Translation',
      },
      startTranslation: 'Start translation',
      stopTranslation: 'Stop translation',
      reviseNow: 'Revise now',
      historyAndExport: (count) => `History and export (${count})`,
      floatingSubtitlesOn: 'Floating subtitles on',
      floatingSubtitlesOff: 'Floating subtitles off',
      voiceOn: 'Voice on',
      voiceOff: 'Voice off',
      voiceUnavailable: 'Voice unavailable',
      volume: 'Volume',
      rate: 'Rate',
      voiceStatus: (status, queueLength) => `Voice: ${status} / queue ${queueLength}`,
      voiceStates: {
        unsupported: 'unsupported',
        off: 'off',
        speaking: 'speaking',
        ready: 'ready',
        idle: 'idle',
      },
      modeOptions: [
        { label: 'Both', value: 'bilingual' },
        { label: 'Translation', value: 'translation_only' },
        { label: 'Source', value: 'source_only' },
      ],
      showDetails: 'Show details',
      hideDetails: 'Hide details',
      details: CONTROL_DETAILS_EN,
      captureBackends: {
        audioWorklet: 'AudioWorklet',
        scriptProcessor: 'ScriptProcessor fallback',
        unknown: '-',
      },
    },
    history: {
      ariaLabel: 'Subtitle history',
      title: 'Subtitle history',
      latestSummary: (visibleCount, totalCount) => `Latest ${visibleCount} of ${totalCount} entries`,
      close: 'Close',
      closeAriaLabel: 'Close subtitle history',
      source: 'Source',
      translated: 'Translated',
      revised: 'Revised',
      empty: 'No subtitles yet.',
      asrRevised: 'ASR revised',
      translationRevised: 'Translation revised',
      copied: 'Copied',
      copyFailed: 'Copy failed',
      copyTxt: 'Copy TXT',
      downloadTxt: 'Download TXT',
      downloadSrt: 'Download SRT',
      downloadVtt: 'Download VTT',
      notesMd: 'Notes MD',
      downloadDiagnostics: 'Download diagnostics',
    },
    settings: {
      ariaLabel: 'Application settings',
      title: 'Settings',
      subtitle: 'Local configuration is saved to the ignored desktop-settings.local.json file.',
      unavailableTitle: 'Local settings unavailable',
      unavailableBody: 'Start with start-web so the browser can use the local backend to read and write the key file.',
      interfaceLanguage: 'Interface language',
      translationEngine: 'Translation engine',
      translationEngineOptions: {
        openai: 'OpenAI compatible',
        claude: 'Claude',
      },
      model: 'Model',
      openaiBaseUrl: 'OpenAI Base URL',
      openaiApiKey: 'OpenAI API Key',
      anthropicApiKey: 'Anthropic API Key',
      keyConfigured: 'Configured',
      keyMissing: 'Not configured',
      keyPlaceholder: 'Leave blank to keep the saved key',
      clearOpenaiKey: 'Clear OpenAI key',
      clearAnthropicKey: 'Clear Anthropic key',
      asrProfile: 'ASR profile',
      asrProfileOptions: {
        remote: 'Remote API',
        light: 'Light CPU',
        cpu: 'CPU',
        gpu: 'GPU high accuracy',
        env: 'Use env files',
      },
      asrModel: 'ASR transcription model',
      asrOpenaiBaseUrl: 'ASR Base URL',
      asrOpenaiApiKey: 'ASR API Key',
      clearAsrOpenaiKey: 'Clear ASR key',
      defaultSourceLanguage: 'Default source',
      localFile: 'Local file',
      restartNotice: 'Translation engine, model, API key, ASR settings, and ASR profile changes take effect after restarting the web launcher or backend.',
      save: 'Save settings',
      saving: 'Saving',
      close: 'Close',
      saved: 'Settings saved',
      saveFailed: 'Save failed',
    },
  },
}


export function getUiText(language: UiLanguage): UiText {
  return UI_TEXT[language]
}


export function isUiLanguage(value: string): value is UiLanguage {
  return value === 'zh-CN' || value === 'en-US'
}
