"""Git管理外のYAMLからアプリ設定を安全に読み込む。"""

from __future__ import annotations

import ipaddress
import math
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
    max_response_length: int = 20000
    result_ttl_seconds: float = 600.0
    min_request_interval_seconds: float = 1.0
    max_concurrent_requests: int = 1
    max_tokens: int = 1024
    temperature: float = 0.7
    request_timeout_seconds: float = 180.0
    max_retries: int = 0
    system_prompt: str = ""
    ollama_host: str = "http://localhost:11434"
    ollama_allow_insecure_http: bool = False
    lmstudio_base_url: str = "http://localhost:1234/v1"
    lmstudio_api_key: str = field(default="lm-studio", repr=False)
    lmstudio_allow_insecure_http: bool = False
    anthropic_api_key: str = field(default="", repr=False)
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_allow_custom_base_url: bool = False
    gemini_api_key: str = field(default="", repr=False)
    openai_api_key: str = field(default="", repr=False)
    openai_base_url: str = "https://api.openai.com/v1"
    openai_allow_custom_base_url: bool = False
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
            return "Ollama API（接続先は非表示）"
        if self.provider == "lmstudio":
            return "LM Studio API（接続先は非表示）"
        if self.provider == "anthropic":
            return "Anthropic API"
        if self.provider == "gemini":
            return "Gemini API"
        return "OpenAI API"

    @property
    def uses_insecure_remote_http(self) -> bool:
        if self.provider == "ollama":
            endpoint = self.ollama_host
        elif self.provider == "lmstudio":
            endpoint = self.lmstudio_base_url
        else:
            return False
        parsed = urlparse(endpoint)
        return parsed.scheme == "http" and not _is_loopback_host(parsed.hostname)


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
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{setting_name}は整数で指定してください。")
    try:
        return int(value)
    except (OverflowError, TypeError, ValueError) as exc:
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
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{setting_name}は数値で指定してください。") from exc
    if not math.isfinite(number):
        raise ValueError(f"{setting_name}は有限の数値で指定してください。")
    return number


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


def _is_loopback_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    normalized = hostname.rstrip(".").lower()
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def _validated_url(
    value: str,
    setting_name: str,
    *,
    require_https: bool = False,
) -> str:
    if "\\" in value or any(
        character.isspace() or ord(character) < 32 for character in value
    ):
        raise ValueError(
            f"{setting_name}に空白、制御文字、バックスラッシュは使用できません。"
        )
    try:
        parsed = urlparse(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise ValueError(f"{setting_name}は有効なURLで指定してください。") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not hostname:
        raise ValueError(
            f"{setting_name}はhttp://またはhttps://から始まる有効なURLで指定してください。"
        )
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{setting_name}のURLに認証情報を埋め込まないでください。")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{setting_name}のURLにクエリやフラグメントは指定できません。")
    if require_https and parsed.scheme != "https" and not _is_loopback_host(hostname):
        raise ValueError(
            f"{setting_name}はHTTPSを使用してください。"
            "HTTPはlocalhostなどのループバック接続でのみ使用できます。"
        )
    return value.rstrip("/")


def _validated_cloud_url(
    value: str,
    setting_name: str,
    official_url: str,
    allow_custom_base_url: bool,
) -> str:
    validated_url = _validated_url(value, setting_name, require_https=True)
    if not allow_custom_base_url and validated_url != official_url:
        provider_name = setting_name.split(".")[1]
        raise ValueError(
            f"{setting_name}を公式接続先以外へ変更する場合は、"
            f"llm.{provider_name}.allow_custom_base_urlをtrueにしてください。"
        )
    return validated_url


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
            f"設定ファイル「{path}」がありません。\n"
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

    anthropic_api_key = _environment_value("ANTHROPIC_API_KEY") or _string(
        anthropic_config, "api_key", "", "llm.anthropic.api_key"
    )
    gemini_api_key = _environment_value("GEMINI_API_KEY", "GOOGLE_API_KEY") or _string(
        gemini_config, "api_key", "", "llm.gemini.api_key"
    )
    openai_api_key = _environment_value("OPENAI_API_KEY") or _string(
        openai_config, "api_key", "", "llm.openai.api_key"
    )
    lmstudio_api_key = (
        _environment_value("LM_STUDIO_API_KEY", "LM_API_TOKEN")
        or _string(lmstudio_config, "api_key", "lm-studio", "llm.lmstudio.api_key")
        or "lm-studio"
    )
    ollama_allow_insecure_http = _boolean(
        ollama_config,
        "allow_insecure_http",
        False,
        "llm.ollama.allow_insecure_http",
    )
    lmstudio_allow_insecure_http = _boolean(
        lmstudio_config,
        "allow_insecure_http",
        False,
        "llm.lmstudio.allow_insecure_http",
    )
    anthropic_allow_custom_base_url = _boolean(
        anthropic_config,
        "allow_custom_base_url",
        False,
        "llm.anthropic.allow_custom_base_url",
    )
    openai_allow_custom_base_url = _boolean(
        openai_config,
        "allow_custom_base_url",
        False,
        "llm.openai.allow_custom_base_url",
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
        max_response_length=_integer(
            app_config,
            "max_response_length",
            20000,
            "app.max_response_length",
        ),
        result_ttl_seconds=_number(
            app_config,
            "result_ttl_seconds",
            600.0,
            "app.result_ttl_seconds",
        ),
        min_request_interval_seconds=_number(
            app_config,
            "min_request_interval_seconds",
            1.0,
            "app.min_request_interval_seconds",
        ),
        max_concurrent_requests=_integer(
            app_config,
            "max_concurrent_requests",
            1,
            "app.max_concurrent_requests",
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
            require_https=not ollama_allow_insecure_http,
        ),
        ollama_allow_insecure_http=ollama_allow_insecure_http,
        lmstudio_base_url=_validated_url(
            _string(
                lmstudio_config,
                "base_url",
                "http://localhost:1234/v1",
                "llm.lmstudio.base_url",
            ),
            "llm.lmstudio.base_url",
            require_https=not lmstudio_allow_insecure_http,
        ),
        lmstudio_api_key=lmstudio_api_key,
        lmstudio_allow_insecure_http=lmstudio_allow_insecure_http,
        anthropic_api_key=anthropic_api_key,
        anthropic_base_url=_validated_cloud_url(
            _string(
                anthropic_config,
                "base_url",
                "https://api.anthropic.com",
                "llm.anthropic.base_url",
            ),
            "llm.anthropic.base_url",
            "https://api.anthropic.com",
            anthropic_allow_custom_base_url,
        ),
        anthropic_allow_custom_base_url=anthropic_allow_custom_base_url,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        openai_base_url=_validated_cloud_url(
            _string(
                openai_config,
                "base_url",
                "https://api.openai.com/v1",
                "llm.openai.base_url",
            ),
            "llm.openai.base_url",
            "https://api.openai.com/v1",
            openai_allow_custom_base_url,
        ),
        openai_allow_custom_base_url=openai_allow_custom_base_url,
        openai_use_temperature=_boolean(
            openai_config,
            "use_temperature",
            False,
            "llm.openai.use_temperature",
        ),
    )

    if settings.max_input_length < 1:
        raise ValueError("app.max_input_lengthは1以上を指定してください。")
    if settings.max_input_length > 100_000:
        raise ValueError("app.max_input_lengthは100000以下を指定してください。")
    if settings.max_request_bytes < 1024:
        raise ValueError("app.max_request_bytesは1024以上を指定してください。")
    if settings.max_request_bytes > 10_485_760:
        raise ValueError("app.max_request_bytesは10485760以下を指定してください。")
    if settings.max_response_length < 1000:
        raise ValueError("app.max_response_lengthは1000以上を指定してください。")
    if settings.max_response_length > 1_000_000:
        raise ValueError("app.max_response_lengthは1000000以下を指定してください。")
    if settings.result_ttl_seconds <= 0:
        raise ValueError("app.result_ttl_secondsは0より大きい値を指定してください。")
    if settings.result_ttl_seconds > 86_400:
        raise ValueError("app.result_ttl_secondsは86400以下を指定してください。")
    if settings.min_request_interval_seconds < 0:
        raise ValueError("app.min_request_interval_secondsは0以上を指定してください。")
    if settings.min_request_interval_seconds > 3600:
        raise ValueError("app.min_request_interval_secondsは3600以下を指定してください。")
    if settings.max_concurrent_requests < 1:
        raise ValueError("app.max_concurrent_requestsは1以上を指定してください。")
    if settings.max_concurrent_requests > 32:
        raise ValueError("app.max_concurrent_requestsは32以下を指定してください。")
    if settings.max_tokens < 1:
        raise ValueError("llm.max_tokensは1以上を指定してください。")
    if settings.max_tokens > 100_000:
        raise ValueError("llm.max_tokensは100000以下を指定してください。")
    if not 0 <= settings.temperature <= 1:
        raise ValueError("llm.temperatureは0以上1以下を指定してください。")
    if settings.request_timeout_seconds <= 0:
        raise ValueError("llm.request_timeout_secondsは0より大きい値を指定してください。")
    if settings.request_timeout_seconds > 3600:
        raise ValueError("llm.request_timeout_secondsは3600以下を指定してください。")
    if settings.max_retries < 0:
        raise ValueError("llm.max_retriesは0以上を指定してください。")
    if settings.max_retries > 5:
        raise ValueError("llm.max_retriesは5以下を指定してください。")

    return settings
