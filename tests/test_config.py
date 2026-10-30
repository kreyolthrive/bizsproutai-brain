import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_import_with_env(env_overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(env_overrides)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import main; print('backend', main.RATE_LIMIT_BACKEND, 'limiter', main.RATE_LIMITER is None)",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
    )


def test_rate_limit_backend_none_imports_successfully():
    result = _run_import_with_env(
        {
            "OPENAI_API_KEY": "test-openai-key",
            "RATE_LIMIT_BACKEND": "none",
        }
    )
    assert result.returncode == 0
    assert "backend none limiter True" in result.stdout


def test_rate_limit_backend_unsupported_fails_import():
    result = _run_import_with_env(
        {
            "OPENAI_API_KEY": "test-openai-key",
            "RATE_LIMIT_BACKEND": "redis",
        }
    )
    assert result.returncode != 0
    assert "Unsupported RATE_LIMIT_BACKEND" in result.stderr
