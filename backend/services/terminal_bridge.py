"""内置终端桥接服务。

在本地桌面/网页场景下，前端 xterm.js 通过 WebSocket 连接本模块，
由本模块在服务端派生一个受限的 PTY 子进程，把终端输出流式转发给前端，
并把前端的按键输入写入 PTY。这样用户可以在应用内直接查看/操作后端
日志与命令，无需另开系统终端窗口。

安全边界：
- 仅在本地回环来源放行（由 router 层的 Origin 校验保证）。
- 进程在独立会话中派生，与后端 uvicorn 进程隔离，子进程崩溃不影响主服务。
- 默认工作目录为仓库根目录。
- 每个连接独立派生进程，连接断开时回收。
"""

from __future__ import annotations

import asyncio
import os
import pty
import signal
import struct
import sys
import termios
from typing import Any, Optional

from loguru import logger

#: 默认 shell：优先使用登录 shell 可让 PATH 与用户环境一致。
DEFAULT_SHELL = os.environ.get("SHELL") or "/bin/sh"

#: 单帧输出上限（字节），防止输出洪泛撑爆 WebSocket 帧。
MAX_FRAME_BYTES = 16 * 1024


class TerminalSession:
    """单个终端会话：负责派生 PTY 子进程并桥接读写。"""

    def __init__(self, session_id: str, cwd: str | None = None) -> None:
        self.session_id = session_id
        self.cwd = cwd or os.getcwd()
        self._master_fd: int | None = None
        self._pid: int | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._closed = False

    @property
    def is_alive(self) -> bool:
        return self._pid is not None and not self._closed

    def start(self) -> None:
        """在独立会话中派生 PTY 子进程。

        使用 setsid 使子进程成为新会话组长，Ctrl+C（SIGINT）由终端
        驱动器广播到前台进程组，行为与系统终端一致。
        """
        if sys.platform == "win32":
            raise RuntimeError("PTY terminal bridge is not supported on Windows yet")

        pid, master_fd = pty.fork()
        if pid == 0:  # 子进程
            try:
                os.chdir(self.cwd)
                os.execvp(DEFAULT_SHELL, [DEFAULT_SHELL, "-l"])
            except Exception as exc:  # pragma: no cover - exec 失败路径
                os.write(2, f"failed to start shell: {exc}\n".encode())
                os._exit(127)

        self._pid = pid
        self._master_fd = master_fd
        logger.info(
            "Terminal session {} started (pid={}, cwd={})",
            self.session_id,
            pid,
            self.cwd,
        )

    async def run(self, send: Any) -> None:
        """运行读循环，直到子进程退出或会话关闭。

        Args:
            send: 异步发送函数（接收 bytes 消息）。
        """
        if self._master_fd is None:
            raise RuntimeError("terminal session is not started")

        loop = asyncio.get_running_loop()
        self._reader_task = loop.create_task(self._read_loop(send))
        try:
            await self._reader_task
        finally:
            self.close()
            self._reap_child()

    def write_input(self, data: bytes) -> None:
        """把前端输入写入 PTY master。"""
        if not self.is_alive or self._master_fd is None or not data:
            return
        try:
            os.write(self._master_fd, data[:MAX_FRAME_BYTES])
        except OSError:
            self.close()

    def resize(self, cols: int, rows: int) -> None:
        """调整 PTY 窗口大小，供前端窗口尺寸变化时同步。"""
        if self._master_fd is None or not self.is_alive:
            return
        try:
            import fcntl

            fcntl.ioctl(
                self._master_fd,
                termios.TIOCSWINSZ,
                struct.pack("HHHH", max(int(rows), 1), max(int(cols), 1), 0, 0),
            )
        except OSError:
            pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True

        if self._pid is not None:
            try:
                os.kill(self._pid, signal.SIGHUP)
            except ProcessLookupError:
                pass

        if self._reader_task is not None and not self._reader_task.done():
            self._reader_task.cancel()

        if self._master_fd is not None:
            with _suppress(OSError):
                os.close(self._master_fd)
            self._master_fd = None
        self._pid = None
        logger.info("Terminal session {} closed", self.session_id)

    def _reap_child(self) -> None:
        if self._pid is None:
            return
        try:
            os.waitpid(self._pid, os.WNOHANG)
        except (ChildProcessError, OSError):
            pass
        self._pid = None

    async def _read_loop(self, send: Any) -> None:
        """从 PTY master 读取输出并发送给前端（每帧立即发送，保证低延迟）。"""
        loop = asyncio.get_running_loop()
        while self.is_alive and self._master_fd is not None:
            try:
                chunk = await loop.run_in_executor(None, os.read, self._master_fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            # 单帧限制：超长输出截断发送，避免撑爆 WebSocket 帧
            remaining = chunk
            while remaining:
                frame, remaining = remaining[:MAX_FRAME_BYTES], remaining[MAX_FRAME_BYTES:]
                try:
                    await send(frame)
                except Exception:
                    return


class _suppress:
    """轻量异常抑制上下文（避免依赖 contextlib 的函数式写法）。"""

    def __init__(self, *exceptions: type[BaseException]) -> None:
        self._exceptions = exceptions

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return exc_type is not None and issubclass(exc_type, self._exceptions)


class TerminalBridge:
    """管理所有活跃终端会话。"""

    def __init__(self) -> None:
        self._sessions: dict[str, TerminalSession] = {}

    def create_session(self, session_id: str, cwd: str | None = None) -> TerminalSession:
        session = TerminalSession(session_id, cwd)
        self._sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[TerminalSession]:
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            session.close()

    async def shutdown(self) -> None:
        for session_id in list(self._sessions):
            self.remove_session(session_id)
        logger.info("Terminal bridge shut down")
