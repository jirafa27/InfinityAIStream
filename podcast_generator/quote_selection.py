from __future__ import annotations

import json
import re
from dataclasses import dataclass

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class WikiquoteQuoteCandidate:
    page_title: str
    quote: str
    work_title: str | None = None


def normalize_quote_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _find_by_quote(
    candidates: list[WikiquoteQuoteCandidate],
    quote: str,
) -> WikiquoteQuoteCandidate | None:
    norm = normalize_quote_text(quote)
    for candidate in candidates:
        if normalize_quote_text(candidate.quote) == norm:
            return candidate
    return None


def _find_by_page_and_quote(
    candidates: list[WikiquoteQuoteCandidate],
    page_title: str,
    quote: str,
) -> WikiquoteQuoteCandidate | None:
    page_norm = page_title.strip().lower()
    quote_norm = normalize_quote_text(quote)
    for candidate in candidates:
        if (
            candidate.page_title.strip().lower() == page_norm
            and normalize_quote_text(candidate.quote) == quote_norm
        ):
            return candidate
    return None


def parse_llm_quote_selection(
    raw: str | None,
    candidates: list[WikiquoteQuoteCandidate],
) -> WikiquoteQuoteCandidate | None:
    """Проверяет ответ LLM: цитата должна дословно совпасть с одним из кандидатов."""
    if not raw or not candidates:
        return None

    text = raw.strip()
    block = _JSON_BLOCK_RE.search(text)
    if block:
        text = block.group(1).strip()

    if text.isdigit():
        index = int(text)
        if 1 <= index <= len(candidates):
            return candidates[index - 1]
        return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    if "index" in data:
        try:
            index = int(data["index"])
        except (TypeError, ValueError):
            return None
        if 1 <= index <= len(candidates):
            return candidates[index - 1]
        return None

    quote = data.get("quote")
    if not isinstance(quote, str) or not quote.strip():
        return None

    page_title = data.get("page") or data.get("page_title") or data.get("title")
    if isinstance(page_title, str) and page_title.strip():
        found = _find_by_page_and_quote(candidates, page_title, quote)
        if found:
            return found

    return _find_by_quote(candidates, quote)
