from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
ENV_FILE_PATHS = (
    REPO_ROOT / ".env",
    BACKEND_ROOT / ".env",
    BACKEND_ROOT / ".env.local",
)


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env."""

    # Service
    #: 默认仅监听本机回环；需要局域网访问时显式配置 HOST。
    #: 竞赛现场为公共 WiFi，绑定 0.0.0.0 会把服务暴露给同网段任何人。
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False

    # CORS：逗号分隔的允许来源列表。桌面/本地场景默认只放行本机前端。
    allowed_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    @property
    def allowed_origin_list(self) -> list[str]:
        """解析为来源列表，去除空白项。"""
        return [
            item.strip()
            for item in self.allowed_origins.split(",")
            if item.strip()
        ]

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_protocol: int = 2
    #: Redis 键前缀，避免与同实例其他应用冲突
    redis_key_prefix: str = "ai-interpreter"

    # ASR
    asr_engine: str = "openai"
    asr_openai_model: str = "whisper-1"
    asr_openai_api_key: str = ""
    asr_openai_base_url: str = ""
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # NMT
    nmt_engine: str = "claude"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    nmt_model: str = "claude-sonnet-4-20250514"
    source_language: str = "en"
    target_language: str = "zh-CN"

    # Context window
    context_window_size: int = 10
    segment_ttl_seconds: int = 300
    #: 上下文分层：最近 N 句保留完整原文（保证指代衔接）
    context_recent_sentences: int = 3
    #: 更早句子的压缩长度上限（字符），超出截断以节省 input token
    context_older_max_chars: int = 40

    # Translation style (Phase 3)
    #: 翻译风格预设：concise（简洁）/ faithful（忠实）/ lecture（讲义式总结）
    translation_style: str = "concise"

    # Revision engine
    revision_enabled: bool = True
    revision_trigger_sentences: int = 3
    revision_max_window: int = 8
    revision_silence_seconds: float = 3.0
    asr_correction_confidence_threshold: float = -0.7
    # 阶段 4：防止过度修正与循环修正
    #: 单个片段允许的最大修正次数（超过后不再修正该片段，防止震荡）
    revision_max_per_segment: int = 2
    #: 同一片段两次修正的最小间隔秒数（节流，避免连续触发）
    revision_min_interval_seconds: float = 5.0
    #: 整场会话总修正次数上限（防御性保护，防 API 成本失控）
    revision_max_total: int = 200

    # Audio
    audio_sample_rate: int = 16000
    audio_chunk_duration_ms: int = 100
    audio_ttl_seconds: int = 120
    audio_queue_max_chunks: int = 100
    diagnostics_emit_interval_seconds: float = 1.0
    #: 单个音频帧的字节上限（100ms @ 16kHz float32 约 6.4KB，留足余量）
    audio_max_chunk_bytes: int = 64 * 1024
    #: 每秒允许的最大音频帧数
    audio_max_chunks_per_second: int = 20
    #: 单会话最大并发翻译数，避免瞬时打爆上游配额
    max_concurrent_translations: int = 2

    # Adaptive VAD segmentation
    #: 是否启用自适应分段（VAD 静音边界 + 时长约束）
    adaptive_segmenter_enabled: bool = True
    #: 最短片段时长（过短缺乏上下文，翻译质量差）
    segment_min_ms: int = 800
    #: 强制切分的最大累积时长（防止长时间无停顿导致延迟过高）
    segment_max_ms: int = 8000
    #: 判定为句子边界的尾部静音时长
    segment_silence_boundary_ms: int = 400
    #: Silero VAD 语音概率阈值
    vad_threshold: float = 0.5
    #: VAD 最小静音时长（毫秒）—— 尾部静音达到该值即断句
    vad_min_silence_ms: int = 500
    #: VAD 最小语音时长（毫秒）—— 过短不切分，避免碎片化
    vad_min_speech_ms: int = 250
    #: VAD 最大句子时长（秒）—— 达到强制断句，防止延迟过高
    vad_max_sentence_s: int = 15

    # Translation memory (TM)
    #: 是否启用翻译记忆（命中时短路 / 注入 few-shot 样例）
    tm_enabled: bool = True
    #: 每个语言对最多缓存句对数
    tm_max_entries_per_pair: int = 200
    #: 精确匹配阈值：相似度达到该值直接短路复用，不再调用上游
    tm_exact_threshold: float = 0.96
    #: 模糊匹配阈值：达到该值的命中作为 few-shot 样例注入 prompt
    tm_fuzzy_threshold: float = 0.72

    # TTS 语音合成
    #: 后端合成引擎：off 禁用 / edge（edge-tts 免费） / openai（OpenAI 兼容）
    tts_engine: str = "off"
    #: edge-tts 语音名（zh-CN 女声；也可选 zh-CN-YunxiNeural 男声等）
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    #: edge-tts 语速（+0% / +10% / -10% 等）
    tts_rate: str = "+0%"
    #: edge-tts 音量（+0% / +10% / -10% 等；越大越响）
    tts_volume: str = "+0%"
    #: 单个片段合成超时（秒）
    tts_timeout_seconds: int = 30
    #: 会话内最多缓存合成结果条数（防止内存无限增长）
    tts_cache_max_entries: int = 256
    #: TTS 合成结果磁盘缓存目录（跨会话复用，重启不丢；为空则仅用内存缓存）
    tts_cache_dir: str = "config/tts-cache"
    #: 磁盘缓存最大条目数（防止磁盘无限膨胀，超过后清理最旧条目）
    tts_cache_max_files: int = 2048

    #: OpenAI 兼容 TTS 引擎配置（tts_engine=openai 时生效）
    tts_openai_model: str = "tts-1"
    tts_openai_base_url: str = "https://api.openai.com/v1"
    tts_openai_api_key: str = ""

    # ASR hotwords (Phase 2: 术语热词注入 ASR)
    #: 是否把术语表 source 注入 ASR 热词，提升技术术语/品牌名识别准确率
    asr_hotwords_enabled: bool = True
    #: 单次 ASR 请求热词上限（防 prompt/hotwords 膨胀拖慢解码）
    asr_hotwords_max_terms: int = 30
    #: 单个热词最大长度（字符），超长条目不参与热词（避免注入噪音）
    asr_hotwords_max_term_length: int = 40

    # ASR 文本后处理（阶段 2：标点/空白/大小写恢复）
    #: 是否对 ASR 输出做轻量文本规范化（折叠空白、补标点、句首大写）
    asr_text_postprocess_enabled: bool = True

    # Speaker diarization
    #: 是否启用说话人分离（默认关闭：内置谱特征为占位实现，生产建议接 pyannote）
    diarization_enabled: bool = False
    #: 判定为同一说话人的余弦相似度阈值
    diarization_similarity_threshold: float = 0.95

    # Translation Memory (V5.3)
    #: 是否启用翻译记忆库（相似句直接复用译文，节省 API 调用）
    translation_memory_enabled: bool = True
    #: 记忆库命中相似度阈值（归一化后 0~1，越大越严格）
    translation_memory_threshold: float = 0.82

    # Subscription (V5.5)
    #: 默认套餐：free | pro | team | enterprise（首次启动生效，之后由 REST/面板切换并持久化）
    subscription_plan: str = "free"

    # 商用成本模型（成本估算与熔断软上限）
    #: NMT 输入 token 单价（美元 / 百万 token）
    cost_nmt_input_per_m: float = 0.15
    #: NMT 输出 token 单价（美元 / 百万 token）
    cost_nmt_output_per_m: float = 0.60
    #: 每日成本软上限（美元），超过后给出降级建议（不中断翻译）
    cost_daily_limit_usd: float = 2.0

    # TTS（后端语音合成）
    #: TTS 引擎：edge（免费、无需 key）| openai（OpenAI 兼容 API）| off
    tts_engine: str = "edge"
    #: edge-tts 语音名（zh-CN 女声；也可选 zh-CN-YunxiNeural 男声等）
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    #: edge-tts 语速（+0% / +10% / -10% 等）
    tts_rate: str = "+0%"
    #: OpenAI TTS 模型名
    tts_openai_model: str = "tts-1"
    tts_openai_base_url: str = "https://api.openai.com/v1"
    tts_openai_api_key: str = ""
    #: 单次合成超时（秒）
    tts_timeout_seconds: int = 30
    #: 合成结果缓存上限（条目数），防长期运行内存无限增长
    tts_cache_max_entries: int = 256

    model_config = SettingsConfigDict(
        env_file=tuple(str(path) for path in ENV_FILE_PATHS),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
