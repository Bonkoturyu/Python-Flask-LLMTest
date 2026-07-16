"""設定したLLMと会話するFlaskアプリケーション。"""

from __future__ import annotations

import hmac
import os
import secrets
import time
from collections import OrderedDict
from threading import Lock
from typing import Any, Protocol
from uuid import uuid4

from flask import Flask, redirect, render_template, request, session, url_for

from llm_clients import build_llm_client
from settings import AppSettings, load_settings


class LLMClient(Protocol):
    def generate(self, user_input: str) -> str:
        """ユーザー入力から回答を生成する。"""


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
    app.secret_key = secret_key
    current_settings = settings or load_settings()
    client = llm_client or build_llm_client(current_settings)
    app.config["MAX_CONTENT_LENGTH"] = current_settings.max_request_bytes

    results: OrderedDict[str, dict[str, Any]] = OrderedDict()
    last_requests: OrderedDict[str, float] = OrderedDict()
    state_lock = Lock()
    max_saved_results = 20
    max_tracked_clients = 200

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
            if result_id and hmac.compare_digest(
                result_id, str(session.get("last_result_id", ""))
            ):
                with state_lock:
                    saved_result = results.get(result_id)
                if saved_result:
                    return render_index(**saved_result)
            return render_index()

        expected_token = str(session.get("csrf_token", ""))
        submitted_token = request.form.get("csrf_token", "")
        if not expected_token or not hmac.compare_digest(
            expected_token, submitted_token
        ):
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

        client_id = session.get("client_id")
        if not client_id:
            client_id = secrets.token_urlsafe(24)
            session["client_id"] = client_id
        now = time.monotonic()
        with state_lock:
            previous_request = last_requests.get(client_id, 0.0)
            if (
                current_settings.min_request_interval_seconds > 0
                and now - previous_request
                < current_settings.min_request_interval_seconds
            ):
                return render_index(
                    user_input=user_input,
                    error_message="連続送信を避けるため、少し待ってから再送信してください。",
                    status_code=429,
                )
            last_requests[client_id] = now
            last_requests.move_to_end(client_id)
            while len(last_requests) > max_tracked_clients:
                last_requests.popitem(last=False)

        result: dict[str, Any]
        try:
            ai_response = client.generate(user_input)
            result = {
                "user_input": user_input,
                "ai_response": ai_response,
                "status_code": 200,
            }
        except Exception:
            app.logger.exception(
                "%sへの問い合わせ中にエラーが発生しました",
                current_settings.provider_display_name,
            )
            result = {
                "user_input": user_input,
                "error_message": (
                    f"{current_settings.provider_display_name}から回答を取得できませんでした。"
                    "設定と接続状態を確認してください。"
                ),
                "status_code": 502,
            }

        result_id = uuid4().hex
        with state_lock:
            results[result_id] = result
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
