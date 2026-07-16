from pathlib import Path

import pytest

from settings import load_settings


def test_loads_ollama_settings(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
app:
  max_input_length: 1234
llm:
  provider: ollama
  model: gemma3:4b
  ollama:
    host: http://example:11434/
""",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.model == "gemma3:4b"
    assert settings.max_input_length == 1234
    assert settings.ollama_host == "http://example:11434"


def test_claude_alias_selects_anthropic(tmp_path: Path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
llm:
  provider: claude
  model: claude-opus-4-6
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "environment-key")

    settings = load_settings(config)

    assert settings.provider == "anthropic"
    assert settings.anthropic_api_key == "environment-key"


def test_loads_lmstudio_settings(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
llm:
  provider: lm-studio
  model: local-model-id
  lmstudio:
    base_url: http://example:1234/v1/
    api_key: test-token
""",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.provider == "lmstudio"
    assert settings.lmstudio_base_url == "http://example:1234/v1"
    assert settings.lmstudio_api_key == "test-token"


@pytest.mark.parametrize(
    ("provider_alias", "expected_provider"),
    [
        ("google", "gemini"),
        ("gpt", "openai"),
        ("codex", "openai"),
    ],
)
def test_cloud_provider_aliases(
    tmp_path: Path,
    provider_alias: str,
    expected_provider: str,
):
    config = tmp_path / f"{provider_alias}.yaml"
    config.write_text(
        f"llm:\n  provider: {provider_alias}\n  model: model-id\n",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.provider == expected_provider


def test_loads_cloud_api_keys_from_environment(tmp_path: Path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(
        "llm:\n  provider: gemini\n  model: model-id\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    settings = load_settings(config)

    assert settings.gemini_api_key == "gemini-key"
    assert settings.openai_api_key == "openai-key"


def test_rejects_unknown_provider(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "llm:\n  provider: unknown\n  model: test\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="ollama、lmstudio、anthropic、gemini、openai",
    ):
        load_settings(config)


def test_null_model_is_rejected_instead_of_becoming_none_string(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "llm:\n  provider: ollama\n  model: null\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="llm.model"):
        load_settings(config)


def test_null_api_key_falls_back_to_environment(tmp_path: Path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
llm:
  provider: openai
  model: model-id
  openai:
    api_key: null
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key")

    settings = load_settings(config)

    assert settings.openai_api_key == "environment-key"
    assert "environment-key" not in repr(settings)


def test_rejects_invalid_connection_url(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
llm:
  provider: ollama
  model: model-id
  ollama:
    host: localhost:11434
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="有効なURL"):
        load_settings(config)
