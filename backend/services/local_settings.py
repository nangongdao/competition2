"""Local browser/desktop settings persistence.

The settings file may contain API keys, so public snapshots intentionally expose
only key presence flags and never raw secret values.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat

from loguru import logger

from core.config import REPO_ROOT


CONFIG_DIR = REPO_ROOT / "config"
LOCAL_SETTINGS_PATH = CONFIG_DIR / "desktop-settings.local.json"
EXAMPLE_SETTINGS_PATH = CONFIG_DIR / "desktop-settings.example.json"

SUPPORTED_UI_LANGUAGES = {"zh-CN", "en-US"}
SUPPORTED_TRANSLATION_ENGINES = {"openai", "claude"}
SUPPORTED_ASR_PROFILES = {"remote", "light", "cpu", "gpu", "env"}
SUPPORTED_SOURCE_LANGUAGES = {"auto", "en", "ja", "ko", "es", "fr", "de"}


@dataclass(frozen=True)
class LocalTranslationSettings:
    engine: str
    model: str
    openai_base_url: str
    openai_api_key: str
    anthropic_api_key: str


@dataclass(frozen=True)
class LocalAsrSettings:
    model: str
    openai_base_url: str
    openai_api_key: str


@dataclass(frozen=True)
class LocalRuntimeSettings:
    asr_profile: str
    source_language: str


@dataclass(frozen=True)
class LocalSettings:
    ui_language: str
    translation: LocalTranslationSettings
    asr: LocalAsrSettings
    runtime: LocalRuntimeSettings


def create_default_local_settings() -> LocalSettings:
    return LocalSettings(
        ui_language="zh-CN",
        translation=LocalTranslationSettings(
            engine="openai",
            model="gpt-4o-mini",
            openai_base_url="https://api.openai.com/v1",
            openai_api_key="",
            anthropic_api_key="",
        ),
        asr=LocalAsrSettings(
            model="whisper-1",
            openai_base_url="https://api.openai.com/v1",
            openai_api_key="",
        ),
        runtime=LocalRuntimeSettings(
            asr_profile="remote",
            source_language="en",
        ),
    )


def read_local_settings(
    path: Path = LOCAL_SETTINGS_PATH,
    example_path: Path = EXAMPLE_SETTINGS_PATH,
) -> LocalSettings:
    fallback = create_default_local_settings()

    for candidate_path in (path, example_path):
        if not candidate_path.exists():
            continue

        try:
            raw_settings = json.loads(candidate_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            logger.warning(
                "Failed to read local settings file {}: {}",
                candidate_path,
                error,
            )
            return fallback

        return normalize_local_settings(raw_settings, fallback)

    return fallback


def normalize_local_settings(
    raw_settings: object,
    fallback: LocalSettings | None = None,
) -> LocalSettings:
    base = fallback or create_default_local_settings()
    raw = as_mapping(raw_settings)
    raw_translation = as_mapping(raw.get("translation"))
    raw_asr = as_mapping(raw.get("asr"))
    raw_runtime = as_mapping(raw.get("runtime"))

    return LocalSettings(
        ui_language=pick_allowed(
            raw.get("uiLanguage"),
            SUPPORTED_UI_LANGUAGES,
            base.ui_language,
        ),
        translation=LocalTranslationSettings(
            engine=pick_allowed(
                raw_translation.get("engine"),
                SUPPORTED_TRANSLATION_ENGINES,
                base.translation.engine,
            ),
            model=pick_string(raw_translation.get("model"), base.translation.model),
            openai_base_url=pick_string(
                raw_translation.get("openaiBaseUrl"),
                base.translation.openai_base_url,
            ),
            openai_api_key=pick_string(
                raw_translation.get("openaiApiKey"),
                base.translation.openai_api_key,
            ),
            anthropic_api_key=pick_string(
                raw_translation.get("anthropicApiKey"),
                base.translation.anthropic_api_key,
            ),
        ),
        asr=LocalAsrSettings(
            model=pick_string(raw_asr.get("model"), base.asr.model),
            openai_base_url=pick_string(
                raw_asr.get("openaiBaseUrl"),
                base.asr.openai_base_url,
            ),
            openai_api_key=pick_string(
                raw_asr.get("openaiApiKey"),
                base.asr.openai_api_key,
            ),
        ),
        runtime=LocalRuntimeSettings(
            asr_profile=pick_allowed(
                raw_runtime.get("asrProfile"),
                SUPPORTED_ASR_PROFILES,
                base.runtime.asr_profile,
            ),
            source_language=pick_allowed(
                raw_runtime.get("sourceLanguage"),
                SUPPORTED_SOURCE_LANGUAGES,
                base.runtime.source_language,
            ),
        ),
    )


def merge_local_settings_update(
    update: object,
    current: LocalSettings | None = None,
) -> LocalSettings:
    current_settings = current or read_local_settings()
    raw_update = as_mapping(update)
    raw_translation = as_mapping(raw_update.get("translation"))
    raw_asr = as_mapping(raw_update.get("asr"))
    raw_runtime = as_mapping(raw_update.get("runtime"))

    normalized = normalize_local_settings(
        {
            "uiLanguage": raw_update.get("uiLanguage"),
            "translation": {
                "engine": raw_translation.get("engine"),
                "model": raw_translation.get("model"),
                "openaiBaseUrl": raw_translation.get("openaiBaseUrl"),
            },
            "asr": {
                "model": raw_asr.get("model"),
                "openaiBaseUrl": raw_asr.get("openaiBaseUrl"),
            },
            "runtime": {
                "asrProfile": raw_runtime.get("asrProfile"),
                "sourceLanguage": raw_runtime.get("sourceLanguage"),
            },
        },
        current_settings,
    )

    return LocalSettings(
        ui_language=normalized.ui_language,
        translation=LocalTranslationSettings(
            engine=normalized.translation.engine,
            model=normalized.translation.model,
            openai_base_url=normalized.translation.openai_base_url,
            openai_api_key=resolve_secret_update(
                current_settings.translation.openai_api_key,
                raw_translation.get("openaiApiKey"),
                raw_translation.get("clearOpenaiApiKey"),
            ),
            anthropic_api_key=resolve_secret_update(
                current_settings.translation.anthropic_api_key,
                raw_translation.get("anthropicApiKey"),
                raw_translation.get("clearAnthropicApiKey"),
            ),
        ),
        asr=LocalAsrSettings(
            model=normalized.asr.model,
            openai_base_url=normalized.asr.openai_base_url,
            openai_api_key=resolve_secret_update(
                current_settings.asr.openai_api_key,
                raw_asr.get("openaiApiKey"),
                raw_asr.get("clearOpenaiApiKey"),
            ),
        ),
        runtime=normalized.runtime,
    )


def write_local_settings(
    settings: LocalSettings,
    path: Path = LOCAL_SETTINGS_PATH,
) -> None:
    """原子写入本地设置。

    文件含 API key，必须以 0600 权限创建 —— 先建立权限再写入内容，
    避免出现"短暂可读"的时间窗口。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    payload = f"{json.dumps(create_settings_file_payload(settings), ensure_ascii=False, indent=2)}\n"

    # 以 0600 创建临时文件，写入后再原子替换
    fd = os.open(
        temp_path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        stat.S_IRUSR | stat.S_IWUSR,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    temp_path.replace(path)


def save_local_settings_update(
    update: object,
    path: Path = LOCAL_SETTINGS_PATH,
    example_path: Path = EXAMPLE_SETTINGS_PATH,
) -> LocalSettings:
    current_settings = read_local_settings(path, example_path)
    next_settings = merge_local_settings_update(update, current_settings)
    write_local_settings(next_settings, path)
    return next_settings


def create_settings_snapshot(
    settings: LocalSettings,
    path: Path = LOCAL_SETTINGS_PATH,
) -> dict[str, object]:
    return {
        "available": True,
        "configPath": str(path),
        "uiLanguage": settings.ui_language,
        "translation": {
            "engine": settings.translation.engine,
            "model": settings.translation.model,
            "openaiBaseUrl": settings.translation.openai_base_url,
            "hasOpenaiApiKey": settings.translation.openai_api_key.strip() != "",
            "hasAnthropicApiKey": settings.translation.anthropic_api_key.strip() != "",
        },
        "asr": {
            "model": settings.asr.model,
            "openaiBaseUrl": settings.asr.openai_base_url,
            "hasOpenaiApiKey": settings.asr.openai_api_key.strip() != "",
        },
        "runtime": {
            "asrProfile": settings.runtime.asr_profile,
            "sourceLanguage": settings.runtime.source_language,
        },
    }


def create_settings_file_payload(settings: LocalSettings) -> dict[str, object]:
    return {
        "uiLanguage": settings.ui_language,
        "translation": {
            "engine": settings.translation.engine,
            "model": settings.translation.model,
            "openaiBaseUrl": settings.translation.openai_base_url,
            "openaiApiKey": settings.translation.openai_api_key,
            "anthropicApiKey": settings.translation.anthropic_api_key,
        },
        "asr": {
            "model": settings.asr.model,
            "openaiBaseUrl": settings.asr.openai_base_url,
            "openaiApiKey": settings.asr.openai_api_key,
        },
        "runtime": {
            "asrProfile": settings.runtime.asr_profile,
            "sourceLanguage": settings.runtime.source_language,
        },
    }


def resolve_secret_update(
    current_value: str,
    next_value: object,
    should_clear: object,
) -> str:
    if should_clear is True:
        return ""

    value = next_value.strip() if isinstance(next_value, str) else ""
    return value or current_value


def pick_allowed(value: object, allowed_values: set[str], fallback: str) -> str:
    if not isinstance(value, str):
        return fallback

    trimmed = value.strip()
    return trimmed if trimmed in allowed_values else fallback


def pick_string(value: object, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback

    trimmed = value.strip()
    return trimmed if trimmed else fallback


def as_mapping(value: object) -> Mapping[object, object]:
    if isinstance(value, Mapping):
        return value
    return {}
