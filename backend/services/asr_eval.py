"""ASR 识别质量评测（WER / CER，纯标准库实现）。

为"ASR 准确率可量化回归"提供可持续的评测手段，无需真机/长测：
- **WER（Word Error Rate，词错误率）**：对 Latin/数字为主的文本按空白切词后，
  计算最小编辑距离（插入 + 删除 + 替换），WER = 编辑距离 / 参考词数。
- **CER（Character Error Rate，字符错误率）**：对以中文为主的文本按字符切分后，
  计算最小编辑距离 / 参考字符数。
- **识别准确率（accuracy）**：`1 - WER`（词级）/ `1 - CER`（字符级），
  与 ROADMAP 附录 B 的「ASR 准确率 (WER)」指标目标对齐。

设计说明：
- 最小编辑距离用标准动态规划实现（纯标准库，O(n*m) 时间 / O(min(n,m)) 空间
  的滚动数组优化），无外部依赖。
- 分词规则与 `quality_eval.tokenize` 保持一致：中文按单字符、Latin/数字按空白，
  保证 BLEU 与 WER 的分词口径统一，便于在同一语料上同时做翻译质量与识别质量回归。
"""

from __future__ import annotations

from dataclasses import dataclass


def tokenize(text: str) -> list[str]:
    """与 quality_eval 口径一致的轻量分词。

    中文（CJK）按单字符切分；拉丁/数字按空白切分（连续非空白视为一个 token）。
    用于词级 WER / 字符级 CER 的统一 token 基准。

    Args:
        text: 待分词文本。

    Returns:
        token 列表。
    """
    if not text:
        return []

    tokens: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            tokens.append("".join(current))
            current.clear()

    for ch in text.strip():
        if _is_cjk(ch):
            flush()
            tokens.append(ch)
        elif ch.isspace():
            flush()
        else:
            current.append(ch)
    flush()
    return tokens


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0xF900 <= code <= 0xFAFF
    )


def edit_distance(a: list[str], b: list[str]) -> int:
    """计算两个 token 序列的最小编辑距离（Levenshtein）。

    操作代价统一为 1：插入、删除、替换。

    Args:
        a: 参考序列。
        b: 候选序列（模型输出）。

    Returns:
        最小编辑距离。
    """
    n, m = len(a), len(b)
    if n == 0:
        return m
    if m == 0:
        return n

    # 滚动数组优化：只需两行。
    prev = list(range(m + 1))
    curr = [0] * (m + 1)
    for i in range(1, n + 1):
        curr[0] = i
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,        # 删除
                curr[j - 1] + 1,    # 插入
                prev[j - 1] + cost,  # 替换/匹配
            )
        prev, curr = curr, prev
    return prev[m]


def word_error_rate(reference: str, candidate: str) -> float:
    """词错误率 WER（token 级编辑距离 / 参考 token 数）。

    参考为空时：候选非空则视为完全错误（WER=1.0），否则为 0.0。

    Args:
        reference: 参考（人工转写）文本。
        candidate: 候选（ASR 识别）文本。

    Returns:
        0~1 的 WER 分数（越小越准）。
    """
    ref_tokens = tokenize(reference)
    cand_tokens = tokenize(candidate)
    if not ref_tokens:
        return 1.0 if cand_tokens else 0.0
    dist = edit_distance(ref_tokens, cand_tokens)
    return dist / len(ref_tokens)


def character_error_rate(reference: str, candidate: str) -> float:
    """字符错误率 CER（字符级编辑距离 / 参考字符数）。

    用于中文为主的识别文本；实现与 WER 相同，仅以字符为基本单元。

    Args:
        reference: 参考文本。
        candidate: 候选文本。

    Returns:
        0~1 的 CER 分数（越小越准）。
    """
    ref_chars = list(reference.strip())
    cand_chars = list(candidate.strip())
    if not ref_chars:
        return 1.0 if cand_chars else 0.0
    dist = edit_distance(ref_chars, cand_chars)
    return dist / len(ref_chars)


@dataclass
class AsrEvalReport:
    """ASR 质量评测报告。

    Attributes:
        word_error_rate: 语料级词错误率（参考词数加权）。
        character_error_rate: 语料级字符错误率。
        word_accuracy: 词级识别准确率（1 - WER）。
        character_accuracy: 字符级识别准确率（1 - CER）。
        num_pairs: 评测句对数。
        reference_tokens: 参考 token 总数。
        reference_chars: 参考字符总数。
        edit_ops: 累计编辑距离（词级）。
    """

    word_error_rate: float
    character_error_rate: float
    word_accuracy: float
    character_accuracy: float
    num_pairs: int
    reference_tokens: int
    reference_chars: int
    edit_ops: int

    def to_dict(self) -> dict:
        return {
            "wer": round(self.word_error_rate, 4),
            "cer": round(self.character_error_rate, 4),
            "word_accuracy": round(self.word_accuracy, 4),
            "character_accuracy": round(self.character_accuracy, 4),
            "num_pairs": self.num_pairs,
            "reference_tokens": self.reference_tokens,
            "reference_chars": self.reference_chars,
            "edit_ops": self.edit_ops,
        }


def evaluate(references: list[str], candidates: list[str]) -> AsrEvalReport:
    """对参考/候选句对做整体 ASR 质量评测。

    Args:
        references: 参考（人工转写）句列表。
        candidates: 候选（ASR 识别）句列表。

    Returns:
        AsrEvalReport。

    Raises:
        ValueError: references 与 candidates 长度不一致。
    """
    if len(references) != len(candidates):
        raise ValueError("references and candidates must be the same length")

    total_edit = 0
    total_ref_tokens = 0
    total_edit_chars = 0
    total_ref_chars = 0

    for ref, cand in zip(references, candidates):
        ref_tokens = tokenize(ref)
        cand_tokens = tokenize(cand)
        total_ref_tokens += len(ref_tokens)
        if ref_tokens:
            total_edit += edit_distance(ref_tokens, cand_tokens)
        elif cand_tokens:
            # 参考为空但候选非空，视为候选全为插入错误。
            total_edit += len(cand_tokens)

        ref_chars = list(ref.strip())
        cand_chars = list(cand.strip())
        total_ref_chars += len(ref_chars)
        if ref_chars:
            total_edit_chars += edit_distance(ref_chars, cand_chars)
        elif cand_chars:
            total_edit_chars += len(cand_chars)

    wer = total_edit / total_ref_tokens if total_ref_tokens else (1.0 if total_edit else 0.0)
    cer = total_edit_chars / total_ref_chars if total_ref_chars else (1.0 if total_edit_chars else 0.0)

    return AsrEvalReport(
        word_error_rate=wer,
        character_error_rate=cer,
        word_accuracy=1.0 - wer,
        character_accuracy=1.0 - cer,
        num_pairs=len(references),
        reference_tokens=total_ref_tokens,
        reference_chars=total_ref_chars,
        edit_ops=total_edit,
    )
