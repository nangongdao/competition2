"""术语表与领域自适应。

技术演讲中的专有名词（人名、产品名、缩写）是翻译质量的最大痛点。
术语表只注入当前句实际命中的条目，避免把整张表塞进每次请求导致 prompt 膨胀。
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class GlossaryEntry:
    """术语表条目。"""

    source: str
    target: str
    #: 是否强制不翻译（如产品名 "Kubernetes" 保持原文）
    keep_original: bool = False


def build_glossary_prompt(glossary: Iterable[GlossaryEntry], text: str) -> str:
    """为当前句构造术语约束提示。

    只注入本句实际命中的术语，避免 prompt 无谓膨胀。

    Args:
        glossary: 术语表条目集合。
        text: 待翻译的句子原文。

    Returns:
        命中术语时的约束提示；未命中时返回空字符串。
    """
    normalized_text = text.lower()
    hits = [entry for entry in glossary if entry.source and entry.source.lower() in normalized_text]
    if not hits:
        return ""

    lines = [
        f"- {entry.source} → {'保持原文' if entry.keep_original else entry.target}"
        for entry in hits
    ]
    return "必须遵守以下术语翻译：\n" + "\n".join(lines)


def parse_glossary_json(raw: object) -> list[GlossaryEntry]:
    """解析 JSON 术语表。

    支持两种结构：
    - 数组：[{"source": "K8s", "target": "Kubernetes"}, ...]
    - 对象：{"entries": [...]}（留出扩展余地）

    Args:
        raw: 反序列化后的 JSON 值。

    Returns:
        解析出的术语表条目列表（忽略非法条目）。
    """
    candidates: object
    if isinstance(raw, dict):
        candidates = raw.get("entries", [])
    else:
        candidates = raw

    if not isinstance(candidates, list):
        return []

    entries: list[GlossaryEntry] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        target = item.get("target")
        if not isinstance(source, str) or not source.strip():
            continue
        if not isinstance(target, str):
            continue
        entries.append(GlossaryEntry(
            source=source.strip(),
            target=target.strip(),
            keep_original=bool(item.get("keep_original", False)),
        ))
    return entries


def normalize_glossary_entries(entries: Iterable[GlossaryEntry], *, max_term_length: int = 64, max_entries: int = 5000) -> list[GlossaryEntry]:
    """对术语表条目做归一化与去重，供模糊匹配回归使用。

    处理四类边界：
    - 空白/纯空白 source 丢弃；超长 source 丢弃（防 prompt 膨胀）。
    - 同一 source 大小写不敏感地去重，后者覆盖前者（与翻译记忆库覆盖语义一致）。
    - keep_original 优先保留（若某条要求保持原文，则不丢失该标记）。
    - 超过 max_entries 时仅保留前 max_entries 条（稳定截断，不抛异常）。

    Args:
        entries: 原始术语表条目。
        max_term_length: 单条 source 的最大字符长度，超长丢弃。
        max_entries: 归一化后最多保留的条目数。

    Returns:
        归一化去重后的术语表条目列表（保持稳定顺序）。
    """
    deduped: dict[str, GlossaryEntry] = {}
    for entry in entries:
        source = entry.source.strip() if entry.source else ""
        if not source or len(source) > max_term_length:
            continue
        key = source.lower()
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = GlossaryEntry(
                source=source,
                target=entry.target.strip(),
                keep_original=entry.keep_original,
            )
            continue
        # 重复 source：合并 keep_original（任一要求保持原文则保持），target 取后者
        deduped[key] = GlossaryEntry(
            source=existing.source,
            target=entry.target.strip() or existing.target,
            keep_original=existing.keep_original or entry.keep_original,
        )
    return list(deduped.values())[:max_entries]


def parse_glossary_csv(text: str) -> list[GlossaryEntry]:
    """解析 CSV 术语表。

    每行一列到三列：source,target[,keep_original]。
    keep_original 可为 "true"/"1"/"yes"（忽略大小写）。

    Args:
        text: CSV 文本内容。

    Returns:
        解析出的术语表条目列表。
    """
    entries: list[GlossaryEntry] = []
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if not row:
            continue
        raw_source = row[0].strip()
        # 跳过空行与 # 注释行
        if not raw_source or raw_source.startswith("#"):
            continue
        source = raw_source
        target = row[1].strip() if len(row) > 1 else ""
        keep_original = (
            len(row) > 2 and row[2].strip().lower() in {"true", "1", "yes"}
        )
        entries.append(GlossaryEntry(source=source, target=target, keep_original=keep_original))
    return entries
