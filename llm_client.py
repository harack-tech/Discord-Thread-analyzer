"""
LLM API 呼び出しラッパー(Google Gemini / OpenAI 切り替え対応)。

環境変数 LLM_PROVIDER で使用するプロバイダーを切り替える。
    - "gemini" (既定) : Google Gemini API(Flash / Flash-Lite など)
    - "openai"        : OpenAI API(GPT系モデル)

チャットログとモードを受け取り、prompts.py のシステムプロンプトに従って
選択したLLMに解析させ、構造化されたテキストを返す。
"""

import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from prompts import SYSTEM_PROMPT, build_user_message

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").strip().lower()

# --- Google Gemini 設定 ---------------------------------------------------
# GEMINI_MODEL には "gemini-flash-latest"(標準Flash) または
# "gemini-flash-lite-latest"(より低コスト・低レイテンシのFlash-Lite)、
# もしくは "gemini-3.6-flash" のような特定バージョン名を指定できる。
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_MAX_OUTPUT_TOKENS = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "4096"))

# --- OpenAI 設定 -----------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
OPENAI_MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "4096"))

_gemini_client = None
_openai_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError(
                "環境変数 GEMINI_API_KEY が設定されていません。.env を確認してください。"
            )
        from google import genai

        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError(
                "環境変数 OPENAI_API_KEY が設定されていません。.env を確認してください。"
            )
        from openai import AsyncOpenAI

        _openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    return _openai_client


async def _analyze_with_gemini(mode: str, log_text: str) -> str:
    from google.genai import types

    client = _get_gemini_client()
    user_message = build_user_message(mode=mode, log_text=log_text)

    response = await client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=GEMINI_MAX_OUTPUT_TOKENS,
        ),
    )
    return (response.text or "").strip()


async def _analyze_with_openai(mode: str, log_text: str) -> str:
    client = _get_openai_client()
    user_message = build_user_message(mode=mode, log_text=log_text)

    response = await client.responses.create(
        model=OPENAI_MODEL,
        instructions=SYSTEM_PROMPT,
        input=user_message,
        max_output_tokens=OPENAI_MAX_OUTPUT_TOKENS,
    )
    return (response.output_text or "").strip()


async def analyze_log(mode: str, log_text: str) -> str:
    """
    チャットログを指定モードで解析し、構造化されたテキストを返す。

    Args:
        mode: "summarize" | "gap_analysis" | "task_management"
        log_text: 整形済みのスレッドチャットログ

    Returns:
        LLMが生成した構造化テキスト(前置き・挨拶なし)
    """
    if LLM_PROVIDER == "openai":
        return await _analyze_with_openai(mode=mode, log_text=log_text)
    if LLM_PROVIDER == "gemini":
        return await _analyze_with_gemini(mode=mode, log_text=log_text)

    raise RuntimeError(
        f"未対応の LLM_PROVIDER です: '{LLM_PROVIDER}'"
        "('gemini' または 'openai' を指定してください)"
    )
