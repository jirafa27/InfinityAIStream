from core.config import Config

_TOPIC_HINT = "Чтобы изменить тему напишите !set_topic НАЗВАНИЕ ТЕМЫ"
_TOPIC_PREFIX = "Следующая тема: "


class ChatOutboundStore:
    """Очередь исходящих сообщений в Twitch-чат."""

    _OUTBOUND = "control:chat_outbound"

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def _key(self) -> str:
        return f"{Config.REDIS_KEY_PREFIX}{self._OUTBOUND}"

    async def enqueue(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        await self._redis.lpush(self._key(), text[:500])
        await self._redis.ltrim(self._key(), 0, 49)

    async def enqueue_topic_announcement(self, topic: str) -> None:
        topic = topic.strip()
        if not topic:
            return
        max_topic = max(1, 500 - len(_TOPIC_PREFIX))
        await self.enqueue(f"{_TOPIC_PREFIX}{topic[:max_topic]}")
        await self.enqueue(_TOPIC_HINT)

    async def clear(self) -> None:
        await self._redis.delete(self._key())

    async def pop_message(self) -> str | None:
        raw = await self._redis.rpop(self._key())
        if raw is None:
            return None
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        return str(raw).strip() or None
