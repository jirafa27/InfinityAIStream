import re

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")
_SPOKEN_QUOTE_RE = re.compile(r"^(«)(.*)(»)\s*(—\s*.+)$", re.DOTALL)


def _split_quote_body(inner: str) -> list[str]:
    parts = [part.strip() for part in _SENTENCE_SPLIT_RE.split(inner) if part.strip()]
    return parts if parts else [inner.strip()]


def split_sentences(text: str) -> list[str]:
    """Разбивает текст на предложения для поочерёдной озвучки."""
    text = (text or "").strip()
    if not text:
        return []

    match = _SPOKEN_QUOTE_RE.match(text)
    if match:
        inner = match.group(2).strip()
        attribution = re.sub(r"^—\s*", "", match.group(4).strip()).strip()
        inner = inner.replace("«", "").replace("»", "").strip()
        if len(re.sub(r"[^a-zA-Zа-яёА-ЯЁ]", "", inner)) < 8:
            return []
        line = f"«{inner}» — {attribution}" if attribution else f"«{inner}»"
        return [line]

    parts = [part.strip() for part in _SENTENCE_SPLIT_RE.split(text) if part.strip()]
    return parts if parts else [text]
