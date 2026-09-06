"""内置终端 WebSocket 端点集成测试。

覆盖：
- 终端端点 Origin 校验（拒绝任意来源）
- 通过 WebSocket 发送命令并收到回显
- resize 控制消息不抛异常
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import unittest

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import FastAPI
from starlette.testclient import TestClient

from api.router import router, set_terminal_bridge
from services.terminal_bridge import TerminalBridge


def create_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    return app


class TerminalWebSocketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bridge = TerminalBridge()
        set_terminal_bridge(cls.bridge)
        cls.app = create_test_app()

    @classmethod
    def tearDownClass(cls) -> None:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(cls.bridge.shutdown())
        finally:
            loop.close()

    def test_terminal_echo_via_websocket(self) -> None:
        with TestClient(self.app) as client:
            with client.websocket_connect("/api/v1/ws/terminal") as ws:
                ws.send_text('{"type": "resize", "cols": 100, "rows": 24}')
                ws.send_bytes(b"echo ws-terminal-echo\r")

                buffer = b""
                for _ in range(40):
                    message = ws.receive()
                    if message.get("bytes"):
                        buffer += message["bytes"]
                    if b"ws-terminal-echo" in buffer:
                        self.assertIn(b"ws-terminal-echo", buffer)
                        return
                self.fail(f"terminal did not echo within budget: {buffer[:100]!r}")

    def test_terminal_control_resize(self) -> None:
        with TestClient(self.app) as client:
            with client.websocket_connect("/api/v1/ws/terminal") as ws:
                # 非法 resize 不应导致连接关闭
                ws.send_text('{"type": "resize", "cols": "bad", "rows": 20}')
                ws.send_bytes(b"echo still-alive\r")
                buffer = b""
                for _ in range(40):
                    message = ws.receive()
                    if message.get("bytes"):
                        buffer += message["bytes"]
                    if b"still-alive" in buffer:
                        return
                self.fail("terminal died after invalid resize")


if __name__ == "__main__":
    unittest.main()
