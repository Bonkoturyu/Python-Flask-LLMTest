"""Git管理外のYAMLからアプリ設定を安全に読み込む。"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.local.yaml"


@dataclass(frozen=True)
class AppSettings:
    provider: str
    model: str
    max_input_length: int = 4000
    max_request_bytes: int = 65536
    min_request_interval_seconds: float = 1.0
    max_tokens: int = 1024
    temperature: float = 0.7
    request_timeout_seconds: float = 180.0
    max_retries: int = 0
    system_prompt: str = ""
    ollama_host: str = "http://localhost:11434"
    lmstudio_base_url: str = "http://localhost:1234/v1"
    lmstudio_api_key: str = field(default="lm-studio", repr=False)
    anthropic_api_key: str = field(default="", repr=False)
    anthropic_base_url: str = "https://api.anthropic.com"
    gemini_api_key: str = field(default="", repr=False)
    openai_api_key: str = field(default="", repr=False)
    openai_base_url: str = "https://api.openai.com/v1"
    openai_use_temperature: bool = False

    @property
    def provider_display_name(self) -> str:
        names = {
            "ollama": "Ollama",
            "lmstudio": "LM Studio",
            "anthropic": "Claude (Anthropic)",
            "gemini": "Gemini (Google)",
            "openai": "GPT / Codex (OpenAI)",
        }
        return names[self.provider]

    @property
    def connection_label(self) -> str:
        if self.provider == "ollama":
            return self.ollama_host
        if self.provider == "lmstudio":
            return self.lmstudio_base_url
        if self.provider == "anthropic":
            return self.anthropic_base_url
        if self.provider == "gemini":
            return "Gemini API"
        return self.openai_base_url


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"設定項目「{name}」はマッピング形式で指定してください。")
    return value


def _string(
    mapping: dict[str, Any],
    key: str,
    default: str,
    setting_name: str,
) -> str:
    value = mapping.get(key)
    if value is None:
        return default
    if not isinstance(value, str):
        raise ValueError(f"{setting_name}は文字列で指定してください。")
    return value.strip()


def _integer(
    mapping: dict[str, Any],
    key: str,
    default: int,
    setting_name: str,
) -> int:
    value = mapping.get(key, default)
    if isinstance(value, bool):
        raise ValueError(f"{setting_name}は整数で指定してください。")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{setting_name}は整数で指定してください。") from exc


def _number(
    mapping: dict[str, Any],
    key: str,
    default: float,
    setting_name: str,
) -> float:
    value = mapping.get(key, default)
    if isinstance(value, bool):
        raise ValueError(f"{setting_name}は数値で指定してください。")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{setting_name}は数値で指定してください。") from exc


def _boolean(
    mapping: dict[str, Any],
    key: str,
    default: bool,
    setting_name: str,
) -> bool:
    value = mapping.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{setting_name}はtrueまたはfalseで指定してください。")
    return value


def _validated_url(value: str, setting_name: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(
            f"{setting_name}はhttp://またはhttps://から始まる有効なURLで指定してください。"
        )
    return value.rstrip("/")


def _environment_value(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def load_settings(config_path: str | Path | None = None) -> AppSettings:
    """YAML設定を検証してAppSettingsへ変換する。"""
    configured_path = config_path or os.getenv("LLM_CONFIG_FILE")
    path = Path(configured_path) if configured_path else DEFAULT_CONFIG_PATH
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path = path.resolve()

    if not path.exists():
        raise FileNotFoundError(
            f"設定ファイル「{path}」がありません。"
            "config.example.yamlをconfig.local.yamlへコピーしてください。"
        )

    with path.open(encoding="utf-8") as config_file:
        raw = yaml.safe_load(config_file) or {}

    root = _mapping(raw, "ルート")
    app_config = _mapping(root.get("app"), "app")
    llm_config = _mapping(root.get("llm"), "llm")
    ollama_config = _mapping(llm_config.get("ollama"), "llm.ollama")
    lmstudio_config = _mapping(llm_config.get("lmstudio"), "llm.lmstudio")
    anthropic_config = _mapping(llm_config.get("anthropic"), "llm.anthropic")
    gemini_config = _mapping(llm_config.get("gemini"), "llm.gemini")
    openai_config = _mapping(llm_config.get("openai"), "llm.openai")

    provider = _string(llm_config, "provider", "ollama", "llm.provider").lower()
    aliases = {
        "claude": "anthropic",
        "lm-studio": "lmstudio",
        "lm_studio": "lmstudio",
        "google": "gemini",
        "gpt": "openai",
        "codex": "openai",
    }
    provider = aliases.get(provider, provider)
    supported_providers = {"ollama", "lmstudio", "anthropic", "gemini", "openai"}
    if provider not in supported_providers:
        raise ValueError(
            "llm.providerはollama、lmstudio、anthropic、gemini、openaiの"
            "いずれかを指定してください。"
        )

    model = _string(llm_config, "model", "", "llm.model")
    if not model:
        raise ValueError("llm.modelを指定してください。")

    anthropic_api_key = _string(
        anthropic_config, "api_key", "", "llm.anthropic.api_key"
    ) or _environment_value("ANTHROPIC_API_KEY")
    gemini_api_key = _string(
        gemini_config, "api_key", "", "llm.gemini.api_key"
    ) or _environment_value("GEMINI_API_KEY", "GOOGLE_API_KEY")
    openai_api_key = _string(
        openai_config, "api_key", "", "llm.openai.api_key"
    ) or _environment_value("OPENAI_API_KEY")
    lmstudio_api_key = (
        _environment_value("LM_STUDIO_API_KEY", "LM_API_TOKEN")
        or _string(lmstudio_config, "api_key", "lm-studio", "llm.lmstudio.api_key")
        or "lm-studio"
    )

    settings = AppSettings(
        provider=provider,
        model=model,
        max_input_length=_integer(
            app_config, "max_input_length", 4000, "app.max_input_length"
        ),
        max_request_bytes=_integer(
            app_config, "max_request_bytes", 65536, "app.max_request_bytes"
        ),
        min_request_interval_seconds=_number(
            app_config,
            "min_request_interval_seconds",
            1.0,
            "app.min_request_interval_seconds",
        ),
        max_tokens=_integer(llm_config, "max_tokens", 1024, "llm.max_tokens"),
        temperature=_number(llm_config, "temperature", 0.7, "llm.temperature"),
        request_timeout_seconds=_number(
            llm_config,
            "request_timeout_seconds",
            180.0,
            "llm.request_timeout_seconds",
        ),
        max_retries=_integer(llm_config, "max_retries", 0, "llm.max_retries"),
        system_prompt=_string(
            llm_config, "system_prompt", "", "llm.system_prompt"
        ),
        ollama_host=_validated_url(
            _string(
                ollama_config,
                "host",
                "http://localhost:11434",
                "llm.ollama.host",
            ),
            "llm.ollama.host",
        ),
        lmstudio_base_url=_validated_url(
            _string(
                lmstudio_config,
                "base_url",
                "http://localhost:1234/v1",
                "llm.lmstudio.base_url",
            ),
            "llm.lmstudio.base_url",
        ),
        lmstudio_api_key=lmstudio_api_key,
        anthropic_api_key=anthropic_api_key,
        anthropic_base_url=_validated_url(
            _string(
                anthropic_config,
                "base_url",
                "https://api.anthropic.com",
                "llm.anthropic.base_url",
            ),
            "llm.anthropic.base_url",
        ),
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        openai_base_url=_validated_url(
            _string(
                openai_config,
                "base_url",
                "https://api.openai.com/v1",
                "llm.openai.base_url",
            ),
            "llm.openai.base_url",
        ),
        openai_use_temperature=_boolean(
            openai_config,
            "use_temperature",
            False,
            "llm.openai.use_temperature",
        ),
    )

    if settings.max_input_length < 1:
        raise ValueError("app.max_input_lengthは1以上を指定してください。")
    if settings.max_request_bytes < 1024:
        raise ValueError("app.max_request_bytesは1024以上を指定してください。")
    if settings.min_request_interval_seconds < 0:
        raise ValueError("app.min_request_interval_secondsは0以上を指定してください。")
    if settings.max_tokens < 1:
        raise ValueError("llm.max_tokensは1以上を指定してください。")
    if not 0 <= settings.temperature <= 1:
        raise ValueError("llm.temperatureは0以上1以下を指定してください。")
    if settings.request_timeout_seconds <= 0:
        raise ValueError("llm.request_timeout_secondsは0より大きい値を指定してください。")
    if settings.max_retries < 0:
        raise ValueError("llm.max_retriesは0以上を指定してください。")

    return settings
