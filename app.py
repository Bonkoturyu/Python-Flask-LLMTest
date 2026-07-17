"""設定したLLMと会話するFlaskアプリケーション。"""

from __future__ import annotations

import hmac
import os
import re
import secrets
import time
import traceback
from collections import OrderedDict
from threading import BoundedSemaphore, Lock
from typing import Any, Protocol

from flask import Flask, redirect, render_template, request, session, url_for

from llm_clients import build_llm_client
from settings import AppSettings, load_settings


class LLMClient(Protocol):
    def generate(self, user_input: str) -> str:
        """ユーザー入力から回答を生成する。"""


RESULT_TOKEN_PATTERN = re.compile(r"[0-9a-f]{32}")
CSRF_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}")
RESPONSE_LIMIT_NOTICE = "\n\n※安全上の表示上限に達したため、以降を省略しました。"


def _tokens_match(expected: object, submitted: object, pattern: re.Pattern[str]) -> bool:
    if not isinstance(expected, str) or not isinstance(submitted, str):
        return False
    if pattern.fullmatch(expected) is None or pattern.fullmatch(submitted) is None:
        return False
    return hmac.compare_digest(expected.encode("ascii"), submitted.encode("ascii"))


def create_app(
    llm_client: LLMClient | None = None,
    settings: AppSettings | None = None,
) -> Flask:
    """Flaskアプリを生成する。テスト時は設定とLLMを差し替えられる。"""
    app = Flask(__name__)
    secret_key = os.getenv("FLASK_SECRET_KEY")
    if not secret_key:
        app.logger.warning(
            "FLASK_SECRET_KEYが設定されていないため、起動時にランダム生成します。"
            "複数ワーカーで運用する場合は、全ワーカーで同じ値を設定してください。"
        )
        secret_key = secrets.token_hex(32)
    elif (
        len(secret_key.encode("utf-8")) < 32
        or len(set(secret_key)) < 8
        or any(character.isspace() for character in secret_key)
    ):
        raise ValueError(
            "FLASK_SECRET_KEYは32バイト以上の十分にランダムな値を設定してください。"
        )
    app.secret_key = secret_key
    current_settings = settings or load_settings()
    if current_settings.uses_insecure_remote_http:
        app.logger.warning(
            "%sへ暗号化されていないHTTPで接続します。"
            "信頼済みネットワークまたは暗号化済みVPNだけで使用してください。",
            current_settings.provider_display_name,
        )
    client = llm_client or build_llm_client(current_settings)
    cookie_secure_value = os.getenv("FLASK_COOKIE_SECURE", "").strip().lower()
    if cookie_secure_value not in {"", "0", "false", "no", "1", "true", "yes"}:
        raise ValueError(
            "FLASK_COOKIE_SECUREは1/true/yesまたは0/false/noで指定してください。"
        )
    app.config.update(
        MAX_CONTENT_LENGTH=current_settings.max_request_bytes,
        MAX_FORM_MEMORY_SIZE=current_settings.max_request_bytes,
        MAX_FORM_PARTS=10,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=cookie_secure_value in {"1", "true", "yes"},
        TRUSTED_HOSTS=["localhost", ".localhost", "127.0.0.1"],
    )

    results: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
    last_requests: OrderedDict[str, float] = OrderedDict()
    state_lock = Lock()
    request_slots = BoundedSemaphore(current_settings.max_concurrent_requests)
    max_saved_results = 20
    max_tracked_clients = 200

    @app.after_request
    def add_security_headers(response):
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; object-src 'none'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        return response

    def render_index(
        *,
        user_input: str = "",
        ai_response: str = "",
        error_message: str = "",
        status_code: int = 200,
    ) -> tuple[str, int]:
        csrf_token = session.get("csrf_token")
        if not csrf_token:
            csrf_token = secrets.token_urlsafe(32)
            session["csrf_token"] = csrf_token
        return (
            render_template(
                "index.html",
                user_input=user_input,
                ai_response=ai_response,
                error_message=error_message,
                provider_name=current_settings.provider_display_name,
                model_name=current_settings.model,
                connection_label=current_settings.connection_label,
                max_input_length=current_settings.max_input_length,
                csrf_token=csrf_token,
            ),
            status_code,
        )

    @app.errorhandler(413)
    def request_too_large(_error):
        return render_index(
            error_message="送信データが大きすぎます。質問を短くして再送信してください。",
            status_code=413,
        )

    @app.route("/", methods=["GET", "POST"])
    def index():
        if request.method == "GET":
            result_id = request.args.get("result", "")
            if _tokens_match(
                session.get("last_result_id"), result_id, RESULT_TOKEN_PATTERN
            ):
                with state_lock:
                    saved_entry = results.get(result_id)
                    if (
                        saved_entry
                        and time.monotonic() - saved_entry[0]
                        <= current_settings.result_ttl_seconds
                    ):
                        saved_result = saved_entry[1]
                    else:
                        saved_result = None
                        results.pop(result_id, None)
                if saved_result is not None:
                    return render_index(**saved_result)
            return render_index()

        expected_token = session.get("csrf_token")
        submitted_token = request.form.get("csrf_token", "")
        if not _tokens_match(expected_token, submitted_token, CSRF_TOKEN_PATTERN):
            return render_index(
                error_message=(
                    "送信の確認情報が無効です。画面を再読み込みして、もう一度お試しください。"
                ),
                status_code=400,
            )

        user_input = request.form.get("user_input", "").strip()
        if not user_input:
            return render_index(
                error_message="質問を入力してください。",
                status_code=400,
            )
        if len(user_input) > current_settings.max_input_length:
            return render_index(
                user_input=user_input,
                error_message=(
                    f"質問は{current_settings.max_input_length:,}文字以内で入力してください。"
                ),
                status_code=400,
            )

        if not request_slots.acquire(blocking=False):
            return render_index(
                user_input=user_input,
                error_message="別の質問を処理中です。完了後にもう一度お試しください。",
                status_code=429,
            )

        try:
            rate_limit_key = request.remote_addr or "unknown"
            now = time.monotonic()
            with state_lock:
                previous_request = last_requests.get(rate_limit_key, 0.0)
                if (
                    current_settings.min_request_interval_seconds > 0
                    and now - previous_request
                    < current_settings.min_request_interval_seconds
                ):
                    return render_index(
                        user_input=user_input,
                        error_message=(
                            "連続送信を避けるため、少し待ってから再送信してください。"
                        ),
                        status_code=429,
                    )
                last_requests[rate_limit_key] = now
                last_requests.move_to_end(rate_limit_key)
                while len(last_requests) > max_tracked_clients:
                    last_requests.popitem(last=False)

            result: dict[str, Any]
            try:
                ai_response = client.generate(user_input)
                if not isinstance(ai_response, str):
                    raise RuntimeError("LLMクライアントが文字列以外を返しました。")
                if len(ai_response) > current_settings.max_response_length:
                    ai_response = (
                        ai_response[: current_settings.max_response_length]
                        + RESPONSE_LIMIT_NOTICE
                    )
                result = {
                    "user_input": user_input,
                    "ai_response": ai_response,
                    "status_code": 200,
                }
            except Exception as exc:
                stack_trace = "".join(traceback.format_tb(exc.__traceback__))
                app.logger.error(
                    "%sへの問い合わせ中にエラーが発生しました"
                    "（例外種別: %s）\n%s",
                    current_settings.provider_display_name,
                    type(exc).__name__,
                    stack_trace,
                )
                result = {
                    "user_input": user_input,
                    "error_message": (
                        f"{current_settings.provider_display_name}から回答を取得できませんでした。"
                        "設定と接続状態を確認してください。"
                    ),
                    "status_code": 502,
                }
        finally:
            request_slots.release()

        result_id = secrets.token_hex(16)
        saved_at = time.monotonic()
        with state_lock:
            while results:
                created_at = next(iter(results.values()))[0]
                if saved_at - created_at <= current_settings.result_ttl_seconds:
                    break
                results.popitem(last=False)
            results[result_id] = (saved_at, result)
            while len(results) > max_saved_results:
                results.popitem(last=False)
        session["last_result_id"] = result_id
        session["csrf_token"] = secrets.token_urlsafe(32)
        return redirect(url_for("index", result=result_id), code=303)

    return app


def main() -> None:
    app = create_app()
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=os.getenv("FLASK_DEBUG") == "1",
    )


if __name__ == "__main__":
    main()
