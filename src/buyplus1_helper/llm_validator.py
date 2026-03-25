"""LLM-based validator for ambiguous online-intent messages.

Used when a message contains 上線 in a time-deferred context (e.g. 「我10分鐘後上線」)
that cannot be reliably classified by keyword rules alone.

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

_SYSTEM_PROMPT = (
    "你是一個分類器，專門判斷繁體中文訊息中「上線」的意圖。\n"
    "只有兩種答案：\n"
    "- now    → 這個人「現在」正在上線\n"
    "- future → 這個人「之後」才會上線（尚未登入，只是預告）\n"
    "只回答一個英文單字：now 或 future。不要有其他文字。"
)

_DEFAULT_MODEL = "gemini-2.5-flash-lite"


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
    """Classify ambiguous 上線 messages via Gemini API with local JSON cache."""

    def __init__(
        self,
        cache_path: Optional[Path] = None,
        model: str = _DEFAULT_MODEL,
    ) -> None:
        self._model = model
        self._cache: dict[str, bool] = {}
        self._cache_path = cache_path

        _load_env()

        if cache_path and cache_path.exists():
            try:
                raw: dict[str, str] = json.loads(
                    cache_path.read_text(encoding="utf-8")
                )
                self._cache = {k: (v == "now") for k, v in raw.items()}
                logger.debug("Loaded %d cached LLM decisions", len(self._cache))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Could not load LLM cache: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_online_now(self, content: str) -> bool:
        """Return True if the message indicates an actual current login."""
        if content in self._cache:
            return self._cache[content]

        try:
            result = self._call_api(content)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "LLM validation failed for %r: %s — defaulting to future",
                content[:50],
                exc,
            )
            result = False

        self._cache[content] = result
        self._save_cache()
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_api(self, content: str) -> bool:
        """Call Gemini and return True if answer is 'now'. Raises on error."""
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
                system_instruction=_SYSTEM_PROMPT,
                max_output_tokens=10,
                temperature=0.0,
            ),
        )
        answer = response.text.strip().lower()
        is_now = answer.startswith("now")
        logger.debug("Gemini %r → %s", content[:50], "now" if is_now else "future")
        return is_now

    def _save_cache(self) -> None:
        if not self._cache_path:
            return
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            raw = {k: ("now" if v else "future") for k, v in self._cache.items()}
            self._cache_path.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not save LLM cache: %s", exc)
