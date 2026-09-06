"""翻译质量评测工具：对翻译记忆库句对跑 BLEU，形成可持续的质量回归基线。

用法：
    python tools/eval_translation_quality.py
        [--store config/translation-memory.local.json]
        [--pair en->zh-CN]
        [--limit 500]
        [--max-n 4]
        [--wer]                     # 输出 ASR 质量评测（WER/CER）
        [--output reports/quality-latest.json]  # 固化 JSON 基线
        [--json]

说明：
- 读取本地翻译记忆库（`config/translation-memory.local.json`）的句对，
  把「源句」视为参考、「译文」视为候选，用轻量 BLEU（纯标准库）评测。
- 注意：这里源句与译文语言不同，BLEU 衡量的是"译文内部自洽性/一致性"
  的近似指标，更适合作为**同译多候选之间的相对一致性**评测；真正的
  翻译质量对比需人工参考译文（可用 --pair-file 提供参考/候选 CSV）。
- 也支持 --pair-file csv（reference,candidate 两列），用于人工参考对比。
- `--wer` 模式下输出 ASR 识别质量（WER/CER/准确率），要求参考/候选为
  同语言文本（人工转写 vs ASR 输出），对应 ROADMAP 附录 B 的
  「ASR 准确率 (WER)」指标目标。
- `--output <path>` 将评测报告以 JSON 固化到指定文件（如 reports/），
  便于 CI 或人工持续跟踪质量回归基线。
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _load_module(name: str, path: Path):
    """直接加载纯标准库服务模块，避免触发 backend/services/__init__.py 的
    重依赖导入链（numpy/torch/faster-whisper 等），使质量回归工具可在
    CI 中零重依赖极速运行，且不改变模块行为。"""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_QUALITY_EVAL_PATH = BACKEND_ROOT / "services" / "quality_eval.py"
_ASR_EVAL_PATH = BACKEND_ROOT / "services" / "asr_eval.py"

_quality_eval = _load_module("_quality_eval_mod", _QUALITY_EVAL_PATH)
evaluate = _quality_eval.evaluate


DEFAULT_STORE = BACKEND_ROOT.parent / "config" / "translation-memory.local.json"


def load_store_pairs(path: Path, language_pair: str | None, limit: int) -> list[dict]:
    """从翻译记忆库文件读取句对。"""
    if not path.exists():
        raise FileNotFoundError(f"Translation memory store not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = raw.get("entries", []) if isinstance(raw, dict) else []
    if not isinstance(entries, list):
        return []
    pairs = []
    for entry in entries:
        source = entry.get("source")
        translated = entry.get("translated")
        entry_pair = entry.get("language_pair", "")
        if not isinstance(source, str) or not isinstance(translated, str):
            continue
        if not source.strip() or not translated.strip():
            continue
        if language_pair and entry_pair != language_pair:
            continue
        pairs.append({"source": source.strip(), "translated": translated.strip()})
        if len(pairs) >= limit:
            break
    return pairs


def load_pair_file(path: Path) -> list[tuple[str, str]]:
    """从 CSV（reference,candidate）读取参考/候选句对。"""
    pairs = []
    with path.open(encoding="utf-8") as fh:
        for row in csv.reader(fh):
            if len(row) < 2:
                continue
            ref, cand = row[0].strip(), row[1].strip()
            if ref and cand:
                pairs.append((ref, cand))
    return pairs


def _write_output(path: Path, data: dict) -> None:
    """将评测报告写入指定 JSON 文件（自动创建父目录）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已写入: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="翻译质量评测（轻量 BLEU）")
    parser.add_argument("--store", default=str(DEFAULT_STORE), help="翻译记忆库 JSON 路径")
    parser.add_argument("--pair", default=None, help="语言对过滤，如 en->zh-CN")
    parser.add_argument("--pair-file", default=None, help="参考/候选 CSV（reference,candidate）")
    parser.add_argument("--limit", type=int, default=500, help="最大句对数")
    parser.add_argument("--max-n", type=int, default=4, help="BLEU 最大 n-gram 阶数")
    parser.add_argument("--wer", action="store_true",
                        help="输出 ASR 质量评测（WER/CER），要求参考/候选为同语言")
    parser.add_argument("--output", default=None,
                        help="将 JSON 报告写入指定文件（如 reports/quality-latest.json）以固化基线")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args()

    if args.pair_file:
        pairs = load_pair_file(Path(args.pair_file))
        refs = [p[0] for p in pairs]
        cands = [p[1] for p in pairs]
        source_label = args.pair_file
    else:
        store_pairs = load_store_pairs(Path(args.store), args.pair, args.limit)
        if not store_pairs:
            print(f"No translation-memory pairs found in {args.store}")
            return 1
        # 翻译记忆库是"源->译文"，这里把源当参考、译文当候选，
        # 用于评估译文一致性/自洽性（近似指标）。
        refs = [p["source"] for p in store_pairs]
        cands = [p["translated"] for p in store_pairs]
        source_label = f"{args.store} (pair={args.pair or 'all'})"

    if args.wer:
        # ASR 质量评测：参考/候选应为同语言文本（人工转写 vs ASR 输出）。
        _asr_eval = _load_module("_asr_eval_mod", _ASR_EVAL_PATH)
        asr_evaluate = _asr_eval.evaluate

        asr_report = asr_evaluate(refs, cands)
        result = {
            "source": source_label,
            "pairs": asr_report.num_pairs,
            "wer": asr_report.word_error_rate,
            "cer": asr_report.character_error_rate,
            "word_accuracy": asr_report.word_accuracy,
            "character_accuracy": asr_report.character_accuracy,
        }
        if args.output:
            _write_output(Path(args.output), result)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("ASR 识别质量评测报告")
            print("=" * 40)
            print(f"数据来源     : {source_label}")
            print(f"句对数       : {asr_report.num_pairs}")
            print(f"WER          : {asr_report.word_error_rate:.4f}")
            print(f"CER          : {asr_report.character_error_rate:.4f}")
            print(f"词级准确率   : {asr_report.word_accuracy:.4f}")
            print(f"字符级准确率 : {asr_report.character_accuracy:.4f}")
        return 0

    report = evaluate(refs, cands, max_n=args.max_n)
    result = {
        "source": source_label,
        "pairs": report.num_pairs,
        "max_n": args.max_n,
        "corpus_bleu": report.corpus_bleu,
        "avg_sentence_bleu": report.avg_sentence_bleu,
    }

    if args.output:
        _write_output(Path(args.output), result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("翻译质量评测报告")
        print("=" * 40)
        print(f"数据来源 : {source_label}")
        print(f"句对数   : {report.num_pairs}")
        print(f"语料BLEU : {report.corpus_bleu:.4f}")
        print(f"单句均值 : {report.avg_sentence_bleu:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
