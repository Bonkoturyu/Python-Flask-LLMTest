from types import SimpleNamespace

from llm_clients import (
    AnthropicLLMClient,
    GeminiLLMClient,
    LMStudioLLMClient,
    OllamaLLMClient,
    OpenAICloudLLMClient,
)
from settings import AppSettings


class FakeOllamaSDK:
    def __init__(self):
        self.parameters = None

    def chat(self, **parameters):
        self.parameters = parameters
        return {"message": {"content": "Ollama回答"}}


class FakeMessagesAPI:
    def __init__(self):
        self.parameters = None

    def create(self, **parameters):
        self.parameters = parameters
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="Claude回答")],
            stop_reason="end_turn",
        )


class FakeChatCompletionsAPI:
    def __init__(self):
        self.parameters = None

    def create(self, **parameters):
        self.parameters = parameters
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="LM Studio回答"),
                    finish_reason="stop",
                )
            ]
        )


class FakeInteractionsAPI:
    def __init__(self):
        self.parameters = None

    def create(self, **parameters):
        self.parameters = parameters
        return SimpleNamespace(output_text="Gemini回答")


class FakeResponsesAPI:
    def __init__(self):
        self.parameters = None

    def create(self, **parameters):
        self.parameters = parameters
        return SimpleNamespace(output_text="OpenAI回答", status="completed")


def test_ollama_client_uses_configured_model():
    sdk = FakeOllamaSDK()
    settings = AppSettings(
        provider="ollama",
        model="qwen2.5-coder:1.5b",
        system_prompt="日本語で回答してください。",
    )

    answer = OllamaLLMClient(settings, sdk).generate("質問")

    assert answer == "Ollama回答"
    assert sdk.parameters["model"] == "qwen2.5-coder:1.5b"
    assert sdk.parameters["messages"][0]["role"] == "system"


def test_anthropic_client_uses_messages_api():
    messages_api = FakeMessagesAPI()
    sdk = SimpleNamespace(messages=messages_api)
    settings = AppSettings(
        provider="anthropic",
        model="claude-opus-4-6",
        anthropic_api_key="test-key",
        max_tokens=512,
    )

    answer = AnthropicLLMClient(settings, sdk).generate("質問")

    assert answer == "Claude回答"
    assert messages_api.parameters["model"] == "claude-opus-4-6"
    assert messages_api.parameters["max_tokens"] == 512


def test_lmstudio_client_uses_openai_compatible_api():
    completions_api = FakeChatCompletionsAPI()
    sdk = SimpleNamespace(
        chat=SimpleNamespace(completions=completions_api)
    )
    settings = AppSettings(
        provider="lmstudio",
        model="local-model-id",
        max_tokens=256,
        system_prompt="日本語で回答してください。",
    )

    answer = LMStudioLLMClient(settings, sdk).generate("質問")

    assert answer == "LM Studio回答"
    assert completions_api.parameters["model"] == "local-model-id"
    assert completions_api.parameters["max_tokens"] == 256
    assert completions_api.parameters["messages"][0]["role"] == "system"


def test_gemini_client_uses_interactions_api():
    interactions_api = FakeInteractionsAPI()
    sdk = SimpleNamespace(interactions=interactions_api)
    settings = AppSettings(
        provider="gemini",
        model="gemini-model-id",
        gemini_api_key="test-key",
        max_tokens=300,
        system_prompt="日本語で回答してください。",
    )

    answer = GeminiLLMClient(settings, sdk).generate("質問")

    assert answer == "Gemini回答"
    assert interactions_api.parameters["model"] == "gemini-model-id"
    assert interactions_api.parameters["store"] is False
    assert interactions_api.parameters["generation_config"]["max_output_tokens"] == 300
    assert interactions_api.parameters["system_instruction"] == "日本語で回答してください。"


def test_openai_client_uses_responses_api():
    responses_api = FakeResponsesAPI()
    sdk = SimpleNamespace(responses=responses_api)
    settings = AppSettings(
        provider="openai",
        model="gpt-5.6-sol",
        openai_api_key="test-key",
        max_tokens=400,
        system_prompt="日本語で回答してください。",
    )

    answer = OpenAICloudLLMClient(settings, sdk).generate("質問")

    assert answer == "OpenAI回答"
    assert responses_api.parameters["model"] == "gpt-5.6-sol"
    assert responses_api.parameters["max_output_tokens"] == 400
    assert responses_api.parameters["store"] is False
    assert responses_api.parameters["instructions"] == "日本語で回答してください。"
    assert "temperature" not in responses_api.parameters


def test_openai_client_sends_temperature_only_when_enabled():
    responses_api = FakeResponsesAPI()
    sdk = SimpleNamespace(responses=responses_api)
    settings = AppSettings(
        provider="openai",
        model="compatible-model-id",
        openai_api_key="test-key",
        temperature=0.2,
        openai_use_temperature=True,
    )

    OpenAICloudLLMClient(settings, sdk).generate("質問")

    assert responses_api.parameters["temperature"] == 0.2


def test_anthropic_client_warns_when_output_is_truncated():
    messages_api = FakeMessagesAPI()
    sdk = SimpleNamespace(messages=messages_api)
    settings = AppSettings(
        provider="anthropic",
        model="claude-model-id",
        anthropic_api_key="test-key",
    )
    messages_api.create = lambda **_: SimpleNamespace(
        content=[SimpleNamespace(type="text", text="途中まで")],
        stop_reason="max_tokens",
    )

    answer = AnthropicLLMClient(settings, sdk).generate("質問")

    assert "出力上限に達した" in answer
