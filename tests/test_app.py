from threading import Event, Thread
from types import SimpleNamespace

import pytest

import app as app_module
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


class BlockingLLMClient:
    def __init__(self):
        self.started = Event()
        self.release = Event()
        self.call_count = 0

    def generate(self, _user_input):
        self.call_count += 1
        self.started.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("テスト用LLMの待機がタイムアウトしました。")
        return "完了"


def make_settings(**overrides):
    values = {
        "provider": "ollama",
        "model": "gemma3:4b",
        "ollama_host": "http://localhost:11434",
        "min_request_interval_seconds": 0,
    }
    values.update(overrides)
    return AppSettings(**values)


def csrf_post(
    client,
    user_input,
    *,
    follow_redirects=True,
    environ_overrides=None,
):
    client.get("/")
    with client.session_transaction() as flask_session:
        csrf_token = flask_session["csrf_token"]
    return client.post(
        "/",
        data={"user_input": user_input, "csrf_token": csrf_token},
        follow_redirects=follow_redirects,
        environ_overrides=environ_overrides,
    )


def test_get_displays_configured_provider_and_model():
    app = create_app(FakeLLMClient(), make_settings())
    response = app.test_client().get("/")

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Ollama" in page
    assert "gemma3:4b" in page
    assert "Ollama API（接続先は非表示）" in page
    assert "http://localhost:11434" not in page


def test_missing_flask_secret_key_logs_multi_worker_warning(
    monkeypatch, caplog
):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)

    create_app(FakeLLMClient(), make_settings())

    assert "複数ワーカーで運用する場合" in caplog.text


def test_flask_secret_key_uses_environment_value(monkeypatch):
    shared_secret = "test-shared-secret-0123456789abcdef"
    monkeypatch.setenv("FLASK_SECRET_KEY", shared_secret)

    app = create_app(FakeLLMClient(), make_settings())

    assert app.secret_key == shared_secret


def test_weak_flask_secret_key_is_rejected(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "short-secret")

    with pytest.raises(ValueError, match="32バイト以上"):
        create_app(FakeLLMClient(), make_settings())


def test_repeated_flask_secret_key_is_rejected(monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "a" * 64)

    with pytest.raises(ValueError, match="十分にランダム"):
        create_app(FakeLLMClient(), make_settings())


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
    assert "LM Studio API（接続先は非表示）" in page
    assert "http://localhost:1234/v1" not in page


def test_remote_plain_http_connection_logs_security_warning(caplog):
    settings = make_settings(
        ollama_host="http://ollama.example.invalid:11434",
        ollama_allow_insecure_http=True,
    )

    create_app(FakeLLMClient(), settings)

    assert "暗号化されていないHTTP" in caplog.text
    assert "ollama.example.invalid" not in caplog.text


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


def test_non_ascii_csrf_token_is_rejected_without_server_error():
    llm_client = FakeLLMClient()
    app = create_app(llm_client, make_settings())
    client = app.test_client()
    client.get("/")

    response = client.post(
        "/",
        data={"user_input": "質問", "csrf_token": "あ"},
    )

    assert response.status_code == 400
    assert llm_client.call_count == 0


def test_non_ascii_result_token_is_ignored_without_server_error():
    app = create_app(FakeLLMClient(), make_settings())
    client = app.test_client()
    client.get("/")
    with client.session_transaction() as flask_session:
        flask_session["last_result_id"] = "a" * 32

    response = client.get("/?result=あ")

    assert response.status_code == 200


def test_llm_error_is_generic_and_does_not_leak_exception_detail(caplog):
    app = create_app(
        FakeLLMClient(error=ConnectionError("秘密の接続先への接続失敗")),
        make_settings(),
    )
    response = csrf_post(app.test_client(), "質問")
    page = response.get_data(as_text=True)

    assert "ConnectionError" in caplog.text
    assert "in generate" in caplog.text

    assert response.status_code == 502
    assert "Ollamaから回答を取得できませんでした。" in page
    assert "秘密の接続先" not in page
    assert "秘密の接続先" not in caplog.text


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


def test_security_headers_are_added_to_responses():
    app = create_app(FakeLLMClient(), make_settings())

    response = app.test_client().get("/")

    assert response.headers["Cache-Control"] == "no-store, max-age=0"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_session_cookie_has_security_attributes(monkeypatch):
    monkeypatch.delenv("FLASK_COOKIE_SECURE", raising=False)
    app = create_app(FakeLLMClient(), make_settings())

    response = app.test_client().get("/")
    cookie = "\n".join(response.headers.getlist("Set-Cookie"))

    assert "HttpOnly" in cookie
    assert "SameSite=Strict" in cookie
    assert "Secure" not in cookie


def test_session_cookie_can_be_restricted_to_https(monkeypatch):
    monkeypatch.setenv("FLASK_COOKIE_SECURE", "1")
    app = create_app(FakeLLMClient(), make_settings())

    response = app.test_client().get("/")
    cookie = "\n".join(response.headers.getlist("Set-Cookie"))

    assert "Secure" in cookie


def test_untrusted_host_is_rejected():
    app = create_app(FakeLLMClient(), make_settings())

    response = app.test_client().get("/", headers={"Host": "evil.example"})

    assert response.status_code == 400


def test_ipv6_loopback_host_is_rejected_when_server_is_ipv4_only():
    app = create_app(FakeLLMClient(), make_settings())

    response = app.test_client().get("/", headers={"Host": "[::1]"})

    assert response.status_code == 400


def test_clearing_cookie_does_not_bypass_ip_rate_limit():
    llm_client = FakeLLMClient()
    app = create_app(
        llm_client,
        make_settings(min_request_interval_seconds=60),
    )

    first_response = csrf_post(app.test_client(), "1回目")
    second_response = csrf_post(app.test_client(), "2回目")

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert llm_client.call_count == 1


def test_concurrent_llm_request_is_rejected():
    llm_client = BlockingLLMClient()
    app = create_app(
        llm_client,
        make_settings(max_concurrent_requests=1),
    )
    first_result = {}

    def send_first_request():
        first_result["response"] = csrf_post(app.test_client(), "1回目")

    worker = Thread(target=send_first_request)
    worker.start()
    try:
        assert llm_client.started.wait(timeout=5)
        second_response = csrf_post(app.test_client(), "2回目")
        assert second_response.status_code == 429
        assert llm_client.call_count == 1
    finally:
        llm_client.release.set()
        worker.join(timeout=5)

    assert not worker.is_alive()
    assert first_result["response"].status_code == 200


def test_rejected_concurrent_request_does_not_consume_rate_limit():
    llm_client = BlockingLLMClient()
    app = create_app(
        llm_client,
        make_settings(
            max_concurrent_requests=1,
            min_request_interval_seconds=60,
        ),
    )
    first_result = {}

    def send_first_request():
        first_result["response"] = csrf_post(
            app.test_client(),
            "1回目",
            environ_overrides={"REMOTE_ADDR": "192.0.2.1"},
        )

    worker = Thread(target=send_first_request)
    worker.start()
    second_client = app.test_client()
    try:
        assert llm_client.started.wait(timeout=5)
        rejected_response = csrf_post(
            second_client,
            "2回目",
            environ_overrides={"REMOTE_ADDR": "192.0.2.2"},
        )
        assert rejected_response.status_code == 429
        assert llm_client.call_count == 1
    finally:
        llm_client.release.set()
        worker.join(timeout=5)

    retry_response = csrf_post(
        second_client,
        "再試行",
        environ_overrides={"REMOTE_ADDR": "192.0.2.2"},
    )

    assert not worker.is_alive()
    assert first_result["response"].status_code == 200
    assert retry_response.status_code == 200
    assert llm_client.call_count == 2


def test_llm_slot_is_released_after_error():
    llm_client = FakeLLMClient(error=RuntimeError("内部情報"))
    app = create_app(llm_client, make_settings(max_concurrent_requests=1))

    first_response = csrf_post(app.test_client(), "1回目")
    second_response = csrf_post(app.test_client(), "2回目")

    assert first_response.status_code == 502
    assert second_response.status_code == 502
    assert llm_client.call_count == 2


def test_llm_response_is_truncated_before_it_is_saved():
    response_text = "あ" * 1200 + "末尾の秘密"
    app = create_app(
        FakeLLMClient(response_text),
        make_settings(max_response_length=1000),
    )

    response = csrf_post(app.test_client(), "質問")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "安全上の表示上限" in page
    assert "末尾の秘密" not in page


def test_user_input_and_llm_output_are_html_escaped():
    payload = '<script>alert("xss")</script>'
    app = create_app(FakeLLMClient(payload), make_settings())

    response = csrf_post(app.test_client(), payload)
    page = response.get_data(as_text=True)

    assert payload not in page
    assert "&lt;script&gt;" in page


def test_saved_result_expires(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(
        app_module,
        "time",
        SimpleNamespace(monotonic=lambda: clock[0]),
    )
    app = create_app(
        FakeLLMClient("期限付き回答"),
        make_settings(result_ttl_seconds=10),
    )
    client = app.test_client()
    response = csrf_post(client, "質問", follow_redirects=False)

    clock[0] = 111.0
    expired_response = client.get(response.headers["Location"])

    assert expired_response.status_code == 200
    assert "期限付き回答" not in expired_response.get_data(as_text=True)
