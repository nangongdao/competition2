"""Preflight checks for real WebSocket endurance baselines.

The preflight is intentionally secret-safe: it reports whether required
provider keys are configured, but never prints or stores key values.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import importlib.metadata
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit, urlunsplit

import redis.asyncio as aioredis


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.config import settings


DEFAULT_OUTPUT_PATH = Path("reports/endurance-preflight-latest.json")
PLACEHOLDER_MARKERS = ("your-", "-here", "example", "placeholder")
PROVIDER_KEY_BY_ENGINE = {
    "claude": ("ANTHROPIC_API_KEY", "anthropic_api_key"),
    "openai": ("OPENAI_API_KEY", "openai_api_key"),
}


@dataclass(frozen=True)
class PreflightConfig:
    output_path: Path
    load_whisper_model: bool


async def check_redis() -> dict[str, object]:
    client = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        protocol=settings.redis_protocol,
    )
    try:
        await client.ping()
        info = await client.info("server")
        version = str(info.get("redis_version", "unknown"))
        return {
            "ok": True,
            "url": redact_url(settings.redis_url),
            "protocol": settings.redis_protocol,
            "version": version,
        }
    except Exception as exc:
        return {
            "ok": False,
            "url": redact_url(settings.redis_url),
            "protocol": settings.redis_protocol,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
    finally:
        await client.aclose()


def build_provider_check() -> dict[str, object]:
    key_config = PROVIDER_KEY_BY_ENGINE.get(settings.nmt_engine)
    if not key_config:
        return {
            "supported": False,
            "engine": settings.nmt_engine,
            "model": settings.nmt_model,
            "required_key": "",
            "key_present": False,
        }

    key_name, settings_attr = key_config
    value = str(getattr(settings, settings_attr, "")).strip()
    return {
        "supported": True,
        "engine": settings.nmt_engine,
        "model": settings.nmt_model,
        "required_key": key_name,
        "key_present": bool(value) and not is_placeholder_value(value),
    }


def build_whisper_check(*, load_model: bool) -> dict[str, object]:
    package_version = get_package_version("faster-whisper")
    cuda_available = detect_cuda_available()
    result: dict[str, object] = {
        "engine": settings.asr_engine,
        "package_present": package_version is not None,
        "package_version": package_version or "",
        "model": settings.whisper_model,
        "device": settings.whisper_device,
        "compute_type": settings.whisper_compute_type,
        "cuda_available": cuda_available,
        "model_load_checked": load_model,
    }

    if load_model and package_version is not None and settings.asr_engine == "whisper":
        result.update(load_whisper_model())

    return result


def load_whisper_model() -> dict[str, object]:
    try:
        from faster_whisper import WhisperModel

        model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        del model
        return {"model_load_ok": True}
    except Exception as exc:
        return {
            "model_load_ok": False,
            "model_load_error_type": type(exc).__name__,
            "model_load_error": str(exc),
        }


def build_report(
    *,
    redis_check: dict[str, object],
    provider_check: dict[str, object],
    whisper_check: dict[str, object],
) -> dict[str, object]:
    blockers: list[str] = []

    if not redis_check.get("ok"):
        blockers.append("Redis is not reachable with the configured protocol.")

    if not provider_check.get("supported"):
        blockers.append("NMT_ENGINE is not supported by the preflight.")
    elif not provider_check.get("key_present"):
        required_key = str(provider_check.get("required_key", "provider key"))
        blockers.append(f"{required_key} is missing or still uses a placeholder value.")

    if whisper_check.get("engine") != "whisper":
        blockers.append("ASR_ENGINE must be whisper for the real endurance baseline.")
    if not whisper_check.get("package_present"):
        blockers.append("faster-whisper is not installed in the backend environment.")
    if whisper_check.get("device") == "cuda" and not whisper_check.get("cuda_available"):
        blockers.append("WHISPER_DEVICE is cuda, but no CUDA device is available.")
    if (
        whisper_check.get("model_load_checked")
        and not whisper_check.get("model_load_ok", True)
    ):
        blockers.append("Whisper model load failed.")

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "ready" if not blockers else "blocked",
        "blockers": blockers,
        "checks": {
            "redis": redis_check,
            "provider": provider_check,
            "whisper": whisper_check,
        },
        "next_command_when_ready": (
            "python tools/endurance_runner.py --duration-seconds 1800 "
            "--source silence --output reports/endurance-30m.json "
            "--max-dropped-chunks 0 --max-queue-depth 8 --min-received-ratio 0.99"
        ),
    }


def redact_url(url: str) -> str:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    if parsed.username or parsed.password:
        host = f"***@{host}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def is_placeholder_value(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def get_package_version(package_name: str) -> str | None:
    try:
        return importlib.metadata.version(package_name)
    except importlib.metadata.PackageNotFoundError:
        return None


def detect_cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        pass

    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_args(argv: list[str] | None = None) -> PreflightConfig:
    parser = argparse.ArgumentParser(
        description="Check Redis, Whisper, and provider readiness for endurance baselines.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--load-whisper-model",
        action="store_true",
        help="Instantiate the configured Whisper model; may download model files.",
    )
    args = parser.parse_args(argv)
    return PreflightConfig(
        output_path=args.output,
        load_whisper_model=args.load_whisper_model,
    )


async def async_main(argv: list[str] | None = None) -> int:
    config = parse_args(argv)
    report = build_report(
        redis_check=await check_redis(),
        provider_check=build_provider_check(),
        whisper_check=build_whisper_check(load_model=config.load_whisper_model),
    )
    write_report(config.output_path, report)
    sys.stdout.write(f"Endurance preflight report written to {config.output_path}\n")
    if report["status"] == "ready":
        return 0
    sys.stderr.write("Endurance preflight blocked:\n")
    for blocker in report["blockers"]:
        sys.stderr.write(f"- {blocker}\n")
    return 2


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(async_main(argv))
    except KeyboardInterrupt:
        sys.stderr.write("Endurance preflight interrupted.\n")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
