"""商用成本模型服务（本地可验证）。

把"同声传译持续消耗 token + 音频"这一商业化的核心痛点量化：
- **用量计量**：NMT token（估算）、ASR 音频秒数、TTS 字符数。
- **成本估算**：按提供商单价 × 用量估算本次/累计成本（美元 + 人民币）。
- **熔断上限**：当日估算成本 / NMT 调用量超过阈值时标记"建议降级"，
  提示切到本地引擎或更低规格模型，避免成本失控（同传不中断，仅提示）。
- **持久化**：累计用量写入 `config/cost.local.json`，重启不丢失。

设计说明：
- token 采用**基于文本长度的估算**（流式接口拿不到精确 usage）：英文约
  4 chars/token、中文约 1.5 chars/token，输入 = 系统提示 + 上下文 + 源句，
  输出 = 译文。
- 熔断是"尽力而为"的软提示，绝不中断实时翻译（同传稳定性优先）；
  真实计费接入时只需替换单价表即可复用计量模型。
- 所有 REST 端点仅允许本机回环客户端访问。
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from loguru import logger

from core.config import settings
from services.local_settings import CONFIG_DIR

#: 持久化文件名（白名单）
COST_FILENAME = "cost.local.json"

#: 每日成本软上限（美元），见 settings.cost_daily_limit_usd（此处保留默认参考值）。
DAILY_NMT_CALL_LIMIT = 500

#: 人民币兑美元参考汇率（仅用于展示估算，可被环境变量覆盖）
CNY_PER_USD = 7.2

#: 默认单价（美元）。输入 token / 输出 token / 每千 token 价格。
#: 以 OpenAI gpt-4o-mini 量级为参考（输入 $0.15/M，输出 $0.60/M）。
#: 实际可按配置覆盖：COST_NMT_INPUT_PER_M / COST_NMT_OUTPUT_PER_M。
DEFAULT_NMT_INPUT_PER_M = 0.15
DEFAULT_NMT_OUTPUT_PER_M = 0.60

#: ASR 单价（美元 / 每分钟音频，Whisper 官方 $0.006/分钟）。
ASR_PRICE_PER_MINUTE_USD = 0.006

#: TTS 单价（美元 / 每 1K 字符，OpenAI tts-1 约 $0.015/K）。
TTS_PRICE_PER_K_CHARS_USD = 0.015


def estimate_tokens(text: str) -> int:
    """按字符长度估算 token 数。

    Args:
        text: 待估算文本。

    Returns:
        估算 token 数（至少为 1，空串为 0）。
    """
    if not text:
        return 0
    # 统计 CJK 字符数，其余按拉丁字符估算。
    cjk = sum(1 for ch in text if _is_cjk(ch))
    other = len(text) - cjk
    # 中文约 1.5 chars/token，拉丁约 4 chars/token。
    tokens = cjk / 1.5 + other / 4.0
    return max(1, int(round(tokens)))


def _is_cjk(ch: str) -> bool:
    """判断单字符是否为 CJK 表意文字。"""
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0xF900 <= code <= 0xFAFF
    )


@dataclass
class CostUsage:
    """一次成本计量的原始用量。

    Attributes:
        nmt_input_tokens: NMT 输入 token（估算）。
        nmt_output_tokens: NMT 输出 token（估算）。
        asr_seconds: ASR 处理的音频秒数。
        tts_chars: TTS 合成的字符数。
    """

    nmt_input_tokens: int = 0
    nmt_output_tokens: int = 0
    asr_seconds: float = 0.0
    tts_chars: int = 0

    def add(self, other: "CostUsage") -> None:
        """累加另一份用量。"""
        self.nmt_input_tokens += other.nmt_input_tokens
        self.nmt_output_tokens += other.nmt_output_tokens
        self.asr_seconds += other.asr_seconds
        self.tts_chars += other.tts_chars

    def to_dict(self) -> dict:
        return {
            "nmt_input_tokens": self.nmt_input_tokens,
            "nmt_output_tokens": self.nmt_output_tokens,
            "asr_seconds": round(self.asr_seconds, 3),
            "tts_chars": self.tts_chars,
        }


@dataclass
class CostState:
    """成本累计状态。

    Attributes:
        sessions: 会话数。
        usage: 累计用量。
        day_key: 当天计量键。
        day_usage: 当天累计用量（用于每日软上限判断）。
        updated_at: 最近更新时间。
    """

    sessions: int = 0
    usage: CostUsage = field(default_factory=CostUsage)
    day_key: str = field(default_factory=lambda: time.strftime("%Y-%m-%d"))
    day_usage: CostUsage = field(default_factory=CostUsage)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "sessions": self.sessions,
            "total": self.usage.to_dict(),
            "day_key": self.day_key,
            "today": self.day_usage.to_dict(),
            "updated_at": self.updated_at,
        }


class CostService:
    """商用成本模型服务：用量计量 + 成本估算 + 熔断软上限提示。

    线程安全：所有共享状态通过锁保护。
    """

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            path = CONFIG_DIR / COST_FILENAME
        self._path = Path(path)
        self._lock = threading.Lock()
        self._state = CostState()
        self._nmt_input_per_m = settings.cost_nmt_input_per_m
        self._nmt_output_per_m = settings.cost_nmt_output_per_m
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def snapshot(self) -> dict:
        """成本概览快照（供 REST 返回与前端展示）。"""
        with self._lock:
            self._roll_day_if_needed_locked()
            usage = self._state.usage
            today = self._state.day_usage

            # 估算今日成本
            today_cost = _estimate_cost(today, self._nmt_input_per_m, self._nmt_output_per_m)
            total_cost = _estimate_cost(usage, self._nmt_input_per_m, self._nmt_output_per_m)

            suggestions: list[str] = []
            if today_cost >= settings.cost_daily_limit_usd:
                suggestions.append(
                    "今日估算成本已达软上限，建议切换本地 Whisper / 更低规格 NMT 模型以控制成本"
                )
            if (today.nmt_input_tokens or today.nmt_output_tokens) > 0 and (
                _nmt_call_count(today) >= DAILY_NMT_CALL_LIMIT
            ):
                suggestions.append("今日 NMT 调用量偏高，建议开启翻译记忆库或降低修正频率")

            return {
                "success": True,
                "reason": "cost overview loaded",
                "total_sessions": self._state.sessions,
                "usage": usage.to_dict(),
                "today": today.to_dict(),
                "total_cost_usd": round(total_cost, 6),
                "total_cost_cny": round(total_cost * CNY_PER_USD, 4),
                "today_cost_usd": round(today_cost, 6),
                "today_cost_cny": round(today_cost * CNY_PER_USD, 4),
                "daily_cost_limit_usd": settings.cost_daily_limit_usd,
                "daily_nmt_call_limit": DAILY_NMT_CALL_LIMIT,
                "suggestions": suggestions,
                "prices": {
                    "nmt_input_per_m": self._nmt_input_per_m,
                    "nmt_output_per_m": self._nmt_output_per_m,
                    "asr_per_minute": ASR_PRICE_PER_MINUTE_USD,
                    "tts_per_k_chars": TTS_PRICE_PER_K_CHARS_USD,
                },
                "token_estimate_note": (
                    "token 为基于文本长度的估算（英文≈4 chars/token，中文≈1.5 chars/token）"
                ),
            }

    def record(self, usage: CostUsage, *, is_new_session: bool = False) -> dict:
        """记录一次用量并返回最新快照。

        Args:
            usage: 本次用量。
            is_new_session: 是否开启新会话（累计会话数）。

        Returns:
            成本概览快照。
        """
        with self._lock:
            self._roll_day_if_needed_locked()
            if is_new_session:
                self._state.sessions += 1
            self._state.usage.add(usage)
            self._state.day_usage.add(usage)
            self._state.updated_at = time.time()
            self._persist_locked()
        return self.snapshot()

    def record_nmt(self, input_text: str, output_text: str, *, is_new_session: bool = False) -> None:
        """记录一次 NMT 翻译用量（基于文本长度估算 token）。"""
        usage = CostUsage(
            nmt_input_tokens=estimate_tokens(input_text),
            nmt_output_tokens=estimate_tokens(output_text),
        )
        self.record(usage, is_new_session=is_new_session)

    def record_asr(self, seconds: float) -> None:
        """记录 ASR 处理时长（秒）。"""
        self.record(CostUsage(asr_seconds=seconds))

    def record_tts(self, chars: int) -> None:
        """记录 TTS 合成字符数。"""
        self.record(CostUsage(tts_chars=chars))

    def reset(self) -> dict:
        """清空累计用量（管理/测试用）。"""
        with self._lock:
            self._state = CostState()
            self._persist_locked()
        return self.snapshot()

    def _roll_day_if_needed_locked(self) -> None:
        """跨天重置当日用量（调用方必须持有锁）。"""
        today = time.strftime("%Y-%m-%d")
        if self._state.day_key != today:
            self._state.day_key = today
            self._state.day_usage = CostUsage()

    def _load(self) -> None:
        """从磁盘加载成本状态（文件不存在或损坏时降级）。"""
        try:
            if not self._path.exists():
                logger.info("Cost file not found, starting fresh: {}", self._path)
                return
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            usage_raw = raw.get("usage", {})
            day_usage_raw = raw.get("day_usage", {})
            self._state = CostState(
                sessions=int(raw.get("sessions", 0)),
                usage=CostUsage(
                    nmt_input_tokens=int(usage_raw.get("nmt_input_tokens", 0)),
                    nmt_output_tokens=int(usage_raw.get("nmt_output_tokens", 0)),
                    asr_seconds=float(usage_raw.get("asr_seconds", 0.0)),
                    tts_chars=int(usage_raw.get("tts_chars", 0)),
                ),
                day_key=str(raw.get("day_key", "")),
                day_usage=CostUsage(
                    nmt_input_tokens=int(day_usage_raw.get("nmt_input_tokens", 0)),
                    nmt_output_tokens=int(day_usage_raw.get("nmt_output_tokens", 0)),
                    asr_seconds=float(day_usage_raw.get("asr_seconds", 0.0)),
                    tts_chars=int(day_usage_raw.get("tts_chars", 0)),
                ),
                updated_at=float(raw.get("updated_at", time.time())),
            )
            self._roll_day_if_needed_locked()
            logger.info("Cost state loaded: {} sessions", self._state.sessions)
        except Exception as exc:
            logger.error("Failed to load cost file {}: {}", self._path, exc)
            self._state = CostState()

    def _persist_locked(self) -> None:
        """原子写回磁盘（调用方必须持有锁）。"""
        payload = {
            "version": 1,
            "sessions": self._state.sessions,
            "usage": self._state.usage.to_dict(),
            "day_key": self._state.day_key,
            "day_usage": self._state.day_usage.to_dict(),
            "updated_at": self._state.updated_at,
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_suffix(".json.tmp")
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_path.replace(self._path)
        except Exception as exc:
            logger.error("Failed to persist cost {}: {}", self._path, exc)
            raise RuntimeError(f"成本状态写入失败: {exc}") from exc


def _estimate_cost(usage: CostUsage, input_per_m: float, output_per_m: float) -> float:
    """按用量估算成本（美元）。

    Args:
        usage: 用量。
        input_per_m: NMT 输入每百万 token 价格（美元）。
        output_per_m: NMT 输出每百万 token 价格（美元）。

    Returns:
        估算成本（美元）。
    """
    nmt_cost = (
        usage.nmt_input_tokens / 1_000_000 * input_per_m
        + usage.nmt_output_tokens / 1_000_000 * output_per_m
    )
    asr_cost = usage.asr_seconds / 60.0 * ASR_PRICE_PER_MINUTE_USD
    tts_cost = usage.tts_chars / 1000.0 * TTS_PRICE_PER_K_CHARS_USD
    return nmt_cost + asr_cost + tts_cost


def _nmt_call_count(usage: CostUsage) -> int:
    """估算 NMT 调用次数（粗略：按输入 token 折算，约每 200 token 一次调用）。"""
    if usage.nmt_input_tokens <= 0:
        return 0
    # 输入 token 里含系统提示+上下文（每次调用固定开销），此处按输出句数粗估。
    # 更精确的调用计数由 pipeline 侧累加；这里仅用于软上限提示。
    return usage.nmt_output_tokens


#: 全局成本服务实例（在 main.py lifespan 中初始化）
_cost_service: Optional[CostService] = None


def get_cost_service() -> Optional[CostService]:
    """获取全局成本服务实例。"""
    return _cost_service


def set_cost_service(service: Optional[CostService]) -> None:
    """设置全局成本服务实例（应用生命周期内调用）。"""
    global _cost_service
    _cost_service = service
