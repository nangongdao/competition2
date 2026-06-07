# AI 同声传译助手 — 后续迭代方向细致方案

> **基础版本**: MVP v0.1.0（已完成）  
> **创建日期**: 2026-06-05  
> **状态**: 待开始  

---

## Current Progress Snapshot - 2026-06-06

This roadmap has moved from an MVP plan into an implemented V2 product slice. The next work should now focus on measured reliability, export validation, and audio-capture validation before adding larger surface-area features.

Implemented capabilities now include:

- Manual revision trigger from the frontend control panel to the backend pipeline.
- Silence-based backend revision checks while preserving the sentence-count trigger.
- Bilingual subtitle data model and rendering path.
- Revision counters and last-revision metadata in the control panel.
- Real low-confidence ASR correction through cached segment audio, Whisper re-decode, and LLM post-edit fallback.
- Revision-cost controls through translation-window caching, unchanged-context skips, and API-call counters.
- Live session diagnostics for latency, dropped chunks, reconnects, revision counters, revision sources, revision triggers, and API-call counters.
- Backend audio-queue diagnostics for current depth, peak depth, capacity, and queue wait latency.
- Reconnect-safe frontend session IDs with per-session ASR stream state and revision cache isolation.
- AudioWorklet-first browser audio capture with a ScriptProcessor fallback for unsupported browsers.
- Client diagnostics now expose the active capture backend for AudioWorklet versus fallback validation.
- Local WebSocket endurance runner that sends paced PCM audio and writes diagnostics JSON reports.
- Endurance runner summaries now expose API-call counters, revision counters, and final-subtitle ordering anomalies for long-run comparison.
- Endurance runner reports can optionally sample runner/backend process RSS memory, summarize start/end/peak/growth values, and fail on memory-growth thresholds.
- Subtitle artifact validation tooling now checks TXT/SRT/VTT/Markdown exports for empty output, cue counts, timestamp overlaps, long gaps, revision markers, transcript counts, and Markdown timeline readability.
- Unified interpreter validation suite now coordinates preflight, optional endurance runs, and optional subtitle artifact checks into one report for real-session acceptance evidence.
- Web-first local launcher that starts the built frontend, FastAPI backend, and
  default browser from a double-click entry without requiring Electron.
- Electron desktop launcher that starts the built frontend, FastAPI backend, and a native desktop window from a double-click entry.
- Desktop launcher backend startup now avoids unhealthy occupied backend ports,
  injects the actual runtime WebSocket URL into Electron, and defaults desktop
  ASR to a low-resource Whisper CPU/int8 profile.
- Electron single-instance, tray restore, minimize-to-tray, and startup-log menu behavior for a more software-like local desktop experience.
- Electron transparent always-on-top floating subtitle overlay so desktop users
  can view translations over other apps while using the main window as the
  control panel.
- Local browser/Electron settings panel now stores local provider/model/API-key
  settings in a Git-ignored settings file, exposes only key presence to the UI,
  injects settings through the launcher on startup, and supports
  Chinese/English interface language switching.
- Windows desktop shortcut installer scripts for desktop launching.
- Durable subtitle history that is separate from the visible subtitle list.
- Subtitle history panel with transcript copy and TXT download.
- SRT subtitle export, VTT subtitle export, and Markdown learning-note export from subtitle history.
- Diagnostics TXT download from the subtitle history panel.
- Optional local Chinese voice playback through the browser/Electron Web Speech API, with queueing, volume control, rate control, revision-aware skip/update behavior, and diagnostics.
- Frontend unit tests for AudioWorklet capture startup, ScriptProcessor fallback, failed-capture cleanup, local TTS queue behavior, TTS numeric guardrails, and TXT/SRT/VTT/Markdown subtitle export formatting.
- Backend unit tests for pipeline queue overflow diagnostics, final ASR-to-translation flow, and closed-session audio rejection.
- English UI copy for the main live-translation controls.
- Mobile control-panel layout fixes for narrow screens, including overflow and touch-target checks.
- Trellis frontend specs updated for durable UI snapshots and fixed overlay panels on mobile.

Most recent recorded validation:

- `npm.cmd run build`
- `npm.cmd run test`
- `node --check frontend\electron\main.cjs`
- `node --check frontend\electron\preload.cjs`
- `.\\backend\\.venv\\Scripts\\python.exe -m unittest tools.test_desktop_launcher`
- `.\\backend\\.venv\\Scripts\\python.exe -m compileall tools\\desktop_launcher.py tools\\test_desktop_launcher.py`
- `npm.cmd audit`
- `.\\backend\\.venv\\Scripts\\python.exe -m unittest backend.test_pipeline`
- `python -m unittest backend.test_endurance_runner`
- `python -m compileall tools backend/test_endurance_runner.py`
- `.\\backend\\.venv\\Scripts\\python.exe -m unittest discover backend`
- `.\\backend\\.venv\\Scripts\\python.exe -m compileall backend\\api backend\\core backend\\models backend\\services backend\\storage`
- `.\\backend\\.venv\\Scripts\\python.exe tools\\endurance_runner.py --help`
- `git diff --check`
- Playwright viewport checks for desktop, mobile, and narrow mobile layouts

Known gaps after the implemented slice:

- The project now has a local endurance runner with queue-depth, received-ratio, subtitle-order, optional memory-growth thresholds, and a combined validation-suite entry point, but still needs a true 30-60 minute live run with Redis, Whisper, provider API keys, and monitored backend PIDs.
- The project now has a secret-safe endurance preflight. The 2026-06-06 local preflight reached Redis and detected Whisper readiness, but the true 30-60 minute baseline is still blocked until a real `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` is configured.
- Export coverage now includes TXT transcript, SRT subtitles, VTT subtitles, Markdown learning notes, diagnostics downloads, unit tests for the formatter outputs, and an artifact validator; the exported files still need real-session timing and readability validation with captured session content.
- Browser audio capture now defaults to `AudioWorklet`, diagnostics show the active backend, and unit tests cover main-path startup, fallback, and failed-capture cleanup; the path still needs real-session comparison against the ScriptProcessor fallback for chunk stability, dropped chunks, and latency.
- Production-grade/provider-backed Chinese TTS playback and full desktop/system-audio capture remain intentionally deferred until the web flow has measurable stability. The current local voice path is browser/Electron Web Speech playback, browser startup is now the recommended local path, and the optional Electron launcher includes a floating subtitle surface, but it is still not a packaged system-audio capture client.

## Priority Improvement Directions - 2026-06-06

The next roadmap slice should make the existing V2 workflow measurable and dependable before expanding the product surface.

1. **Reliability and observability baseline**: run `tools/interpreter_validation_suite.py` first, then run 30-60 minute live sessions through the suite or `tools/endurance_runner.py` after Redis, Whisper, and provider keys are ready. Record client-to-backend received ratio, audio queue depth, queue wait latency, queue drops, reconnects, subtitle ordering, memory growth, ASR latency, translation latency, revision latency, revision sources, and API-call counts.
2. **Export validation and artifact refinement**: validate SRT/VTT timing, revised-segment markers, Markdown note readability, and unchanged TXT/diagnostics behavior in real sessions with `tools/interpreter_validation_suite.py --artifact ...` or `tools/subtitle_artifact_validator.py`.
3. **Browser audio-capture validation**: validate the AudioWorklet capture path in real sessions and compare the recorded capture backend, chunk stability, dropped chunks, and latency against the ScriptProcessor fallback.
4. **Chinese TTS playback**: validate the local Web Speech TTS slice in real sessions, including queue behavior, revised-segment handling, browser/Electron voice availability, and whether provider-backed synthesis is needed for consistent output.
5. **Web-first startup and optional desktop overlay**: use `start-web.cmd` for local demos and reliability runs. Keep Electron floating subtitle overlay validation optional for click-through behavior, z-order, fullscreen behavior, DPI, and multi-monitor placement. Keep full desktop/system-audio capture deferred until the browser workflow is stable, then evaluate Electron/Tauri using real requirements for capture, packaging size, memory usage, and cross-platform support.
6. **Later expansion**: keep multi-language input, glossary support, and learning-assistant features behind the reliability/export/TTS work so core live interpretation quality remains the priority.

---

## 目录

- [产品目标与完成标准](#产品目标与完成标准)
- [总体演进路线](#总体演进路线)
- [V2 — 修正引擎集成与翻译体验增强](#v2--修正引擎集成与翻译体验增强)
- [V3 — 多语种支持与多音频源](#v3--多语种支持与多音频源)
- [V4 — 桌面客户端与全系统音频](#v4--桌面客户端与全系统音频)
- [V5 — 高级特性与商业化](#v5--高级特性与商业化--远期规划-)

---

## 产品目标与完成标准

### 最终产品目标

本项目的目标不是“把一句英文翻译成中文”，而是做成一款真正可持续使用的 **AI 同声传译助手**：

- 面向英语演讲、技术分享、国际会议、网课、直播、录播课程等 **单向音频流** 场景
- 能够将外语内容 **实时、流畅、低延迟** 地翻译成中文
- 以 **字幕或语音** 的方式呈现，帮助用户跟上内容节奏
- 系统具备 **自动修正能力**，可以纠正之前的 ASR 识别错误或翻译错误
- 用户能够长期依赖它获取信息，而不是只做一次演示

### 用户价值

当项目达到理想状态时，用户应当能够：

- 打开一个英语技术分享或国际会议，不暂停也能跟上主要内容
- 在双语字幕和中文字幕之间快速切换
- 在识别错误或误译出现后，看到系统自动回看并修正
- 在不方便盯着屏幕时，切换为中文语音播报
- 在结束后导出双语字幕、中文摘要和学习笔记

### 最终验收标准

项目若要达到“完成度很高”的水平，至少应满足以下标准：

| 编号 | 验收标准 | 说明 |
|------|---------|------|
| AC-G1 | 外语单向音频流可持续实时翻译 | 支持长时间运行，不因会话拉长而明显退化 |
| AC-G2 | 字幕延迟可控且节奏稳定 | 用户能跟上内容，不需频繁暂停回看 |
| AC-G3 | 双语字幕与中文字幕模式完整可用 | 支持仅中文、双语、仅原文 |
| AC-G4 | 自动修正真实可见 | 能修正旧字幕，且区分 ASR 修正与翻译修正 |
| AC-G5 | 支持语音播报 | 可将中文翻译结果转为可听语音输出 |
| AC-G6 | 支持多种输入源 | 浏览器音频、系统音频、麦克风、文件输入 |
| AC-G7 | 支持导出与复盘 | 导出字幕、摘要、笔记等产物 |
| AC-G8 | 有稳定的测试和监控能力 | 关键协议、核心路径、延迟和成本都有可观测性 |

---

## 总体演进路线

下面这条路线描述的是“从当前项目状态出发，如何逐步达到完整产品目标”。它与后文的 V2/V3/V4/V5 细化方案互补：

### 阶段 1：实时性与稳定性

目标：先把“持续听、持续翻、持续出字幕”做到稳定。

关键方向：

- 音频流处理优化，避免 chunk 丢失、重复、错序
- WebSocket 连接恢复、异常状态提示、会话重建
- ASR / NMT / 修正链路的串行或队列化控制，避免并发错位
- 长时间运行稳定性优化，防止内存增长和后台任务泄漏
- 端到端延迟控制在可接受范围内

完成标志：

- 连续运行 30-60 分钟字幕不中断
- 字幕顺序始终与音频顺序一致
- 网络闪断后可恢复

### 阶段 2：ASR 能力升级

目标：让原文识别足够可靠，特别是在技术演讲和术语密集场景中。

关键方向：

- 真正使用缓存音频做 Whisper 二次解码，而不只依赖 LLM 后编辑
- 低置信度片段回看和自动纠错
- 技术术语、品牌名、产品名、缩写热词支持
- 多输入源音频预处理和降噪
- 标点、专有名词、大小写恢复

完成标志：

- 技术术语误识别明显下降
- 低置信度 ASR 片段可进入自动纠错链路
- `asr_correction` 成为真实高频能力而不是保留字段

### 阶段 3：翻译质量升级

目标：让中文译文自然、稳定、一致，而不是逐字直译。

关键方向：

- 上下文窗口优化，按语义段组织上下文
- 术语一致性约束和固定译名
- 字幕风格控制：简洁、忠实、讲义式总结等
- 长句拆分、短句合并、数字和专名稳定输出
- 双语对齐和句级历史保留

完成标志：

- 用户在不暂停的情况下可以理解主要内容
- 同一术语在整场演讲中翻译一致
- 修正后的译文能替换旧译文且不影响阅读节奏

### 阶段 4：修正引擎生产化

目标：把“自动纠正旧错误”打造成产品差异化能力。

关键方向：

- 手动、静默、句数、歧义词、低置信度等多触发策略并存
- 缓存、上下文指纹、相似度阈值等成本控制
- 修正优先级：先纠 ASR，再纠高风险翻译
- 修正历史、修正统计、最近修正状态可观测
- 防止过度修正和循环修正

完成标志：

- 用户能明确感知旧字幕被回看修正
- 修正准确率足以让用户信任系统
- 成本和延迟不会因为修正链路失控

### 阶段 5：字幕体验产品化

目标：字幕不只是能显示，而是适合真实观看和学习。

关键方向：

- 仅中文 / 双语 / 仅原文 模式
- 字体、背景、位置、浮窗样式优化
- 修正高亮和视觉反馈
- 字幕历史面板、最近几分钟回看
- 复制、导出、关键词高亮、时间对齐
- 移动端、桌面端、不同浏览器兼容性

完成标志：

- 用户可以长时间观看，不觉得字幕界面妨碍内容
- 修正发生时能被感知，但不会造成闪烁或干扰

### 阶段 6：语音播报能力

目标：满足“字幕或语音形式呈现”的完整要求。

关键方向：

- 中文 TTS 输出
- 字幕 + 语音双模式
- 播报队列、语速、音量、延迟控制
- 修正场景下的播报策略

完成标志：

- 用户可在不盯屏幕时，仅靠中文语音获取主要内容
- 播报延迟仍然在可接受范围内

### 阶段 7：桌面客户端与系统音频

目标：摆脱浏览器限制，接入更广泛的真实使用场景。

关键方向：

- Tauri / Electron 桌面客户端
- 系统音频抓取
- 多窗口浮层字幕
- 快捷键、托盘、后台运行
- 主流会议/视频应用兼容

完成标志：

- YouTube、Zoom、Teams、网课平台、本地播放器都可使用
- 系统音频可稳定采集

### 阶段 8：多语种扩展

目标：从英译中主路径扩展到多语言输入。

关键方向：

- 源语言自动检测
- 日语、韩语、西班牙语、法语等到中文
- 每种语言独立术语和提示词优化
- 多语种 ASR / NMT 适配

完成标志：

- 英语路径质量最高，其它语言达到稳定演示或实用水平

### 阶段 9：内容沉淀与学习辅助

目标：让系统不仅服务“实时看懂”，还服务“事后复盘和学习”。

关键方向：

- 导出 `.srt` / `.vtt`
- 生成双语 transcript
- 自动摘要、会议纪要、关键词、行动项
- 输出 Markdown 笔记
- 与知识库工具集成

完成标志：

- 观看结束后可直接得到学习产物，而不是只剩看过的过程

### 阶段 10：工程化与生产准备

目标：让系统能持续演进、可部署、可维护。

关键方向：

- 单元测试、集成测试、端到端测试
- 延迟、成本、修正次数、错误率监控
- 配置体系、特性开关、异常恢复
- 数据生命周期和隐私控制

完成标志：

- 关键路径有自动化验证
- 系统出错时可定位、可恢复、可迭代

### 推荐实现顺序

按投入产出比，推荐后续开发顺序如下：

1. 长时稳定性、延迟和资源占用基线验证
2. 导出产物真实会话校验与格式优化
3. AudioWorklet browser capture validation
4. TTS 中文语音播报
5. 桌面端系统音频采集
6. 自动化测试体系与指标监控补强
7. 多语言、术语库与学习辅助能力

---

## V2 — 修正引擎集成与翻译体验增强

> **目标**: 将修正能力从"已实现但未验证"推进到"可演示的差异化功能"。同时提升双语字幕、ASR 纠错等翻译体验。

### V2.1 修正引擎生产化

**Updated status (2026-06-06)**: the core revision-production slice is implemented. `RevisionService` now includes translation-window caching, unchanged-context skips, semantic-ambiguity triggers, API-call counters, and real `asr_correction` through cached audio re-decode with LLM post-edit fallback. The implementation notes below are retained as historical design context; future work should treat them as completed unless validation reveals a regression.

Remaining productionization work:
1. Run 30-60 minute live sessions with Redis, Whisper, and provider API keys.
2. Establish latency, API-call, and revision-quality thresholds from real sessions.
3. Add broader tests around reconnect recovery, queue overflow, subtitle ordering, and revision idempotency.
4. Use the captured metrics to decide whether additional cache tuning or trigger throttling is needed.

#### V2.1.1 修正触发策略升级

```
修正触发策略（升级后）：

┌──────────────────────────────────────────────────────┐
│                  触发条件                             │
├────────────┬─────────────────────────────────────────┤
│ 增量触发    │ 每收到 3 个新 final 句子时触发一次        │
│ 句子结束    │ VAD 检测到句子结束时（silence ≥ 1.5s）   │
│ 静默触发    │ 音频暂停 ≥ 3 秒时                        │
│ 语义触发    │ 关键词/歧义词出现时（如代词、多义词）      │
│ 手动触发    │ 用户点击"修正"按钮（前端新增）            │
└────────────┴─────────────────────────────────────────┘
```

**实现步骤**:

1. **前端新增"修正"按钮** (1 天)
   - 在 `ControlPanel.tsx` 中添加一个 "↻ 修正" 按钮
   - 点击时发送控制消息: `{ type: "manual_revise" }`
   - 添加键盘快捷键 (Ctrl+R)

2. **后端 Pipeline 添加静默检测** (2 天)
   ```python
   # core/pipeline.py 中新增
   class Pipeline:
       def __init__(self, ...):
           ...
           self._last_audio_time: float = 0
           self._silence_timer: Optional[asyncio.Task] = None
       
       async def process_audio(self, audio_chunk: bytes) -> None:
           self._last_audio_time = time.time()
           if self._silence_timer:
               self._silence_timer.cancel()
           self._silence_timer = asyncio.create_task(self._check_silence())
       
       async def _check_silence(self) -> None:
           await asyncio.sleep(3.0)
           if time.time() - self._last_audio_time >= 3.0:
               await self._check_revision()
   ```

3. **语义触发** (3 天)
   ```python
   # services/revision_service.py 中新增
   class RevisionService:
       # 容易因缺少上下文而误译的关键词
       AMBIGUOUS_PATTERNS = [
           r'\b(it|they|he|she|this|that|which)\b',  # 代词指代
           r'\b(bank|run|set|point|right|left)\b',   # 一词多义
       ]
       
       def _check_semantic_ambiguity(self, new_segment: Segment) -> bool:
           """检测新句子是否包含可能改变旧翻译语义的关键词"""
           import re
           for pattern in self.AMBIGUOUS_PATTERNS:
               if re.search(pattern, new_segment.text_asr, re.IGNORECASE):
                   return True
           return False
   ```

#### V2.1.2 修正成本优化

**问题**: 当前`check_and_revise`会对窗口中每句话重新调用LLM翻译，N=8时每次触发最多8次API调用。

**优化方案**: 智能跳过策略 + 缓存

```python
# services/revision_service.py 优化

class RevisionService:
    # 缓存：最近翻译过的(原句hash, 翻译结果)
    _translation_cache: dict[str, str] = {}
    _cache_max_size: int = 100

    def _compute_hash(self, text: str, context_window: str) -> str:
        """计算翻译请求的哈希，用于缓存去重"""
        import hashlib
        content = f"{text}|{context_window}"
        return hashlib.md5(content.encode()).hexdigest()[:16]

    async def check_and_revise(
        self, context: ContextWindow, nmt: NMTService
    ) -> list[RevisionResult]:
        revisions: list[RevisionResult] = []
        segments = context.get_all()
        revisable = segments[-settings.revision_max_window:-1]

        if len(revisable) < 2:
            return revisions

        context_text = context.to_context_text(max_sentences=8)
        
        for seg in revisable:
            cache_key = self._compute_hash(seg.text_asr, context_text)
            
            # 1. 缓存命中 → 跳过
            if cache_key in self._translation_cache:
                continue
            
            # 2. 快速跳过：上次翻译置信度高 + 上下文无变化 → 跳过
            if seg.confidence > 0.9 and not self._context_changed(seg, context):
                continue

            # 3. 需要重新翻译
            new_translation = ""
            async for token in nmt.translate_stream(context, seg):
                if token != "<FINAL>":
                    new_translation += token
                else:
                    break

            # 4. 语义相似度判断（替代编辑距离）
            if self._semantic_differs(seg.text_translated, new_translation):
                revisions.append(RevisionResult(
                    segment_id=seg.id,
                    new_text=new_translation,
                    reason="translation_correction",
                ))
                seg.apply_revision(new_translation, "translation_correction")
                
            # 5. 写入缓存
            self._translation_cache[cache_key] = new_translation
            self._trim_cache()

    def _semantic_differs(self, old_text: str, new_text: str) -> bool:
        """语义级差异判断（改进版）
        
        使用句子嵌入的余弦相似度代替编辑距离，
        更好地处理"语义相同但表述不同"的情况。
        """
        # MVP 方案：继续使用 difflib，降低阈值
        # 生产方案：使用 sentence-transformers 或 LLM-as-judge
        import difflib
        similarity = difflib.SequenceMatcher(None, old_text, new_text).ratio()
        return similarity < 0.80  # 从 0.85 降低到 0.80，减少误触发
```

**实现步骤**:

| 步骤 | 描述 | 预估工时 |
|------|------|---------|
| 1 | 添加翻译缓存（hash 去重） | 1 天 |
| 2 | 添加上下文变化检测 | 0.5 天 |
| 3 | 集成语义相似度判断 | 1.5 天 |
| 4 | 端到端测试 + 调参 | 1 天 |

#### V2.1.3 ASR 纠错路径实现

**当前状态**: 修正引擎只处理翻译纠错，ASR纠错消息类型已定义但从未产生。

**实现方案**: Whisper 重解码 + 交叉验证

```python
# services/revision_service.py 新增

class RevisionService:
    
    async def check_asr_correction(
        self,
        segment: Segment,
        asr: ASRService,
        context: ContextWindow,
    ) -> Optional[RevisionResult]:
        """检查 ASR 识别错误并进行修正
        
        策略：
        1. 用当前上下文窗口的音频重新解码目标 segment
        2. 对比新旧 ASR 文本
        3. 如果不同，推送 ASR 修正
        """
        # 方法1：让 Whisper 用更长上下文重新解码
        # （需要保留原始音频片段——见 V2.1.4 音频归档）
        
        # 方法2：用 LLM 进行 ASR 后编辑
        # "Given the context: [前后的英文原文], 
        #  is the sentence 'XXX' correctly transcribed? 
        #  If not, provide the corrected version."
        
        prompt = f"""You are an ASR post-editor. Given the surrounding context, check if the middle sentence has transcription errors.

Previous sentence: "{context.get_before(segment.id)}"
Current sentence: "{segment.text_asr}"  
Next sentence: "{context.get_after(segment.id)}"

If the current sentence has obvious transcription errors (homophones, missing words, wrong word boundaries), output the corrected version.
If it seems correct, output "CORRECT".

Corrected:"""

        # 调用 LLM（使用 NMT 服务的客户端，但用不同 system prompt）
        corrected = await self._llm_correct(nmt, prompt)
        
        if corrected and corrected.strip() != "CORRECT":
            # 对比原文与修正文
            if self._should_revise(segment.text_asr, corrected):
                return RevisionResult(
                    segment_id=segment.id,
                    new_text=corrected,
                    reason="asr_correction",
                )
        
        return None
```

#### V2.1.4 音频归档（ASR 纠错前提）

ASR 纠错需要保留原始音频才能重新解码。当前系统收到音频chunk后立即送入ASR，解码完成后丢弃。

```python
# services/context_manager.py 新增

class ContextManager:
    
    async def save_audio_chunk(
        self, session_id: str, segment_id: str, audio_data: bytes
    ) -> None:
        """保存某段音频的原始数据（用于后续 ASR 纠错重解码）"""
        key = f"session:{session_id}:audio:{segment_id}"
        await self._redis.set(key, audio_data, ex=settings.audio_ttl_seconds)
    
    async def get_audio_chunk(
        self, session_id: str, segment_id: str
    ) -> Optional[bytes]:
        """获取某段音频的原始数据"""
        key = f"session:{session_id}:audio:{segment_id}"
        return await self._redis.get(key)
```

**配置新增项**:
```python
# core/config.py
audio_ttl_seconds: int = 120  # 音频缓存 2 分钟，足够修正窗口
```

**Pipeline 改造**:
```python
# core/pipeline.py — 在 _handle_asr_final 中保存音频
async def _handle_asr_final(self, text: str, confidence: float) -> None:
    ...
    # 保存该段的原始音频（用于后续 ASR 纠错）
    segment_audio = self._asr.get_last_audio_chunk()
    await self._ctx.save_audio_chunk(
        self.session_id, segment.id, segment_audio
    )
    ...
```

### V2.2 双语字幕模式

**目标**: 同时显示英文原文（识别文本）+ 中文译文（翻译文本）

#### V2.2.1 数据模型扩展

```typescript
// frontend/src/types.ts 新增

/** 字幕显示模式 */
export type SubtitleMode = 'zh_only' | 'bilingual' | 'en_only'

/** 双语字幕条目 */
export interface BilingualSubtitleEntry {
  segmentId: string
  sourceText: string      // 原文（英文 ASR 结果）
  translatedText: string  // 译文（中文翻译）
  isPartial: boolean
  isRevised: boolean
  timestamp: number
}
```

#### V2.2.2 后端消息扩展

```python
# models/messages.py 新增字段

@dataclass
class ServerMessage:
    type: Literal[
        "asr_partial",
        "asr_final", 
        "translation_token",
        "revision",
        "bilingual_update",  # 新增：双语同步更新
        "status",
        "error",
    ]
    ...
    source_text: Optional[str] = None  # 新增：原文文本（双语模式用）
```

#### V2.2.3 前端渲染器改造

```typescript
// subtitle/SubtitleRenderer.ts 改造

export class SubtitleRenderer {
  
  renderBilingual(entry: BilingualSubtitleEntry): void {
    let el = this._entries.get(entry.segmentId)
    
    if (!el) {
      el = this._createBilingualElement(entry)
      this._overlay.appendChild(el)
      this._entries.set(entry.segmentId, el)
    } else {
      this._updateBilingualText(el, entry)
    }
    
    this._trim()
  }

  private _createBilingualElement(entry: BilingualSubtitleEntry): HTMLDivElement {
    const wrapper = document.createElement('div')
    wrapper.className = 'subtitle-entry bilingual'
    wrapper.dataset.segmentId = entry.segmentId
    wrapper.style.cssText = `
      display: inline-block;
      padding: 8px 16px;
      background: rgba(0, 0, 0, 0.8);
      border-radius: 8px;
      color: #fff;
      font-size: 16px;
      line-height: 1.6;
      text-align: center;
      max-width: 100%;
      word-break: break-word;
    `

    // 第一行：英文原文（较小、较暗）
    const sourceLine = document.createElement('div')
    sourceLine.className = 'subtitle-source'
    sourceLine.style.cssText = `
      font-size: 13px;
      color: #aaa;
      margin-bottom: 2px;
    `
    sourceLine.textContent = entry.sourceText
    wrapper.appendChild(sourceLine)

    // 第二行：中文译文（较大、较亮）
    const targetLine = document.createElement('div')
    targetLine.className = 'subtitle-target'
    targetLine.style.cssText = `
      font-size: 18px;
      color: #fff;
      font-weight: 500;
    `
    targetLine.textContent = entry.translatedText
    wrapper.appendChild(targetLine)

    return wrapper
  }
}
```

#### V2.2.4 显示模式切换

```tsx
// ui/ControlPanel.tsx 新增

const SubtitleModeSelector: React.FC<{
  mode: SubtitleMode
  onChange: (mode: SubtitleMode) => void
}> = ({ mode, onChange }) => (
  <div style={{
    display: 'flex',
    gap: '4px',
    background: 'rgba(255,255,255,0.1)',
    borderRadius: '6px',
    padding: '2px',
  }}>
    {([
      ['zh_only', '中文'],
      ['bilingual', '双语'],
      ['en_only', '英文'],
    ] as const).map(([value, label]) => (
      <button
        key={value}
        onClick={() => onChange(value)}
        style={{
          padding: '4px 10px',
          border: 'none',
          borderRadius: '4px',
          fontSize: '12px',
          cursor: 'pointer',
          background: mode === value ? '#4caf50' : 'transparent',
          color: mode === value ? '#fff' : '#aaa',
        }}
      >
        {label}
      </button>
    ))}
  </div>
)
```

**实现步骤**:

| 步骤 | 描述 | 预估工时 |
|------|------|---------|
| 1 | 后端消息协议扩展 (bilingual_update) | 1 天 |
| 2 | Pipeline 中同时推送原文和译文 | 0.5 天 |
| 3 | SubtitleRenderer 双语渲染 | 1.5 天 |
| 4 | 控制面板模式切换 UI | 1 天 |
| 5 | 端到端测试 | 0.5 天 |

### V2.3 字幕样式可配置

**目标**: 允许用户调整字幕的字体大小、颜色、背景透明度、位置。

#### 设计

```typescript
// frontend/src/types.ts 新增

export interface SubtitleStyleConfig {
  fontSize: number          // 12-32, 默认 18
  fontColor: string         // 默认 '#ffffff'
  backgroundColor: string   // 默认 'rgba(0,0,0,0.75)'
  backgroundOpacity: number // 0-1, 默认 0.75
  position: 'bottom' | 'top' | 'middle'
  bottomOffset: number      // 距底部百分比, 默认 12
}
```

```tsx
// ui/StyleSettings.tsx（新组件）

export const StyleSettings: React.FC<{
  config: SubtitleStyleConfig
  onChange: (config: SubtitleStyleConfig) => void
  onClose: () => void
}> = ({ config, onChange, onClose }) => {
  return (
    <div style={settingsPanelStyle}>
      <h3>字幕样式设置</h3>
      
      {/* 字体大小滑块 */}
      <label>
        字体大小: {config.fontSize}px
        <input type="range" min="12" max="32" value={config.fontSize}
          onChange={e => onChange({...config, fontSize: Number(e.target.value)})}
        />
      </label>
      
      {/* 字体颜色选择器 */}
      <label>
        字体颜色:
        <input type="color" value={config.fontColor}
          onChange={e => onChange({...config, fontColor: e.target.value})}
        />
      </label>
      
      {/* 背景透明度 */}
      <label>
        背景透明度: {Math.round(config.backgroundOpacity * 100)}%
        <input type="range" min="0" max="100" 
          value={Math.round(config.backgroundOpacity * 100)}
          onChange={e => onChange({...config, backgroundOpacity: Number(e.target.value) / 100})}
        />
      </label>
      
      {/* 位置选择 */}
      <label>
        字幕位置:
        <select value={config.position}
          onChange={e => onChange({...config, position: e.target.value as any})}
        >
          <option value="bottom">底部</option>
          <option value="top">顶部</option>
          <option value="middle">中间</option>
        </select>
      </label>
    </div>
  )
}
```

### V2.4 VAD 句子切分优化

**当前状态**: 使用 Whisper 内置 VAD (silero-vad)，但配置不灵活。

**优化方案**:

```python
# services/asr_service.py 改造

class ASRService:
    def __init__(self):
        ...
        # VAD 参数可配置
        self._vad_threshold: float = 0.5       # 语音检测阈值
        self._min_silence_duration_ms: int = 500  # 最小静音时长（断句用）
        self._min_speech_duration_ms: int = 250   # 最小语音时长
        self._max_sentence_duration_s: int = 15   # 最大句子时长（强制断句）
    
    async def initialize(self) -> None:
        if self._engine == "whisper":
            await self._init_whisper()
            # 独立初始化 VAD（Silero VAD）
            await self._init_vad()
    
    async def _init_vad(self) -> None:
        """初始化独立的 VAD 模型"""
        import torch
        self._vad_model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False,
        )
        self._vad_model.eval()
        (self._get_speech_timestamps,
         self._save_audio,
         self._read_audio,
         self._vad_collector) = utils
```

**配置新增项**:
```python
# core/config.py 新增
vad_threshold: float = 0.5
vad_min_silence_ms: int = 500
vad_min_speech_ms: int = 250
vad_max_sentence_s: int = 15
```

### V2.5 V2 验收标准

| 编号 | 验收标准 | 验证方法 |
|------|---------|---------|
| AC-V2.1 | 修正引擎在生产环境能正确触发翻译修正 | 播放含歧义词的英语演讲，观察修正次数 |
| AC-V2.2 | ASR 纠错路径能正确修正同音词错误 | 注入含 "their/there" 等词的音频，验证修正 |
| AC-V2.3 | 双语模式下原文和译文同时显示 | 启动双语模式，验证两行字幕 |
| AC-V2.4 | 字幕样式修改立即生效 | 拖动滑块，观察字幕实时变化 |
| AC-V2.5 | VAD 断句准确率 > 90% | 统计断句位置与实际句子边界的一致性 |
| AC-V2.6 | 修正触发不会造成 UI 抖动 | 多次修正，观察字幕是否平滑过渡 |

**V2 总预估工时**: 10-15 个工作日

---

## V3 — 多语种支持与多音频源

> **目标**: 从"英语→中文"扩展到多语种互译。同时支持麦克风输入、音频文件上传等多种音频源。

### V3.1 多语种互译

#### V3.1.1 整体策略

```
语言支持规划：

Phase 1 (V3): 英语 ↔ 中文（双向）
Phase 2 (V3.1): + 日语、韩语
Phase 3 (V3.2): + 法语、德语、西班牙语
Phase 4 (V3.3): + 其余主要语种（共 12+ 种）
```

#### V3.1.2 后端语言路由

```python
# services/language_router.py（新模块）

from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class LanguagePair:
    source: str  # ISO 639-1 code
    target: str

# 语言能力矩阵
LANGUAGE_CAPABILITIES = {
    # ASR 支持（Whisper 原生支持 99 种语言）
    "asr": {
        "en", "zh", "ja", "ko", "fr", "de", "es",
        "pt", "ru", "ar", "hi", "it", "nl", "pl",
        "tr", "vi", "th", "sv", "da", "fi", "no",
        # ... 更多
    },
    
    # NMT 支持（LLM 支持的主流转译语言）
    "nmt": {
        ("en", "zh"), ("zh", "en"),
        ("en", "ja"), ("ja", "en"),
        ("en", "ko"), ("ko", "en"),
        ("en", "fr"), ("fr", "en"),
        ("en", "de"), ("de", "en"),
        ("en", "es"), ("es", "en"),
        ("ja", "zh"), ("zh", "ja"),
        ("ko", "zh"), ("zh", "ko"),
        # ... 更多
    },
}

class LanguageRouter:
    """语言路由器
    
    根据用户选择的语言对，决定 ASR 语言参数和 NMT prompt。
    """
    
    @staticmethod
    def get_asr_language(source_lang: str) -> str:
        """获取 ASR 的语言参数
        
        Whisper 使用 ISO 639-1 或全语言名称。
        """
        WHISPER_LANG_MAP = {
            "en": "en",
            "zh": "zh",
            "ja": "ja",
            "ko": "ko",
            "fr": "fr",
            "de": "de",
            "es": "es",
            "auto": None,  # None = Whisper 自动检测
        }
        return WHISPER_LANG_MAP.get(source_lang, source_lang)
    
    @staticmethod
    def get_nmt_prompt(pair: LanguagePair) -> str:
        """根据语言对生成翻译 system prompt"""
        
        LANG_NAMES = {
            "en": "English",
            "zh": "Simplified Chinese (简体中文)",
            "ja": "Japanese (日本語)",
            "ko": "Korean (한국어)",
            "fr": "French (Français)",
            "de": "German (Deutsch)",
            "es": "Spanish (Español)",
        }
        
        source_name = LANG_NAMES.get(pair.source, pair.source)
        target_name = LANG_NAMES.get(pair.target, pair.target)
        
        return f"""You are a real-time interpreter translating {source_name} to {target_name}.

Rules:
1. Translate naturally and fluently into {target_name}
2. Preserve technical terms, proper nouns, and brand names in their original form
3. Maintain the speaker's tone consistently
4. Use context from previous sentences to resolve ambiguities
5. Output ONLY the translation, no explanations
6. Keep the translation concise — match the original sentence length"""
    
    @staticmethod
    def validate_pair(pair: LanguagePair) -> bool:
        """验证语言对是否支持"""
        return (pair.source, pair.target) in LANGUAGE_CAPABILITIES["nmt"]
```

#### V3.1.3 Pipeline 改造

```python
# core/pipeline.py 改造

class Pipeline:
    def __init__(
        self,
        session_id: str,
        asr: ASRService,
        nmt: NMTService,
        ctx_manager: ContextManager,
        revision: Optional[RevisionService] = None,
        language_pair: LanguagePair = LanguagePair("en", "zh"),  # 新增
    ):
        ...
        self._language_pair = language_pair
        self._language_router = LanguageRouter()
    
    async def update_language(self, pair: LanguagePair) -> None:
        """运行时切换语言对"""
        if not self._language_router.validate_pair(pair):
            raise ValueError(f"Unsupported language pair: {pair.source}→{pair.target}")
        
        self._language_pair = pair
        
        # 更新 ASR 语言
        asr_lang = self._language_router.get_asr_language(pair.source)
        await self._asr.set_language(asr_lang)
        
        # 更新 NMT prompt
        nmt_prompt = self._language_router.get_nmt_prompt(pair)
        self._nmt.set_system_prompt(nmt_prompt)
        
        # 通知前端
        if self._on_message:
            await self._on_message({
                "type": "status",
                "code": "LANGUAGE_UPDATED",
                "message": f"Language pair updated: {pair.source} → {pair.target}",
            })
```

#### V3.1.4 前端语言选择器

```tsx
// ui/LanguageSelector.tsx（新组件）

const LANGUAGES = [
  { code: 'en', name: 'English', flag: '🇺🇸' },
  { code: 'zh', name: '简体中文', flag: '🇨🇳' },
  { code: 'ja', name: '日本語', flag: '🇯🇵' },
  { code: 'ko', name: '한국어', flag: '🇰🇷' },
  { code: 'fr', name: 'Français', flag: '🇫🇷' },
  { code: 'de', name: 'Deutsch', flag: '🇩🇪' },
  { code: 'es', name: 'Español', flag: '🇪🇸' },
  { code: 'auto', name: '自动检测', flag: '🌐' },
]

export const LanguageSelector: React.FC<{
  sourceLang: string
  targetLang: string
  onChange: (source: string, target: string) => void
}> = ({ sourceLang, targetLang, onChange }) => {
  const [open, setOpen] = useState(false)
  
  return (
    <div style={containerStyle}>
      <button onClick={() => setOpen(!open)} style={triggerStyle}>
        {LANGUAGES.find(l => l.code === sourceLang)?.flag} 
        → 
        {LANGUAGES.find(l => l.code === targetLang)?.flag}
        {' '}▾
      </button>
      
      {open && (
        <div style={dropdownStyle}>
          <div style={columnStyle}>
            <div style={labelStyle}>源语言</div>
            {LANGUAGES.map(lang => (
              <button
                key={`src-${lang.code}`}
                onClick={() => { onChange(lang.code, targetLang); setOpen(false) }}
                style={{
                  ...optionStyle,
                  background: sourceLang === lang.code ? '#4caf50' : 'transparent',
                }}
              >
                {lang.flag} {lang.name}
              </button>
            ))}
          </div>
          
          <div style={swapStyle}>
            <button onClick={() => onChange(targetLang, sourceLang)}
              style={swapButtonStyle}>⇄</button>
          </div>
          
          <div style={columnStyle}>
            <div style={labelStyle}>目标语言</div>
            {LANGUAGES.filter(l => l.code !== 'auto').map(lang => (
              <button
                key={`tgt-${lang.code}`}
                onClick={() => { onChange(sourceLang, lang.code); setOpen(false) }}
                style={{
                  ...optionStyle,
                  background: targetLang === lang.code ? '#4caf50' : 'transparent',
                }}
              >
                {lang.flag} {lang.name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
```

### V3.2 多音频源支持

#### V3.2.1 音频源抽象层

```typescript
// frontend/src/audio/AudioSourceManager.ts（新模块）

/** 音频源接口 */
interface AudioSource {
  /** 音频源类型标识 */
  readonly type: 'tab' | 'microphone' | 'file'
  /** 音频源显示名称 */
  readonly label: string
  /** 开始捕获 */
  start(): Promise<void>
  /** 停止捕获 */
  stop(): void
  /** 音频数据回调 */
  setCallbacks(callbacks: AudioCaptureCallbacks): void
  /** 当前状态 */
  readonly state: AudioCaptureState
}

/** 标签页音频源（现有实现，需重构） */
class TabAudioSource implements AudioSource { ... }

/** 麦克风音频源（新增） */
class MicrophoneAudioSource implements AudioSource {
  private _stream: MediaStream | null = null
  private _audioContext: AudioContext | null = null
  
  readonly type = 'microphone'
  readonly label = '麦克风'
  
  async start(): Promise<void> {
    this._stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
      video: false,
    })
    // 其余和 TabAudioSource 的音频处理逻辑相同（可抽取共用代码）
    // ... 
  }
  
  stop(): void {
    // ...
  }
}

/** 音频文件源（新增） */
class FileAudioSource implements AudioSource {
  private _audioContext: AudioContext | null = null
  private _sourceNode: AudioBufferSourceNode | null = null
  
  readonly type = 'file'
  readonly label = '音频文件'
  
  async start(): Promise<void> {
    // 1. 打开文件选择器
    const file = await this._pickFile()
    
    // 2. 解码音频文件
    const arrayBuffer = await file.arrayBuffer()
    this._audioContext = new AudioContext({ sampleRate: 16000 })
    const audioBuffer = await this._audioContext.decodeAudioData(arrayBuffer)
    
    // 3. 模拟实时播放（按时间分片输出 PCM chunk）
    this._sourceNode = this._audioContext.createBufferSource()
    this._sourceNode.buffer = audioBuffer
    
    // 连接 ScriptProcessor 进行分片
    const processor = this._audioContext.createScriptProcessor(2048, 1, 1)
    processor.onaudioprocess = (event) => {
      const chunk = new Float32Array(event.inputBuffer.getChannelData(0))
      this._callbacks?.onAudioChunk(chunk.buffer)
    }
    
    this._sourceNode.connect(processor)
    processor.connect(this._audioContext.destination)
    this._sourceNode.start()
  }
}
```

#### V3.2.2 音频源切换 UI

```tsx
// ui/AudioSourceSelector.tsx（新组件）

export const AudioSourceSelector: React.FC<{
  activeSource: AudioSourceType
  onSelect: (source: AudioSourceType) => void
  disabled: boolean
}> = ({ activeSource, onSelect, disabled }) => (
  <div style={containerStyle}>
    {([
      ['tab', '🖥️ 系统音频', '捕获浏览器标签页/窗口音频'],
      ['microphone', '🎤 麦克风', '使用麦克风输入'],
      ['file', '📁 文件', '上传音频文件进行翻译'],
    ] as const).map(([type, label, desc]) => (
      <button
        key={type}
        disabled={disabled}
        onClick={() => onSelect(type)}
        style={{
          ...buttonStyle,
          background: activeSource === type ? '#4caf50' : 'rgba(255,255,255,0.1)',
          opacity: disabled ? 0.5 : 1,
        }}
        title={desc}
      >
        {label}
      </button>
    ))}
  </div>
)
```

#### V3.2.3 AudioSourceManager 集成到 AppController

```typescript
// store/AppStore.ts 改造

export class AppController {
  private _sourceManager: AudioSourceManager  // 新增
  
  constructor() {
    this._sourceManager = new AudioSourceManager()
    ...
  }

  async start(sourceType: AudioSourceType = 'tab'): Promise<void> {
    // 1. 切换音频源
    const source = this._sourceManager.createSource(sourceType)
    source.setCallbacks({
      onStateChange: ...,
      onAudioChunk: (chunk) => this._wsClient.sendAudio(chunk),
    })
    
    // 2. 开始捕获
    await source.start()
    
    // 3. 连接 WebSocket
    this._wsClient.connect()
  }
}
```

### V3.3 语音合成输出（TTS）

**目标**: 前端将翻译文本转换为语音朗读，与字幕同步。

#### V3.3.1 后端 TTS Service

```python
# services/tts_service.py（新模块）

class TTSService:
    """语音合成服务
    
    支持多种 TTS 引擎：
    - OpenAI TTS API
    - Edge TTS（免费，质量好）
    - 本地 Coqui TTS
    """
    
    async def initialize(self) -> None:
        """初始化 TTS 引擎"""
        if settings.tts_engine == "openai":
            await self._init_openai_tts()
        elif settings.tts_engine == "edge":
            await self._init_edge_tts()
        elif settings.tts_engine == "coqui":
            await self._init_coqui_tts()
    
    async def synthesize(
        self, text: str, language: str = "zh"
    ) -> bytes:
        """将文本合成为音频
        
        Returns:
            MP3 音频字节（或 PCM 格式，取决于引擎）
        """
        if self._engine == "openai":
            return await self._synthesize_openai(text)
        elif self._engine == "edge":
            return await self._synthesize_edge(text, language)
        elif self._engine == "coqui":
            return await self._synthesize_coqui(text, language)
```

#### V3.3.2 WebSocket 消息扩展

```python
# TTS 音频数据通过 WebSocket binary 发送
# 新增消息类型
# Server → Client:
@dataclass
class TTSAudioMessage:
    type: Literal["tts_audio"]
    segment_id: str
    format: str = "mp3"  # mp3 | pcm
    # 音频数据通过 WebSocket binary 紧随发送
```

#### V3.3.3 前端播放器

```typescript
// audio/TTSPlayer.ts（新模块）

export class TTSPlayer {
  private _audioContext: AudioContext | null = null
  private _enabled: boolean = false
  private _volume: number = 0.8
  
  get enabled(): boolean { return this._enabled }
  set enabled(v: boolean) { this._enabled = v }
  
  /** 播放 TTS 音频块 */
  playAudioChunk(audioData: ArrayBuffer, format: string = 'pcm'): void {
    if (!this._enabled) return
    
    // 解码并播放音频
    this._audioContext?.decodeAudioData(audioData).then(buffer => {
      const source = this._audioContext!.createBufferSource()
      const gainNode = this._audioContext!.createGain()
      gainNode.gain.value = this._volume
      source.buffer = buffer
      source.connect(gainNode)
      gainNode.connect(this._audioContext!.destination)
      source.start()
    })
  }
}
```

### V3.4 字幕历史回溯

**目标**: 用户可以回看最近 N 条字幕，避免漏看。

```tsx
// ui/SubtitleHistory.tsx（新组件）

export const SubtitleHistory: React.FC<{
  history: SubtitleEntry[]
  maxItems?: number
}> = ({ history, maxItems = 10 }) => {
  const [open, setOpen] = useState(false)
  const recentItems = history.slice(-maxItems).reverse()
  
  return (
    <>
      <button
        onClick={() => setOpen(!open)}
        style={{
          position: 'fixed',
          bottom: '16px',
          right: '16px',
          zIndex: 100000,
          ...floatingButtonStyle,
        }}
      >
        📜 历史 ({history.length})
      </button>
      
      {open && (
        <div style={historyPanelStyle}>
          <h4>字幕历史</h4>
          {recentItems.map((item, i) => (
            <div key={i} style={historyItemStyle}>
              <span style={timeStyle}>
                {new Date(item.timestamp).toLocaleTimeString()}
              </span>
              <span style={textStyle}>
                {item.text}
                {item.isRevised && ' ✏️'}
              </span>
            </div>
          ))}
        </div>
      )}
    </>
  )
}
```

### V3.5 V3 验收标准

| 编号 | 验收标准 | 验证方法 |
|------|---------|---------|
| AC-V3.1 | 支持英→中、中→英、日→中等至少 6 种语言对 | 逐一测试各语言对翻译 |
| AC-V3.2 | 语言切换后翻译管线立即生效 | 运行时切换语言对，验证字幕语言变化 |
| AC-V3.3 | 麦克风输入正常捕获和翻译 | 用麦克风说话，验证翻译 |
| AC-V3.4 | 音频文件上传后逐句翻译 | 上传 1 分钟英语音频，验证逐句输出 |
| AC-V3.5 | TTS 语音与字幕同步 | 开启 TTS，验证语音同步 |
| AC-V3.6 | 字幕历史可回溯最近 10 条 | 翻译 20 句后打开历史面板，验证 |

**V3 总预估工时**: 15-20 个工作日

---

## V4 — 桌面客户端与全系统音频

> **目标**: 通过 Electron/Tauri 封装桌面客户端，实现真正的全系统音频捕获，消除浏览器限制。

### V4.1 桌面客户端选型

| 方案 | 优点 | 缺点 | 推荐度 |
|------|------|------|--------|
| **Electron** | 生态成熟、社区大、前端代码复用 | 体积大 (~150MB)、内存占用高 | ⭐⭐⭐⭐ |
| **Tauri** | 体积小 (~10MB)、性能好、Rust | 生态较新、原生模块需 Rust 实现 | ⭐⭐⭐⭐⭐ |
| **PWA** | 无需安装、轻量 | 系统音频捕获受限 | ⭐⭐ |

**推荐**: Tauri v2（Rust 后端 + React 前端，可复用现有前端代码）

#### V4.1.1 Tauri 项目结构

```
desktop/
├── src-tauri/
│   ├── Cargo.toml
│   ├── tauri.conf.json
│   ├── capabilities/
│   │   └── default.json
│   └── src/
│       ├── main.rs          # Tauri 入口
│       ├── audio_capture.rs # 系统音频捕获（Windows WASAPI / macOS CoreAudio）
│       ├── commands.rs      # Tauri 命令（暴露给前端）
│       └── lib.rs
├── src/                     # 复用前端代码
│   └── (symlink to ../../frontend/src)
├── package.json
└── vite.config.ts
```

#### V4.1.2 系统音频捕获（Tauri 侧）

```rust
// src-tauri/src/audio_capture.rs

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{Device, SampleFormat, StreamConfig};
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter};

/// 系统音频捕获器（使用 CPAL 库）
pub struct SystemAudioCapture {
    stream: Option<cpal::Stream>,
    is_active: Arc<Mutex<bool>>,
}

impl SystemAudioCapture {
    /// 创建新的音频捕获实例
    pub fn new() -> Self {
        Self {
            stream: None,
            is_active: Arc::new(Mutex::new(false)),
        }
    }

    /// 开始捕获系统音频
    pub fn start(&mut self, app: AppHandle) -> Result<(), String> {
        let host = cpal::default_host();
        
        // 查找 Loopback 设备（捕获系统输出音频）
        let device = host
            .output_devices()
            .map_err(|e| e.to_string())?
            .find(|d| {
                d.name()
                    .map(|n| {
                        n.contains("Loopback")
                            || n.contains("Stereo Mix")
                            || n.contains("BlackHole")
                            || n.contains("VB-Audio")
                    })
                    .unwrap_or(false)
            })
            .ok_or("No loopback device found. Please install BlackHole or VB-Audio Cable.")?;

        let config = device
            .default_output_config()
            .map_err(|e| e.to_string())?;

        let sample_rate = config.sample_rate().0;
        let channels = config.channels() as u16;
        
        let is_active = self.is_active.clone();
        
        // 创建音频流
        let stream = match config.sample_format() {
            SampleFormat::F32 => {
                device.build_input_stream(
                    &StreamConfig {
                        channels,
                        sample_rate: cpal::SampleRate(sample_rate),
                        buffer_size: cpal::BufferSize::Fixed(2048),
                    },
                    move |data: &[f32], _: &cpal::InputCallbackInfo| {
                        if *is_active.lock().unwrap() {
                            // 将 PCM 数据发送到前端
                            let bytes = unsafe {
                                std::slice::from_raw_parts(
                                    data.as_ptr() as *const u8,
                                    data.len() * 4,
                                )
                            };
                            let _ = app.emit(
                                "audio-data",
                                serde_json::json!({
                                    "data": base64::encode(bytes),
                                    "sampleRate": sample_rate,
                                    "channels": channels,
                                }),
                            );
                        }
                    },
                    |err| eprintln!("Audio error: {}", err),
                    None,
                )
            }
            _ => return Err("Unsupported sample format".into()),
        }
        .map_err(|e| e.to_string())?;

        stream.play().map_err(|e| e.to_string())?;
        self.stream = Some(stream);
        *self.is_active.lock().unwrap() = true;
        
        Ok(())
    }

    pub fn stop(&mut self) {
        *self.is_active.lock().unwrap() = false;
        self.stream = None;
    }
}
```

#### V4.1.3 Tauri 命令（桥梁层）

```rust
// src-tauri/src/commands.rs

use tauri::State;
use std::sync::Mutex;

pub struct AudioState(pub Mutex<SystemAudioCapture>);

#[tauri::command]
pub fn start_audio_capture(
    state: State<'_, AudioState>,
    app: tauri::AppHandle,
) -> Result<(), String> {
    let mut capture = state.0.lock().map_err(|e| e.to_string())?;
    capture.start(app)
}

#[tauri::command]
pub fn stop_audio_capture(
    state: State<'_, AudioState>,
) -> Result<(), String> {
    let mut capture = state.0.lock().map_err(|e| e.to_string())?;
    capture.stop();
    Ok(())
}

#[tauri::command]
pub fn get_audio_devices() -> Result<Vec<String>, String> {
    let host = cpal::default_host();
    let devices: Vec<String> = host
        .output_devices()
        .map_err(|e| e.to_string())?
        .filter_map(|d| d.name().ok())
        .collect();
    Ok(devices)
}
```

#### V4.1.4 前端适配层

```typescript
// desktop/src/audio/DesktopAudioCapture.ts（新增）

import { listen } from '@tauri-apps/api/event'
import { invoke } from '@tauri-apps/api/core'

/** Tauri 桌面端的系统音频捕获 */
export class DesktopAudioCapture {
  private _unlisten: (() => void) | null = null
  
  async start(): Promise<void> {
    // 启动 Rust 侧音频捕获
    await invoke('start_audio_capture')
    
    // 监听音频数据事件
    this._unlisten = await listen<{ data: string; sampleRate: number; channels: number }>(
      'audio-data',
      (event) => {
        const binaryStr = atob(event.payload.data)
        const bytes = new Uint8Array(binaryStr.length)
        for (let i = 0; i < binaryStr.length; i++) {
          bytes[i] = binaryStr.charCodeAt(i)
        }
        this._callbacks?.onAudioChunk(bytes.buffer)
      }
    )
  }
  
  async stop(): Promise<void> {
    this._unlisten?.()
    await invoke('stop_audio_capture')
  }
}
```

### V4.2 系统托盘与常驻

```rust
// src-tauri/src/main.rs

use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager,
};

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            // 创建系统托盘
            let toggle = MenuItem::with_id(app, "toggle", "开始/停止翻译", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&toggle, &quit])?;
            
            let _tray = TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "toggle" => {
                        // 切换翻译状态
                        let window = app.get_webview_window("main").unwrap();
                        let _ = window.eval("window.__toggleTranslation()");
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                })
                .build(app)?;
            
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::start_audio_capture,
            commands::stop_audio_capture,
            commands::get_audio_devices,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

### V4.3 移动端适配（V4.3）

#### React Native / Capacitor 方案

```
移动端使用 Capacitor 封装：
- 音频捕获：@capacitor/voice-recorder 或原生 API
- 前端代码：几乎完全复用（React Web → React Native 需适配）
- 后端：复用 FastAPI 后端（远程服务器）

目录结构：
mobile/
├── android/
├── ios/
├── src/                    # 复用前端代码
└── capacitor.config.ts
```

### V4.4 V4 验收标准

| 编号 | 验收标准 | 验证方法 |
|------|---------|---------|
| AC-V4.1 | 桌面客户端安装包 < 20MB (Tauri) | 构建安装包，检查大小 |
| AC-V4.2 | 系统音频（非浏览器）正常捕获 | 播放 YouTube/本地视频，验证翻译 |
| AC-V4.3 | 系统托盘正常工作 | 最小化到托盘，点击托盘恢复 |
| AC-V4.4 | 内存占用 < 200MB | 运行 1 小时后检查内存 |
| AC-V4.5 | 翻译延迟相比浏览器版降低 30%+ | A/B 测试延迟 |
| AC-V4.6 | 支持 Chrome/YouTube/Teams/Zoom 等主流应用 | 逐一测试各应用音频捕获 |

**V4 总预估工时**: 15-25 个工作日

---

## V5 — 高级特性与商业化（远期规划）

### V5.1 术语库与自定义词典

```python
# services/glossary_service.py（新模块）

class GlossaryService:
    """术语管理服务
    
    允许用户导入/维护自定义术语表，
    在翻译时通过 system prompt 注入术语约束。
    """
    
    def __init__(self):
        self._glossaries: dict[str, dict[str, str]] = {}
    
    async def load_glossary(self, user_id: str, path: str) -> None:
        """加载术语表文件（CSV/JSON 格式）"""
        # 格式: {"Artificial Intelligence": "人工智能", "LLM": "大语言模型"}
        ...
    
    def inject_terms_to_prompt(self, system_prompt: str, glossary: dict[str, str]) -> str:
        """将术语约束注入翻译 prompt"""
        term_rules = "\n".join(
            f'- "{src}" MUST be translated as "{tgt}"'
            for src, tgt in glossary.items()
        )
        return f"{system_prompt}\n\nTerminology rules:\n{term_rules}"
```

**应用场景**:
- 医疗/法律/技术等垂直领域的专业术语
- 公司品牌名、产品名的固定翻译
- 演讲者个人偏好的翻译风格

### V5.2 多人会话与协作翻译

- 一个房间多个用户同时观看同一内容
- 用户可编辑/修正翻译，提交后全员可见
- 类似 Google Docs 的协作编辑体验

### V5.3 翻译记忆库

- 对已翻译过的句对建立索引
- 相似句子直接复用翻译（避免重复 API 调用）
- 使用向量数据库（如 ChromaDB）存储句子嵌入

### V5.4 离线模式

- 前端 PWA + Service Worker 离线可访问
- 本地 Whisper + 本地 NMT 模型（ONNX/TensorRT）
- 适合飞行模式或网络不稳定场景

### V5.5 付费与订阅系统

| 套餐 | 价格 | 功能 |
|------|------|------|
| 免费版 | ¥0/月 | 每天 30 分钟，仅英→中，字幕模式 |
| 个人版 | ¥29/月 | 无限时长，双语字幕，多语种，TTS |
| 专业版 | ¥99/月 | 术语库、API 接入、协作翻译、优先支持 |
| 企业版 | 定制 | 私有部署、SSO、SLA |

---

## 附录 A：技术债务清单（跨版本）

| 编号 | 技术债务 | 当前状态 | 计划版本 | 优先级 |
|------|---------|---------|---------|--------|
| TD-1 | ScriptProcessorNode to AudioWorklet | Implemented with fallback; needs live-session comparison | V2.3 | MEDIUM |
| TD-2 | 字幕 Store/Renderer 数据重复同步 | 全量渲染 | V2.2 | MEDIUM |
| TD-3 | 多 Session 共享 ASR 模型实例 | 单用户 | V3 | LOW |
| TD-4 | Redis 上下文更新非原子操作 | 竞态风险 | V2.1 | HIGH |
| TD-5 | WebSocket 断开时翻译任务未取消 | 资源泄漏 | V2.1 | HIGH |
| TD-6 | 缺少单元测试 | 0% 覆盖率 | V2.1 | HIGH |
| TD-7 | 缺少 E2E 测试 | 0% 覆盖率 | V2.5 | MEDIUM |
| TD-8 | print/console.log 调试输出 | 生产中有调试日志 | V2.2 | LOW |

## 附录 B：性能指标目标

| 指标 | MVP 当前 | V2 目标 | V3 目标 | V4 目标 |
|------|---------|--------|--------|--------|
| 端到端延迟 (E2E Latency) | < 5s | < 3s | < 2s | < 1.5s |
| ASR 准确率 (WER) | 85% | 90% | 92% | 93% |
| 翻译 BLEU 分数 | — | 25+ | 28+ | 30+ |
| 修正准确率 (用户认可) | — | 70% | 80% | 85% |
| 前端内存占用 | < 100MB | < 80MB | < 80MB | < 200MB (桌面) |
| 并发 Session 数 | 1 | 3 | 10 | 50 |
| API 调用成本 / 分钟 | — | < ¥0.5 | < ¥0.3 | < ¥0.2 |

---

> **文档维护**: 本文档应在每个版本结束后更新，将已完成的条目标记为 ✅，并根据实际开发情况调整后续版本的计划。
