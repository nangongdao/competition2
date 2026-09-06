"""Translation style presets for NMT prompts (ROADMAP Phase 3).

字幕风格控制：简洁 / 忠实 / 讲义式总结 等预设，通过追加到 system prompt
的方式影响译文输出，无需改动翻译调用链路。
"""

from __future__ import annotations

#: 支持的翻译风格预设。
#: - ``concise``：简洁 —— 紧贴原句长度，去冗余，适合实时字幕
#: - ``faithful``：忠实 —— 完整保留信息与语气，贴近逐句对译
#: - ``lecture``：讲义式 —— 面向学习/复盘，适当展开解释关键概念
STYLE_PRESETS: dict[str, str] = {
    "concise": (
        "Translation style: CONCISE.\n"
        "Keep the translation short and punchy, close to the original sentence "
        "length. Omit filler words while preserving every key fact."
    ),
    "faithful": (
        "Translation style: FAITHFUL.\n"
        "Translate completely and faithfully, preserving the speaker's tone, "
        "emphasis, and every detail. Do not omit or condense information."
    ),
    "lecture": (
        "Translation style: LECTURE NOTES.\n"
        "Translate as clear lecture-style notes: keep it accurate but slightly "
        "expanded when a technical term or concept benefits from a short gloss. "
        "Aim for readability and study value."
    ),
}

#: 默认风格（与历史行为一致：简洁、贴近原句长度）。
DEFAULT_STYLE_PRESET = "concise"

#: 风格别名归一化（容错用户输入）。
STYLE_ALIASES: dict[str, str] = {
    "concise": "concise",
    "brief": "concise",
    "short": "concise",
    "faithful": "faithful",
    "literal": "faithful",
    "lecture": "lecture",
    "lecture_notes": "lecture",
    "lecture-notes": "lecture",
    "summary": "lecture",
    "learning": "lecture",
    "auto": DEFAULT_STYLE_PRESET,
    "default": DEFAULT_STYLE_PRESET,
    "": DEFAULT_STYLE_PRESET,
}


def normalize_style_preset(value: object) -> str:
    """归一化风格预设名；未知值回退到默认风格。

    Args:
        value: 用户传入的风格名（大小写不敏感）。

    Returns:
        规范化后的风格 key（属于 STYLE_PRESETS）。
    """
    if not isinstance(value, str):
        return DEFAULT_STYLE_PRESET
    key = STYLE_ALIASES.get(value.strip().lower())
    if key is not None and key in STYLE_PRESETS:
        return key
    return DEFAULT_STYLE_PRESET


def style_preset_instruction(style_preset: object) -> str:
    """返回风格预设对应的 prompt 指令文本。

    Args:
        style_preset: 风格名（未归一化亦可）。

    Returns:
        指令文本；未知风格返回空字符串（不注入额外约束）。
    """
    key = normalize_style_preset(style_preset)
    if key == DEFAULT_STYLE_PRESET:
        # 默认风格不注入额外指令，保持与历史行为一致
        return ""
    return STYLE_PRESETS[key]
