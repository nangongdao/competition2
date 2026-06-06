"""Desktop-style launcher for the local AI Interpreter app.

The launcher keeps the project lightweight: it serves the built Vite frontend,
starts the FastAPI backend when needed, and opens Edge/Chrome in app mode so the
user gets a native-window feel without adding a large desktop runtime.
"""

from __future__ import annotations

import argparse
import contextlib
import http.client
import http.server
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "desktop-launcher.log"

HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8000
DEFAULT_FRONTEND_PORT = 0
BACKEND_HEALTH_PATH = "/api/v1/health"
BACKEND_START_TIMEOUT_SECONDS = 35

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class LauncherError(RuntimeError):
    """Raised when the desktop launcher cannot complete startup."""


class SplashWindow:
    """Small Tk splash window used while local services are starting."""

    def __init__(self, enabled: bool) -> None:
        self._root = None
        self._status_label = None

        if not enabled:
            return

        try:
            import tkinter as tk
        except Exception as error:  # pragma: no cover - depends on OS image
            write_log(f"Tk splash unavailable: {error}")
            return

        root = tk.Tk()
        root.title("AI Interpreter")
        root.geometry("420x190")
        root.resizable(False, False)
        root.configure(bg="#101722")

        title = tk.Label(
            root,
            text="AI Interpreter",
            bg="#101722",
            fg="#f4f7fb",
            font=("Segoe UI", 18, "bold"),
        )
        title.pack(pady=(28, 8))

        subtitle = tk.Label(
            root,
            text="Starting local services",
            bg="#101722",
            fg="#9fb0c4",
            font=("Segoe UI", 10),
        )
        subtitle.pack()

        status_label = tk.Label(
            root,
            text="Preparing...",
            bg="#101722",
            fg="#63d2ff",
            font=("Segoe UI", 10),
        )
        status_label.pack(pady=(22, 0))

        root.update()
        self._root = root
        self._status_label = status_label

    def set_status(self, message: str) -> None:
        if self._root is None or self._status_label is None:
            write_log(message)
            return

        self._status_label.configure(text=message)
        self._root.update()

    def close(self) -> None:
        if self._root is None:
            return

        with contextlib.suppress(Exception):
            self._root.destroy()
        self._root = None
        self._status_label = None


def write_log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def reset_log() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text("", encoding="utf-8")


def show_error(message: str) -> None:
    detailed_message = f"{message}\n\nSee log:\n{LOG_FILE}"
    try:
        import tkinter as tk
        from tkinter import messagebox
    except Exception:  # pragma: no cover - depends on OS image
        write_log(detailed_message)
        return

    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("AI Interpreter startup failed", detailed_message)
    root.destroy()


def run_command(command: list[str], cwd: Path) -> None:
    write_log(f"Running command in {cwd}: {' '.join(command)}")
    completed = subprocess.run(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )

    if completed.stdout:
        write_log(completed.stdout.rstrip())

    if completed.returncode != 0:
        raise LauncherError(
            f"Command failed with exit code {completed.returncode}: {' '.join(command)}"
        )


def npm_command() -> str:
    if sys.platform == "win32":
        return "npm.cmd"
    return "npm"


def ensure_frontend_build(force_build: bool) -> None:
    index_file = DIST_DIR / "index.html"
    if index_file.exists() and not force_build:
        write_log("Using existing frontend build")
        return

    if not (FRONTEND_DIR / "node_modules").exists():
        run_command([npm_command(), "install"], FRONTEND_DIR)

    run_command([npm_command(), "run", "build"], FRONTEND_DIR)

    if not index_file.exists():
        raise LauncherError("Frontend build did not create dist/index.html")


def resolve_python_executable() -> str:
    configured = os.environ.get("AI_INTERPRETER_PYTHON")
    if configured:
        return configured

    if sys.platform == "win32":
        venv_python = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
    else:
        venv_python = BACKEND_DIR / ".venv" / "bin" / "python"

    if venv_python.exists():
        return str(venv_python)

    for candidate in ("python", "python3"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    raise LauncherError(
        "Python executable not found. Set AI_INTERPRETER_PYTHON or create backend/.venv."
    )


def is_backend_healthy(port: int) -> bool:
    connection = http.client.HTTPConnection(HOST, port, timeout=1.2)
    try:
        connection.request("GET", BACKEND_HEALTH_PATH)
        response = connection.getresponse()
        response.read()
        return response.status == 200
    except OSError:
        return False
    finally:
        connection.close()


def stream_process_output(process: subprocess.Popen[str], prefix: str) -> None:
    stream = process.stdout
    if stream is None:
        return

    for line in stream:
        write_log(f"{prefix}: {line.rstrip()}")


def start_backend(port: int) -> subprocess.Popen[str] | None:
    if is_backend_healthy(port):
        write_log(f"Backend already healthy on {HOST}:{port}")
        return None

    python_executable = resolve_python_executable()
    command = [
        python_executable,
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        HOST,
        "--port",
        str(port),
    ]

    write_log(f"Starting backend: {' '.join(command)}")
    process = subprocess.Popen(
        command,
        cwd=BACKEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )
    threading.Thread(
        target=stream_process_output,
        args=(process, "backend"),
        daemon=True,
    ).start()

    deadline = time.monotonic() + BACKEND_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise LauncherError(
                f"Backend exited before becoming healthy, code {process.returncode}"
            )
        if is_backend_healthy(port):
            write_log("Backend health check passed")
            return process
        time.sleep(0.4)

    terminate_process(process)
    raise LauncherError("Backend did not become healthy before timeout")


class DesktopStaticHandler(http.server.SimpleHTTPRequestHandler):
    """Static file handler rooted at the built frontend directory."""

    def log_message(self, format_text: str, *args: object) -> None:
        write_log(f"frontend: {format_text % args}")


def start_frontend_server(port: int) -> tuple[http.server.ThreadingHTTPServer, str]:
    if not (DIST_DIR / "index.html").exists():
        raise LauncherError("Frontend dist/index.html is missing")

    class Handler(DesktopStaticHandler):
        def __init__(
            self,
            *args: object,
            directory: str | None = None,
            **kwargs: object,
        ) -> None:
            super().__init__(*args, directory=str(DIST_DIR), **kwargs)

    server = http.server.ThreadingHTTPServer((HOST, port), Handler)
    actual_port = int(server.server_address[1])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://{HOST}:{actual_port}/"
    write_log(f"Frontend server started at {url}")
    return server, url


def windows_browser_candidates() -> list[Path]:
    candidates: list[Path] = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
        base = os.environ.get(env_name)
        if not base:
            continue
        root = Path(base)
        candidates.extend(
            [
                root / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                root / "Google" / "Chrome" / "Application" / "chrome.exe",
            ]
        )
    return candidates


def resolve_app_browser() -> str | None:
    configured = os.environ.get("AI_INTERPRETER_BROWSER")
    if configured:
        return configured

    if sys.platform == "win32":
        for candidate in windows_browser_candidates():
            if candidate.exists():
                return str(candidate)

    for name in ("msedge", "microsoft-edge", "google-chrome", "chrome", "chromium"):
        resolved = shutil.which(name)
        if resolved:
            return resolved

    return None


def launch_browser_app(url: str, profile_dir: Path) -> subprocess.Popen[str] | None:
    browser = resolve_app_browser()
    if browser is None:
        write_log("No app-mode browser found; falling back to default browser")
        webbrowser.open(url)
        return None

    command = [
        browser,
        f"--app={url}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--disable-extensions",
    ]
    write_log(f"Launching browser app: {' '.join(command)}")
    return subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )


def terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def wait_without_browser_process() -> None:
    write_log("Waiting until interrupted because browser process is not trackable")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        write_log("Launcher interrupted")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start AI Interpreter in desktop mode")
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build the frontend before starting desktop mode",
    )
    parser.add_argument(
        "--backend-port",
        type=int,
        default=int(os.environ.get("AI_INTERPRETER_BACKEND_PORT", DEFAULT_BACKEND_PORT)),
        help="FastAPI backend port",
    )
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=int(os.environ.get("AI_INTERPRETER_FRONTEND_PORT", DEFAULT_FRONTEND_PORT)),
        help="Local static frontend port, or 0 for an available port",
    )
    parser.add_argument(
        "--no-splash",
        action="store_true",
        help="Disable the startup splash window",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reset_log()

    splash = SplashWindow(enabled=not args.no_splash)
    backend_process: subprocess.Popen[str] | None = None
    frontend_server: http.server.ThreadingHTTPServer | None = None
    profile_dir = Path(tempfile.mkdtemp(prefix="ai-interpreter-desktop-"))

    try:
        splash.set_status("Preparing frontend")
        ensure_frontend_build(force_build=args.build)

        splash.set_status("Starting frontend")
        frontend_server, frontend_url = start_frontend_server(args.frontend_port)

        splash.set_status("Starting backend")
        backend_process = start_backend(args.backend_port)

        splash.set_status("Opening app window")
        browser_process = launch_browser_app(frontend_url, profile_dir)
        splash.close()

        if browser_process is None:
            wait_without_browser_process()
        else:
            browser_process.wait()

        return 0
    except LauncherError as error:
        splash.close()
        write_log(f"Startup failed: {error}")
        show_error(str(error))
        return 1
    finally:
        if frontend_server is not None:
            frontend_server.shutdown()
            frontend_server.server_close()
            write_log("Frontend server stopped")

        if backend_process is not None:
            terminate_process(backend_process)
            write_log("Backend process stopped")

        shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
