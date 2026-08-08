"""Generate placeholder 16 kHz mono PCM WAV fixtures for endurance runs.

真实语音样本应从 LibriSpeech / CommonVoice 等公开数据集获取（标注来源与许可）；
本脚本生成占位音频，用于传输层与管线的冒烟测试。

用法:
    python tools/generate_test_audio.py --type tone --duration 5 --output tests/fixtures/audio/tone.wav
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import struct
import sys
import wave


SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # 16-bit PCM


def generate_samples(
    *,
    source_type: str,
    duration_seconds: float,
    sample_rate: int = SAMPLE_RATE,
) -> list[float]:
    """生成指定类型的 float32 采样序列。"""
    total_frames = max(1, round(duration_seconds * sample_rate))
    if source_type == "silence":
        return [0.0] * total_frames

    if source_type == "tone":
        frequency = 220.0
        return [
            0.2 * math.sin(2 * math.pi * frequency * index / sample_rate)
            for index in range(total_frames)
        ]

    if source_type == "speechlike":
        # 合成"像语音"的占位：440Hz 音素串 + 静音间隔，模拟句子节奏。
        samples: list[float] = []
        phoneme_frames = round(sample_rate * 0.25)
        silence_frames = round(sample_rate * 0.15)
        while len(samples) < total_frames:
            tone = [
                0.15 * math.sin(2 * math.pi * (260 + 180 * math.sin(0.2 * i)) * i / sample_rate)
                for i in range(phoneme_frames)
            ]
            samples.extend(tone)
            samples.extend([0.0] * silence_frames)
        return samples[:total_frames]

    raise ValueError(f"Unsupported type: {source_type}")


def write_wav(path: Path, samples: list[float], sample_rate: int) -> None:
    """将 float32 采样写入 16-bit 单声道 WAV 文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm16 = [
        max(-32768, min(32767, round(sample * 32767)))
        for sample in samples
    ]
    frames = struct.pack(f"<{len(pcm16)}h", *pcm16)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(SAMPLE_WIDTH)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frames)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", choices=["silence", "tone", "speechlike"], default="tone")
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tests/fixtures/audio/tone.wav"),
        help="输出 WAV 路径（默认 tests/fixtures/audio/tone.wav）",
    )
    args = parser.parse_args(argv)

    samples = generate_samples(source_type=args.type, duration_seconds=args.duration)
    write_wav(args.output, samples, SAMPLE_RATE)
    print(f"Wrote {args.output} ({len(samples)} samples, {args.duration:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
