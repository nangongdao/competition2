from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

import numpy as np


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.config import settings
from services.asr_service import ASRService, float32_audio_to_wav_bytes


class FakeTranscriptions:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(text=" hello from remote ")


class FakeAudio:
    def __init__(self) -> None:
        self.transcriptions = FakeTranscriptions()


class FakeOpenAIClient:
    def __init__(self) -> None:
        self.audio = FakeAudio()


class OpenAIAsrServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_asr_buffers_audio_and_emits_final_text(self) -> None:
        client = FakeOpenAIClient()
        service = ASRService()
        service._engine = "openai"
        service._client = client
        service.set_language("ja")
        finals: list[tuple[str, float]] = []

        async def on_final(text: str, confidence: float, detected_language: str | None = None) -> None:
            finals.append((text, confidence))

        service.set_on_final(on_final)

        one_second = np.zeros(service._sample_rate, dtype=np.float32).tobytes()
        emitted_first = await service.process_chunk(one_second)
        emitted_second = await service.process_chunk(one_second)

        self.assertEqual(emitted_first, 0)
        self.assertEqual(emitted_second, 1)
        # ASR 文本后处理（阶段 2）：折叠空白 + 补句尾标点
        self.assertEqual(finals, [("hello from remote.", 0.0)])
        self.assertEqual(len(client.audio.transcriptions.calls), 1)

        call = client.audio.transcriptions.calls[0]
        self.assertEqual(call["model"], settings.asr_openai_model)
        self.assertEqual(call["language"], "ja")
        self.assertEqual(call["response_format"], "verbose_json")

        file_payload = call["file"]
        self.assertIsInstance(file_payload, tuple)
        self.assertEqual(file_payload[0], "audio.wav")
        self.assertIsInstance(file_payload[1], bytes)
        self.assertTrue(file_payload[1].startswith(b"RIFF"))
        self.assertEqual(file_payload[2], "audio/wav")

    async def test_openai_asr_omits_language_for_auto_detect(self) -> None:
        client = FakeOpenAIClient()
        service = ASRService()
        service._engine = "openai"
        service._client = client
        service.set_language("auto")

        audio = np.zeros(service._sample_rate * 2, dtype=np.float32).tobytes()
        await service.process_chunk(audio)

        call = client.audio.transcriptions.calls[0]
        self.assertNotIn("language", call)

    async def test_openai_asr_injects_hotwords_prompt(self) -> None:
        """阶段 2：设置热词后，OpenAI 转录请求应携带 prompt 提示。"""
        client = FakeOpenAIClient()
        service = ASRService()
        service._engine = "openai"
        service._client = client
        service.set_hotwords(["Kubernetes", "K8s", "Transformer"])

        audio = np.zeros(service._sample_rate * 2, dtype=np.float32).tobytes()
        await service.process_chunk(audio)

        call = client.audio.transcriptions.calls[0]
        self.assertEqual(call["prompt"], "Kubernetes, K8s, Transformer")

    async def test_openai_asr_omits_hotwords_when_disabled(self) -> None:
        """阶段 2：热词开关关闭时请求不带 prompt。"""
        client = FakeOpenAIClient()
        service = ASRService()
        service._engine = "openai"
        service._client = client
        service.set_hotwords(["Kubernetes"])
        service.set_hotwords_enabled(False)

        audio = np.zeros(service._sample_rate * 2, dtype=np.float32).tobytes()
        await service.process_chunk(audio)

        call = client.audio.transcriptions.calls[0]
        self.assertNotIn("prompt", call)

    async def test_hotwords_filter_length_and_duplicates(self) -> None:
        """阶段 2：超长/空/重复热词被过滤，长度超限被裁剪。"""
        client = FakeOpenAIClient()
        service = ASRService()
        service._engine = "openai"
        service._client = client
        service.set_hotwords([
            "Kubernetes",
            "kubernetes",  # 大小写去重
            "   ",          # 空白被忽略
            "x" * 100,      # 超长被忽略
        ])

        self.assertEqual(service.hotwords, ["Kubernetes"])
        self.assertEqual(service.hotwords_enabled, True)

        audio = np.zeros(service._sample_rate * 2, dtype=np.float32).tobytes()
        await service.process_chunk(audio)
        call = client.audio.transcriptions.calls[0]
        self.assertEqual(call["prompt"], "Kubernetes")


class AudioEncodingTests(unittest.TestCase):
    def test_float32_audio_to_wav_bytes_writes_wav_container(self) -> None:
        audio = np.array([-2.0, -0.5, 0.5, 2.0], dtype=np.float32)
        wav_bytes = float32_audio_to_wav_bytes(audio, 16000)

        self.assertTrue(wav_bytes.startswith(b"RIFF"))
        self.assertIn(b"WAVE", wav_bytes[:16])


if __name__ == "__main__":
    unittest.main()
