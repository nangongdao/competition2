"""Unit tests for backend settings loading."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.config import ENV_FILE_PATHS, REPO_ROOT, Settings


class SettingsConfigTests(unittest.TestCase):
    def test_default_env_files_include_local_backend_override(self) -> None:
        expected_paths = (
            REPO_ROOT / ".env",
            BACKEND_ROOT / ".env",
            BACKEND_ROOT / ".env.local",
        )

        self.assertEqual(ENV_FILE_PATHS, expected_paths)

    def test_later_dotenv_files_override_earlier_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root_env = Path(temp_dir) / "root.env"
            backend_env = Path(temp_dir) / "backend.env"
            local_env = Path(temp_dir) / "local.env"
            root_env.write_text(
                "ANTHROPIC_API_KEY=from-root\nNMT_ENGINE=claude\n",
                encoding="utf-8",
            )
            backend_env.write_text(
                "ANTHROPIC_API_KEY=from-backend\n",
                encoding="utf-8",
            )
            local_env.write_text(
                "ANTHROPIC_API_KEY=from-local\nUNKNOWN_LOCAL_VALUE=ignored\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                settings = Settings(_env_file=(root_env, backend_env, local_env))

        self.assertEqual(settings.anthropic_api_key, "from-local")
        self.assertEqual(settings.nmt_engine, "claude")

    def test_environment_variables_override_dotenv_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            local_env = Path(temp_dir) / "local.env"
            local_env.write_text(
                "ANTHROPIC_API_KEY=from-local\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {"ANTHROPIC_API_KEY": "from-env"},
                clear=True,
            ):
                settings = Settings(_env_file=local_env)

        self.assertEqual(settings.anthropic_api_key, "from-env")


if __name__ == "__main__":
    unittest.main()
