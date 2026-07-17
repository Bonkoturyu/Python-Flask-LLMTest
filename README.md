# LLMチャットアプリ

Flaskで作られた、シンプルなWebチャットアプリです。

設定ファイルを書き換えることで、次のLLMを利用できます。

- Ollamaで動かすGemma、Qwen、Llamaなどのモデル
- LM Studioで動かすローカルモデル
- Anthropic APIで提供されるClaude
- Google Gemini APIで提供されるGemini
- OpenAI Responses APIでテキスト出力に対応するGPT／Codex系モデル

このREADMEでは、WindowsとPowerShellを使い、初めてPythonアプリを動かす人でもセットアップできるように説明します。

## 目次

1. [このアプリの仕組み](#このアプリの仕組み)
2. [必要なもの](#必要なもの)
3. [プロジェクトを開く](#1-プロジェクトを開く)
4. [uvをインストールする](#2-uvをインストールする)
5. [Python環境を作る](#3-python環境を作る)
6. [設定ファイルを作る](#4-設定ファイルを作る)
7. [Ollamaを準備する](#5-ollamaを使う場合の準備)
8. [LM Studioを準備する](#6-lm-studioを使う場合の準備)
9. [アプリを起動する](#7-アプリを起動する)
10. [モデルやクラウドLLMを切り替える](#モデルやプロバイダーを切り替える)
11. [トラブルシューティング](#トラブルシューティング)

## このアプリの仕組み

ブラウザーで入力した質問は、Flaskアプリを経由して、設定したLLMへ送られます。LLMから返ってきた回答をFlaskがWeb画面に表示します。

```text
ブラウザー
    ↓ 質問
Flaskアプリ
    ↓
Ollama、LM Studio、または各社のクラウドLLM API
    ↓ 回答
Flaskアプリ
    ↓
ブラウザーに表示
```

OllamaまたはLM Studioを選んだ場合は、ローカルLLMサーバーが動いているPCへ質問を送ります。Claude、Gemini、GPT／Codexを選んだ場合は、インターネット経由で各社のクラウドAPIへ質問を送ります。

## 必要なもの

共通で必要なもの:

- Windows 10以降
- PowerShell
- インターネット接続（初回セットアップ時）
- このプロジェクト一式

Ollamaを使う場合:

- OllamaがインストールされたPC
- 使用するモデルを保存できるディスク容量

LM Studioを使う場合:

- LM StudioがインストールされたPC
- LM Studioにダウンロードしたチャット対応モデル
- 使用するモデルを保存できるディスク容量

クラウドLLMを使う場合:

- 使用するサービスのアカウント
- Anthropic、GoogleまたはOpenAIで発行したAPIキー
- API利用料金の支払い設定

> クラウドLLMのAPIは、各社のチャットサービスとは別の契約・利用枠になる場合があります。料金、利用可能モデル、レート制限を各サービスの管理画面で確認してください。

## 初回セットアップ

### 1. プロジェクトを開く

VS Codeでこのプロジェクトのフォルダーを開き、メニューから「ターミナル」→「新しいターミナル」を選びます。

ターミナルの先頭が次のように、プロジェクトの場所になっていることを確認してください。

```text
PS C:\...\Python-Flask-LLMTest>
```

別の場所が表示されている場合は、`cd` コマンドで移動します。

```powershell
cd "プロジェクトを保存したフォルダー\Python-Flask-LLMTest"
```

### 2. uvをインストールする

このプロジェクトでは、Python本体とライブラリを管理するために `uv` を使います。すでにインストール済みなら、この手順は不要です。

まず確認します。

```powershell
uv --version
```

バージョン番号が表示されればインストール済みです。`uv` が見つからない場合は、次のどちらか一方でインストールします。

WinGetを使う方法:

```powershell
winget install --id=astral-sh.uv -e
```

WinGetを利用できない場合は、[uv公式インストールガイド](https://docs.astral.sh/uv/getting-started/installation/)をブラウザーで開き、Windows向けの最新手順を確認してください。ダウンロードしたスクリプトを内容確認せず直接実行する手順は、このREADMEでは案内しません。

インストール後はVS Codeのターミナルを閉じ、新しいターミナルを開いてから、もう一度 `uv --version` を実行してください。詳しくは[uv公式インストールガイド](https://docs.astral.sh/uv/getting-started/installation/)を参照してください。

### 3. Python環境を作る

プロジェクト専用のPython環境を `.venv` フォルダーに作ります。

```powershell
uv venv --python 3.14 .venv
```

Python 3.14がPCにない場合、`uv` が必要なPythonを自動的に取得します。

続いて、このアプリに必要なライブラリをインストールします。

```powershell
uv pip install --python .venv\Scripts\python.exe --require-hashes -r requirements.lock
```

このコマンドは [requirements.lock](requirements.lock) に固定された版と配布物ハッシュを検証し、Flask、Ollama SDK、OpenAI SDK、Google Gen AI SDK、Anthropic SDKなどをプロジェクト専用環境へインストールします。[requirements.txt](requirements.txt) は更新候補の許容範囲を管理する元ファイルです。通常の環境構築ではロックファイルを使用してください。

インストールを確認します。

```powershell
& ".\.venv\Scripts\python.exe" --version
```

`Python 3.14.x` のように表示されれば成功です。

> Windowsで `python` とだけ実行すると、Microsoft Store用のエイリアスが起動することがあります。このREADMEでは、確実にプロジェクト用Pythonを使うため、`.venv\Scripts\python.exe` を直接指定します。

### 4. 設定ファイルを作る

[config.example.yaml](config.example.yaml) は、公開しても問題のない設定例です。これを `config.local.yaml` という名前でコピーします。

```powershell
Copy-Item config.example.yaml config.local.yaml
```

すでに `config.local.yaml` がある場合は、コピーせず、そのファイルを使用してください。

`config.local.yaml` は `.gitignore` に登録されています。そのため、実際のホスト名やAPIキーを書いても通常はGitへコミットされません。

> `config.example.yaml` には、実際のAPIキー、社内ホスト名、個人PC名などを書かないでください。公開可能な例だけを記載します。

初期設定は次のようなOllama用設定です。

```yaml
app:
  max_input_length: 4000
  max_request_bytes: 65536
  max_response_length: 20000
  result_ttl_seconds: 600
  min_request_interval_seconds: 1.0
  max_concurrent_requests: 1

llm:
  provider: ollama
  model: gemma3:4b
  max_tokens: 1024
  temperature: 0.7
  request_timeout_seconds: 180
  max_retries: 0
  system_prompt: あなたは日本語で簡潔に回答するアシスタントです。

  ollama:
    host: http://localhost:11434
    allow_insecure_http: false

  lmstudio:
    base_url: http://localhost:1234/v1
    api_key: lm-studio
    allow_insecure_http: false

  anthropic:
    api_key: ""
    base_url: https://api.anthropic.com
    allow_custom_base_url: false

  gemini:
    api_key: ""

  openai:
    api_key: ""
    base_url: https://api.openai.com/v1
    allow_custom_base_url: false
    use_temperature: false
```

各項目の意味は次のとおりです。

| 設定項目 | 説明 | 設定例 |
|---|---|---|
| `app.max_input_length` | 画面から送信できる最大文字数 | `4000` |
| `app.max_request_bytes` | HTTPリクエスト全体の最大サイズ（バイト） | `65536` |
| `app.max_response_length` | サーバーが保存・表示する回答の最大文字数 | `20000` |
| `app.result_ttl_seconds` | 回答をサーバーのメモリへ一時保持する秒数 | `600` |
| `app.min_request_interval_seconds` | 同じ送信元IPからLLMへ送信できる最短間隔。`0`で無効 | `1.0` |
| `app.max_concurrent_requests` | 同時にLLMへ問い合わせる最大件数 | `1` |
| `llm.provider` | 使用するサービス | `ollama` / `lmstudio` / `anthropic` / `gemini` / `openai` |
| `llm.model` | 使用するモデルの正確な名前 | `gemma3:4b` |
| `llm.max_tokens` | 回答として生成する最大トークン数 | `1024` |
| `llm.temperature` | 回答のランダム性。小さいほど安定 | `0.7` |
| `llm.request_timeout_seconds` | LLM APIの応答を待つ最大秒数 | `180` |
| `llm.max_retries` | SDKによる自動再試行回数 | `0` |
| `llm.system_prompt` | LLMへ常に渡す基本指示 | `日本語で回答してください。` |
| `llm.ollama.host` | Ollama APIの接続先 | `http://localhost:11434` |
| `llm.ollama.allow_insecure_http` | 別PCへの平文HTTPを明示的に許可するか | `false` |
| `llm.lmstudio.base_url` | LM StudioのOpenAI互換API接続先 | `http://localhost:1234/v1` |
| `llm.lmstudio.api_key` | LM StudioのAPI Token。認証なしなら任意文字列 | `lm-studio` |
| `llm.lmstudio.allow_insecure_http` | 別PCへの平文HTTPを明示的に許可するか | `false` |
| `llm.anthropic.api_key` | Anthropic APIキー。環境変数の利用を推奨 | `""` |
| `llm.anthropic.base_url` | Anthropic APIの接続先 | `https://api.anthropic.com` |
| `llm.anthropic.allow_custom_base_url` | 公式以外の接続先を明示的に許可するか | `false` |
| `llm.gemini.api_key` | Google Gemini APIキー。環境変数の利用を推奨 | `""` |
| `llm.openai.api_key` | OpenAI APIキー。環境変数の利用を推奨 | `""` |
| `llm.openai.base_url` | OpenAI APIの接続先 | `https://api.openai.com/v1` |
| `llm.openai.allow_custom_base_url` | 公式以外の接続先を明示的に許可するか | `false` |
| `llm.openai.use_temperature` | OpenAIへtemperatureを送るか。対応モデルでのみ有効化 | `false` |

`temperature` は `0` から `1` の間で指定します。OpenAIでは、推論モデルなどがこの項目を受け付けない場合があるため、初期値では送信しません。利用モデルが対応していることを確認できた場合だけ `llm.openai.use_temperature: true` にします。

`max_retries` の初期値を `0` にしているのは、クラウドAPIへの自動再送と意図しない重複課金を避けるためです。一時的な通信失敗をSDKに再試行させたい場合だけ増やしてください。設定変更は、アプリを再起動したときに反映されます。

設定事故による過剰な課金や長時間占有を防ぐため、`max_tokens` は100,000以下、`request_timeout_seconds` は3,600以下、`max_retries` は5以下、`max_concurrent_requests` は32以下に制限されます。入力は100,000文字、HTTPリクエストは10 MiB、保存する回答は1,000,000文字、回答保持期間は86,400秒が上限です。

### 5. Ollamaを使う場合の準備

LM StudioまたはクラウドLLMだけを使う場合は、この手順を飛ばして構いません。

#### Ollamaをインストールする

Ollamaを動かすPCにOllamaをインストールします。[Ollama Windows版のダウンロードページ](https://ollama.com/download/windows)から公式インストーラーを取得してください。

インストール後、PowerShellを開き直して確認します。

```powershell
ollama --version
```

Windows版Ollamaは通常バックグラウンドで動き、同じPCからは `http://localhost:11434` で接続できます。詳細は[OllamaのWindows向け公式資料](https://docs.ollama.com/windows)を参照してください。

#### モデルをダウンロードする

`config.local.yaml` の `llm.model` に指定したモデルを、Ollama側へダウンロードします。

```powershell
ollama pull gemma3:4b
```

ダウンロード済みのモデルを確認します。

```powershell
ollama list
```

一覧に `gemma3:4b` が表示されれば準備完了です。

#### 別のPCにあるOllamaを使う場合

FlaskアプリとOllamaが別のPCにある場合は、`config.local.yaml` の `host` をOllama側PCのアドレスへ変更します。

```yaml
ollama:
  host: http://Ollama側PCのホスト名またはIPアドレス:11434
  allow_insecure_http: true
```

別PCから接続するには、Ollama側の待受設定やWindowsファイアウォールの設定も必要になる場合があります。ホスト名やIPアドレスはネットワーク管理者へ確認してください。

`http://` の通信では質問と回答が暗号化されません。別PCへ接続する場合は、第三者が参加できない信頼済みネットワークまたは暗号化済みVPNに限定してください。共有LANなどを経由する場合は、HTTPSリバースプロキシを用意し、`https://ollama.example.invalid` のような接続先を使用します。

### 6. LM Studioを使う場合の準備

OllamaまたはクラウドLLMだけを使う場合は、この手順を飛ばして構いません。

#### LM Studioをインストールする

[LM Studio公式サイト](https://lmstudio.ai/)からWindows版をダウンロードしてインストールします。

LM Studioを起動したら、検索画面から使用したいチャット対応モデルをダウンロードします。モデルによって必要なメモリやディスク容量が異なるため、自分のPCで動かせるサイズを選んでください。

#### モデルを読み込む

1. LM Studioを開きます。
2. 「Chat」または「Developer」画面でダウンロードしたモデルを選択します。
3. モデルをメモリへ読み込みます。
4. LM Studioに表示されるモデル識別子を控えます。

設定の `llm.model` は、このモデル識別子と一致させます。

#### ローカルサーバーを起動する

1. LM Studioの「Developer」画面を開きます。
2. 「Start server」のスイッチをオンにします。
3. ポート番号を確認します。標準設定は `1234` です。

CLIを導入済みの場合は、次のコマンドでも開始できます。

```powershell
lms server start
```

サーバーと読み込み済みモデルを確認するには、PowerShellで次を実行します。

```powershell
Invoke-RestMethod http://localhost:1234/v1/models
```

モデル情報が表示されれば、LM StudioのAPIは利用可能です。LM StudioはOpenAI互換APIを提供しており、このアプリでは `/v1/chat/completions` を使用します。詳細は[LM StudioのOpenAI互換API公式資料](https://lmstudio.ai/docs/developer/openai-compat)を参照してください。

#### API Token認証を使う場合

LM Studioのサーバーは初期状態では認証なしで利用できます。この場合、設定の `api_key` は `lm-studio` のままで構いません。OpenAI互換SDKが要求する値ですが、認証なしのLM Studio側では検証されません。

LM Studio 0.4.0以降でAPI Token認証を有効にした場合は、「Developer」→「Server Settings」→「Manage Tokens」でTokenを作ります。Tokenは設定ファイルへ直接書かず、環境変数で渡す方法を推奨します。

```yaml
lmstudio:
  base_url: http://localhost:1234/v1
  api_key: ""
```

同じPowerShellウィンドウで、履歴へToken本体を残さないよう対話入力します。

```powershell
$secureKey = Read-Host "LM Studio API Token" -AsSecureString
$env:LM_STUDIO_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
Remove-Variable secureKey
```

環境変数 `LM_API_TOKEN` にも対応しています。環境変数はYAMLの `api_key` より優先されます。詳しくは[LM Studioの認証公式資料](https://lmstudio.ai/docs/developer/core/authentication)を参照してください。

#### 別のPCにあるLM Studioを使う場合

LM Studioの「Developer」画面でローカルネットワークからの接続を許可し、`base_url` をLM Studio側PCのアドレスへ変更します。

```yaml
lmstudio:
  base_url: http://LM-Studio側PCのホスト名またはIPアドレス:1234/v1
  api_key: lm-studio
  allow_insecure_http: true
```

別PCから接続する場合はAPI Token認証の利用を推奨します。Windowsファイアウォールやネットワーク設定も必要になる場合があります。

ただし、HTTP上のToken認証はToken・質問・回答を暗号化しません。第三者が参加できない信頼済みネットワークまたは暗号化済みVPNに限定し、それ以外ではHTTPSリバースプロキシを使用してください。

### 7. アプリを起動する

プロジェクトのフォルダーで次を実行します。

```powershell
& ".\.venv\Scripts\python.exe" -u ".\app.py"
```

正常に起動すると、次のような表示が出ます。

```text
* Serving Flask app 'app'
* Running on http://127.0.0.1:5000
```

このターミナルは閉じずに、そのままにしてください。ブラウザーで次のURLを開きます。

<http://127.0.0.1:5000>

質問を入力して「送信」ボタンを押し、回答が表示されれば成功です。OllamaやLM Studioでは、初回のモデル読み込みに時間がかかることがあります。

アプリを終了するときは、起動したターミナルを選んで `Ctrl+C` を押します。

## 2回目以降の起動

初回セットアップが済んでいれば、毎回環境を作り直す必要はありません。次のコマンドだけで起動できます。

```powershell
& ".\.venv\Scripts\python.exe" -u ".\app.py"
```

## モデルやプロバイダーを切り替える

切り替える前に、起動中のアプリを `Ctrl+C` で停止します。`config.local.yaml` を編集して保存し、アプリを再起動してください。

### Ollamaの別モデルへ切り替える

例としてQwenへ切り替える場合、まずOllama側でモデルを取得します。

```powershell
ollama pull qwen2.5-coder:1.5b
```

次に `config.local.yaml` を変更します。

```yaml
llm:
  provider: ollama
  model: qwen2.5-coder:1.5b

  ollama:
    host: http://localhost:11434
```

モデル名は `ollama list` に表示される名前と完全に一致させてください。

### LM Studioへ切り替える

LM Studioでモデルを読み込み、「Developer」画面からサーバーを開始します。次に `config.local.yaml` を変更します。

```yaml
llm:
  provider: lmstudio
  model: LM Studioに表示されるモデル識別子
  max_tokens: 1024
  temperature: 0.7
  system_prompt: あなたは日本語で簡潔に回答するアシスタントです。

  lmstudio:
    base_url: http://localhost:1234/v1
    api_key: lm-studio
```

モデル識別子は、次のコマンドの `id` でも確認できます。

```powershell
(Invoke-RestMethod http://localhost:1234/v1/models).data | Select-Object id
```

設定後にFlaskアプリを再起動してください。

### Claude（Anthropic）へ切り替える

Claudeはローカルモデルではなく、AnthropicのクラウドAPIを利用します。

1. [Anthropic Console](https://console.anthropic.com/)でアカウントを準備します。
2. Consoleの「Settings」→「API keys」でAPIキーを作成します。
3. 利用可能なモデルIDを[Claudeモデル一覧](https://platform.claude.com/docs/en/about-claude/models/overview)で確認します。
4. `config.local.yaml` を変更します。

```yaml
llm:
  provider: anthropic
  model: 利用するClaudeのモデルID
  max_tokens: 1024
  temperature: 0.7
  system_prompt: あなたは日本語で簡潔に回答するアシスタントです。

  anthropic:
    api_key: ""
    base_url: https://api.anthropic.com
    allow_custom_base_url: false
```

APIキーはPowerShellの環境変数で渡します。次の対話入力なら、コマンド履歴へAPIキー本体が残りません。

```powershell
$secureKey = Read-Host "Anthropic APIキー" -AsSecureString
$env:ANTHROPIC_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
Remove-Variable secureKey
```

環境変数はYAMLの `api_key` より優先されます。誤って古いキーを使わないよう、YAML側は空欄のままにします。

```yaml
anthropic:
  api_key: ""
  base_url: https://api.anthropic.com
  allow_custom_base_url: false
```

APIキーはパスワードと同じ秘密情報です。画面共有、チャット、Issue、コミットなどへ貼り付けないでください。漏えいした可能性がある場合は、Anthropic Consoleでキーを無効化して作り直してください。詳細は[Anthropicの認証ガイド](https://platform.claude.com/docs/en/manage-claude/authentication)を参照してください。

### Gemini（Google）へ切り替える

GeminiはGoogleのクラウドAPIを利用します。このアプリではInteractions APIを使用するため、このAPIでテキスト出力に対応するモデルを選びます。Interactions APIはプレビュー提供で仕様変更の可能性があるため、`google-genai` を更新した後は自動テストを実行してください。

1. [Google AI Studio](https://aistudio.google.com/)でAPIキーを作成します。
2. [Gemini APIのモデル一覧](https://ai.google.dev/gemini-api/docs/models)で利用するモデルIDを確認します。
3. `config.local.yaml` を変更します。

```yaml
llm:
  provider: gemini
  model: 利用するGeminiのモデルID
  max_tokens: 1024
  temperature: 0.7
  system_prompt: あなたは日本語で簡潔に回答するアシスタントです。

  gemini:
    api_key: ""
```

APIキーは環境変数で設定します。

```powershell
$secureKey = Read-Host "Gemini APIキー" -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
Remove-Variable secureKey
```

環境変数はYAMLの `api_key` より優先されます。YAML側は空欄のままにします。`GOOGLE_API_KEY` にも対応しています。

```yaml
gemini:
  api_key: ""
```

Geminiの呼び出しでは、履歴を保存しない `store: false` を指定しています。API仕様については[Gemini Interactions API公式資料](https://ai.google.dev/gemini-api/docs/interactions-overview)を参照してください。

### GPT／Codex（OpenAI）へ切り替える

OpenAIのクラウドAPIを利用します。このアプリはResponses APIを使用するため、このAPIでテキスト出力に対応するGPT／Codex系モデルを選びます。モデル名だけではAPI互換性を判断できないため、公式モデル一覧でResponses API対応を確認してください。

1. [OpenAI Platform](https://platform.openai.com/)でAPIキーと支払い設定を準備します。
2. [OpenAI APIのモデル一覧](https://developers.openai.com/api/docs/models)で、自分のアカウントから利用できるモデルIDを確認します。
3. `config.local.yaml` を変更します。

利用できるモデルを指定する例:

```yaml
llm:
  provider: openai
  model: ここにResponses API対応モデルID
  max_tokens: 1024
  system_prompt: あなたは日本語で簡潔に回答するアシスタントです。

  openai:
    api_key: ""
    base_url: https://api.openai.com/v1
    allow_custom_base_url: false
    use_temperature: false
```

モデル名はコード内で固定していません。Sol／Terra／Lunaという名称のモデルやCodex系モデルを利用する場合も、契約中のAPIで実際に表示される正確なモデルIDを `llm.model` に指定します。ただし、モデルIDが存在するだけでは不十分で、Responses APIの `input` とテキスト出力に対応している必要があります。提供状況やIDは変わるため、利用時点の公式モデル一覧を優先してください。

APIキーを環境変数で設定する場合:

```powershell
$secureKey = Read-Host "OpenAI APIキー" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
Remove-Variable secureKey
```

環境変数はYAMLの `api_key` より優先されます。YAML側は空欄のままにします。

```yaml
openai:
  api_key: ""
  base_url: https://api.openai.com/v1
  allow_custom_base_url: false
  use_temperature: false
```

OpenAIの呼び出しでも履歴を保存しない `store: false` を指定しています。

## 別の設定ファイルを使う

通常は `config.local.yaml` を使います。別の設定を一時的に使いたい場合は、`LLM_CONFIG_FILE` 環境変数を設定してから起動します。

```powershell
$env:LLM_CONFIG_FILE = "config.test.yaml"
& ".\.venv\Scripts\python.exe" -u ".\app.py"
```

`config.yaml`、`config.local.yaml`、`config.test.yaml` のような `config.*.yaml` と、それらの `.yml` 版はGit管理から除外されます。`.env`、一般的な秘密鍵ファイルも除外対象です。公開用の `config.example.yaml` だけが例外です。

`LLM_CONFIG_FILE` に上記以外の名前を指定した場合は、コミット前にそのファイルが無視されることを確認してください。

```powershell
git check-ignore -v config.local.yaml
git status --short
git diff --cached
```

秘密情報を含むファイルを `git add -f` で強制追加しないでください。

## テストを実行する

開発時の動作確認用に自動テストが用意されています。

初回だけ、テストと脆弱性監査に使う開発用ライブラリをハッシュ検証付きでインストールします。

```powershell
uv pip install --python .venv\Scripts\python.exe --require-hashes -r requirements-dev.lock
```

テストを実行します。

```powershell
& ".\.venv\Scripts\python.exe" -m pytest
```

すべてのテストが `passed` と表示されれば成功です。テストでは実際のAPIキーや課金APIを使用しません。

インストール済みライブラリを最新の脆弱性データベースと照合する場合は、インターネットへ接続した状態で次を実行します。

```powershell
& ".\.venv\Scripts\python.exe" -m pip_audit --path .venv\Lib\site-packages --progress-spinner off
```

### 依存ライブラリを更新する場合

[requirements.txt](requirements.txt) または [requirements-dev.txt](requirements-dev.txt) を変更したら、Python 3.14向けロックファイルを両方とも再生成します。

```powershell
uv pip compile requirements.txt --python-version 3.14 --generate-hashes --no-emit-index-url --output-file requirements.lock
uv pip compile requirements-dev.txt --python-version 3.14 --generate-hashes --no-emit-index-url --output-file requirements-dev.lock
```

再生成後はハッシュ付きロックからインストールし直し、テストと脆弱性監査を実行してください。`requirements*.txt` と対応する `requirements*.lock` は同じ変更に含めます。

## トラブルシューティング

### `uv` が認識されない

```text
uv : 用語 'uv' は認識されません
```

uvをインストールしたあと、VS Codeのターミナルを閉じて開き直してください。それでも直らない場合はVS Code自体を再起動します。

### `python` を実行しても `Python` とだけ表示される

Windows Store用エイリアスが呼ばれています。`python app.py` は使わず、次のコマンドで起動してください。

```powershell
& ".\.venv\Scripts\python.exe" -u ".\app.py"
```

### `.venv\Scripts\python.exe` が見つからない

仮想環境がまだ作成されていません。プロジェクトのフォルダーで次を実行します。

```powershell
uv venv --python 3.14 .venv
uv pip install --python .venv\Scripts\python.exe --require-hashes -r requirements.lock
```

### ブラウザーに `ERR_CONNECTION_REFUSED` と表示される

Flaskアプリが起動していないか、終了しています。ターミナルで起動コマンドを実行し、`Running on http://127.0.0.1:5000` と表示された状態を保ってください。

### `config.local.yaml` がないと表示される

設定例をコピーします。

```powershell
Copy-Item config.example.yaml config.local.yaml
```

### Ollamaへ接続できない

次の点を確認します。

- Ollamaアプリが起動しているか
- `config.local.yaml` の `llm.provider` が `ollama` か
- `llm.ollama.host` が正しいか
- 別PCの場合、ネットワークとファイアウォールが許可されているか

同じPCのOllamaを確認する例:

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```

### Ollamaでモデルが見つからない

設定したモデル名がダウンロードされているか確認します。

```powershell
ollama list
```

なければ取得します。

```powershell
ollama pull gemma3:4b
```

### LM Studioへ接続できない

次の点を確認します。

- LM Studioが起動しているか
- 「Developer」画面でサーバーを開始しているか
- 使用するモデルが読み込まれているか
- `llm.provider` が `lmstudio` か
- `llm.lmstudio.base_url` のポート番号がLM Studio画面と一致しているか
- 認証を有効にした場合、API Tokenが正しいか

同じPCのLM Studioを確認する例:

```powershell
Invoke-RestMethod http://localhost:1234/v1/models
```

### LM Studioでモデルが見つからない

LM Studioに表示されるモデル識別子と、`llm.model` が一致しているか確認します。次のコマンドでAPIから見えるモデルIDを確認できます。

```powershell
(Invoke-RestMethod http://localhost:1234/v1/models).data | Select-Object id
```

### Claudeで認証エラーになる

- APIキーの先頭や末尾に余分な空白がないか確認する
- APIキーが有効期限切れや無効化済みでないか確認する
- `llm.provider` が `anthropic` になっているか確認する
- API利用の支払い設定や利用上限を確認する

### Geminiで認証エラーになる

- `llm.provider` が `gemini` になっているか確認する
- `GEMINI_API_KEY`、`GOOGLE_API_KEY`、またはYAMLのAPIキーを確認する
- Google AI StudioでAPIキーが有効か確認する
- 指定したモデルを自分のAPI利用枠で使用できるか確認する
- APIの利用上限や支払い設定を確認する

### GPT／Codexで認証・モデルエラーになる

- `llm.provider` が `openai` になっているか確認する
- `OPENAI_API_KEY`、またはYAMLのAPIキーを確認する
- `base_url` が `https://api.openai.com/v1` になっているか確認する
- `llm.model` が公式モデル一覧の正確なIDと一致しているか確認する
- 指定したモデルへ自分のプロジェクトからアクセスできるか確認する
- APIの利用上限や支払い設定を確認する

### 回答に時間がかかる

OllamaやLM Studioでは、モデルをメモリへ読み込むため回答開始まで時間がかかることがあります。PCのCPU、GPU、メモリ性能やモデルサイズによって速度が変わります。

## ファイル構成

```text
Python-Flask-LLMTest/
├─ app.py                 Flaskアプリ本体
├─ settings.py            YAML設定の読込と検証
├─ llm_clients.py         ローカル／クラウドLLMの呼び分け
├─ config.example.yaml    公開用の設定例
├─ config.local.yaml      実際の設定（Git管理外）
├─ requirements.txt       必要なPythonライブラリ
├─ requirements.lock      固定版と配布物ハッシュ
├─ requirements-dev.txt   テスト・監査用ライブラリ
├─ requirements-dev.lock  開発用の固定版と配布物ハッシュ
├─ templates/
│  └─ index.html          チャット画面のHTML
├─ static/
│  ├─ styles.css          チャット画面のデザイン
│  └─ app.js              二重送信を防ぐ画面処理
└─ tests/                 自動テスト
```

## セキュリティ上の注意

- `config.local.yaml` や `.env` など、実環境の設定・APIキー・秘密鍵をGitへ追加しないでください。APIキーはREADME、Issue、チャット、画面共有にも貼り付けません。
- 接続URLへユーザー名、パスワード、APIキー、クエリ、フラグメントを埋め込む設定は拒否されます。AnthropicとOpenAIはHTTPSかつ公式接続先が既定で、互換APIは `allow_custom_base_url: true` を明示した場合だけ許可されます。Ollama／LM Studioの別PCへのHTTP接続も既定では拒否され、`allow_insecure_http: true` を明示した場合だけ許可されます。その場合も、信頼済みネットワークまたは暗号化済みVPNに限定してください。
- アプリは `127.0.0.1` だけで待ち受け、Hostヘッダーもローカルホストだけを許可します。Flaskの開発サーバーをそのままLANやインターネットへ公開しないでください。
- CSRF検証、入力・回答サイズ制限、回答の保持期限、送信元IP単位の連続送信制限、LLM同時実行上限、Cookie属性、CSPなどの防御ヘッダーを実装しています。ただし、レート制限と回答保存は単一プロセス内だけで、利用者認証もありません。本番公開時はHTTPS、利用者認証、共有ストレージを使うレート制限を別途実装してください。
- `FLASK_SECRET_KEY` が未設定の場合は起動ごとにランダム生成されます。複数ワーカーでは、32バイト以上の十分にランダムな同一値を全ワーカーへ設定してください。次のコマンドなら秘密値そのものはPowerShell履歴へ残りません。

```powershell
$env:FLASK_SECRET_KEY = & ".\.venv\Scripts\python.exe" -c "import secrets; print(secrets.token_urlsafe(48))"
```

- HTTPSで運用する場合は `FLASK_COOKIE_SECURE=1` も設定します。HTTPの `127.0.0.1` で動かす間は設定しないでください。
