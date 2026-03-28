"""LLM-based validator for ambiguous online/offline intent messages.

Used when keyword rules alone cannot reliably classify a message:
  - Online:  「我10分鐘後上線」 → future intent, not a current login
  - Offline: 「我離開一下確認」 → a task detour, not actually logging off

Backend: Google Gemini (GEMINI_API_KEY from .env).
Results are cached to a JSON file so the same message is never sent to the API
more than once across multiple runs.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ONLINE_SYSTEM_PROMPT = (
    "你是一個分類器，專門判斷繁體中文訊息中「上線」的意圖。\n"
    "只有兩種答案：\n"
    "- now    → 這個人「現在」正在上線\n"
    "- future → 這個人「之後」才會上線（尚未登入，只是預告）\n"
    "只回答一個英文單字：now 或 future。不要有其他文字。"
)

_OFFLINE_SYSTEM_PROMPT = (
    "你是一個分類器，專門判斷繁體中文工作群組訊息中的「離開」意圖。\n"
    "這個人是客服人員，在線上工作群組中發訊息。\n"
    "只有兩種答案：\n"
    "- offline → 這個人正在結束這段工作、要離線了（不管是暫時還是今天結束）\n"
    "- working → 這個人只是暫時去做某件事（確認訂單、查資料、回個訊息等），仍在線上工作\n"
    "只回答一個英文單字：offline 或 working。不要有其他文字。"
)

_DEFAULT_MODEL = "gemini-2.5-flash-lite"

# Prefix used in the JSON cache to namespace offline decisions
_OFFLINE_KEY_PREFIX = "offline:"


def _load_env() -> None:
    """Load .env from the project root if python-dotenv is available."""
    try:
        from dotenv import load_dotenv

        # Walk up from this file to find .env
        here = Path(__file__).resolve()
        for parent in [here.parent, here.parent.parent, here.parent.parent.parent]:
            env_file = parent / ".env"
            if env_file.exists():
                load_dotenv(env_file)
                return
    except ImportError:
        pass  # python-dotenv not installed — rely on env vars set externally


class LLMValidator:
    """Classify ambiguous 上線/離開 messages via Gemini API with local JSON cache.

    Cache format (JSON):
      {
        "<message>":          "now" | "future",   # online decisions
        "offline:<message>":  "offline" | "working"  # offline decisions
      }
    """

    def __init__(
        self,
        cache_path: Optional[Path] = None,
        model: str = _DEFAULT_MODEL,
    ) -> None:
        self._model = model
        self._cache: dict[str, str] = {}  # raw string values from JSON
        self._cache_path = cache_path

        _load_env()

        if cache_path and cache_path.exists():
            try:
                self._cache = json.loads(cache_path.read_text(encoding="utf-8"))
                logger.debug("Loaded %d cached LLM decisions", len(self._cache))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not load LLM cache: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_online_now(self, content: str) -> bool:
        """Return True if the message indicates an actual current login."""
        key = content
        if key in self._cache:
            return self._cache[key] == "now"

        try:
            answer = self._call_api(content, _ONLINE_SYSTEM_PROMPT)
            result = "now" if answer.startswith("now") else "future"
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "LLM online validation failed for %r: %s — defaulting to future",
                content[:50],
                exc,
            )
            result = "future"

        logger.debug("Gemini online %r → %s", content[:50], result)
        self._cache[key] = result
        self._save_cache()
        return result == "now"

    def is_offline_now(self, content: str) -> bool:
        """Return True if the message indicates the person is actually logging off."""
        key = _OFFLINE_KEY_PREFIX + content
        if key in self._cache:
            return self._cache[key] == "offline"

        try:
            answer = self._call_api(content, _OFFLINE_SYSTEM_PROMPT)
            result = "offline" if answer.startswith("offline") else "working"
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "LLM offline validation failed for %r: %s — defaulting to working",
                content[:50],
                exc,
            )
            result = "working"

        logger.debug("Gemini offline %r → %s", content[:50], result)
        self._cache[key] = result
        self._save_cache()
        return result == "offline"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_api(self, content: str, system_prompt: str) -> str:
        """Call Gemini with the given system prompt. Returns the raw answer string."""
        from google import genai  # lazy import — google-genai package
        from google.genai import types

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY not set. Add it to .env or export it as an env var."
            )

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=self._model,
            contents=content,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=10,
                temperature=0.0,
            ),
        )
        return response.text.strip().lower()

    def _save_cache(self) -> None:
        if not self._cache_path:
            return
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not save LLM cache: %s", exc)
