# 补齐远程 ASR 配置入口

## Goal

让用户可以在网页启动场景中直接配置远程 ASR，包括 OpenAI 官方 Whisper/audio transcriptions API 和兼容接口，避免误把翻译用 chat 模型当成语音识别模型。

## Requirements

* 在本地网页设置文件中增加独立 ASR 配置段，包含 ASR 转写模型、Base URL、API key。
* 网页设置面板显示远程 ASR 配置项，并以写入式密钥输入保存，不在读取快照中暴露真实 key。
* 后端本地设置 API 能读取、保存、清空 ASR API key。
* 网页启动器读取本地设置后，将远程 ASR 配置注入 `ASR_ENGINE=openai`、`ASR_OPENAI_MODEL`、`ASR_OPENAI_BASE_URL`、`ASR_OPENAI_API_KEY`。
* 示例配置和文档明确区分：
  * ASR 使用 `/audio/transcriptions`，默认模型 `whisper-1`，Base URL 默认 `https://api.openai.com/v1`。
  * MT 使用 `/chat/completions`，继续通过 `NMT_MODEL` 配置翻译模型。

## Acceptance Criteria

* [ ] `config/desktop-settings.example.json` 包含远程 ASR 配置示例。
* [ ] 网页设置面板可填写 ASR model/base URL/API key，并显示 key 是否已配置。
* [ ] 保存设置后 `config/desktop-settings.local.json` 中有独立 `asr` 段。
* [ ] 启动器会把 `asr` 段映射到后端 `ASR_OPENAI_*` 环境变量。
* [ ] 相关前后端单元测试通过。
* [ ] 文档说明官方 OpenAI Whisper API 的填写格式。

## Definition of Done

* Tests added/updated where behavior changes.
* Frontend build/tests pass.
* Backend tests for local settings / launcher pass.
* Docs and examples updated.
* Changes committed and pushed to the project PR branch.

## Technical Approach

沿用现有本地设置机制：网页通过后端 loopback `/api/v1/settings/local` 读写 `config/desktop-settings.local.json`，启动器再读取该文件并注入后端环境变量。新增 `asr` JSON 段，不复用 `translation` 段，避免 ASR 与 MT 模型/接口混淆。

## Decision (ADR-lite)

**Context**: 当前 `.env.local` 旧文件不会自动出现新增 ASR 字段，且网页设置只暴露 ASR profile，用户无法在页面里配置 `/audio/transcriptions` 模型。

**Decision**: 新增独立远程 ASR 设置段，并让 `remote` profile 默认使用该段配置。未填写 ASR key/base URL 时仍允许后端 fallback 到通用 OpenAI 配置。

**Consequences**: 用户可以把翻译模型和语音转写模型分开配置；旧设置文件仍兼容；保存后需要重启网页启动器或后端生效。

## Out of Scope

* 不实现新的 ASR 供应商 SDK。
* 不让普通 chat completion 模型直接解析音频。
* 不删除本地 Whisper 可选 profile。

## Technical Notes

* `backend/services/asr_service.py` 已实现 OpenAI-compatible `/audio/transcriptions` 调用。
* `backend/services/local_settings.py` 管理网页本地设置快照和密钥隐藏。
* `tools/desktop_launcher.py` 将本地设置转成后端环境变量。
* `frontend/src/ui/SettingsPanel.tsx` 是网页设置面板。
