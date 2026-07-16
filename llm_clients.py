"""プロバイダー別LLMクライアント。"""

from __future__ import annotations

from typing import Any

import anthropic
import ollama
from google import genai
from google.genai import types as genai_types
from openai import OpenAI

from settings import AppSettings


TRUNCATION_NOTICE = (
    "\n\n※出力上限に達したため、回答が途中で終了しています。"
    "必要に応じてllm.max_tokensを増やしてください。"
)


def _with_truncation_notice(text: str, truncated: bool) -> str:
    return f"{text}{TRUNCATION_NOTICE}" if truncated else text


class OllamaLLMClient:
    def __init__(self, settings: AppSettings, client: Any | None = None) -> None:
        self.settings = settings
        self.client = client or ollama.Client(
            host=settings.ollama_host,
            timeout=settings.request_timeout_seconds,
        )

    def generate(self, user_input: str) -> str:
        messages = []
        if self.settings.system_prompt:
            messages.append(
                {"role": "system", "content": self.settings.system_prompt}
            )
        messages.append({"role": "user", "content": user_input})

        response = self.client.chat(
            model=self.settings.model,
            messages=messages,
            options={
                "temperature": self.settings.temperature,
                "num_predict": self.settings.max_tokens,
            },
        )
        message = response["message"]
        content = message.get("content") if isinstance(message, dict) else message.content
        if not content:
            raise RuntimeError("Ollamaの応答にテキストが含まれていません。")
        done_reason = (
            response.get("done_reason")
            if isinstance(response, dict)
            else getattr(response, "done_reason", None)
        )
        return _with_truncation_notice(str(content), done_reason == "length")


class AnthropicLLMClient:
    def __init__(self, settings: AppSettings, client: Any | None = None) -> None:
        if not settings.anthropic_api_key and client is None:
            raise ValueError(
                "Claudeを使用する場合はllm.anthropic.api_keyまたは"
                "ANTHROPIC_API_KEYを設定してください。"
            )
        self.settings = settings
        self.client = client or anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            timeout=settings.request_timeout_seconds,
            max_retries=settings.max_retries,
        )

    def generate(self, user_input: str) -> str:
        parameters: dict[str, Any] = {
            "model": self.settings.model,
            "max_tokens": self.settings.max_tokens,
            "temperature": self.settings.temperature,
            "messages": [{"role": "user", "content": user_input}],
        }
        if self.settings.system_prompt:
            parameters["system"] = self.settings.system_prompt

        response = self.client.messages.create(**parameters)
        text_blocks = [
            block.text
            for block in response.content
            if getattr(block, "type", None) == "text"
        ]
        if not text_blocks:
            raise RuntimeError("Claudeの応答にテキストが含まれていません。")
        text = "\n".join(text_blocks)
        return _with_truncation_notice(
            text, getattr(response, "stop_reason", None) == "max_tokens"
        )


class LMStudioLLMClient:
    def __init__(self, settings: AppSettings, client: Any | None = None) -> None:
        self.settings = settings
        self.client = client or OpenAI(
            base_url=settings.lmstudio_base_url,
            api_key=settings.lmstudio_api_key,
            timeout=settings.request_timeout_seconds,
            max_retries=settings.max_retries,
        )

    def generate(self, user_input: str) -> str:
        messages = []
        if self.settings.system_prompt:
            messages.append(
                {"role": "system", "content": self.settings.system_prompt}
            )
        messages.append({"role": "user", "content": user_input})

        response = self.client.chat.completions.create(
            model=self.settings.model,
            messages=messages,
            max_tokens=self.settings.max_tokens,
            temperature=self.settings.temperature,
        )
        choice = response.choices[0]
        content = choice.message.content
        if not content:
            raise RuntimeError("LM Studioの応答にテキストが含まれていません。")
        return _with_truncation_notice(
            str(content), getattr(choice, "finish_reason", None) == "length"
        )


class GeminiLLMClient:
    def __init__(self, settings: AppSettings, client: Any | None = None) -> None:
        if not settings.gemini_api_key and client is None:
            raise ValueError(
                "Geminiを使用する場合はllm.gemini.api_key、GEMINI_API_KEY、"
                "GOOGLE_API_KEYのいずれかを設定してください。"
            )
        self.settings = settings
        self.client = client or genai.Client(
            api_key=settings.gemini_api_key,
            http_options=genai_types.HttpOptions(
                timeout=int(settings.request_timeout_seconds * 1000),
                retry_options=genai_types.HttpRetryOptions(
                    attempts=settings.max_retries + 1
                ),
            ),
        )

    def generate(self, user_input: str) -> str:
        parameters: dict[str, Any] = {
            "model": self.settings.model,
            "input": user_input,
            "store": False,
            "generation_config": {
                "temperature": self.settings.temperature,
                "max_output_tokens": self.settings.max_tokens,
            },
        }
        if self.settings.system_prompt:
            parameters["system_instruction"] = self.settings.system_prompt

        interaction = self.client.interactions.create(**parameters)
        if not interaction.output_text:
            raise RuntimeError("Geminiの応答にテキストが含まれていません。")
        return str(interaction.output_text)


class OpenAICloudLLMClient:
    def __init__(self, settings: AppSettings, client: Any | None = None) -> None:
        if not settings.openai_api_key and client is None:
            raise ValueError(
                "GPTまたはCodexを使用する場合はllm.openai.api_keyまたは"
                "OPENAI_API_KEYを設定してください。"
            )
        self.settings = settings
        self.client = client or OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.request_timeout_seconds,
            max_retries=settings.max_retries,
        )

    def generate(self, user_input: str) -> str:
        parameters: dict[str, Any] = {
            "model": self.settings.model,
            "input": user_input,
            "max_output_tokens": self.settings.max_tokens,
            "store": False,
        }
        if self.settings.system_prompt:
            parameters["instructions"] = self.settings.system_prompt
        if self.settings.openai_use_temperature:
            parameters["temperature"] = self.settings.temperature

        response = self.client.responses.create(**parameters)
        if not response.output_text:
            raise RuntimeError("OpenAIの応答にテキストが含まれていません。")
        return _with_truncation_notice(
            str(response.output_text), getattr(response, "status", None) == "incomplete"
        )


def build_llm_client(
    settings: AppSettings,
) -> (
    OllamaLLMClient
    | LMStudioLLMClient
    | AnthropicLLMClient
    | GeminiLLMClient
    | OpenAICloudLLMClient
):
    if settings.provider == "ollama":
        return OllamaLLMClient(settings)
    if settings.provider == "lmstudio":
        return LMStudioLLMClient(settings)
    if settings.provider == "anthropic":
        return AnthropicLLMClient(settings)
    if settings.provider == "gemini":
        return GeminiLLMClient(settings)
    return OpenAICloudLLMClient(settings)
