# 测试音频 fixtures

- `silence-3s.wav` / `speechlike-3s.wav`：由 `tools/generate_test_audio.py` 生成的占位音频，
  用于传输层与管线冒烟测试（`endurance_runner --wav`）。
- **验收基线必须使用真实语音**（LibriSpeech / CommonVoice 等公开数据集），
  标注来源与许可，参考 `docs/PERFORMANCE_BASELINE.md`。
- `expected/` 存放人工校对参考译文，供 WER/BLEU 评估（待真实音频后补充）。
