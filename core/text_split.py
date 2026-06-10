import re

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…»\"'])\s+")


def split_sentences(text: str) -> list[str]:
    """Разбивает текст на предложения для поочерёдной озвучки."""
    text = (text or "").strip()
    if not text:
        return []
    parts = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]
    return parts if parts else [text]
