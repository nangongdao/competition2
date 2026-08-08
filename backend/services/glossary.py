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
