"""Language configuration helpers for live interpretation sessions."""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_SOURCE_LANGUAGE = "en"
DEFAULT_TARGET_LANGUAGE = "zh-CN"

SOURCE_LANGUAGE_LABELS: dict[str, str] = {
    "auto": "the detected source language",
    "en": "English",
    "zh-CN": "Simplified Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
}

TARGET_LANGUAGE_LABELS: dict[str, str] = {
    "zh": "Chinese",
    "zh-CN": "Simplified Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
}

SOURCE_LANGUAGE_ALIASES: dict[str, str] = {
    "automatic": "auto",
    "detect": "auto",
    "jp": "ja",
    "kr": "ko",
    "cn": "zh-CN",
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh_hans": "zh-CN",
    "zh-hans": "zh-CN",
}

TARGET_LANGUAGE_ALIASES: dict[str, str] = {
    "cn": "zh-CN",
    "zh-cn": "zh-CN",
    "zh_hans": "zh-CN",
    "zh-hans": "zh-CN",
    "english": "en",
    "jp": "ja",
    "kr": "ko",
    "es-es": "es",
    "fr-fr": "fr",
    "de-de": "de",
}


@dataclass(frozen=True)
class LanguageConfig:
    source_language: str = DEFAULT_SOURCE_LANGUAGE
    target_language: str = DEFAULT_TARGET_LANGUAGE

    @classmethod
    def from_values(
        cls,
        source_language: object,
        target_language: object,
    ) -> "LanguageConfig":
        return cls(
            source_language=normalize_source_language(source_language),
            target_language=normalize_target_language(target_language),
        )

    @property
    def source_label(self) -> str:
        return source_language_label(self.source_language)

    @property
    def target_label(self) -> str:
        return target_language_label(self.target_language)


def normalize_source_language(value: object) -> str:
    return _normalize_language_code(
        value,
        labels=SOURCE_LANGUAGE_LABELS,
        aliases=SOURCE_LANGUAGE_ALIASES,
        default=DEFAULT_SOURCE_LANGUAGE,
    )


def normalize_target_language(value: object) -> str:
    return _normalize_language_code(
        value,
        labels=TARGET_LANGUAGE_LABELS,
        aliases=TARGET_LANGUAGE_ALIASES,
        default=DEFAULT_TARGET_LANGUAGE,
    )


def source_language_label(code: object) -> str:
    normalized = normalize_source_language(code)
    return SOURCE_LANGUAGE_LABELS[normalized]


def target_language_label(code: object) -> str:
    normalized = normalize_target_language(code)
    return TARGET_LANGUAGE_LABELS[normalized]


def whisper_language_code(source_language: object) -> str | None:
    normalized = normalize_source_language(source_language)
    return None if normalized == "auto" else normalized


#: Whisper 检测语言名（verbose_json 顶层 language 字段 / faster-whisper
#: TranscriptionInfo.language）到项目语言代码的映射。Whisper 返回完整
#: 英文语言名（如 ``"english"`` / ``"japanese"``），本项目使用 ISO 代码。
WHISPER_LANGUAGE_TO_CODE: dict[str, str] = {
    "english": "en",
    "chinese": "zh-CN",
    "mandarin": "zh-CN",
    "cantonese": "zh-CN",
    "japanese": "ja",
    "korean": "ko",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    # 未在本项目源语言列表中，但 Whisper 可能返回的其他常见语言
    "russian": "en",
    "italian": "en",
    "portuguese": "en",
    "dutch": "en",
    "polish": "en",
    "arabic": "en",
    "hindi": "en",
    "indonesian": "en",
    "thai": "en",
    "vietnamese": "en",
    "turkish": "en",
    "ukrainian": "en",
}


def detected_language_to_source_code(whisper_language: object) -> str | None:
    """把 Whisper 检测到的语言名映射为项目源语言代码。

    Args:
        whisper_language: Whisper 返回的语言（如 ``"english"`` / ``"en"``）。

    Returns:
        项目源语言代码（en / zh-CN / ja / ko / es / fr / de）；
        未识别或无法映射时返回 None（调用方保持 auto）。
    """
    if not isinstance(whisper_language, str):
        return None
    normalized = whisper_language.strip().lower()
    if not normalized:
        return None
    # 已是项目语言代码（如 faster-whisper 返回 "en" / "ja"；"zh-cn" 归一化为 "zh-CN"）
    normalized_source = normalize_source_language(normalized)
    if normalized_source != DEFAULT_SOURCE_LANGUAGE or normalized in {"en", "zh-cn", "zh"}:
        if normalized_source in SOURCE_LANGUAGE_LABELS:
            return normalized_source
    # 完整语言名映射（Whisper 返回 "english" / "japanese"）
    return WHISPER_LANGUAGE_TO_CODE.get(normalized)


def _normalize_language_code(
    value: object,
    *,
    labels: dict[str, str],
    aliases: dict[str, str],
    default: str,
) -> str:
    if not isinstance(value, str):
        return default

    stripped = value.strip()
    if stripped in labels:
        return stripped

    lowered = stripped.lower()
    aliased = aliases.get(lowered)
    if aliased and aliased in labels:
        return aliased

    if lowered in labels:
        return lowered

    return default
