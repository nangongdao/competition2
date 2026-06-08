"""Language configuration helpers for live interpretation sessions."""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_SOURCE_LANGUAGE = "en"
DEFAULT_TARGET_LANGUAGE = "zh-CN"

SOURCE_LANGUAGE_LABELS: dict[str, str] = {
    "auto": "the detected source language",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
}

TARGET_LANGUAGE_LABELS: dict[str, str] = {
    "zh": "Chinese",
    "zh-CN": "Simplified Chinese",
}

SOURCE_LANGUAGE_ALIASES: dict[str, str] = {
    "automatic": "auto",
    "detect": "auto",
    "jp": "ja",
    "kr": "ko",
}

TARGET_LANGUAGE_ALIASES: dict[str, str] = {
    "cn": "zh-CN",
    "zh-cn": "zh-CN",
    "zh_hans": "zh-CN",
    "zh-hans": "zh-CN",
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
