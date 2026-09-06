"""质量回归脚本：运行翻译质量（BLEU）与 ASR 识别质量（WER/CER）评测，
与固化基线对比，超阈值即失败，供 CI 每次提交自动回归。

用法：
    python tools/quality_regression.py
        [--bleu-threshold 0.05]   # BLEU 允许下降的最大绝对量
        [--wer-threshold 0.02]    # WER 允许上升的最大绝对量
        [--json]                  # 以 JSON 输出汇总
        [--update-baseline]       # 更新基线（人为确认后可调用）

数据源（tests/fixtures/quality/）：
- reference-pairs.csv：翻译质量参考/候选句对（同语言，BLEU）
- asr-pairs.csv：ASR 参考转写/候选转写句对（WER/CER）
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "eval_translation_quality.py"
FIXTURES = ROOT / "tests" / "fixtures" / "quality"
BLEU_FIXTURE = FIXTURES / "reference-pairs.csv"
ASR_FIXTURE = FIXTURES / "asr-pairs.csv"
BLEU_BASELINE = ROOT / "reports" / "quality-translation-latest.json"
ASR_BASELINE = ROOT / "reports" / "quality-asr-latest.json"


def _run_eval(args: list[str]) -> dict:
    """调用 eval_translation_quality.py 并解析 JSON 输出。"""
    proc = subprocess.run(
        [sys.executable, str(TOOL), *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"eval_translation_quality.py failed: {proc.stderr or proc.stdout}"
        )
    # 解析输出中第一个 JSON 对象（工具在 --json 模式下输出单个 JSON）。
    out = proc.stdout.strip()
    try:
        return json.loads(out)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Cannot parse eval output: {out!r}") from exc


def _read_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Baseline not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_regression(
    bleu_report: dict,
    bleu_baseline: dict,
    asr_report: dict,
    asr_baseline: dict,
    bleu_threshold: float,
    wer_threshold: float,
) -> dict:
    """根据评测报告与基线判断是否回归，返回汇总 dict（含 ok/failures）。

    纯函数、可单元测试：不访问文件系统，只基于传入的 dict 计算。
    """
    failures: list[str] = []

    base_bleu = float(bleu_baseline.get("corpus_bleu", 0.0))
    cur_bleu = float(bleu_report.get("corpus_bleu", 0.0))
    allowed = max(base_bleu, 1e-9) * bleu_threshold
    bleu_drop = base_bleu - cur_bleu
    bleu_ok = bleu_drop <= allowed
    if not bleu_ok:
        failures.append(
            f"BLEU 回归：基线 {base_bleu:.4f} -> 当前 {cur_bleu:.4f} "
            f"(下降 {bleu_drop:.4f}，允许 {allowed:.4f})"
        )

    base_wer = float(asr_baseline.get("wer", 0.0))
    cur_wer = float(asr_report.get("wer", 0.0))
    wer_rise = cur_wer - base_wer
    wer_ok = wer_rise <= wer_threshold
    if not wer_ok:
        failures.append(
            f"WER 回归：基线 {base_wer:.4f} -> 当前 {cur_wer:.4f} "
            f"(上升 {wer_rise:.4f}，允许 {wer_threshold})"
        )

    return {
        "ok": not failures,
        "bleu": {
            "baseline": base_bleu,
            "current": cur_bleu,
            "drop": bleu_drop,
            "allowed_drop": allowed,
            "ok": bleu_ok,
        },
        "wer": {
            "baseline": base_wer,
            "current": cur_wer,
            "rise": wer_rise,
            "allowed_rise": wer_threshold,
            "ok": wer_ok,
        },
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bleu-threshold", type=float, default=0.05,
                        help="BLEU 允许相对下降的最大比例（相对基线）。默认 0.05")
    parser.add_argument("--wer-threshold", type=float, default=0.02,
                        help="WER 允许上升的最大绝对量。默认 0.02")
    parser.add_argument("--json", action="store_true", help="以 JSON 汇总输出")
    parser.add_argument("--update-baseline", action="store_true",
                        help="评测后更新基线（需人工确认）")
    args = parser.parse_args()

    # ---- 翻译质量（BLEU）----
    bleu_report = _run_eval(["--pair-file", str(BLEU_FIXTURE), "--json"])
    bleu_baseline = _read_json(BLEU_BASELINE)

    # ---- ASR 识别质量（WER/CER）----
    asr_report = _run_eval(["--pair-file", str(ASR_FIXTURE), "--wer", "--json"])
    asr_baseline = _read_json(ASR_BASELINE)

    result = evaluate_regression(
        bleu_report=bleu_report,
        bleu_baseline=bleu_baseline,
        asr_report=asr_report,
        asr_baseline=asr_baseline,
        bleu_threshold=args.bleu_threshold,
        wer_threshold=args.wer_threshold,
    )
    failures = result["failures"]
    base_bleu = result["bleu"]["baseline"]
    cur_bleu = result["bleu"]["current"]
    bleu_ok = result["bleu"]["ok"]
    base_wer = result["wer"]["baseline"]
    cur_wer = result["wer"]["current"]
    wer_ok = result["wer"]["ok"]

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("翻译 + ASR 质量回归")
        print("=" * 48)
        print(
            f"BLEU : 基线 {base_bleu:.4f} -> 当前 {cur_bleu:.4f} "
            f"({'OK' if bleu_ok else 'FAIL'})"
        )
        print(
            f"WER  : 基线 {base_wer:.4f} -> 当前 {cur_wer:.4f} "
            f"({'OK' if wer_ok else 'FAIL'})"
        )
        if failures:
            print("\n失败项：")
            for f in failures:
                print(f"  - {f}")
        else:
            print("\n质量回归通过。")

    # ---- 更新基线 ----
    if args.update_baseline and not failures:
        bleu_baseline.update({
            "corpus_bleu": cur_bleu,
            "avg_sentence_bleu": bleu_report.get("avg_sentence_bleu", 0.0),
            "source": str(BLEU_FIXTURE),
        })
        BLEU_BASELINE.write_text(
            json.dumps(bleu_baseline, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        asr_baseline.update({
            "wer": cur_wer,
            "cer": asr_report.get("cer", 0.0),
            "word_accuracy": asr_report.get("word_accuracy", 0.0),
            "character_accuracy": asr_report.get("character_accuracy", 0.0),
            "source": str(ASR_FIXTURE),
        })
        ASR_BASELINE.write_text(
            json.dumps(asr_baseline, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("基线已更新。")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
