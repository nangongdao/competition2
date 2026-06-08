# 默认远程 API 启动

## Goal

让网页启动成为默认可用的低资源路径：启动时默认使用远程 OpenAI-compatible ASR API，不下载或加载本地 Whisper 模型；本地 Whisper 只作为用户显式选择的可选模式保留。

## Requirements

* Web/Electron launcher 默认 ASR profile 改为 `remote`。
* `remote` profile 启动后端时必须设置远程 ASR 环境变量，且不得注入 `WHISPER_MODEL`、`WHISPER_DEVICE`、`WHISPER_COMPUTE_TYPE`。
* 后端 ASR 服务支持远程 OpenAI-compatible 转写接口，默认复用已配置的 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`。
* 本地 Whisper profile (`light`, `cpu`, `gpu`, `env`) 继续可用，用户手动选择后才可能加载本地模型。
* 本地设置 API、前端设置面板、类型、文案和示例配置都要接受并展示 `remote` ASR profile。
* README 启动说明必须说明默认不会下载模型，本地模型只在选择本地 profile 时使用。

## Acceptance Criteria

* [ ] `start-web.cmd` 默认启动不会触发 Faster-Whisper 模型下载或加载。
* [ ] 默认 settings snapshot 中 `runtime.asrProfile` 为 `remote`。
* [ ] 选择 `light/cpu/gpu/env` 时仍保留原本本地 ASR 行为。
* [ ] 后端远程 ASR 逻辑有单元测试覆盖，不需要真实网络调用。
* [ ] 现有前端、后端和 launcher 测试通过。

## Definition of Done

* 相关测试已更新并运行。
* README / spec 记录新的默认启动行为。
* 使用 Conventional Commit 提交并推送到现有 PR 分支。

## Technical Approach

新增 `ASR_ENGINE=openai` 远程 ASR 路径，使用 OpenAI SDK 的 audio transcription API。Launcher 默认 profile 改为 `remote` 并注入 `ASR_ENGINE=openai`。远程 ASR 处理前端传来的 float32 PCM，按现有 2 秒窗口合并后转成 WAV，通过 OpenAI-compatible `/audio/transcriptions` 调用转写文本，再交给现有翻译、修正和字幕管线。

## Decision (ADR-lite)

**Context**: 默认本地 Whisper 会下载 HuggingFace 模型，和用户期望的远程 API 默认路径冲突，也导致低配置机器启动失败。

**Decision**: 默认使用远程 OpenAI-compatible ASR，保留本地 Whisper profile 作为显式选项。

**Consequences**: 默认启动不再依赖本地显存/模型缓存；实时转写能力依赖远程供应商是否支持 OpenAI audio transcriptions 接口。若供应商不支持该接口，用户仍可选择本地 Whisper 或更换支持 ASR 的远程服务。

## Out of Scope

* 不删除 Faster-Whisper 依赖和本地 Whisper 实现。
* 不实现 Deepgram/Azure ASR。
* 不改变当前翻译 LLM 的配置存储方式。

## Technical Notes

* `tools/desktop_launcher.py` 当前默认 `DEFAULT_DESKTOP_ASR_PROFILE = "light"`，会注入本地 Whisper 配置。
* `backend/services/asr_service.py` 当前启动时只真正实现 `whisper`，`deepgram`/`azure` 只是占位。
* `backend/services/local_settings.py`、`frontend/src/desktop/settings.ts`、`frontend/src/ui/SettingsPanel.tsx`、`frontend/src/types.ts` 都需要接受 `remote`。
