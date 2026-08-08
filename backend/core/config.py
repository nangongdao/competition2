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

    # Revision engine
    revision_enabled: bool = True
    revision_trigger_sentences: int = 3
    revision_max_window: int = 8
    revision_silence_seconds: float = 3.0
    asr_correction_confidence_threshold: float = -0.7

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

    # Speaker diarization
    #: 是否启用说话人分离（默认关闭：内置谱特征为占位实现，生产建议接 pyannote）
    diarization_enabled: bool = False
    #: 判定为同一说话人的余弦相似度阈值
    diarization_similarity_threshold: float = 0.95

    model_config = SettingsConfigDict(
        env_file=tuple(str(path) for path in ENV_FILE_PATHS),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
