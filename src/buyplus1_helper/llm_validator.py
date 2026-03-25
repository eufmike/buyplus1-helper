"""LLM-based validator for ambiguous online-intent messages.

Used when a message contains 上線 in a time-deferred context (e.g. 「我10分鐘後上線」)
that cannot be reliably classified by keyword rules alone.

Results are cached to a JSON file so the same message content is never sent to
the API more than once across multiple runs.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是一個分類器，專門判斷繁體中文訊息中「上線」的意圖。
只有兩種答案：
- "now"   → 這個人「現在」正在上線（即使訊息中說「等一下」也算，只要她確認正在登入）
- "future" → 這個人「之後」才會上線（尚未登入，只是預告或說明）

只回答一個英文單字：now 或 future。不要有其他文字。"""


class LLMValidator:
    """Classify ambiguous 上線 messages via Claude API with local JSON cache."""

    def __init__(
        self,
        cache_path: Optional[Path] = None,
        model: str = "claude-haiku-4-5",
    ) -> None:
        self._model = model
        self._cache: dict[str, bool] = {}   # content → is_online_now
        self._cache_path = cache_path

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
        """Call Claude and return True if answer is 'now'. Raises on API error."""
        import anthropic  # lazy import — optional dependency

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=self._model,
            max_tokens=10,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        answer = response.content[0].text.strip().lower()
        is_now = answer.startswith("now")
        logger.debug("LLM %r → %s", content[:50], "now" if is_now else "future")
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
