# AI 同声传译助手 — 性能验收基线

> 对应 `UPGRADE_PLAN.md` 的 TEST-01 与 `PERFORMANCE_UPGRADE.md` 第 6 节。
> 本表固化端到端性能目标，用 `tools/endurance_runner.py --wav <真实音频>` 验证并写进 README。

## 指标基线

| 指标 | 目标值 | 验证方式 |
|---|---|---|
| ASR 首字延迟 P50 | ≤ 800 ms | `latest_diagnostics.latency.capture_to_asr_ms.avg_ms` |
| 端到端延迟 P50（正常语速） | ≤ 2.0 s，且不随时长增长 | `latency.asr_to_translation_final_ms.avg_ms` |
| 端到端延迟 P95 | ≤ 3.5 s | 采样分位数（runner 扩展） |
| 音频丢弃率 | 0% | `summary.backend_audio_chunks_dropped` |
| 10 分钟内存增长 | ≤ 50 MB | `summary.memory`（RSS 采样） |
| 字幕顺序 | 0 乱序 / 0 缺口 | `summary.subtitle_ordering` |
| WER（清晰英语，可选） | ≤ 15% | 人工校对参考译文（`tests/fixtures/audio/expected/`） |

## 运行方式

```bash
# 1. 启动后端 + Redis（需配置真实 API key）
# 2. 生成或准备 16 kHz 单声道 PCM WAV 测试音频
python tools/generate_test_audio.py --type speechlike --duration 60 --output tests/fixtures/audio/en-short-clear.wav

# 3. 跑耐久测试
python tools/endurance_runner.py --wav tests/fixtures/audio/en-short-clear.wav \
  --duration 60 --output reports/endurance-real-audio.json

# 4. 校验报告
python tools/interpreter_validation_suite.py --endurance reports/endurance-real-audio.json
```

## 测试音频集规划

```
tests/fixtures/audio/
├── en-short-clear.wav       # 30s 清晰英语，安静环境（建议用 LibriSpeech/CommonVoice 片段）
├── en-long-lecture.wav      # 10min 讲座录音，含停顿
├── en-noisy-meeting.wav     # 5min 会议录音，多人+背景噪音
├── en-accented.wav          # 3min 带口音英语
└── expected/
    └── en-short-clear.json  # 人工校对的参考译文（供 WER/BLEU 评估）
```

> 说明：真实语音样本需标注来源与许可（LibriSpeech/CommonVoice 均为公开可商用数据集）。
> 仓库内置的 `generate_test_audio.py` 可生成占位音频用于传输层/管线冒烟，
> 但**验收基线必须用真实语音**。

## 首次真实音频跑测记录（2026-08-02）

**样本**：`tests/fixtures/audio/en-short-clear.wav` —— LibriSpeech test-clean
（`hf-internal-testing/librispeech_asr_dummy`，CC BY 4.0），5.86s 真实英语语音，
参考转写见 `tests/fixtures/audio/expected/en-short-clear.json`。

**环境**：本地 `faster-whisper small`（CPU/int8，无需 API key）+ Redis 本地实例；
NMT 因无上游 key 走降级路径（验证 ARCH-02）。

**命令**：`python -m tools.endurance_runner --wav tests/fixtures/audio/en-short-clear.wav --duration 30`

| 指标 | 实测 | 目标 | 结论 |
|---|---|---|---|
| ASR 片段数 | **5**（此前静音报告为 0） | >0 | ✅ 真实语音驱动了 AI 管线 |
| 翻译 final 数 | 4 | >0 | ✅ 管线执行（NMT 无 key 降级为 `[未翻译]`） |
| 字幕乱序 | 0 乱序 / 0 缺口 | 0 | ✅ 异步乱序保护生效 |
| 音频接收比 | 96%（288/300 chunk） | — | 传输层稳健 |
| 队列满丢弃 | 133 | 0% | ⚠️ CPU Whisper 解码慢于 10 fps 语音，队列溢出 |
| 翻译 final 到达间隔 P50 | 6.5s | ≤2.0s | ⚠️ 受 CPU Whisper 解码速度拖累（非翻译本身） |

> **关键结论**：真实语音已端到端驱动 ASR → 翻译 → 修正全链路（此前唯一的耐久报告
> 输入为静音、`asr_segments: 0`）。当前瓶颈是 **CPU 小模型解码速度**（慢于实时），
> 生产/答辩环境应使用远程 ASR 或 GPU 推理，重新测量后更新本表。

## 结论记录

| 日期 | 音频 | 端到端 P50 | 丢弃率 | 内存增长 | 结论 |
|---|---|---|---|---|---|
| 2026-08-02 | en-short-clear.wav（真实语音） | 6.5s（受 CPU Whisper 拖累） | 44%（CPU 解码瓶颈） | 未采样 | ASR 管线已真实跑通；需换远程/GPU ASR 后复测 |
