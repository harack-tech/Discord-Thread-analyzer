"""
Discord スレッド解析ボット
=========================
指定したスレッド内のチャットログを取得し、LLM API(既定: Google Gemini。
環境変数 LLM_PROVIDER で OpenAI に切り替え可能)を用いて
「要約」「認識ズレ指摘」「簡易マネジメント」の3モードで構造化分析を行う。

使い方:
    スレッド内で `/analyze mode:<要約|認識ズレ指摘|簡易マネジメント> [limit:300]`
    を実行すると、そのスレッドの直近 <limit> 件のメッセージを取得して
    解析結果を返信する。
"""

import logging
import os
from typing import List

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

from llm_client import analyze_log
from prompts import MODE_CHOICES

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID")  # 開発時の即時同期用（任意）
DEFAULT_HISTORY_LIMIT = int(os.getenv("DEFAULT_HISTORY_LIMIT", "300"))
DISCORD_MESSAGE_LIMIT = 1900  # Discordの2000文字制限に対する安全マージン

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("thread_analyzer_bot")

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)


def format_thread_log(messages: List[discord.Message]) -> str:
    """
    discord.Message のリストを、LLMに渡すためのプレーンテキストのチャットログに変換する。
    投稿時刻・発言者表示名・本文・添付ファイル名のみを含み、
    本文に存在しない情報を付け加えない（捏造防止）。
    """
    lines = []
    for msg in messages:
        if msg.author.bot:
            # ボット自身の過去の解析結果などは解析対象に含めない
            continue

        content = msg.content.strip()
        if not content and not msg.attachments:
            continue

        timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M")
        author = msg.author.display_name
        line = f"[{timestamp}] {author}: {content}"

        if msg.attachments:
            attachment_names = ", ".join(a.filename for a in msg.attachments)
            line += f" (添付ファイル: {attachment_names})"

        lines.append(line)

    return "\n".join(lines)


async def fetch_thread_messages(
    thread: discord.Thread, limit: int
) -> List[discord.Message]:
    """スレッドから直近 limit 件のメッセージを、投稿順（古い→新しい）で取得する。"""
    messages = [msg async for msg in thread.history(limit=limit, oldest_first=False)]
    messages.reverse()
    return messages


def split_for_discord(text: str, chunk_size: int = DISCORD_MESSAGE_LIMIT) -> List[str]:
    """
    Discordの1メッセージ文字数制限に収まるよう、改行境界を優先してテキストを分割する。
    1行自体が chunk_size を超える場合は、その行を強制的に分割する。
    """
    if len(text) <= chunk_size:
        return [text]

    chunks: List[str] = []
    current = ""

    def flush():
        nonlocal current
        if current:
            chunks.append(current)
            current = ""

    for line in text.split("\n"):
        while len(line) > chunk_size:
            flush()
            chunks.append(line[:chunk_size])
            line = line[chunk_size:]

        added_len = len(line) + (1 if current else 0)
        if len(current) + added_len > chunk_size:
            flush()
        current = f"{current}\n{line}" if current else line

    flush()
    return chunks


@bot.event
async def on_ready():
    try:
        if DISCORD_GUILD_ID:
            guild = discord.Object(id=int(DISCORD_GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
        else:
            synced = await bot.tree.sync()
        logger.info("スラッシュコマンドを %d 件同期しました。", len(synced))
    except Exception:
        logger.exception("スラッシュコマンドの同期に失敗しました。")
    logger.info("ログイン完了: %s", bot.user)


@bot.tree.command(
    name="analyze",
    description="このスレッドのチャットログを指定モードで解析します。",
)
@app_commands.describe(
    mode="実行モードを選択してください。",
    limit="解析対象とする直近メッセージ件数（デフォルト: 300、最大1000）",
)
@app_commands.choices(mode=MODE_CHOICES)
async def analyze(
    interaction: discord.Interaction,
    mode: app_commands.Choice[str],
    limit: int = DEFAULT_HISTORY_LIMIT,
):
    if not isinstance(interaction.channel, discord.Thread):
        await interaction.response.send_message(
            "このコマンドはスレッド内でのみ実行できます。", ephemeral=True
        )
        return

    if limit <= 0 or limit > 1000:
        await interaction.response.send_message(
            "limit は 1〜1000 の範囲で指定してください。", ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)

    thread: discord.Thread = interaction.channel

    try:
        messages = await fetch_thread_messages(thread, limit=limit)
    except discord.Forbidden:
        await interaction.followup.send("このスレッドの履歴を取得する権限がありません。")
        return
    except discord.HTTPException:
        logger.exception("スレッド履歴の取得に失敗しました。")
        await interaction.followup.send(
            "スレッド履歴の取得中にエラーが発生しました。時間をおいて再度お試しください。"
        )
        return

    log_text = format_thread_log(messages)

    if not log_text:
        await interaction.followup.send("解析対象となる発言が見つかりませんでした。")
        return

    try:
        result = await analyze_log(mode=mode.value, log_text=log_text)
    except Exception:
        logger.exception("LLM解析中にエラーが発生しました。")
        await interaction.followup.send(
            "解析中にエラーが発生しました。しばらくしてから再度お試しください。"
        )
        return

    if not result:
        await interaction.followup.send("解析結果が空でした。もう一度お試しください。")
        return

    chunks = split_for_discord(result)
    await interaction.followup.send(chunks[0])
    for chunk in chunks[1:]:
        await thread.send(chunk)


def main():
    if not DISCORD_BOT_TOKEN:
        raise RuntimeError(
            "環境変数 DISCORD_BOT_TOKEN が設定されていません。.env を確認してください。"
        )
    bot.run(DISCORD_BOT_TOKEN)


if __name__ == "__main__":
    main()
