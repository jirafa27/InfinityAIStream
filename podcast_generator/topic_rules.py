import re

TOPIC_LINE_RE = re.compile(
    r"^[\*_#\s]*(?:НОВАЯ|Следующая)\s+ТЕМА[\*_\s]*\s*[:\-—]\s*(.+?)\s*$",
    re.IGNORECASE,
)
TOPIC_INLINE_RE = re.compile(
    r"\s+[\*_#\s]*(?:НОВАЯ|Следующая)\s+ТЕМА[\*_\s]*\s*[:\-—]\s*.+$",
    re.IGNORECASE,
)


def decode_topic_list(raw_topics) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_topics or []:
        text = item.decode("utf-8") if isinstance(item, bytes) else str(item)
        text = text.strip()
        if not text:
            continue
        key = normalize_topic_key(text)
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def format_banned_topics(topics: list[str], *, limit: int = 15) -> str:
    if not topics:
        return "(пока нет)"
    lines = topics[:limit]
    return "\n".join(f"- {topic}" for topic in lines)


def normalize_topic_key(topic: str) -> str:
    text = topic.lower().strip()
    text = re.sub(r"[^\w\sа-яё]", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def topics_are_similar(left: str, right: str) -> bool:
    a = normalize_topic_key(left)
    b = normalize_topic_key(right)
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return True
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return False
    overlap = len(words_a & words_b)
    threshold = max(2, min(len(words_a), len(words_b)) // 2)
    return overlap >= threshold


def is_topic_repeated(new_topic: str, recent_topics: list[str]) -> bool:
    return any(topics_are_similar(new_topic, old) for old in recent_topics)


def strip_topic_markers(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    lines = text.splitlines()
    cleaned: list[str] = []
    for line in lines:
        if TOPIC_LINE_RE.match(line.strip()):
            continue
        cleaned.append(TOPIC_INLINE_RE.sub("", line).strip())

    result = "\n".join(line for line in cleaned if line).strip()
    return TOPIC_INLINE_RE.sub("", result).strip()
