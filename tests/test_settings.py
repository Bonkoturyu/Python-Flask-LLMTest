from pathlib import Path

import pytest

from settings import load_settings


@pytest.fixture(autouse=True)
def clear_configuration_environment(monkeypatch):
    for name in (
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "LM_STUDIO_API_KEY",
        "LM_API_TOKEN",
        "LLM_CONFIG_FILE",
    ):
        monkeypatch.delenv(name, raising=False)


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
    allow_insecure_http: true
""",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.model == "gemma3:4b"
    assert settings.max_input_length == 1234
    assert settings.ollama_host == "http://example:11434"
    assert settings.ollama_allow_insecure_http is True


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
    allow_insecure_http: true
""",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.provider == "lmstudio"
    assert settings.lmstudio_base_url == "http://example:1234/v1"
    assert settings.lmstudio_api_key == "test-token"
    assert settings.lmstudio_allow_insecure_http is True


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


def test_environment_api_keys_override_yaml_values(tmp_path: Path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
llm:
  provider: gemini
  model: model-id
  anthropic:
    api_key: yaml-anthropic-key
  gemini:
    api_key: yaml-gemini-key
  openai:
    api_key: yaml-openai-key
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-environment-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    settings = load_settings(config)

    assert settings.anthropic_api_key == "anthropic-environment-key"
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


@pytest.mark.parametrize(
    "invalid_url",
    [
        "https://user:secret@example.com/v1",
        "https://example.com/v1?api_key=secret",
        "https://example.com/v1#secret",
        "https://example.com\\@attacker.example/v1",
        "https://example.com:not-a-port/v1",
    ],
)
def test_rejects_unsafe_connection_urls(tmp_path: Path, invalid_url: str):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
llm:
  provider: openai
  model: model-id
  openai:
    base_url: {invalid_url}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        load_settings(config)


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_cloud_provider_rejects_remote_plain_http(
    tmp_path: Path,
    provider: str,
):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
llm:
  provider: {provider}
  model: model-id
  {provider}:
    base_url: http://api.example.com/v1
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="HTTPS"):
        load_settings(config)


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_cloud_provider_allows_loopback_http_for_compatible_server(
    tmp_path: Path,
    provider: str,
):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
llm:
  provider: {provider}
  model: model-id
  {provider}:
    base_url: http://127.0.0.1:9999/v1
    allow_custom_base_url: true
""",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.provider == provider


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_cloud_provider_rejects_unapproved_custom_https_endpoint(
    tmp_path: Path,
    provider: str,
):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
llm:
  provider: {provider}
  model: model-id
  {provider}:
    base_url: https://compatible.example.invalid/v1
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="allow_custom_base_url"):
        load_settings(config)


@pytest.mark.parametrize("provider", ["anthropic", "openai"])
def test_cloud_provider_allows_explicit_custom_https_endpoint(
    tmp_path: Path,
    provider: str,
):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
llm:
  provider: {provider}
  model: model-id
  {provider}:
    base_url: https://compatible.example.invalid/v1
    allow_custom_base_url: true
""",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.provider == provider


@pytest.mark.parametrize(
    ("provider", "url_key", "remote_url"),
    [
        ("ollama", "host", "http://ollama.example.invalid:11434"),
        ("lmstudio", "base_url", "http://lmstudio.example.invalid:1234/v1"),
    ],
)
def test_local_provider_rejects_remote_plain_http_without_explicit_opt_in(
    tmp_path: Path,
    provider: str,
    url_key: str,
    remote_url: str,
):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
llm:
  provider: {provider}
  model: model-id
  {provider}:
    {url_key}: {remote_url}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="HTTPS"):
        load_settings(config)


def test_loads_response_security_limits(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
app:
  max_response_length: 1234
  result_ttl_seconds: 45
  max_concurrent_requests: 2
llm:
  provider: ollama
  model: model-id
""",
        encoding="utf-8",
    )

    settings = load_settings(config)

    assert settings.max_response_length == 1234
    assert settings.result_ttl_seconds == 45
    assert settings.max_concurrent_requests == 2


@pytest.mark.parametrize(
    ("setting_name", "value", "message"),
    [
        ("max_tokens", 100_001, "100000以下"),
        ("request_timeout_seconds", 3601, "3600以下"),
        ("max_retries", 6, "5以下"),
    ],
)
def test_rejects_cost_or_resource_limit_misconfiguration(
    tmp_path: Path,
    setting_name: str,
    value: int,
    message: str,
):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
llm:
  provider: ollama
  model: model-id
  {setting_name}: {value}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        load_settings(config)


def test_rejects_excessive_concurrency(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
app:
  max_concurrent_requests: 33
llm:
  provider: ollama
  model: model-id
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="32以下"):
        load_settings(config)


@pytest.mark.parametrize(
    ("setting_name", "value", "message"),
    [
        ("max_input_length", 100_001, "100000以下"),
        ("max_request_bytes", 10_485_761, "10485760以下"),
        ("max_response_length", 1_000_001, "1000000以下"),
        ("result_ttl_seconds", 86_401, "86400以下"),
        ("min_request_interval_seconds", 3601, "3600以下"),
    ],
)
def test_rejects_excessive_app_resource_limits(
    tmp_path: Path,
    setting_name: str,
    value: int,
    message: str,
):
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
app:
  {setting_name}: {value}
llm:
  provider: ollama
  model: model-id
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        load_settings(config)


def test_rejects_non_finite_number(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
llm:
  provider: ollama
  model: model-id
  request_timeout_seconds: .nan
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="有限の数値"):
        load_settings(config)


def test_rejects_fractional_integer(tmp_path: Path):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
llm:
  provider: ollama
  model: model-id
  max_tokens: 1.5
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="整数"):
        load_settings(config)


def test_missing_config_message_separates_the_recovery_instruction(
    tmp_path: Path,
):
    missing_config = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError) as error:
        load_settings(missing_config)

    assert "ありません。\nconfig.example.yaml" in str(error.value)
