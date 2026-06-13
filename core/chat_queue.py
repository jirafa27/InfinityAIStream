import json

from core.chat_guard import ChatGuard, chat_guard


def parse_chat_payload(raw) -> dict | None:
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        message = json.loads(text)
        if not isinstance(message, dict):
            return None
        return message
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return None


async def has_actionable_chat_messages(
    redis_manager,
    *,
    guard: ChatGuard = chat_guard,
) -> bool:
    """True — в очереди есть сообщение, на которое можно ответить прямо сейчас."""
    if await redis_manager.is_chat_processing():
        return True

    for raw in await redis_manager.list_chat_messages(limit=20):
        message = parse_chat_payload(raw)
        if message is None:
            return True
        author = message.get("author", "Аноним")
        if guard.can_respond_to_user(author):
            return True
    return False
