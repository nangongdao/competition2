"""Session-level diagnostics for live interpretation quality."""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class LatencyStats:
    """Aggregate latency samples without storing every event."""

    count: int = 0
    total_ms: int = 0
    max_ms: int = 0

    def add(self, latency_ms: int) -> None:
        normalized = max(0, int(latency_ms))
        self.count += 1
        self.total_ms += normalized
        self.max_ms = max(self.max_ms, normalized)

    def to_dict(self) -> dict[str, int]:
        avg_ms = round(self.total_ms / self.count) if self.count else 0
        return {
            "count": self.count,
            "avg_ms": avg_ms,
            "max_ms": self.max_ms,
        }


@dataclass
class SessionDiagnostics:
    """Mutable metrics owned by one websocket interpretation session."""

    session_id: str
    started_at: float = field(default_factory=time.time)
    status: str = "running"
    audio_chunks_received: int = 0
    audio_bytes_received: int = 0
    audio_chunks_dropped: int = 0
    asr_segments: int = 0
    translation_segments: int = 0
    revision_segments: int = 0
    reconnect_count: int = 0
    api_call_counts: Counter[str] = field(default_factory=Counter)
    revision_counts: Counter[str] = field(default_factory=Counter)
    revision_sources: Counter[str] = field(default_factory=Counter)
    revision_triggers: Counter[str] = field(default_factory=Counter)
    latency: dict[str, LatencyStats] = field(default_factory=dict)

    def record_audio_chunk(self, size_bytes: int) -> None:
        self.audio_chunks_received += 1
        self.audio_bytes_received += max(0, size_bytes)

    def record_dropped_audio_chunk(self) -> None:
        self.audio_chunks_dropped += 1

    def record_asr_segment(self, latency_ms: int | None = None) -> None:
        self.asr_segments += 1
        if latency_ms is not None:
            self.record_latency("capture_to_asr_ms", latency_ms)

    def record_translation_segment(
        self,
        *,
        first_token_latency_ms: int | None,
        final_latency_ms: int | None,
    ) -> None:
        self.translation_segments += 1
        self.api_call_counts["nmt_stream"] += 1
        if first_token_latency_ms is not None:
            self.record_latency("asr_to_first_token_ms", first_token_latency_ms)
        if final_latency_ms is not None:
            self.record_latency("asr_to_translation_final_ms", final_latency_ms)

    def record_revision(
        self,
        *,
        reason: str,
        source: str | None,
        trigger: str | None,
        latency_ms: int | None,
    ) -> None:
        self.revision_segments += 1
        self.revision_counts[reason] += 1
        if source:
            self.revision_sources[source] += 1
        if trigger:
            self.revision_triggers[trigger] += 1
        if latency_ms is not None:
            self.record_latency("revision_final_ms", latency_ms)

    def record_latency(self, name: str, latency_ms: int) -> None:
        stats = self.latency.setdefault(name, LatencyStats())
        stats.add(latency_ms)

    def record_api_call(self, name: str, count: int = 1) -> None:
        self.api_call_counts[name] += max(0, count)

    def set_reconnect_count(self, count: int) -> None:
        self.reconnect_count = max(0, count)

    def finish(self) -> None:
        self.status = "closed"

    def snapshot(self) -> dict:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "started_at": self.started_at,
            "duration_ms": round((time.time() - self.started_at) * 1000),
            "audio_chunks_received": self.audio_chunks_received,
            "audio_bytes_received": self.audio_bytes_received,
            "audio_chunks_dropped": self.audio_chunks_dropped,
            "asr_segments": self.asr_segments,
            "translation_segments": self.translation_segments,
            "revision_segments": self.revision_segments,
            "reconnect_count": self.reconnect_count,
            "latency": {
                name: stats.to_dict()
                for name, stats in sorted(self.latency.items())
            },
            "api_call_counts": dict(sorted(self.api_call_counts.items())),
            "revision_counts": dict(sorted(self.revision_counts.items())),
            "revision_sources": dict(sorted(self.revision_sources.items())),
            "revision_triggers": dict(sorted(self.revision_triggers.items())),
        }
