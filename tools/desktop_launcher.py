"""Local launcher for the AI Interpreter app.

The launcher serves the built Vite frontend, starts the FastAPI backend when
needed, and opens the UI in either an Electron BrowserWindow or the default web
browser. The Python process owns service lifecycle so backend/static services
are cleaned up when the app session exits.
"""

from __future__ import annotations

import argparse
import contextlib
from dataclasses import dataclass
import http.client
import http.server
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import webbrowser


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"
ELECTRON_MAIN = FRONTEND_DIR / "electron" / "main.cjs"
CONFIG_DIR = PROJECT_ROOT / "config"
DESKTOP_SETTINGS_LOCAL_PATH = CONFIG_DIR / "desktop-settings.local.json"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "desktop-launcher.log"

HOST = "127.0.0.1"
DEFAULT_BACKEND_PORT = 8000
DEFAULT_FRONTEND_PORT = 0
BACKEND_HEALTH_PATH = "/api/v1/health"
BACKEND_WS_PATH = "/api/v1/ws/translate"
BACKEND_START_TIMEOUT_SECONDS = 180
DEFAULT_DESKTOP_ASR_PROFILE = "remote"

#: 后端 CORS / WS Origin 白名单默认值（含 Vite dev server 与 launcher 注入的前端源）
DEFAULT_ALLOWED_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")


def frontend_origin_from_url(frontend_url: str) -> str:
    """从 launcher 的前端 URL 提取 origin（scheme://host[:port]）。

    launcher 使用随机端口提供前端，浏览器/Electron 的 WS 握手 Origin 会是
    该实际地址，必须注入后端 ALLOWED_ORIGINS，否则核心翻译流被 Origin 校验拒绝。
    """
    parsed = urlsplit(frontend_url)
    if parsed.port:
        return f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
    return f"{parsed.scheme}://{parsed.hostname}"
DESKTOP_ASR_PROFILE_ENV = "AI_INTERPRETER_DESKTOP_ASR_PROFILE"
WS_URL_QUERY_PARAM = "wsUrl"
LAUNCH_MODES = {"desktop", "web"}
SUPPORTED_UI_LANGUAGES = {"zh-CN", "en-US"}
SUPPORTED_TRANSLATION_ENGINES = {"claude", "openai"}
SUPPORTED_SOURCE_LANGUAGES = {"auto", "en", "ja", "ko", "es", "fr", "de"}

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class LauncherError(RuntimeError):
    """Raised when the desktop launcher cannot complete startup."""


@dataclass(frozen=True)
class DesktopAsrProfile:
    model: str
    device: str
    compute_type: str


@dataclass(frozen=True)
class DesktopSettings:
    ui_language: str = ""
    nmt_engine: str = ""
    nmt_model: str = ""
    openai_base_url: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    asr_model: str = ""
    asr_openai_base_url: str = ""
    asr_openai_api_key: str = ""
    asr_profile: str = ""
    source_language: str = ""


DESKTOP_ASR_PROFILES = {
    "light": DesktopAsrProfile(
        model="small",
        device="cpu",
        compute_type="int8",
    ),
    "cpu": DesktopAsrProfile(
        model="small",
        device="cpu",
        compute_type="int8",
    ),
    "gpu": DesktopAsrProfile(
        model="large-v3",
        device="cuda",
        compute_type="float16",
    ),
}


def load_desktop_settings(path: Path = DESKTOP_SETTINGS_LOCAL_PATH) -> DesktopSettings:
    if not path.exists():
        return DesktopSettings()

    try:
        with path.open("r", encoding="utf-8") as handle:
            raw_settings = json.load(handle)
    except (OSError, json.JSONDecodeError) as error:
        write_log(f"Ignoring desktop settings file {path}: {error}")
        return DesktopSettings()

    if not isinstance(raw_settings, dict):
        write_log(f"Ignoring desktop settings file {path}: root value must be an object")
        return DesktopSettings()

    settings = normalize_desktop_settings(raw_settings)
    write_log(f"Loaded desktop settings from {path}")
    return settings


def normalize_desktop_settings(raw_settings: dict[object, object]) -> DesktopSettings:
    translation = get_object_section(raw_settings, "translation")
    asr = get_object_section(raw_settings, "asr")
    runtime = get_object_section(raw_settings, "runtime")

    return DesktopSettings(
        ui_language=clean_allowed_string(
            get_string_value(raw_settings, "uiLanguage"),
            SUPPORTED_UI_LANGUAGES,
        ),
        nmt_engine=clean_allowed_string(
            get_string_value(translation, "engine"),
            SUPPORTED_TRANSLATION_ENGINES,
        ),
        nmt_model=get_string_value(translation, "model"),
        openai_base_url=get_string_value(translation, "openaiBaseUrl"),
        openai_api_key=get_string_value(translation, "openaiApiKey"),
        anthropic_api_key=get_string_value(translation, "anthropicApiKey"),
        asr_model=get_string_value(asr, "model"),
        asr_openai_base_url=get_string_value(asr, "openaiBaseUrl"),
        asr_openai_api_key=get_string_value(asr, "openaiApiKey"),
        asr_profile=clean_allowed_string(
            get_string_value(runtime, "asrProfile"),
            {"remote", "env", *DESKTOP_ASR_PROFILES.keys()},
        ),
        source_language=clean_allowed_string(
            get_string_value(runtime, "sourceLanguage"),
            SUPPORTED_SOURCE_LANGUAGES,
        ),
    )


def get_object_section(
    raw_settings: dict[object, object],
    name: str,
) -> dict[object, object]:
    value = raw_settings.get(name)
    if isinstance(value, dict):
        return value
    return {}


def get_string_value(raw_settings: dict[object, object], name: str) -> str:
    value = raw_settings.get(name)
    if isinstance(value, str):
        return value.strip()
    return ""


def clean_allowed_string(value: str, allowed_values: set[str]) -> str:
    if value in allowed_values:
        return value
    return ""


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


def parse_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"Port must be an integer: {value}") from error

    if port < 0 or port > 65535:
        raise argparse.ArgumentTypeError("Port must be between 0 and 65535")
    return port


def get_env_port(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    return parse_port(value)


def is_port_available(port: int) -> bool:
    if port == 0:
        return True

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((HOST, port))
        except OSError:
            return False
    return True


def find_available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))
        return int(probe.getsockname()[1])


def resolve_backend_port(requested_port: int) -> int:
    if requested_port == 0:
        selected_port = find_available_port()
        write_log(f"Backend port auto-selected: {HOST}:{selected_port}")
        return selected_port

    if is_backend_healthy(requested_port):
        write_log(f"Backend already healthy on requested port {HOST}:{requested_port}")
        return requested_port

    if is_port_available(requested_port):
        return requested_port

    selected_port = find_available_port()
    write_log(
        "Backend port "
        f"{HOST}:{requested_port} is occupied but not healthy; "
        f"using {HOST}:{selected_port}"
    )
    return selected_port


def build_backend_environment(
    port: int,
    asr_profile: str,
    desktop_settings: DesktopSettings | None = None,
    allowed_origins: tuple[str, ...] | None = None,
) -> dict[str, str]:
    resolved_settings = desktop_settings or DesktopSettings()
    env = os.environ.copy()
    env["PORT"] = str(port)
    apply_desktop_settings_to_env(env, resolved_settings)
    apply_desktop_asr_profile(env, asr_profile, resolved_settings)
    if allowed_origins:
        env["ALLOWED_ORIGINS"] = ",".join(allowed_origins)
    return env


def apply_desktop_settings_to_env(
    env: dict[str, str],
    desktop_settings: DesktopSettings,
) -> None:
    set_default_env_value(env, "NMT_ENGINE", desktop_settings.nmt_engine)
    set_default_env_value(env, "NMT_MODEL", desktop_settings.nmt_model)
    set_default_env_value(env, "OPENAI_BASE_URL", desktop_settings.openai_base_url)
    set_default_env_value(env, "OPENAI_API_KEY", desktop_settings.openai_api_key)
    set_default_env_value(env, "ANTHROPIC_API_KEY", desktop_settings.anthropic_api_key)
    set_default_env_value(env, "SOURCE_LANGUAGE", desktop_settings.source_language)


def resolve_desktop_asr_profile(
    cli_profile: str | None,
    desktop_settings: DesktopSettings,
) -> str:
    if cli_profile and cli_profile.strip():
        return cli_profile.strip()

    env_profile = os.environ.get(DESKTOP_ASR_PROFILE_ENV, "").strip()
    if env_profile:
        return env_profile

    if desktop_settings.asr_profile:
        return desktop_settings.asr_profile

    return DEFAULT_DESKTOP_ASR_PROFILE


def apply_desktop_asr_profile(
    env: dict[str, str],
    asr_profile: str,
    desktop_settings: DesktopSettings,
) -> None:
    profile_name = (asr_profile or DEFAULT_DESKTOP_ASR_PROFILE).strip().lower()
    if profile_name == "remote":
        set_default_env_value(env, "ASR_ENGINE", "openai")
        set_default_env_value(env, "ASR_OPENAI_MODEL", desktop_settings.asr_model)
        set_default_env_value(
            env,
            "ASR_OPENAI_BASE_URL",
            desktop_settings.asr_openai_base_url,
        )
        set_default_env_value(
            env,
            "ASR_OPENAI_API_KEY",
            desktop_settings.asr_openai_api_key,
        )
        write_log("Desktop ASR profile remote: ASR_ENGINE=openai")
        return

    if profile_name == "env":
        write_log(
            "Desktop ASR profile env selected; backend ASR settings come from "
            "process environment and dotenv files."
        )
        return

    profile = DESKTOP_ASR_PROFILES.get(profile_name)
    if profile is None:
        allowed = ", ".join(["remote", "env", *sorted(DESKTOP_ASR_PROFILES)])
        raise LauncherError(
            f"Unknown desktop ASR profile '{asr_profile}'. Choose one of: {allowed}."
        )

    set_default_env_value(env, "ASR_ENGINE", "whisper")
    set_default_env_value(env, "WHISPER_MODEL", profile.model)
    set_default_env_value(env, "WHISPER_DEVICE", profile.device)
    set_default_env_value(env, "WHISPER_COMPUTE_TYPE", profile.compute_type)
    write_log(
        f"Desktop ASR profile {profile_name}: "
        f"ASR_ENGINE={env['ASR_ENGINE']}, "
        f"WHISPER_MODEL={env['WHISPER_MODEL']}, "
        f"WHISPER_DEVICE={env['WHISPER_DEVICE']}, "
        f"WHISPER_COMPUTE_TYPE={env['WHISPER_COMPUTE_TYPE']}"
    )


def set_default_env_value(env: dict[str, str], key: str, value: str) -> None:
    if not value.strip():
        return
    if env.get(key, "").strip():
        return
    env[key] = value


def create_backend_ws_url(port: int) -> str:
    return f"ws://{HOST}:{port}{BACKEND_WS_PATH}"


def append_query_param(url: str, name: str, value: str) -> str:
    parsed_url = urlsplit(url)
    query_params = [
        (key, current_value)
        for key, current_value in parse_qsl(
            parsed_url.query,
            keep_blank_values=True,
        )
        if key != name
    ]
    query_params.append((name, value))
    return urlunsplit((
        parsed_url.scheme,
        parsed_url.netloc,
        parsed_url.path,
        urlencode(query_params),
        parsed_url.fragment,
    ))


def create_frontend_app_url(frontend_url: str, backend_ws_url: str) -> str:
    return append_query_param(frontend_url, WS_URL_QUERY_PARAM, backend_ws_url)


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


def start_backend(
    port: int,
    asr_profile: str,
    desktop_settings: DesktopSettings | None = None,
    allowed_origins: tuple[str, ...] | None = None,
) -> subprocess.Popen[str] | None:
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
    env = build_backend_environment(port, asr_profile, desktop_settings, allowed_origins)

    write_log(f"Starting backend: {' '.join(command)}")
    process = subprocess.Popen(
        command,
        cwd=BACKEND_DIR,
        env=env,
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


def electron_command() -> Path:
    if sys.platform == "win32":
        return FRONTEND_DIR / "node_modules" / ".bin" / "electron.cmd"
    return FRONTEND_DIR / "node_modules" / ".bin" / "electron"


def ensure_desktop_runtime() -> Path:
    executable = electron_command()
    if executable.exists():
        return executable

    write_log("Electron runtime missing; running npm install")
    run_command([npm_command(), "install"], FRONTEND_DIR)

    if executable.exists():
        return executable

    raise LauncherError("Electron runtime is missing after npm install")


def launch_desktop_window(url: str, backend_ws_url: str) -> subprocess.Popen[str]:
    electron_executable = ensure_desktop_runtime()
    if not ELECTRON_MAIN.exists():
        raise LauncherError(f"Electron main process file is missing: {ELECTRON_MAIN}")

    command = [str(electron_executable), str(ELECTRON_MAIN)]
    desktop_url = create_frontend_app_url(url, backend_ws_url)
    env = os.environ.copy()
    env["AI_INTERPRETER_DESKTOP_URL"] = desktop_url
    env["AI_INTERPRETER_LOG_FILE"] = str(LOG_FILE)

    write_log(f"Desktop backend WebSocket URL: {backend_ws_url}")
    write_log(f"Launching Electron desktop window: {' '.join(command)}")
    process = subprocess.Popen(
        command,
        cwd=FRONTEND_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )
    threading.Thread(
        target=stream_process_output,
        args=(process, "electron"),
        daemon=True,
    ).start()
    return process


def launch_web_browser(url: str, backend_ws_url: str) -> str:
    app_url = create_frontend_app_url(url, backend_ws_url)
    write_log(f"Web backend WebSocket URL: {backend_ws_url}")
    write_log(f"Opening browser app URL: {app_url}")
    opened = webbrowser.open(app_url, new=2)
    if not opened:
        write_log("Default browser did not report a successful open; URL printed to console")
    return app_url


def wait_for_web_session(app_url: str) -> None:
    print("")
    print("AI Interpreter web mode is running.")
    print(f"App URL: {app_url}")
    print(f"Startup log: {LOG_FILE}")
    print("Press Ctrl+C or close this window to stop launcher-owned services.")
    print("")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        write_log("Web launcher stopped by keyboard interrupt")


def terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start AI Interpreter in local mode")
    parser.add_argument(
        "--mode",
        choices=sorted(LAUNCH_MODES),
        default="desktop",
        help="Launch surface: desktop opens Electron, web opens the default browser",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build the frontend before starting local mode",
    )
    parser.add_argument(
        "--backend-port",
        type=parse_port,
        default=get_env_port("AI_INTERPRETER_BACKEND_PORT", DEFAULT_BACKEND_PORT),
        help=(
            "Preferred FastAPI backend port. Use 0 to choose an available port; "
            "occupied unhealthy ports are avoided automatically."
        ),
    )
    parser.add_argument(
        "--frontend-port",
        type=parse_port,
        default=get_env_port("AI_INTERPRETER_FRONTEND_PORT", DEFAULT_FRONTEND_PORT),
        help="Local static frontend port, or 0 for an available port",
    )
    parser.add_argument(
        "--asr-profile",
        default=None,
        help=(
            "Desktop ASR resource profile: remote uses OpenAI-compatible ASR, "
            "light/cpu uses small Whisper on CPU int8, gpu uses large-v3 on "
            "CUDA float16, env preserves dotenv ASR settings. Defaults to "
            "AI_INTERPRETER_DESKTOP_ASR_PROFILE, then local desktop settings, "
            "then remote."
        ),
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
    desktop_settings = load_desktop_settings()
    asr_profile = resolve_desktop_asr_profile(args.asr_profile, desktop_settings)

    splash = SplashWindow(enabled=not args.no_splash)
    backend_process: subprocess.Popen[str] | None = None
    frontend_server: http.server.ThreadingHTTPServer | None = None

    try:
        splash.set_status("Preparing frontend")
        ensure_frontend_build(force_build=args.build)

        splash.set_status("Starting frontend")
        frontend_server, frontend_url = start_frontend_server(args.frontend_port)

        splash.set_status("Starting backend")
        backend_port = resolve_backend_port(args.backend_port)
        # launcher 用随机端口提供前端，必须把实际前端 origin 注入白名单，
        # 否则浏览器/Electron 的 WS Origin 校验会拒绝核心翻译流。
        allowed_origins = DEFAULT_ALLOWED_ORIGINS + (
            frontend_origin_from_url(frontend_url),
        )
        backend_process = start_backend(
            backend_port,
            asr_profile,
            desktop_settings,
            allowed_origins=allowed_origins,
        )

        backend_ws_url = create_backend_ws_url(backend_port)
        splash.set_status("Opening app")

        if args.mode == "web":
            app_url = launch_web_browser(frontend_url, backend_ws_url)
            splash.close()
            wait_for_web_session(app_url)
            return 0

        desktop_process = launch_desktop_window(frontend_url, backend_ws_url)
        splash.close()
        desktop_process.wait()

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


if __name__ == "__main__":
    raise SystemExit(main())
