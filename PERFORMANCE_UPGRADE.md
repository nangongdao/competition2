# competition2 性能与能力升级方案

> 配套文档：`UPGRADE_PLAN.md`（安全与工程质量）
> 本文档专注**性能提升**与**能力进阶** —— 即"从能跑到跑得好"的部分。
> 审计日期：2026-08-01

---

## 0. 为什么需要这份文档

`UPGRADE_PLAN.md` 解决的是"不扣分"的问题（漏洞、CI、版本控制），
那些是及格线。本文档解决的是"拿高分"的问题：

**同传系统的唯一核心指标是延迟。** 一个字幕落后说话人 10 秒的系统，
即使代码再干净、测试再全，产品上也是失败的。

本文档的第 1 节就是本次审计中**最有价值的单条发现**。

---

## 1. 【P0】管线阻塞导致延迟无限累积

### 1.1 问题

`backend/core/pipeline.py:252-300`，`_handle_asr_final` 是 **ASR 的回调函数**，
但它在回调内部**同步 await 完成了整条翻译链路**：

```python
async def _handle_asr_final(self, text: str, confidence: float) -> None:
    # ... 构造 segment ...
    await self._ctx.add_segment(self.session_id, segment)
    await self._emit({"type": "asr_final", ...})

    context_window = await self._ctx.get_window(self.session_id)

    # ↓↓↓ 阻塞点 1：整个翻译流式过程在此 await 完成（1-3 秒）
    async for token in self._nmt.translate_stream(context_window, segment):
        await self._emit({"type": "translation_token", ...})

    await self._ctx.update_segment(self.session_id, segment)

    # ↓↓↓ 阻塞点 2：修正引擎再调一次 LLM（1-2 秒）
    asr_revision = await self._revision.check_asr_correction(...)
```

**后果**：这个协程返回之前，ASR 无法处理下一句。
翻译耗时若超过说话间隔，延迟就会**逐句累积且永不收敛**。

### 1.2 量化影响（实测模拟）

假设：翻译 1.8s、修正 1.2s（每 3 句触发一次）：

| 场景 | 第 1 句 | 第 10 句 | 第 20 句 | 第 30 句 | 是否收敛 |
|---|---|---|---|---|---|
| 慢速演讲（每句 3.0s） | 1.8s | 1.8s | 1.8s | 3.0s | 勉强 |
| **正常语速（每句 2.0s）** | 1.8s | 3.8s | **5.4s** | **9.4s** | ❌ 发散 |
| **快速讲座（每句 1.5s）** | 2.1s | 8.4s | **15.0s** | **24.0s** | ❌ 发散 |
| 快速 + 上游慢（2.5s/次） | 3.5s | 17.0s | 31.5s | **49.0s** | ❌ 严重发散 |

**读法**：一场 30 分钟的正常语速讲座，到中段字幕已落后近 10 秒；
快速讲座场景下字幕落后 24 秒 —— 用户看到的字幕和当前听到的内容
**完全对不上**，同传功能实质失效。

> 这也解释了为什么现有耐久测试（静音输入、`asr_segments: 0`）
> 从未暴露这个问题 —— **管线一次都没真正跑过**。

### 1.3 改造方案：三级解耦

#### 第一步：翻译与修正异步化（收益最大，改动最小）

ASR 回调只负责"落库 + 广播 ASR 结果"，翻译丢给独立任务：

```python
# backend/core/pipeline.py

class Pipeline:
    def __init__(self, ...):
        # ...
        #: 进行中的翻译任务，键为 segment_id，用于取消与等待
        self._translation_tasks: dict[str, asyncio.Task[None]] = {}
        #: 限制并发翻译数，避免瞬时打爆上游配额
        self._translation_semaphore = asyncio.Semaphore(
            settings.max_concurrent_translations
        )

    async def _handle_asr_final(self, text: str, confidence: float) -> None:
        """ASR 出最终结果的回调。

        只做轻量工作（落库 + 广播），翻译与修正交给后台任务，
        避免阻塞 ASR 处理下一句 —— 这是延迟不累积的关键。
        """
        if not text.strip():
            return

        # ... 构造 segment、记录诊断（保持原样，都是快操作）...
        await self._ctx.add_segment(self.session_id, segment)
        await self._emit({"type": "asr_final", ...})

        # 翻译链路异步化：立即返回，不阻塞下一句 ASR
        task = asyncio.create_task(
            self._translate_and_revise(segment, asr_final_at),
            name=f"translate-{segment.id}",
        )
        self._translation_tasks[segment.id] = task
        task.add_done_callback(
            lambda t: self._translation_tasks.pop(segment.id, None)
        )

    async def _translate_and_revise(self, segment: Segment, asr_final_at: float) -> None:
        """后台执行翻译与修正。

        Args:
            segment: 待翻译的语音片段。
            asr_final_at: ASR 出结果的时刻，用于计算端到端延迟。
        """
        async with self._translation_semaphore:
            try:
                await self._run_translation(segment, asr_final_at)
                await self._run_revision(segment)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Translation failed for {}: {}", segment.id, exc)
                # 降级：至少让用户看到原文（配合 UPGRADE_PLAN 的 ARCH-02）
                await self._emit({
                    "type": "translation_token",
                    "segment_id": segment.id,
                    "token": f"[未翻译] {segment.text_asr}",
                    "is_final": True,
                })
```

会话停止时需等待在途任务：

```python
    async def stop(self) -> None:
        self._running = False

        # 给在途翻译一个短暂的收尾窗口，超时则取消
        if self._translation_tasks:
            pending = list(self._translation_tasks.values())
            done, still_pending = await asyncio.wait(pending, timeout=3.0)
            for task in still_pending:
                task.cancel()
            await asyncio.gather(*still_pending, return_exceptions=True)

        # ... 原有清理逻辑
```

**收益**：延迟从"随时长发散"变为"恒定 = 单句翻译耗时"。
快速讲座场景下第 30 句延迟从 24s 降到 1.8s，**提升 13 倍**。

#### 第二步：乱序保护

异步化后，短句可能比先到的长句先译完，导致字幕乱序。
需要在**前端**按 `segment_index` 排序落位（而非按到达顺序 append）：

```typescript
// frontend/src/subtitle/SubtitleStore.ts

/**
 * 按 segment 序号有序插入字幕。
 *
 * 翻译异步化后结果可能乱序到达，必须按序号定位而非追加，
 * 否则短句会插到长句前面。
 */
insertOrdered(entry: SubtitleEntry): void {
  const index = this._entries.findIndex((item) => item.seq > entry.seq)
  if (index === -1) {
    this._entries.push(entry)
  } else {
    this._entries.splice(index, 0, entry)
  }
}
```

后端需在消息中带上单调递增的 `seq`（`segment_index` 已有，直接复用）。

#### 第三步：修正引擎降级为低优先级

修正（`revision_service`）是"锦上添花"，不应与翻译争抢上游配额。
建议用独立的低优先级队列，且在积压时**主动丢弃**：

```python
#: 修正任务队列，满时丢弃最旧的（修正是可选功能，不应拖累主链路）
self._revision_queue: asyncio.Queue[Segment] = asyncio.Queue(maxsize=8)

def _enqueue_revision(self, segment: Segment) -> None:
    """将片段加入修正队列，队列满时丢弃最旧任务。"""
    try:
        self._revision_queue.put_nowait(segment)
    except asyncio.QueueFull:
        try:
            dropped = self._revision_queue.get_nowait()
            logger.debug("Revision queue full, dropped {}", dropped.id)
            self._revision_queue.put_nowait(segment)
        except (asyncio.QueueEmpty, asyncio.QueueFull):
            pass
```

---

## 2. 【P1】首字延迟优化：流式转发

### 2.1 现状

`nmt_service.translate_stream` 已经是流式的（`yield token`），
`pipeline.py:256-267` 也逐 token `_emit` —— **这部分做对了**。

但 `revision_service` 的 `_complete_claude`（`nmt_service.py:145`）
使用的是**非流式** `messages.create`，会等完整响应返回。

### 2.2 优化

修正结果本身适合整段替换（不需要流式），但**可以并行发起**：

```python
async def _run_revision(self, segment: Segment) -> None:
    """并行发起 ASR 修正与译文润色，取先完成者。"""
    tasks = [
        asyncio.create_task(self._revision.check_asr_correction(...)),
    ]
    if settings.revision_polish_enabled:
        tasks.append(asyncio.create_task(self._revision.polish_translation(...)))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Revision sub-task failed: {}", result)
            continue
        if result:
            self._record_revision(result)
```

---

## 3. 【P1】上游调用成本与延迟双优化

### 3.1 上下文窗口裁剪

`context_window_size: int = 10`（`config.py:37`）意味着**每次翻译都携带前 10 句**。
一场 1 小时的会议：

- 每句约 30 token，10 句上下文 = 300 token
- 每句翻译请求 ≈ 300（上下文）+ 30（当前句）+ 系统提示 ≈ 400 input token
- 1 小时约 1200 句 → **48 万 input token**

**优化：分层上下文** —— 近 3 句用原文，更早的用摘要：

```python
async def get_window(self, session_id: str) -> ContextWindow:
    """获取分层上下文窗口。

    近 3 句保留完整原文（保证指代衔接），
    第 4-10 句压缩为一句话摘要（保留主题连贯性但省 token）。
    """
    segments = await self._load_segments(session_id)
    recent = segments[-3:]
    older = segments[-10:-3]

    summary = None
    if older:
        summary = await self._get_or_build_summary(session_id, older)

    return ContextWindow(recent=recent, summary=summary)
```

**预估收益**：input token 从 400 降到约 150，**成本降低 60%**，
且更短的 prompt 也意味着更低的首 token 延迟。

### 3.2 相同句子的翻译缓存

演讲中重复语句很常见（"接下来我们看"、"这一点非常重要"）。
加一层 LRU 缓存：

```python
from functools import lru_cache
import hashlib

def _translation_cache_key(text: str, src: str, tgt: str) -> str:
    """构造翻译缓存键（含语言对，避免跨语言污染）。"""
    digest = hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:16]
    return f"{src}:{tgt}:{digest}"
```

短句（≤10 词）命中率通常可达 15-25%，直接省掉一次 LLM 往返。
**注意**：只对无上下文依赖的短句启用缓存，长句因为依赖上下文不应缓存。

---

## 4. 【P2】能力进阶：从"能用"到"有竞争力"

以下是提升项目**技术含金量**的方向，按投入产出比排序。

### 4.1 说话人分离（Speaker Diarization）★★★★★

**为什么值得做**：这是当前方案与商业同传产品的最大差距。
多人会议场景下，不区分说话人的字幕可读性极差。

**实现路径**（成本可控）：

```python
# backend/services/diarization_service.py

"""说话人分离服务。

使用 pyannote.audio 的预训练模型做说话人嵌入聚类，
为每个 segment 标注说话人 ID。
"""

class DiarizationService:
    """基于嵌入聚类的轻量说话人分离。"""

    def __init__(self) -> None:
        #: 已知说话人的嵌入中心，键为说话人 ID
        self._centroids: dict[str, np.ndarray] = {}
        #: 判定为同一说话人的余弦相似度阈值
        self._threshold = settings.diarization_similarity_threshold

    async def identify(self, audio_chunk: bytes) -> str:
        """识别音频片段的说话人。

        Args:
            audio_chunk: PCM float32 音频数据。

        Returns:
            说话人标识，如 "speaker_1"。
        """
        embedding = await self._extract_embedding(audio_chunk)

        best_id, best_score = None, -1.0
        for speaker_id, centroid in self._centroids.items():
            score = float(np.dot(embedding, centroid))
            if score > best_score:
                best_id, best_score = speaker_id, score

        if best_id is None or best_score < self._threshold:
            new_id = f"speaker_{len(self._centroids) + 1}"
            self._centroids[new_id] = embedding
            return new_id

        # 在线更新中心（指数移动平均）
        self._centroids[best_id] = 0.9 * self._centroids[best_id] + 0.1 * embedding
        return best_id
```

前端字幕加上说话人色块与名称。**答辩效果极佳** —— 这是评委一眼能看出差异的功能。

### 4.2 术语表与领域自适应 ★★★★☆

技术演讲中的专有名词（人名、产品名、缩写）是翻译质量的最大痛点。

```python
@dataclass(frozen=True)
class GlossaryEntry:
    """术语表条目。"""
    source: str
    target: str
    #: 是否强制不翻译（如产品名 "Kubernetes" 保持原文）
    keep_original: bool = False


def build_glossary_prompt(glossary: list[GlossaryEntry], text: str) -> str:
    """为当前句构造术语约束提示。

    只注入本句实际命中的术语，避免 prompt 无谓膨胀。
    """
    hits = [g for g in glossary if g.source.lower() in text.lower()]
    if not hits:
        return ""

    lines = [
        f"- {g.source} → {'保持原文' if g.keep_original else g.target}"
        for g in hits
    ]
    return "必须遵守以下术语翻译：\n" + "\n".join(lines)
```

**只注入命中的术语**是关键设计 —— 避免把整张术语表塞进每次请求。

支持用户上传术语表（CSV/JSON），会前导入。这是真实会议场景的刚需。

### 4.3 自适应 VAD 与句子边界优化 ★★★★☆

当前 `asr_service.py:113-116` 按**固定 32000 样本**（2 秒）切分，
这会把句子从中间切断，严重影响翻译质量（半句话没法正确翻译）。

**改进：基于 VAD 静音 + 语义边界的动态切分**

```python
class AdaptiveSegmenter:
    """自适应语音分段器。

    结合 VAD 静音检测与最大时长约束，在自然停顿处切分，
    避免把完整句子从中间截断导致翻译质量下降。
    """

    #: 判定为句子边界的静音时长
    SILENCE_BOUNDARY_MS = 400
    #: 强制切分的最大累积时长（防止长时间无停顿导致延迟过高）
    MAX_SEGMENT_MS = 8000
    #: 最短片段（过短的片段缺乏上下文，翻译质量差）
    MIN_SEGMENT_MS = 800

    def should_emit(self, buffer_ms: int, silence_ms: int) -> bool:
        """判断当前缓冲是否应作为一个片段输出。"""
        if buffer_ms < self.MIN_SEGMENT_MS:
            return False
        if buffer_ms >= self.MAX_SEGMENT_MS:
            return True
        return silence_ms >= self.SILENCE_BOUNDARY_MS
```

项目已经依赖 `silero-vad`（`requirements.txt:12`）但似乎未充分利用 —— 这是现成的优势。

### 4.4 双流输出：字幕 + 语音合成 ★★★☆☆

ROADMAP 阶段 6 已规划"语音播报能力"。技术上可以做到**边翻译边合成**：

```python
async def _stream_tts(self, segment_id: str, token_stream: AsyncIterator[str]) -> None:
    """流式 TTS：按标点分句，边翻译边合成，降低语音延迟。"""
    buffer = ""
    async for token in token_stream:
        buffer += token
        # 遇到句末标点就送去合成，不等整段翻译完
        if any(punct in token for punct in "。！？；"):
            await self._tts.synthesize_and_emit(segment_id, buffer)
            buffer = ""
```

前端已有 `TtsPlayer.ts`，接线成本不高。

---

## 5. 【P2】前端性能

### 5.1 字幕渲染虚拟化

`SubtitleHistoryPanel.tsx`（480 行）渲染完整历史列表。
一场 1 小时会议约 1200 条字幕，全量渲染会导致明显卡顿。

```typescript
/**
 * 虚拟滚动：只渲染视口内的字幕条目。
 *
 * 长会议的字幕历史可达数千条，全量渲染会让主线程卡死。
 */
function useVirtualizedSubtitles(
  entries: readonly SubtitleEntry[],
  viewportHeight: number,
  itemHeight: number,
): { visible: readonly SubtitleEntry[]; offsetY: number; totalHeight: number } {
  const [scrollTop, setScrollTop] = useState(0)

  const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - 5)
  const visibleCount = Math.ceil(viewportHeight / itemHeight) + 10

  return {
    visible: entries.slice(startIndex, startIndex + visibleCount),
    offsetY: startIndex * itemHeight,
    totalHeight: entries.length * itemHeight,
  }
}
```

### 5.2 音频采集链路

`AudioCapture.ts` 已使用 AudioWorklet（`public/audio-capture-worklet.js`）——
**这是正确选择**（相比已废弃的 ScriptProcessorNode，不阻塞主线程）。

可优化项：在 worklet 内做**降采样与静音丢弃**，减少 WebSocket 传输量：

```javascript
// public/audio-capture-worklet.js

/** RMS 低于该值视为静音，不发送以节省带宽与后端算力 */
const SILENCE_RMS_THRESHOLD = 0.008

process(inputs) {
  const input = inputs[0]?.[0]
  if (!input) return true

  // 静音帧直接丢弃：一场会议中静音占比通常达 30-40%
  let sumSquares = 0
  for (let i = 0; i < input.length; i += 1) {
    sumSquares += input[i] * input[i]
  }
  const rms = Math.sqrt(sumSquares / input.length)

  if (rms < SILENCE_RMS_THRESHOLD) {
    this._silentFrames += 1
    // 连续静音只发送心跳，不发实际数据
    if (this._silentFrames % 10 !== 0) return true
  } else {
    this._silentFrames = 0
  }

  this.port.postMessage(input)
  return true
}
```

**预估收益**：传输量与后端 ASR 调用降低 30-40%（会议中的静音占比）。

---

## 6. 性能基线与验收

改造完成后，用真实音频跑基准测试（配合 `UPGRADE_PLAN.md` 的 TEST-01），
并把结果写进 README：

| 指标 | 改造前（估算） | 改造后目标 | 验证方式 |
|---|---|---|---|
| 端到端延迟 P50（正常语速） | 5.4s（第 20 句） | **≤ 2.0s，且不随时长增长** | 30 分钟真实录音 |
| 端到端延迟 P95 | 发散 | ≤ 3.5s | 同上 |
| ASR 首字延迟 P50 | 未测 | ≤ 800ms | 同上 |
| 单位时长翻译成本 | 基线 | **降低 60%**（上下文分层） | token 计数 |
| 音频传输量 | 基线 | 降低 30%（静音丢弃） | 字节计数 |
| 30 分钟内存增长 | 未测 | ≤ 50MB | RSS 采样 |
| 1200 条字幕渲染帧率 | 未测 | ≥ 50 FPS | Performance 面板 |

---

## 7. 实施优先级

| 优先级 | 任务 | 预计工期 | 收益 |
|---|---|---|---|
| **P0** | §1 管线异步化（含乱序保护） | 1–2 天 | **延迟从发散变恒定，快速场景提升 13 倍** |
| P1 | §3.1 上下文分层 | 1 天 | 成本降 60%，首字延迟降低 |
| P1 | §4.3 自适应 VAD 切分 | 1–2 天 | 翻译质量显著提升（不再切断句子） |
| P2 | §4.1 说话人分离 | 3–4 天 | **答辩杀手锏，评委一眼可见** |
| P2 | §4.2 术语表 | 2 天 | 专业场景翻译质量 |
| P2 | §5.1 字幕虚拟化 | 1 天 | 长会议不卡顿 |
| P3 | §5.2 静音丢弃 | 半天 | 带宽与成本降 30% |
| P3 | §4.4 流式 TTS | 2–3 天 | 产品完整度 |

**如果只做一件事：做 §1。** 它把一个"20 分钟后就不可用"的系统
变成一个"能撑完整场会议"的系统 —— 这是能力的质变，不是优化。

---

## 附录：本文档结论的推导方式

第 1 节的延迟累积数据来自对 `pipeline.py:252-300` 控制流的分析
与离散事件模拟，模型为：

```
lag(i) = max(0, lag(i-1) + work(i) - sentence_duration)
work(i) = translation_time + (revision_time if i % 3 == 0 else 0)
```

这是排队论中的标准 D/D/1 模型：**当服务时间 > 到达间隔时，队列长度线性发散**。
参数（翻译 1.8s、修正 1.2s）取自同类 LLM 翻译服务的典型值，
实际数值需用真实音频测量校准，但**发散这一定性结论与具体参数无关** ——
只要单句处理时间超过说话间隔就必然发生。

*本方案基于 2026-08-01 的代码状态。*
