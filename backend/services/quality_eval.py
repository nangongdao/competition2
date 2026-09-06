"""翻译质量评测基准（轻量 BLEU，纯标准库实现）。

为"翻译质量可量化回归"提供可持续的评测手段，无需真机/长测：
- **BLEU-1~4 加权**：sentence-BLEU 与语料级 BLEU（带长度惩罚），
  纯标准库实现，不引入 sacrebleu 重依赖。
- **对现有翻译记忆库句对评测**：`tools/eval_translation_quality.py`
  读取本地翻译记忆库中的句对，输出 BLEU 分数，形成可持续的质量回归基线。

设计说明：
- 分词：中英混合场景，中文按字符切分、拉丁按空白切分（简化版）。
- 语料级 BLEU：参考句与候选句按 n-gram 计数汇总，加平滑（+1）
  避免未命中 n-gram 导致分数骤降为 0。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


def tokenize(text: str) -> list[str]:
    """简单中英混合分词。

    中文（CJK）按单字符切分；拉丁/数字按空白切分（连续非空白视为一个 token）。
    标点保留在 token 中（对 BLEU 的 n-gram 匹配影响可控）。

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


def _ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    """生成长度为 n 的 n-gram 列表。"""
    if n <= 0 or len(tokens) < n:
        return []
    return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def _brevity_penalty(reference_len: int, candidate_len: int) -> float:
    """BLEU 长度惩罚。

    候选过短时惩罚，过长不惩罚。reference_len 为参考句长度。
    """
    if candidate_len == 0:
        return 0.0
    if candidate_len > reference_len:
        return 1.0
    return float(__import__("math").exp(1.0 - reference_len / candidate_len))


def sentence_bleu(reference: str, candidate: str, max_n: int = 4) -> float:
    """单句 BLEU（简化，无语料级 clip 汇总）。

    Args:
        reference: 参考译文。
        candidate: 候选译文（模型输出）。
        max_n: 最大 n-gram 阶数（默认 4）。

    Returns:
        0~1 的 BLEU 分数。
    """
    ref_tokens = tokenize(reference)
    cand_tokens = tokenize(candidate)
    if not ref_tokens or not cand_tokens:
        return 0.0

    scores: list[float] = []
    weights = 1.0 / max_n
    for n in range(1, max_n + 1):
        ref_counts = Counter(_ngrams(ref_tokens, n))
        cand_counts = Counter(_ngrams(cand_tokens, n))
        matches = sum(min(cand_counts[gram], count) for gram, count in ref_counts.items())
        total = sum(cand_counts.values())
        # 加 1 平滑：避免 n>=2 且短句未命中时分数骤降为 0
        precision = (matches + 1.0) / (total + 1.0) if total > 0 else 0.0
        scores.append(precision)

    # 几何平均 + 长度惩罚
    geo = __import__("math").exp(
        sum(weights * __import__("math").log(p) for p in scores if p > 0)
    )
    # 若任一阶 precision 为 0，几何平均为 0，采用加平滑后的近似值
    if geo <= 0:
        geo = sum(scores) / max_n
    bp = _brevity_penalty(len(ref_tokens), len(cand_tokens))
    return max(0.0, min(1.0, geo * bp))


def corpus_bleu(
    references: list[str],
    candidates: list[str],
    max_n: int = 4,
) -> float:
    """语料级 BLEU（clip 计数汇总 + 平滑）。

    Args:
        references: 参考句列表（与 candidates 一一对应）。
        candidates: 候选句列表。
        max_n: 最大 n-gram 阶数。

    Returns:
        0~1 的语料级 BLEU 分数。
    """
    if len(references) != len(candidates):
        raise ValueError("references and candidates must be the same length")
    if not references:
        return 0.0

    total_ref_len = 0
    total_cand_len = 0
    # n-gram 级全局计数
    global_matches: dict[int, int] = {}
    global_cand_counts: dict[int, int] = {}

    for ref, cand in zip(references, candidates):
        ref_tokens = tokenize(ref)
        cand_tokens = tokenize(cand)
        total_ref_len += len(ref_tokens)
        total_cand_len += len(cand_tokens)
        for n in range(1, max_n + 1):
            ref_counts = Counter(_ngrams(ref_tokens, n))
            cand_counts = Counter(_ngrams(cand_tokens, n))
            matches = sum(min(cand_counts[gram], count) for gram, count in ref_counts.items())
            global_matches[n] = global_matches.get(n, 0) + matches
            global_cand_counts[n] = global_cand_counts.get(n, 0) + sum(cand_counts.values())

    if total_cand_len == 0:
        return 0.0

    precisions: list[float] = []
    for n in range(1, max_n + 1):
        matches = global_matches.get(n, 0)
        total = global_cand_counts.get(n, 0)
        # 加 1 平滑
        precision = (matches + 1.0) / (total + 1.0) if total > 0 else 0.0
        precisions.append(precision)

    weights = 1.0 / max_n
    # 几何平均；任一阶为 0 时退化为算术平均（平滑后）
    log_sum = sum(weights * __import__("math").log(p) for p in precisions if p > 0)
    geo = __import__("math").exp(log_sum)
    if geo <= 0:
        geo = sum(precisions) / max_n

    bp = _brevity_penalty(total_ref_len, total_cand_len)
    return max(0.0, min(1.0, geo * bp))


@dataclass
class QualityReport:
    """翻译质量评测报告。

    Attributes:
        corpus_bleu: 语料级 BLEU。
        sentence_scores: 各句 BLEU 分数列表。
        avg_sentence_bleu: 单句 BLEU 平均。
        num_pairs: 句对数。
    """

    corpus_bleu: float
    sentence_scores: list[float]
    avg_sentence_bleu: float
    num_pairs: int

    def to_dict(self) -> dict:
        return {
            "corpus_bleu": round(self.corpus_bleu, 4),
            "avg_sentence_bleu": round(self.avg_sentence_bleu, 4),
            "num_pairs": self.num_pairs,
            "sentence_bleus": [round(s, 4) for s in self.sentence_scores],
        }


def evaluate(references: list[str], candidates: list[str], max_n: int = 4) -> QualityReport:
    """对参考/候选句对做整体质量评测。

    Args:
        references: 参考句列表。
        candidates: 候选句列表。
        max_n: 最大 n-gram 阶数。

    Returns:
        QualityReport。
    """
    if len(references) != len(candidates):
        raise ValueError("references and candidates must be the same length")

    sentence_scores = [
        sentence_bleu(ref, cand, max_n=max_n)
        for ref, cand in zip(references, candidates)
    ]
    corpus = corpus_bleu(references, candidates, max_n=max_n)
    avg = sum(sentence_scores) / len(sentence_scores) if sentence_scores else 0.0
    return QualityReport(
        corpus_bleu=corpus,
        sentence_scores=sentence_scores,
        avg_sentence_bleu=avg,
        num_pairs=len(sentence_scores),
    )
