"""WebSocket connection handler for live translation sessions."""

import json
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from core.pipeline import Pipeline
from services.asr_service import ASRService
from services.context_manager import ContextManager
from services.nmt_service import NMTService
from services.revision_service import RevisionService


class WebSocketHandler:
    """Owns per-session pipelines and routes websocket messages."""

    def __init__(self) -> None:
        self._asr: Optional[ASRService] = None
        self._nmt: Optional[NMTService] = None
        self._ctx_manager: Optional[ContextManager] = None
        self._active_pipelines: dict[str, Pipeline] = {}

    async def initialize(self) -> None:
        self._asr = ASRService()
        self._nmt = NMTService()
        self._ctx_manager = ContextManager()

        await self._asr.initialize()
        await self._nmt.initialize()
        await self._ctx_manager.initialize()

        logger.info("WebSocket handler initialized")

    async def handle_connection(self, ws: WebSocket, session_id: str) -> None:
        await ws.accept()
        logger.info("WebSocket connected: {}", session_id)

        if not self._asr or not self._nmt or not self._ctx_manager:
            await ws.send_json({
                "type": "error",
                "code": "SERVICE_NOT_READY",
                "message": "Translation service is not initialized",
            })
            await ws.close()
            return

        existing = self._active_pipelines.get(session_id)
        if existing:
            logger.info("Replacing active pipeline for reconnecting session {}", session_id)
            await existing.stop()

        pipeline = Pipeline(
            session_id=session_id,
            asr=self._asr.create_session(),
            nmt=self._nmt,
            ctx_manager=self._ctx_manager,
            revision=RevisionService(),
        )
        pipeline.set_on_message(lambda msg: self._send_message(ws, msg))
        await pipeline.start()
        self._active_pipelines[session_id] = pipeline

        try:
            while True:
                raw = await ws.receive()

                if raw["type"] == "websocket.receive":
                    if "bytes" in raw:
                        await pipeline.process_audio(raw["bytes"])
                    elif "text" in raw:
                        await self._handle_control_message(pipeline, raw["text"])
                elif raw["type"] == "websocket.disconnect":
                    break
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected: {}", session_id)
        except Exception as exc:
            logger.error("WebSocket error for {}: {}", session_id, exc)
        finally:
            await pipeline.stop()
            if self._active_pipelines.get(session_id) is pipeline:
                self._active_pipelines.pop(session_id, None)

    async def _handle_control_message(self, pipeline: Pipeline, text: str) -> None:
        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON control message")
            return

        msg_type = msg.get("type")
        if msg_type == "pause":
            logger.debug("Pause received")
            return

        if msg_type == "resume":
            logger.debug("Resume received")
            return

        if msg_type == "config":
            language = msg.get("language", "en")
            target = msg.get("target_language", "zh")
            logger.info("Config updated: {} -> {}", language, target)
            return

        if msg_type == "manual_revise":
            logger.info("Manual revision requested for session {}", pipeline.session_id)
            await pipeline.trigger_manual_revision()
            return

        logger.warning("Unknown message type: {}", msg_type)

    async def _send_message(self, ws: WebSocket, message: dict) -> None:
        try:
            await ws.send_json(message)
        except Exception as exc:
            logger.error("Failed to send message: {}", exc)

    async def shutdown(self) -> None:
        for session_id, pipeline in list(self._active_pipelines.items()):
            await pipeline.stop()
            self._active_pipelines.pop(session_id, None)

        if self._asr:
            await self._asr.shutdown()
        if self._nmt:
            await self._nmt.shutdown()
        if self._ctx_manager:
            await self._ctx_manager.shutdown()

        logger.info("WebSocket handler shut down")
