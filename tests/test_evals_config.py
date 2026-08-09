from pathlib import Path

import pytest

from evals.asset_snapshot.config import EvalSettings


def test_eval_settings_load_judge_configuration_from_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EVAL_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("EVAL_JUDGE_BASE_URL", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "EVAL_JUDGE_MODEL=qwen3:8b\nEVAL_JUDGE_BASE_URL=http://judge-host:11434\n",
        encoding="utf-8",
    )

    settings = EvalSettings(_env_file=env_path)

    assert settings.eval_judge_model == "qwen3:8b"
    assert settings.eval_judge_base_url == "http://judge-host:11434"


def test_environment_overrides_eval_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("EVAL_JUDGE_MODEL=dotenv-model\n", encoding="utf-8")
    monkeypatch.setenv("EVAL_JUDGE_MODEL", "process-model")

    settings = EvalSettings(_env_file=env_path)

    assert settings.eval_judge_model == "process-model"


def test_empty_eval_configuration_uses_none_for_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EVAL_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("EVAL_JUDGE_BASE_URL", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "EVAL_JUDGE_MODEL=\nEVAL_JUDGE_BASE_URL=   \n",
        encoding="utf-8",
    )

    settings = EvalSettings(_env_file=env_path)

    assert settings.eval_judge_model is None
    assert settings.eval_judge_base_url is None
