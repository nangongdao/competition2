"""内置终端桥接服务测试。

覆盖：
- TerminalSession 派生 PTY 子进程并回显输出
- resize 调整窗口尺寸
- close 回收子进程
- TerminalBridge 会话生命周期
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import os
import sys
import time
import unittest


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.terminal_bridge import TerminalBridge, TerminalSession


class TerminalSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self) -> None:
        self.loop.close()

    def test_session_spawns_pty_and_echoes_input(self) -> None:
        async def scenario() -> None:
            session = TerminalSession("test-echo", cwd="/tmp")
            session.start()
            self.assertTrue(session.is_alive)

            session.write_input(b"echo pty-ok\r")

            deadline = time.monotonic() + 3.0
            output = b""
            while time.monotonic() < deadline:
                chunk = session._read_available()
                if chunk:
                    output += chunk
                if b"pty-ok" in output:
                    break
                await asyncio.sleep(0.05)

            self.assertIn(b"pty-ok", output)
            session.close()
            self.assertFalse(session.is_alive)

        self.loop.run_until_complete(scenario())

    def test_session_resize(self) -> None:
        async def scenario() -> None:
            session = TerminalSession("test-resize", cwd="/tmp")
            session.start()
            # resize 不应抛异常，且不影响存活
            session.resize(120, 40)
            session.resize(0, 0)  # 非法值应被钳制
            self.assertTrue(session.is_alive)
            session.close()

        self.loop.run_until_complete(scenario())

    def test_session_start_on_windows_raises(self) -> None:
        if sys.platform != "win32":
            self.skipTest("PTY-only check applies to Windows")
        session = TerminalSession("test-win", cwd="/tmp")
        with self.assertRaises(RuntimeError):
            session.start()

    def test_bridge_lifecycle(self) -> None:
        async def scenario() -> None:
            bridge = TerminalBridge()
            session = bridge.create_session("bridge-1", cwd="/tmp")
            session.start()
            self.assertIs(bridge.get_session("bridge-1"), session)

            bridge.remove_session("bridge-1")
            self.assertIsNone(bridge.get_session("bridge-1"))
            self.assertFalse(session.is_alive)

            await bridge.shutdown()

        self.loop.run_until_complete(scenario())


def _read_available_impl(session: TerminalSession) -> bytes:
    """同步读取 PTY master 上当前可读的输出（供测试轮询）。"""
    if session._master_fd is None:
        return b""
    try:
        import fcntl

        flags = fcntl.fcntl(session._master_fd, fcntl.F_GETFL)
        fcntl.fcntl(session._master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    except OSError:
        return b""
    chunks = []
    while True:
        try:
            data = os.read(session._master_fd, 4096)
            if not data:
                break
            chunks.append(data)
        except BlockingIOError:
            break
        except OSError:
            break
    return b"".join(chunks)


# 给 TerminalSession 挂上测试辅助方法（避免污染生产类）
TerminalSession._read_available = _read_available_impl


if __name__ == "__main__":
    unittest.main()
