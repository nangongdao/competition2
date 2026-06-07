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
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    redis_protocol: int = 2

    # ASR
    asr_engine: str = "whisper"
    whisper_model: str = "large-v3"
    whisper_device: str = "cuda"
    whisper_compute_type: str = "float16"

    # NMT
    nmt_engine: str = "claude"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    nmt_model: str = "claude-sonnet-4-20250514"

    # Context window
    context_window_size: int = 10
    segment_ttl_seconds: int = 300

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

    model_config = SettingsConfigDict(
        env_file=tuple(str(path) for path in ENV_FILE_PATHS),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
