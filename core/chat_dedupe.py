import hashlib


def chat_dedupe_key(author: str, content: str, message_id: str = "") -> str:
    if message_id:
        return message_id
    normalized = f"{author.strip().lower()}:{content.strip()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
