from core.config import Config

_PERSON_HINT = "Автор: !set_topic ИМЯ | сброс: !set_topic сброс"
_QUOTE_PREFIX = "Следующая цитата: "


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

    async def enqueue_quote_announcement(self, person: str, quote: str) -> None:
        person = person.strip()
        quote = quote.strip()
        if not person or not quote:
            return
        short_quote = quote if len(quote) <= 180 else f"{quote[:177]}…"
        line = f"{_QUOTE_PREFIX}{person}: «{short_quote}»"
        await self.enqueue(line[:500])
        await self.enqueue(_PERSON_HINT)

    async def enqueue_page_announcement(self, page_title: str) -> None:
        await self.enqueue_quote_announcement(page_title, "…")

    async def enqueue_topic_announcement(self, topic: str) -> None:
        await self.enqueue(f"Следующая случайная цитата: {topic.strip()[:400]}")
        await self.enqueue(_PERSON_HINT)

    async def clear(self) -> None:
        await self._redis.delete(self._key())

    async def pop_message(self) -> str | None:
        raw = await self._redis.rpop(self._key())
        if raw is None:
            return None
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        return str(raw).strip() or None
