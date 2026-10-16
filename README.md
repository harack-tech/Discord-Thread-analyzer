# Discord スレッド解析ボット

指定したDiscordスレッド内のチャットログを取得し、LLM API(既定: Google Gemini。
`OpenAI` に切り替え可能)を用いて「要約」「認識ズレ指摘」「簡易マネジメント」の
3モードで構造化分析を行うボットです。

## 構成ファイル

| ファイル | 内容 |
|---|---|
| `bot.py` | ボット本体(スラッシュコマンド、履歴取得、メッセージ整形・送信) |
| `prompts.py` | モード別システムプロンプトとメッセージ組み立て |
| `llm_client.py` | LLM API 呼び出しラッパー(Gemini / OpenAI 切り替え対応) |
| `requirements.txt` | 依存パッケージ |
| `.env.example` | 環境変数のサンプル |

## セットアップ

1. 依存パッケージをインストール
   ```bash
   pip install -r requirements.txt
   ```

2. `.env.example` を `.env` にコピーし、値を設定
   ```bash
   cp .env.example .env
   ```
   - `DISCORD_BOT_TOKEN`: Discord Developer Portal で作成したボットのトークン
   - `LLM_PROVIDER`: `gemini`(既定)または `openai`
   - `GEMINI_API_KEY`: Google AI Studio で取得したAPIキー(`LLM_PROVIDER=gemini` の場合に必要)
   - `OPENAI_API_KEY`: OpenAIのAPIキー(`LLM_PROVIDER=openai` の場合に必要)

3. Discord Developer Portal でのボット設定
   - **Bot** タブで `MESSAGE CONTENT INTENT` を有効化
   - **OAuth2 > URL Generator** で `bot` と `applications.commands` のスコープ、
     および `Read Message History` / `Send Messages` / `Send Messages in Threads` /
     `View Channel` 権限を付与した招待URLを発行し、サーバーに招待

4. 起動
   ```bash
   python bot.py
   ```

## 使用するLLMの切り替え

`.env` の `LLM_PROVIDER` で切り替える。

- `LLM_PROVIDER=gemini`(既定): `GEMINI_MODEL` に `gemini-flash-latest`(標準Flash)
  または `gemini-flash-lite-latest`(より低コスト・低レイテンシのFlash-Lite)を指定。
  特定バージョンを固定したい場合は `gemini-3.6-flash` のような具体的なモデルIDも指定可能。
- `LLM_PROVIDER=openai`: `OPENAI_MODEL` に使用したいモデル(既定: `gpt-5-mini`)を指定。

いずれのモデル名もAPI提供元の都合で変更・廃止されることがあるため、
エラーが出る場合は各社の最新モデル一覧を確認のうえ `.env` を更新してください。

## 使い方

解析したいスレッド内で以下のスラッシュコマンドを実行します。

```
/analyze mode:<要約 | 認識ズレ指摘 | 簡易マネジメント> limit:<件数(任意、既定300)>
```

- `mode`: 3つの実行モードから選択
  - 要約 (`summarize`)
  - 認識ズレ指摘 (`gap_analysis`)
  - 簡易マネジメント (`task_management`)
- `limit`: 解析対象とする直近メッセージ件数（1〜1000、既定300）

ボット自身の過去の発言は解析対象から除外され、結果は前置き・挨拶なしの
構造化テキストとしてスレッドに返信されます。2000文字を超える場合は
自動で複数メッセージに分割送信されます。

## 注意事項

- コマンドはスレッド内でのみ実行可能です（通常チャンネルでは動作しません）。
- スラッシュコマンドをすぐに反映させたい場合は、`.env` の `DISCORD_GUILD_ID`
  に開発用サーバーのIDを指定してください（グローバル同期は反映まで最大1時間程度）。
- チャットログに存在しない情報の捏造を防ぐため、システムプロンプト側で
  「事実と推測の区別」を明示的に指示しています。
- Gemini・OpenAIいずれも従量課金です。解析対象の文字数・件数に応じてコストが
  発生するため、必要に応じて `limit` や各モデルの max_output_tokens 系設定で
  調整してください。
