"""ASR 输出文本轻量后处理（阶段 2：标点、空白、大小写恢复）。

实时同传场景下，Whisper / OpenAI 兼容 ASR 返回的文本往往带有：
- 连续/多余空白（"hello   world "）；
- 中英文之间缺失或多余的空格（"hello世界" / "hello  world"）；
- 句首字母未大写、句尾标点缺失（直播语音常见）；
- 全角/半角标点混用。

这些噪音会直接进入 NMT 翻译 prompt 与字幕渲染，影响翻译质量与观感。
本模块提供纯函数式的轻量规范化，不引入外部依赖、不做语义改写、
不改变专有名词大小写 —— 目标是"去噪音、补标点"，不碰内容。

注意：后处理是**尽力而为**的文本清理，绝不修改语义；对未知语言回退为
仅折叠空白的安全处理。
"""

from __future__ import annotations

import re

#: 连续的空白（含换行）折叠为单个空格
_MULTI_WS = re.compile(r"\s+")

#: 句子结束标点（英文句号/问号/感叹号）
_SENTENCE_END = re.compile(r"[.!?]")

#: 英文单词（含连字符/撇号）
_WORD = re.compile(r"[A-Za-z][A-Za-z''-]*")

#: 中文 CJK 字符范围
_CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")

#: 常见半角标点 -> 后补空格（在英文之间时）
_EN_PUNCT_SPACE = re.compile(r"(?<=[A-Za-z0-9]),\s*|\s+,\s*")


def _is_cjk(text: str) -> bool:
    """判断文本是否以中文为主（CJK 字符占比 >= 30% 视为中文语境）。"""
    if not text:
        return False
    cjk_count = sum(1 for ch in text if _CJK.match(ch))
    return cjk_count / max(len(text), 1) >= 0.3


def collapse_whitespace(text: str) -> str:
    """折叠所有连续空白（含换行）为单个空格，并去除首尾空白。"""
    return _MULTI_WS.sub(" ", text).strip()


def normalize_cjk_spacing(text: str) -> str:
    """中英文混排空格规范化：去掉中文字符与相邻标点之间的多余空格。

    规则（保持简单、安全）：
    - 中文与英文/数字之间的空格**保留**（"AI 助手" 保持）；
    - 中文字符与相邻标点（，。！？；：等）之间的空格**移除**；
    - 逗号后若紧跟英文则补一个空格（"hello,world" -> "hello, world"）。
    """
    if not text:
        return text

    # 中文标点与汉字之间的空格移除："， " -> "，"
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[，。！？；：、）】」』])", "", text)
    text = re.sub(r"(?<=[，。！？；：、）】」』])\s+(?=[\u4e00-\u9fff])", "", text)

    # 汉字之间的多余空格移除（"你好 世界" -> "你好世界"）
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)

    # 半角逗号/句点后紧跟字母且无空格时补一个空格（避免 "hello,world"）
    text = re.sub(r"(?<=[A-Za-z0-9]),([A-Za-z])", r", \1", text)
    return text


def ensure_sentence_ending(text: str) -> str:
    """句子末尾补全标点。

    英文文本：以字母/数字/引号结尾且无结束标点时补句号。
    中文文本：以汉字/引号结尾且无中文结束标点时补句号。
    不做语义判断 —— 直播语音片段本身可能不完整，此处仅保证渲染统一。
    """
    if not text:
        return text
    stripped = text.rstrip()
    if not stripped:
        return text
    last_char = stripped[-1]
    if last_char in ".!?。！？…":
        return stripped

    if _is_cjk(stripped):
        if _CJK.search(stripped):
            return stripped + "。"
        return stripped

    # 英文语境：仅当结尾是字母/数字/引号/右括号时才补句号
    if re.search(r"[A-Za-z0-9\"')\]]$", stripped):
        return stripped + "."
    return stripped


#: 全角数字（０-９）与全角小数点/逗号
_FULLWIDTH_DIGIT = str.maketrans("０１２３４５６７８９", "0123456789")

#: 数字 token：整数 / 小数 / 带千分位 / 百分比 / 货币（$ ¥ € 等前缀）
_NUMBER_TOKEN = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:[$¥€£]\s*)?\d[\d,]*(?:\.\d+)?%?"
    r"(?![A-Za-z0-9])"
)


def normalize_numbers(text: str) -> str:
    """数字格式规范化（阶段 3：数字稳定输出）。

    仅做格式层面的统一，**不改变数值语义**：
    - 全角数字转半角（"１２３" -> "123"）；
    - 去除数字与 % 之间多余空格（"50 %" -> "50%"）；
    - 统一千分位与小数点的全角变体（"１，２３４．５６" -> "1,234.56"）。

    不执行单位换算、不进位、不补千分位 —— 同传场景下保持 ASR 原样
    优先于过度格式化。
    """
    if not text:
        return text

    # 全角数字/标点 -> 半角
    text = text.translate(_FULLWIDTH_DIGIT)
    text = text.replace("，", ",").replace("．", ".")

    # 数字与百分号之间去空格
    text = re.sub(r"(?<=\d)\s+%", "%", text)
    return text


def restore_sentence_capitalization(text: str, *, language: str = "en") -> str:
    """恢复句首字母大写（仅对拉丁字母语言生效，中文不处理）。

    对每个句子结束标点（.!?）之后的第一个字母单词首字母大写；
    不修改专有名词（无法可靠判断，仅处理"句首必然大写"的位置）。
    """
    if _is_cjk(text):
        return text

    def _capitalize_after(match: re.Match[str]) -> str:
        punct = match.group(1)
        following = match.group(2)
        # 保留一个空格：". good" -> ". Good"
        return punct + " " + following[0].upper() + following[1:] if following else punct

    # 句首：整个文本开头
    result = text[:1].upper() + text[1:] if text and text[0].isalpha() else text

    # 每个结束标点后的首字母
    result = re.sub(r"([.!?])\s+([a-z])", _capitalize_after, result)
    return result


def postprocess_asr_text(text: str, *, language: str | None = None) -> str:
    """对外统一入口：对 ASR 输出做轻量后处理。

    Args:
        text: ASR 返回的原始文本。
        language: 语言代码（en / zh-CN / ja ...），影响标点策略；
            未知时按文本内容自动判断中文语境。

    Returns:
        规范化后的文本；空输入返回原值。
    """
    if not text:
        return text

    cleaned = collapse_whitespace(text)
    if not cleaned:
        return text

    cleaned = normalize_cjk_spacing(cleaned)
    # 阶段 3：数字格式规范化（全角转半角、百分号去空格），不改变数值语义
    cleaned = normalize_numbers(cleaned)
    cleaned = ensure_sentence_ending(cleaned)

    is_latin = language in {"en", "es", "fr", "de", "ko", None} or not _is_cjk(cleaned)
    if is_latin and language != "ja":
        cleaned = restore_sentence_capitalization(cleaned)
    return cleaned
