"""Dataclasses describing websocket payloads."""

from dataclasses import dataclass, field
import time
from typing import Any, Literal, Optional


@dataclass
class ServerMessage:
    type: Literal[
        "asr_partial",
        "asr_final",
        "translation_token",
        "revision",
        "session_diagnostics",
        "status",
        "error",
    ]
    session_id: Optional[str] = None
    segment_id: Optional[str] = None
    text: Optional[str] = None
    confidence: Optional[float] = None
    token: Optional[str] = None
    is_final: bool = False
    new_text: Optional[str] = None
    source_text: Optional[str] = None
    reason: Optional[Literal["asr_correction", "translation_correction"]] = None
    old_text: Optional[str] = None
    old_source_text: Optional[str] = None
    correction_source: Optional[str] = None
    trigger: Optional[str] = None
    latency_ms: Optional[int] = None
    diagnostics: Optional[dict[str, Any]] = None
    code: Optional[str] = None
    message: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in self.__dict__.items() if value is not None}


@dataclass
class ClientMessage:
    type: Literal["audio_chunk", "pause", "resume", "config", "manual_revise"]
    data: Optional[bytes] = None
    timestamp: Optional[float] = None
    language: Optional[str] = None
    target_language: Optional[str] = None
