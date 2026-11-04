import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_import(env_overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("OPENAI_MODEL", None)
    env.pop("OPENAI_TIMEOUT_SECONDS", None)
    env.update(env_overrides)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import main; print('model', main.OPENAI_MODEL, 'timeout', main.OPENAI_TIMEOUT)",
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_default_model_and_timeout_are_loaded():
    result = run_import({"OPENAI_API_KEY": "test-openai-key"})

    assert result.returncode == 0
    assert "model gpt-4o-mini timeout 45.0" in result.stdout


def test_model_and_timeout_can_be_overridden_by_environment():
    result = run_import(
        {
            "OPENAI_API_KEY": "test-openai-key",
            "OPENAI_MODEL": "test-model",
            "OPENAI_TIMEOUT_SECONDS": "12.5",
        }
    )

    assert result.returncode == 0
    assert "model test-model timeout 12.5" in result.stdout


def test_invalid_timeout_prevents_application_import():
    result = run_import(
        {
            "OPENAI_API_KEY": "test-openai-key",
            "OPENAI_TIMEOUT_SECONDS": "not-a-number",
        }
    )

    assert result.returncode != 0
    assert "ValueError" in result.stderr
