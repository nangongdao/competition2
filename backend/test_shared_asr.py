"""ASR 多会话共享模型引用计数与生命周期测试（TD-3 深化）。"""

from __future__ import annotations

import sys
from pathlib import Path
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.asr_service import ASRService


class SharedAsrInstanceTests(unittest.TestCase):
    """验证 create_session 派生子会话共享模型 + 引用计数安全释放。"""

    def test_create_session_shares_model_state(self) -> None:
        parent = ASRService()
        parent._model = "shared-model"
        parent._client = "shared-client"

        child = parent.create_session()

        # 子会话与父会话共享同一个底层持有者
        self.assertIs(child._shared, parent._shared)
        self.assertIs(child._model, parent._model)
        self.assertIs(child._client, parent._client)
        # 共享引用计数 +1（父 1 + 子 1 = 2）
        self.assertEqual(parent._shared.refcount, 2)

    def test_child_shutdown_does_not_free_shared_model(self) -> None:
        parent = ASRService()
        parent._model = "shared-model"

        child = parent.create_session()
        # 释放子会话引用 -> 计数归 1，模型仍保留
        child._shared.release()
        self.assertEqual(parent._shared.refcount, 1)
        self.assertIsNotNone(parent._shared.model)

    def test_release_all_clears_resources(self) -> None:
        parent = ASRService()
        parent._model = "shared-model"
        parent._client = "shared-client"
        parent._vad = "shared-vad"

        child = parent.create_session()
        # 释放父 + 子两个引用 -> 计数归 0，底层资源被清空
        parent._shared.release()
        child._shared.release()
        self.assertEqual(parent._shared.refcount, 0)
        self.assertIsNone(parent._shared.model)
        self.assertIsNone(parent._shared.client)
        self.assertIsNone(parent._shared.vad)

    def test_acquire_increments_refcount(self) -> None:
        parent = ASRService()
        parent._shared.acquire()
        parent._shared.acquire()
        self.assertEqual(parent._shared.refcount, 3)

    def test_release_below_zero_is_noop(self) -> None:
        state = ASRService()._shared
        state.release()
        state.release()
        self.assertLessEqual(state.refcount, 0)

    def test_multiple_children_all_share_one_model(self) -> None:
        parent = ASRService()
        parent._model = "one-model"

        c1 = parent.create_session()
        c2 = parent.create_session()
        c3 = parent.create_session()

        # 父 + 3 子 = 4 引用，所有子共享同一模型
        self.assertEqual(parent._shared.refcount, 4)
        for child in (c1, c2, c3):
            self.assertIs(child._model, "one-model")

        # 关掉 3 个子会话，模型仍存活（父仍持有）
        for child in (c1, c2, c3):
            child._shared.release()
        self.assertEqual(parent._shared.refcount, 1)
        self.assertIsNotNone(parent._shared.model)

    def test_shutdown_parent_then_children_releases_all(self) -> None:
        parent = ASRService()
        parent._model = "model"
        child = parent.create_session()

        # 模拟应用关闭：先 parent.shutdown（计数 2->1），再 child（1->0）
        import asyncio

        asyncio.run(parent.shutdown())
        self.assertEqual(parent._shared.refcount, 1)
        self.assertIsNotNone(parent._shared.model)

        asyncio.run(child.shutdown())
        self.assertEqual(parent._shared.refcount, 0)
        self.assertIsNone(parent._shared.model)

    def test_create_session_resets_stream_state(self) -> None:
        parent = ASRService()
        parent._audio_buffer.append("buffered")  # type: ignore[arg-type]
        parent._latest_input_audio_chunk = b"x"

        child = parent.create_session()
        # 子会话拥有独立的流状态，不共享音频缓冲
        self.assertNotEqual(child._audio_buffer, parent._audio_buffer)
        self.assertEqual(child._latest_input_audio_chunk, b"")


if __name__ == "__main__":
    unittest.main()
