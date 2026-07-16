from app import create_app
from settings import AppSettings


class FakeLLMClient:
    def __init__(self, response="テスト回答", error=None):
        self.response = response
        self.error = error
        self.last_input = None
        self.call_count = 0

    def generate(self, user_input):
        self.call_count += 1
        self.last_input = user_input
        if self.error:
            raise self.error
        return self.response


def make_settings(**overrides):
    values = {
        "provider": "ollama",
        "model": "gemma3:4b",
        "ollama_host": "http://localhost:11434",
        "min_request_interval_seconds": 0,
    }
    values.update(overrides)
    return AppSettings(**values)


def csrf_post(client, user_input, *, follow_redirects=True):
    client.get("/")
    with client.session_transaction() as flask_session:
        csrf_token = flask_session["csrf_token"]
    return client.post(
        "/",
        data={"user_input": user_input, "csrf_token": csrf_token},
        follow_redirects=follow_redirects,
    )


def test_get_displays_configured_provider_and_model():
    app = create_app(FakeLLMClient(), make_settings())
    response = app.test_client().get("/")

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Ollama" in page
    assert "gemma3:4b" in page
    assert "http://localhost:11434" in page


def test_missing_flask_secret_key_logs_multi_worker_warning(
    monkeypatch, caplog
):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)

    create_app(FakeLLMClient(), make_settings())

    assert "複数ワーカーで運用する場合" in caplog.text


def test_flask_secret_key_uses_environment_value(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-shared-secret")

    app = create_app(FakeLLMClient(), make_settings())

    assert app.secret_key == "test-shared-secret"


def test_post_sends_question_to_selected_llm_then_redirects():
    llm_client = FakeLLMClient("こんにちは！")
    app = create_app(llm_client, make_settings())
    client = app.test_client()

    response = csrf_post(client, "こんにちは", follow_redirects=False)

    assert response.status_code == 303
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert "こんにちは！" in page
    assert llm_client.last_input == "こんにちは"


def test_refreshing_result_does_not_resubmit_to_llm():
    llm_client = FakeLLMClient()
    app = create_app(llm_client, make_settings())
    client = app.test_client()

    response = csrf_post(client, "質問", follow_redirects=False)
    client.get(response.headers["Location"])
    client.get(response.headers["Location"])

    assert llm_client.call_count == 1


def test_anthropic_provider_is_displayed_as_claude():
    settings = make_settings(
        provider="anthropic",
        model="claude-opus-4-6",
        anthropic_api_key="test-key",
    )
    app = create_app(FakeLLMClient(), settings)

    page = app.test_client().get("/").get_data(as_text=True)

    assert "Claude (Anthropic)" in page
    assert "claude-opus-4-6" in page


def test_lmstudio_provider_is_displayed():
    settings = make_settings(
        provider="lmstudio",
        model="local-model-id",
        lmstudio_base_url="http://localhost:1234/v1",
    )
    app = create_app(FakeLLMClient(), settings)

    page = app.test_client().get("/").get_data(as_text=True)

    assert "LM Studio" in page
    assert "local-model-id" in page
    assert "http://localhost:1234/v1" in page


def test_gemini_provider_is_displayed():
    settings = make_settings(
        provider="gemini",
        model="gemini-model-id",
        gemini_api_key="test-key",
    )
    app = create_app(FakeLLMClient(), settings)

    page = app.test_client().get("/").get_data(as_text=True)

    assert "Gemini (Google)" in page
    assert "gemini-model-id" in page


def test_openai_provider_is_displayed():
    settings = make_settings(
        provider="openai",
        model="compatible-model-id",
        openai_api_key="test-key",
    )
    app = create_app(FakeLLMClient(), settings)

    page = app.test_client().get("/").get_data(as_text=True)

    assert "GPT / Codex (OpenAI)" in page
    assert "compatible-model-id" in page


def test_empty_question_shows_validation_error():
    app = create_app(FakeLLMClient(), make_settings())
    response = csrf_post(app.test_client(), "   ")

    assert response.status_code == 400
    assert "質問を入力してください。" in response.get_data(as_text=True)


def test_missing_csrf_token_is_rejected_without_calling_llm():
    llm_client = FakeLLMClient()
    app = create_app(llm_client, make_settings())

    response = app.test_client().post("/", data={"user_input": "質問"})

    assert response.status_code == 400
    assert llm_client.call_count == 0


def test_llm_error_is_generic_and_does_not_leak_exception_detail():
    app = create_app(
        FakeLLMClient(error=ConnectionError("秘密の接続先への接続失敗")),
        make_settings(),
    )
    response = csrf_post(app.test_client(), "質問")
    page = response.get_data(as_text=True)

    assert response.status_code == 502
    assert "Ollamaから回答を取得できませんでした。" in page
    assert "秘密の接続先" not in page


def test_oversized_request_is_rejected():
    app = create_app(
        FakeLLMClient(),
        make_settings(max_request_bytes=1024, max_input_length=2000),
    )
    client = app.test_client()
    client.get("/")
    with client.session_transaction() as flask_session:
        csrf_token = flask_session["csrf_token"]

    response = client.post(
        "/",
        data={"user_input": "あ" * 1500, "csrf_token": csrf_token},
    )

    assert response.status_code == 413
    assert "送信データが大きすぎます" in response.get_data(as_text=True)
