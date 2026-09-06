import type {
  AppStatus,
  DesktopAsrProfile,
  RevisionReason,
  SourceLanguage,
  SubtitleMode,
  SubtitlePosition,
  TargetLanguage,
  TranslationEngine,
  TranslationStyle,
  TtsEngine,
  UiLanguage,
} from './types'


export interface UiText {
  appName: string
  idleTitle: string
  idleDescription: string
  idleSettingsButton: string
  idleStartButton: string
  idleFeatures: Array<{ icon: string; title: string; desc: string }>
  startError: string
  control: ControlPanelText
  history: HistoryPanelText
  sessionHistory: SessionHistoryPanelText
  revisionTimeline: RevisionTimelinePanelText
  summary: SummaryPanelText
  glossary: GlossaryPanelText
  translationMemory: TranslationMemoryPanelText
  subtitleStyle: SubtitleStylePanelText
  collaboration: CollaborationPanelText
  subscription: SubscriptionPanelText
  cost: CostPanelText
  settings: SettingsPanelText
}


export interface GlossaryPanelText {
  ariaLabel: string
  title: string
  close: string
  loading: string
  loadFailed: string
  searchPlaceholder: string
  importButton: string
  importFailed: string
  importEmpty: string
  clearAll: string
  confirmClear: string
  sourcePlaceholder: string
  targetPlaceholder: string
  keepOriginal: string
  keepOriginalBadge: string
  addButton: string
  added: string
  addFailed: string
  sourceRequired: string
  deleteFailed: string
  empty: string
  refresh: string
  deleteEntry: (source: string) => string
}


export interface TranslationMemoryPanelText {
  ariaLabel: string
  title: string
  close: string
  description: string
  loading: string
  loadFailed: string
  noData: string
  entries: string
  hits: string
  misses: string
  written: string
  hitRate: string
  threshold: string
  persisted: string
  persistedPairs: string
  persistedLanguages: string
  activeSessions: string
  refresh: string
  clearAll: string
  confirmClear: string
  noActiveSession: string
}


export interface ControlPanelText {
  ariaLabel: string
  statusLabels: Record<AppStatus, string>
  websocket: string
  connectionHint: string
  groupLanguages: string
  groupActions: string
  settingsButton: string
  source: string
  sourceAriaLabel: string
  sourceOptions: Record<SourceLanguage, string>
  /** 阶段 8：auto 模式下提示检测到的源语言。 */
  detectedSource: (code: string) => string
  target: string
  targetAriaLabel: string
  targetOptions: Record<TargetLanguage, string>
  /** 翻译风格（阶段 3）：简洁 / 忠实 / 讲义式。 */
  translationStyle: string
  translationStyleAriaLabel: string
  translationStyleOptions: Record<TranslationStyle, string>
  /** 阶段 2：ASR 术语热词注入开关。 */
  asrHotwords: string
  audioSource: string
  audioSourceOptions: Array<{ label: string; value: 'mic' | 'tab' | 'system' | 'file' }>
  audioFilePick: string
  audioFileLoaded: string
  audioFileEnded: string
  audioFileLoadFailed: string
  translationFixes: string
  asrFixes: string
  lastFix: string
  none: string
  revisionLabels: Record<RevisionReason, string>
  startTranslation: string
  stopTranslation: string
  reviseNow: string
  historyAndExport: (count: number) => string
  openTerminal: string
  openSummary: string
  openGlossary: string
  openTranslationMemory: string
  openSubtitleStyle: string
  openCollaboration: string
  openSubscription: string
  openCost: string
  openSessionHistory: string
  openRevisionTimeline: string
  terminalUnavailable: string
  floatingSubtitlesOn: string
  floatingSubtitlesOff: string
  openFloatingSubtitles: string
  closeFloatingSubtitles: string
  floatingSubtitlesOpenFailed: string
  systemAudioOn: string
  systemAudioOff: string
  systemAudioUnavailable: string
  voiceOn: string
  voiceOff: string
  voiceUnavailable: string
  voiceEngine: string
  voiceEngineOptions: Array<{ label: string; value: TtsEngine }>
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
  glossaryImport: string
  glossaryImportFailed: string
  glossaryImported: string
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
  /** 第二梯队-方向 7：一键导出完整产物包（zip）。 */
  downloadBundle: string
  bundleDownloaded: string
  /** 第二梯队-方向 5：回看跳转。 */
  jumpToEntry: string
  seekUnavailable: string
  /** 时长格式化单位。 */
  sessionSeconds: string
  sessionMinutes: string
  /** 阶段 5：历史搜索。 */
  searchPlaceholder: string
  searchClear: string
  searchMatchLabel: (count: number) => string
  searchNoMatch: string
}


export interface SessionHistoryPanelText {
  ariaLabel: string
  title: string
  closeAriaLabel: string
  refresh: string
  purge: string
  clearAll: string
  confirmClear: string
  statSessions: string
  statSegments: string
  statRetention: string
  empty: string
  metaSegments: string
  metaDuration: string
  deleteAriaLabel: string
  privacyNote: string
  qualityTitle: string
  qualityAsr: string
  qualityTranslation: string
  qualityRevision: string
  qualityDropped: string
  qualityQueue: string
  qualityReconnect: string
  qualityLatency: string
  noQuality: string
}


export interface RevisionTimelinePanelText {
  ariaLabel: string
  title: string
  close: string
  empty: string
  statTotal: string
  statAsr: string
  statTranslation: string
  segmentLabel: string
  reasonLabels: Record<RevisionReason, string>
  /** 修正来源标签（correction_source）。 */
  sourceLabels: Record<string, string>
  /** 触发方式标签（trigger）。 */
  triggerLabels: Record<string, string>
  oldTextLabel: string
  newTextLabel: string
  sourceTextLabel: string
  confidenceLabel: string
  latencyLabel: string
  ago: (minutes: number) => string
}


export interface SubtitleStylePanelText {
  ariaLabel: string
  title: string
  close: string
  description: string
  fontSize: string
  fontColor: string
  backgroundColor: string
  backgroundOpacity: string
  position: string
  positionOptions: Record<SubtitlePosition, string>
  reset: string
  confirmReset: string
  preview: string
  saved: string
}


export interface CollaborationPanelText {
  ariaLabel: string
  title: string
  close: string
  loading: string
  loadFailed: string
  createPlaceholder: string
  createButton: string
  createFailed: string
  memberNamePlaceholder: string
  joinButton: string
  joinFailed: string
  leaveButton: string
  destroyButton: string
  confirmDestroy: string
  refresh: string
  roomList: string
  noRooms: string
  members: string
  memberCount: string
  membersLabel: string
  ownerBadge: string
  revisions: string
  segmentIdPlaceholder: string
  revisionPlaceholder: string
  submitRevision: string
  revisionEmpty: string
  revisionFailed: string
  noRevisions: string
  clearRevisions: string
}


export interface SubscriptionPanelText {
  ariaLabel: string
  title: string
  close: string
  loading: string
  loadFailed: string
  noData: string
  switchFailed: string
  resetFailed: string
  refresh: string
  resetUsage: string
  currentPlan: string
  dailyUsage: string
  remaining: string
  limitReached: string
  unlimited: string
  switchPlan: string
  plans: string
}


export interface CostPanelText {
  ariaLabel: string
  title: string
  close: string
  loading: string
  loadFailed: string
  noData: string
  resetFailed: string
  refresh: string
  resetUsage: string
  totalSessions: string
  totalCost: string
  todayCost: string
  usage: string
  nmtInputTokens: string
  nmtOutputTokens: string
  asrSeconds: string
  ttsChars: string
  estimateNote: string
  suggestions: string
  noSuggestions: string
  today: string
  total: string
  usd: string
  cny: string
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
  defaultTargetLanguage: string
  localFile: string
  restartNotice: string
  save: string
  saving: string
  close: string
  saved: string
  saveFailed: string
}


export interface SummaryPanelText {
  ariaLabel: string
  title: string
  close: string
  useLlm: string
  llmHint: string
  generate: string
  generating: string
  needActiveSession: string
  needSubtitles: string
  fetchFailed: string
  duration: string
  segments: string
  revisions: string
  speakers: string
  keyPoints: string
  actionItems: string
  keywords: string
  copied: string
  copyFailed: string
  copyMd: string
  downloadMd: string
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
  'zh-CN': '简体中文',
  ja: '日语',
  ko: '韩语',
  es: '西班牙语',
  fr: '法语',
  de: '德语',
}


const SOURCE_OPTIONS_EN: Record<SourceLanguage, string> = {
  auto: 'Auto detect',
  en: 'English',
  'zh-CN': 'Simplified Chinese',
  ja: 'Japanese',
  ko: 'Korean',
  es: 'Spanish',
  fr: 'French',
  de: 'German',
}


const TARGET_OPTIONS_ZH: Record<TargetLanguage, string> = {
  'zh-CN': '简体中文',
  en: '英语',
  ja: '日语',
  ko: '韩语',
  es: '西班牙语',
  fr: '法语',
  de: '德语',
}


const TARGET_OPTIONS_EN: Record<TargetLanguage, string> = {
  'zh-CN': 'Simplified Chinese',
  en: 'English',
  ja: 'Japanese',
  ko: 'Korean',
  es: 'Spanish',
  fr: 'French',
  de: 'German',
}


const TRANSLATION_STYLE_OPTIONS_ZH: Record<TranslationStyle, string> = {
  concise: '简洁',
  faithful: '忠实',
  lecture: '讲义式',
}


const TRANSLATION_STYLE_OPTIONS_EN: Record<TranslationStyle, string> = {
  concise: 'Concise',
  faithful: 'Faithful',
  lecture: 'Lecture notes',
}


const UI_TEXT: Record<UiLanguage, UiText> = {
  'zh-CN': {
    appName: 'AI 同声传译助手',
    idleTitle: 'Live Interpreter',
    idleDescription: '从控制面板开始翻译。停顿时会自动修正识别和翻译，历史记录可随时导出。',
    idleSettingsButton: '打开设置',
    idleStartButton: '开始翻译',
    idleFeatures: [
      { icon: '🎯', title: '实时同传', desc: '外语音频流实时识别并翻译成中文' },
      { icon: '🧠', title: '智能修正', desc: '停顿处自动纠正识别与翻译错误' },
      { icon: '🔊', title: '语音播报', desc: '字幕与语音双通道输出，边看边听' },
    ],
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
      connectionHint: '未连接，检查后端是否启动',
      groupLanguages: '语言与输入',
      groupActions: '实时翻译',
      settingsButton: '设置',
      source: '源语言',
      sourceAriaLabel: '源语言',
      sourceOptions: SOURCE_OPTIONS_ZH,
      detectedSource: (code) => {
        const label = SOURCE_OPTIONS_ZH[code as SourceLanguage] ?? code
        return `已检测：${label}`
      },
      target: '目标语言',
      targetAriaLabel: '目标语言',
      targetOptions: TARGET_OPTIONS_ZH,
      translationStyle: '翻译风格',
      translationStyleAriaLabel: '翻译风格',
      translationStyleOptions: TRANSLATION_STYLE_OPTIONS_ZH,
      asrHotwords: '术语热词注入 ASR',
      audioSource: '音频输入',
      audioSourceOptions: [
        { label: '麦克风', value: 'mic' },
        { label: '标签页/窗口', value: 'tab' },
        { label: '系统音频 (Tauri)', value: 'system' },
        { label: '音频文件', value: 'file' },
      ],
      audioFilePick: '选择音频文件',
      audioFileLoaded: '文件已加载，开始翻译',
      audioFileEnded: '文件播放完毕',
      audioFileLoadFailed: '文件加载或解码失败，请换一个音频文件',
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
      openTerminal: '内置终端',
      openSummary: '学习摘要',
      openGlossary: '术语库',
      openTranslationMemory: '翻译记忆库',
      openSubtitleStyle: '字幕样式',
      openCollaboration: '协作翻译',
      openSubscription: '订阅与配额',
      openCost: '成本估算',
      openSessionHistory: '会话历史',
      openRevisionTimeline: '修正历史',
      terminalUnavailable: '终端不可用',
      glossaryImport: '导入术语表',
      glossaryImportFailed: '术语表解析失败（支持 JSON/CSV）',
      glossaryImported: '术语表已应用',
      floatingSubtitlesOn: '悬浮字幕已开启',
      floatingSubtitlesOff: '悬浮字幕已关闭',
      openFloatingSubtitles: '打开悬浮字幕窗',
      closeFloatingSubtitles: '关闭悬浮字幕窗',
      floatingSubtitlesOpenFailed: '无法打开悬浮字幕窗。请允许浏览器弹窗，或使用最新版 Chrome / Edge。',
      systemAudioOn: '系统音频采集已开启',
      systemAudioOff: '系统音频采集已关闭',
      systemAudioUnavailable: '系统音频不可用',
      voiceOn: '语音已开启',
      voiceOff: '语音已关闭',
      voiceUnavailable: '语音不可用',
      voiceEngine: '语音引擎',
      voiceEngineOptions: [
        { label: '自动（优先服务端）', value: 'auto' },
        { label: '本地浏览器语音', value: 'local' },
        { label: '服务端 TTS', value: 'backend' },
      ],
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
      latestSummary: (_visibleCount, totalCount) => `共 ${totalCount} 条字幕`,
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
      downloadBundle: '导出全部（ZIP）',
      bundleDownloaded: '产物包已导出',
      jumpToEntry: '跳到该句',
      seekUnavailable: '当前输入源不支持跳转',
      sessionSeconds: '秒',
      sessionMinutes: '分',
      searchPlaceholder: '搜索原文或译文…',
      searchClear: '清空搜索',
      searchMatchLabel: (count) => `找到 ${count} 条匹配`,
      searchNoMatch: '没有匹配的字幕。',
    },
    sessionHistory: {
      ariaLabel: '会话历史与隐私管理',
      title: '会话历史',
      closeAriaLabel: '关闭会话历史',
      refresh: '刷新',
      purge: '清理过期',
      clearAll: '清空全部',
      confirmClear: '确认清空？',
      statSessions: '会话',
      statSegments: '句数',
      statRetention: '保留期',
      empty: '还没有会话记录。',
      metaSegments: '句数',
      metaDuration: '时长',
      deleteAriaLabel: '删除该会话记录',
      privacyNote: '删除仅移除本地会话台账（含隐私信息），不影响正在进行的实时翻译。',
      qualityTitle: '质量指标',
      qualityAsr: '识别句',
      qualityTranslation: '翻译句',
      qualityRevision: '修正',
      qualityDropped: '丢包',
      qualityQueue: '队列峰值',
      qualityReconnect: '重连',
      qualityLatency: '平均延迟',
      noQuality: '该会话暂无质量指标。',
    },
    revisionTimeline: {
      ariaLabel: '修正历史时间线',
      title: '修正历史',
      close: '关闭',
      empty: '本会话还没有修正记录。修正会在低置信度识别、静默或手动触发时产生。',
      statTotal: '修正总数',
      statAsr: '识别修正',
      statTranslation: '翻译修正',
      segmentLabel: '片段',
      reasonLabels: {
        asr_correction: '识别',
        translation_correction: '翻译',
      },
      sourceLabels: {
        audio_redecode: '音频重解码',
        llm_post_edit: 'LLM 后编辑',
        translation_cache: '翻译缓存',
        translation_window: '上下文窗口',
        manual: '手动',
      },
      triggerLabels: {
        low_confidence: '低置信度',
        sentence_count: '句数触发',
        silence: '静默触发',
        manual: '手动触发',
        semantic_ambiguity: '语义歧义',
        asr_final: 'ASR 完成',
      },
      oldTextLabel: '原文',
      newTextLabel: '修正后',
      sourceTextLabel: '识别原文',
      confidenceLabel: '置信度',
      latencyLabel: '耗时',
      ago: (minutes) => (minutes < 1 ? '刚刚' : `${Math.round(minutes)} 分钟前`),
    },
    summary: {
      ariaLabel: '会话学习摘要',
      title: '学习摘要',
      close: '关闭',
      useLlm: '使用 AI 生成要点与行动项',
      llmHint: '需要已配置的翻译模型；失败时自动回退为本地统计摘要',
      generate: '生成摘要',
      generating: '生成中',
      needActiveSession: '请先开始一次翻译会话。',
      needSubtitles: '本会话还没有字幕，先翻译一段时间再生成摘要。',
      fetchFailed: '摘要生成失败，请稍后重试。',
      duration: '时长',
      segments: '句数',
      revisions: '修正',
      speakers: '说话人',
      keyPoints: '要点',
      actionItems: '行动项',
      keywords: '高频关键词',
      copied: '已复制',
      copyFailed: '复制失败',
      copyMd: '复制摘要',
      downloadMd: '下载摘要 MD',
    },
    glossary: {
      ariaLabel: '术语库管理',
      title: '术语库',
      close: '关闭',
      loading: '加载中',
      loadFailed: '术语库加载失败，请确认后端已启动。',
      searchPlaceholder: '搜索术语…',
      importButton: '导入文件',
      importFailed: '导入失败，请检查文件格式（JSON/CSV）。',
      importEmpty: '没有可导入的新术语（已存在或被跳过）。',
      clearAll: '清空',
      confirmClear: '确认清空全部？',
      sourcePlaceholder: '术语原文，如 Kubernetes',
      targetPlaceholder: '译文，如 容器编排平台',
      keepOriginal: '保持原文不翻译',
      keepOriginalBadge: '保持原文',
      addButton: '添加',
      added: '已添加',
      addFailed: '添加失败（可能已存在或参数非法）',
      sourceRequired: '请填写术语原文。',
      deleteFailed: '删除失败',
      empty: '术语库为空。可手动添加或导入 JSON/CSV 文件。',
      refresh: '刷新',
      deleteEntry: (source) => `删除术语「${source}」`,
    },
    translationMemory: {
      ariaLabel: '翻译记忆库统计',
      title: '翻译记忆库',
      close: '关闭',
      description: '相似句直接复用已翻译结果，减少重复调用翻译 API。命中率越高，节省越多。翻译记忆会跨会话持久化累积。',
      loading: '加载中',
      loadFailed: '翻译记忆库统计加载失败。',
      noData: '当前没有活跃会话的记忆库统计。开始翻译后自动累积。',
      entries: '句对数',
      hits: '命中',
      misses: '未命中',
      written: '写入',
      hitRate: '命中率',
      threshold: '阈值',
      persisted: '跨会话持久化',
      persistedPairs: '持久化句对',
      persistedLanguages: '语言对',
      activeSessions: '活跃会话',
      refresh: '刷新',
      clearAll: '清空',
      confirmClear: '确认清空？',
      noActiveSession: '没有活跃会话可清空。',
    },
    subtitleStyle: {
      ariaLabel: '字幕样式设置',
      title: '字幕样式',
      close: '关闭',
      description: '自定义字幕外观：字号、颜色、背景与位置会实时应用到主界面与悬浮字幕窗，并保存到本地设置。',
      fontSize: '字号',
      fontColor: '字体颜色',
      backgroundColor: '背景颜色',
      backgroundOpacity: '背景不透明度',
      position: '字幕位置',
      positionOptions: {
        bottom: '底部',
        middle: '居中',
        top: '顶部',
      },
      reset: '重置',
      confirmReset: '确认重置？',
      preview: '实时预览',
      saved: '已保存',
    },
    collaboration: {
      ariaLabel: '多人协作翻译',
      title: '协作翻译',
      close: '关闭',
      loading: '加载中',
      loadFailed: '协作房间加载失败，请确认后端已启动。',
      createPlaceholder: '房间标题，如「周三产品评审」',
      createButton: '创建房间',
      createFailed: '创建房间失败。',
      memberNamePlaceholder: '你的昵称（默认“成员”）',
      joinButton: '加入',
      joinFailed: '加入房间失败。',
      leaveButton: '离开',
      destroyButton: '销毁房间',
      confirmDestroy: '确认销毁？',
      refresh: '刷新',
      roomList: '房间列表',
      noRooms: '还没有协作房间。创建一个房间，邀请他人一起观看同一内容并协作修正翻译。',
      members: '成员',
      memberCount: '人',
      membersLabel: '成员列表',
      ownerBadge: '房主',
      revisions: '协作修正（全员可见）',
      segmentIdPlaceholder: '片段 ID（如会话片段序号）',
      revisionPlaceholder: '修正后的译文…',
      submitRevision: '提交修正',
      revisionEmpty: '片段 ID 与修正译文不能为空。',
      revisionFailed: '提交失败，请确认你已在房间内。',
      noRevisions: '还没有协作修正。',
      clearRevisions: '清空修正记录',
    },
    subscription: {
      ariaLabel: '付费订阅与配额',
      title: '订阅与配额',
      close: '关闭',
      loading: '加载中',
      loadFailed: '订阅状态加载失败，请确认后端已启动。',
      noData: '订阅服务不可用。',
      switchFailed: '切换套餐失败。',
      resetFailed: '重置用量失败。',
      refresh: '刷新',
      resetUsage: '重置当天用量',
      currentPlan: '当前套餐',
      dailyUsage: '今日翻译句数',
      remaining: '剩余',
      limitReached: '已达今日配额上限，翻译不中断；升级套餐可继续。',
      unlimited: '企业版无限用量',
      switchPlan: '切换到此套餐',
      plans: '套餐对比',
    },
    cost: {
      ariaLabel: '商用成本模型',
      title: '成本估算',
      close: '关闭',
      loading: '加载中',
      loadFailed: '成本数据加载失败，请确认后端已启动。',
      noData: '成本服务不可用。',
      resetFailed: '重置用量失败。',
      refresh: '刷新',
      resetUsage: '清空累计用量',
      totalSessions: '累计会话',
      totalCost: '累计成本',
      todayCost: '今日成本',
      usage: '用量明细',
      nmtInputTokens: 'NMT 输入 token',
      nmtOutputTokens: 'NMT 输出 token',
      asrSeconds: 'ASR 音频（秒）',
      ttsChars: 'TTS 字符',
      estimateNote: 'token 为基于文本长度的估算（英文≈4 chars/token，中文≈1.5 chars/token）',
      suggestions: '成本建议',
      noSuggestions: '用量正常，无降级建议。',
      today: '今日',
      total: '累计',
      usd: '美元',
      cny: '人民币',
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
      defaultTargetLanguage: '默认目标语言',
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
    idleStartButton: 'Start Interpreting',
    idleFeatures: [
      { icon: '🎯', title: 'Live Interpreting', desc: 'Real-time speech recognition & translation' },
      { icon: '🧠', title: 'Smart Correction', desc: 'Auto-corrects ASR & translation on pauses' },
      { icon: '🔊', title: 'Voice & Subtitle', desc: 'Dual-channel output — read and listen' },
    ],
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
      connectionHint: 'Disconnected — check backend',
      groupLanguages: 'Language & Input',
      groupActions: 'Live Translation',
      settingsButton: 'Settings',
      source: 'Source',
      sourceAriaLabel: 'Source language',
      sourceOptions: SOURCE_OPTIONS_EN,
      detectedSource: (code) => {
        const label = SOURCE_OPTIONS_EN[code as SourceLanguage] ?? code
        return `Detected: ${label}`
      },
      target: 'Target language',
      targetAriaLabel: 'Target language',
      targetOptions: TARGET_OPTIONS_EN,
      translationStyle: 'Translation style',
      translationStyleAriaLabel: 'Translation style',
      translationStyleOptions: TRANSLATION_STYLE_OPTIONS_EN,
      asrHotwords: 'Glossary hotwords for ASR',
      audioSource: 'Audio input',
      audioSourceOptions: [
        { label: 'Microphone', value: 'mic' },
        { label: 'Tab / window', value: 'tab' },
        { label: 'System audio (Tauri)', value: 'system' },
        { label: 'Audio file', value: 'file' },
      ],
      audioFilePick: 'Pick an audio file',
      audioFileLoaded: 'File loaded, translation started',
      audioFileEnded: 'File playback finished',
      audioFileLoadFailed: 'Failed to load or decode the file. Try another audio file.',
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
      openTerminal: 'Terminal',
      openSummary: 'Summary',
      openGlossary: 'Glossary',
      openTranslationMemory: 'Translation Memory',
      openSubtitleStyle: 'Subtitle Style',
      openCollaboration: 'Collaboration',
      openSubscription: 'Subscription',
      openCost: 'Cost',
      openSessionHistory: 'Session history',
      openRevisionTimeline: 'Revision history',
      terminalUnavailable: 'Terminal unavailable',
      glossaryImport: 'Import glossary',
      glossaryImportFailed: 'Failed to parse glossary (JSON/CSV)',
      glossaryImported: 'Glossary applied',
      floatingSubtitlesOn: 'Floating subtitles on',
      floatingSubtitlesOff: 'Floating subtitles off',
      openFloatingSubtitles: 'Open floating subtitles',
      closeFloatingSubtitles: 'Close floating subtitles',
      floatingSubtitlesOpenFailed: 'Could not open the floating subtitle window. Allow browser popups or use the latest Chrome / Edge.',
      systemAudioOn: 'System audio capture on',
      systemAudioOff: 'System audio capture off',
      systemAudioUnavailable: 'System audio unavailable',
      voiceOn: 'Voice on',
      voiceOff: 'Voice off',
      voiceUnavailable: 'Voice unavailable',
      voiceEngine: 'Voice engine',
      voiceEngineOptions: [
        { label: 'Auto (server first)', value: 'auto' },
        { label: 'Local browser voice', value: 'local' },
        { label: 'Server TTS', value: 'backend' },
      ],
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
      latestSummary: (_visibleCount, totalCount) => `${totalCount} subtitles`,
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
      downloadBundle: 'Export all (ZIP)',
      bundleDownloaded: 'Bundle exported',
      jumpToEntry: 'Jump to line',
      seekUnavailable: 'Current source does not support seeking',
      sessionSeconds: 's',
      sessionMinutes: 'm',
      searchPlaceholder: 'Search source or translation…',
      searchClear: 'Clear search',
      searchMatchLabel: (count) => `${count} match${count === 1 ? '' : 'es'} found`,
      searchNoMatch: 'No matching subtitles.',
    },
    sessionHistory: {
      ariaLabel: 'Session history and privacy',
      title: 'Session history',
      closeAriaLabel: 'Close session history',
      refresh: 'Refresh',
      purge: 'Purge expired',
      clearAll: 'Clear all',
      confirmClear: 'Confirm clear?',
      statSessions: 'Sessions',
      statSegments: 'Segments',
      statRetention: 'Retention',
      empty: 'No session records yet.',
      metaSegments: 'Segments',
      metaDuration: 'Duration',
      deleteAriaLabel: 'Delete this session record',
      privacyNote: 'Deleting only removes local session records (including private info); live translation continues.',
      qualityTitle: 'Quality',
      qualityAsr: 'ASR',
      qualityTranslation: 'Translated',
      qualityRevision: 'Revisions',
      qualityDropped: 'Dropped',
      qualityQueue: 'Queue peak',
      qualityReconnect: 'Reconnects',
      qualityLatency: 'Avg latency',
      noQuality: 'No quality metrics for this session.',
    },
    revisionTimeline: {
      ariaLabel: 'Revision history timeline',
      title: 'Revision history',
      close: 'Close',
      empty: 'No revisions in this session yet. Revisions occur on low-confidence ASR, silence, or manual trigger.',
      statTotal: 'Total revisions',
      statAsr: 'ASR fixes',
      statTranslation: 'Translation fixes',
      segmentLabel: 'Segment',
      reasonLabels: {
        asr_correction: 'ASR',
        translation_correction: 'Translation',
      },
      sourceLabels: {
        audio_redecode: 'Audio re-decode',
        llm_post_edit: 'LLM post-edit',
        translation_cache: 'Translation cache',
        translation_window: 'Context window',
        manual: 'Manual',
      },
      triggerLabels: {
        low_confidence: 'Low confidence',
        sentence_count: 'Sentence count',
        silence: 'Silence',
        manual: 'Manual',
        semantic_ambiguity: 'Semantic ambiguity',
        asr_final: 'ASR final',
      },
      oldTextLabel: 'Before',
      newTextLabel: 'After',
      sourceTextLabel: 'ASR source',
      confidenceLabel: 'Confidence',
      latencyLabel: 'Latency',
      ago: (minutes) => (minutes < 1 ? 'just now' : `${Math.round(minutes)} min ago`),
    },
    summary: {
      ariaLabel: 'Session learning summary',
      title: 'Learning summary',
      close: 'Close',
      useLlm: 'Use AI to generate key points and action items',
      llmHint: 'Requires a configured translation model; falls back to local statistics on failure',
      generate: 'Generate summary',
      generating: 'Generating',
      needActiveSession: 'Start a translation session first.',
      needSubtitles: 'This session has no subtitles yet. Translate for a while before generating a summary.',
      fetchFailed: 'Summary generation failed. Try again later.',
      duration: 'Duration',
      segments: 'Segments',
      revisions: 'Revisions',
      speakers: 'Speakers',
      keyPoints: 'Key points',
      actionItems: 'Action items',
      keywords: 'Top keywords',
      copied: 'Copied',
      copyFailed: 'Copy failed',
      copyMd: 'Copy summary',
      downloadMd: 'Download MD',
    },
    glossary: {
      ariaLabel: 'Glossary management',
      title: 'Glossary',
      close: 'Close',
      loading: 'Loading',
      loadFailed: 'Failed to load glossary. Make sure the backend is running.',
      searchPlaceholder: 'Search terms...',
      importButton: 'Import file',
      importFailed: 'Import failed. Check the file format (JSON/CSV).',
      importEmpty: 'No new terms to import (already present or skipped).',
      clearAll: 'Clear',
      confirmClear: 'Clear all?',
      sourcePlaceholder: 'Term, e.g. Kubernetes',
      targetPlaceholder: 'Translation, e.g. container platform',
      keepOriginal: 'Keep original (do not translate)',
      keepOriginalBadge: 'Keep original',
      addButton: 'Add',
      added: 'Added',
      addFailed: 'Add failed (duplicate or invalid input)',
      sourceRequired: 'Term source is required.',
      deleteFailed: 'Delete failed',
      empty: 'The glossary is empty. Add terms manually or import a JSON/CSV file.',
      refresh: 'Refresh',
      deleteEntry: (source) => `Delete term "${source}"`,
    },
    translationMemory: {
      ariaLabel: 'Translation memory stats',
      title: 'Translation Memory',
      close: 'Close',
      description: 'Similar sentences reuse previous translations, reducing repeated API calls. Higher hit rate saves more. Memory accumulates across sessions.',
      loading: 'Loading',
      loadFailed: 'Failed to load translation memory stats.',
      noData: 'No translation memory stats for active sessions. Stats accumulate once translation starts.',
      entries: 'Entries',
      hits: 'Hits',
      misses: 'Misses',
      written: 'Written',
      hitRate: 'Hit rate',
      threshold: 'Threshold',
      persisted: 'Cross-session',
      persistedPairs: 'Persisted pairs',
      persistedLanguages: 'Language pairs',
      activeSessions: 'Active sessions',
      refresh: 'Refresh',
      clearAll: 'Clear',
      confirmClear: 'Clear all?',
      noActiveSession: 'No active session to clear.',
    },
    subtitleStyle: {
      ariaLabel: 'Subtitle style settings',
      title: 'Subtitle Style',
      close: 'Close',
      description: 'Customize subtitle appearance: font size, colors, background and position apply instantly to the main view and floating subtitle windows, and are saved to local settings.',
      fontSize: 'Font size',
      fontColor: 'Font color',
      backgroundColor: 'Background color',
      backgroundOpacity: 'Background opacity',
      position: 'Position',
      positionOptions: {
        bottom: 'Bottom',
        middle: 'Middle',
        top: 'Top',
      },
      reset: 'Reset',
      confirmReset: 'Reset?',
      preview: 'Live preview',
      saved: 'Saved',
    },
    collaboration: {
      ariaLabel: 'Collaborative translation',
      title: 'Collaboration',
      close: 'Close',
      loading: 'Loading',
      loadFailed: 'Failed to load collaboration rooms. Make sure the backend is running.',
      createPlaceholder: 'Room title, e.g. "Wednesday product review"',
      createButton: 'Create room',
      createFailed: 'Failed to create room.',
      memberNamePlaceholder: 'Your nickname (default "Member")',
      joinButton: 'Join',
      joinFailed: 'Failed to join room.',
      leaveButton: 'Leave',
      destroyButton: 'Destroy room',
      confirmDestroy: 'Destroy?',
      refresh: 'Refresh',
      roomList: 'Rooms',
      noRooms: 'No collaboration rooms yet. Create one to watch the same content together and collaboratively refine translations.',
      members: 'Members',
      memberCount: 'people',
      membersLabel: 'Members',
      ownerBadge: 'Owner',
      revisions: 'Collaborative revisions (visible to all)',
      segmentIdPlaceholder: 'Segment ID (e.g. segment index)',
      revisionPlaceholder: 'Corrected translation…',
      submitRevision: 'Submit',
      revisionEmpty: 'Segment ID and corrected text are required.',
      revisionFailed: 'Failed to submit. Make sure you are in the room.',
      noRevisions: 'No collaborative revisions yet.',
      clearRevisions: 'Clear revisions',
    },
    subscription: {
      ariaLabel: 'Subscription and quota',
      title: 'Subscription',
      close: 'Close',
      loading: 'Loading',
      loadFailed: 'Failed to load subscription. Make sure the backend is running.',
      noData: 'Subscription service unavailable.',
      switchFailed: 'Failed to switch plan.',
      resetFailed: 'Failed to reset usage.',
      refresh: 'Refresh',
      resetUsage: 'Reset daily usage',
      currentPlan: 'Current plan',
      dailyUsage: 'Translations today',
      remaining: 'Remaining',
      limitReached: 'Daily quota reached. Translation continues; upgrade to keep translating.',
      unlimited: 'Enterprise unlimited usage',
      switchPlan: 'Switch to this plan',
      plans: 'Plans',
    },
    cost: {
      ariaLabel: 'Cost model',
      title: 'Cost estimate',
      close: 'Close',
      loading: 'Loading',
      loadFailed: 'Failed to load cost data. Make sure the backend is running.',
      noData: 'Cost service unavailable.',
      resetFailed: 'Failed to reset usage.',
      refresh: 'Refresh',
      resetUsage: 'Clear accumulated usage',
      totalSessions: 'Total sessions',
      totalCost: 'Total cost',
      todayCost: 'Today cost',
      usage: 'Usage breakdown',
      nmtInputTokens: 'NMT input tokens',
      nmtOutputTokens: 'NMT output tokens',
      asrSeconds: 'ASR audio (s)',
      ttsChars: 'TTS chars',
      estimateNote: 'Tokens are estimated from text length (~4 chars/token for Latin, ~1.5 for CJK)',
      suggestions: 'Cost suggestions',
      noSuggestions: 'Usage is normal, no downgrade suggestion.',
      today: 'Today',
      total: 'Total',
      usd: 'USD',
      cny: 'CNY',
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
      defaultTargetLanguage: 'Default target',
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
