from core.config import Config

DEFAULT_TOPIC = "Зачем философия современному человеку?"


class TopicControlStore:
    """Текущая/следующая тема монолога и очередь уведомлений для Telegram."""

    _CURRENT = "control:current_topic"
    _PENDING = "control:pending_topic"
    _NOTIFY = "control:topic_notifications"
    _REVISION = "control:topic_revision"
    _MANUAL_REV = "control:topic_manual_revision"

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def _key(self, name: str) -> str:
        return f"{Config.REDIS_KEY_PREFIX}{name}"

    @staticmethod
    def _decode(value) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode()
        return str(value)

    async def get_current_topic(self) -> str:
        value = self._decode(await self._redis.get(self._key(self._CURRENT)))
        return value.strip() if value and value.strip() else DEFAULT_TOPIC

    async def set_current_topic(self, topic: str, *, notify: bool = True) -> None:
        topic = topic.strip()
        prev_raw = self._decode(await self._redis.get(self._key(self._CURRENT)))
        prev = prev_raw.strip() if prev_raw and prev_raw.strip() else None
        await self._redis.set(self._key(self._CURRENT), topic)
        if notify and prev != topic:
            await self.enqueue_notification(topic)

    async def get_pending_topic(self) -> str | None:
        value = self._decode(await self._redis.get(self._key(self._PENDING)))
        if value and value.strip():
            return value.strip()
        return None

    async def set_pending_topic(self, topic: str) -> None:
        await self._redis.set(self._key(self._PENDING), topic.strip())

    async def clear_pending_topic(self) -> None:
        await self._redis.delete(self._key(self._PENDING))

    async def consume_pending_topic(self) -> str | None:
        topic = await self.get_pending_topic()
        if topic:
            await self.clear_pending_topic()
        return topic

    async def get_topic_revision(self) -> int:
        raw = await self._redis.get(self._key(self._REVISION))
        if raw is None:
            return 0
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return int(raw)
        except ValueError:
            return 0

    async def bump_revision(self) -> int:
        return int(await self._redis.incr(self._key(self._REVISION)))

    async def get_manual_topic_revision(self) -> int | None:
        raw = await self._redis.get(self._key(self._MANUAL_REV))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return int(raw)
        except ValueError:
            return None

    async def clear_manual_topic_lock(self) -> None:
        await self._redis.delete(self._key(self._MANUAL_REV))

    async def is_manual_topic_active(self) -> bool:
        manual_rev = await self.get_manual_topic_revision()
        if manual_rev is None:
            return False
        return await self.get_topic_revision() == manual_rev

    async def apply_topic_now(self, topic: str) -> int:
        """Сразу меняет текущую тему (экран + следующий монолог)."""
        await self.clear_pending_topic()
        await self.set_current_topic(topic.strip(), notify=True)
        rev = await self.bump_revision()
        await self._redis.set(self._key(self._MANUAL_REV), rev)
        return rev

    async def enqueue_notification(self, topic: str) -> None:
        await self._redis.lpush(self._key(self._NOTIFY), topic.strip())

    async def pop_notification(self) -> str | None:
        value = self._decode(await self._redis.rpop(self._key(self._NOTIFY)))
        if value and value.strip():
            return value.strip()
        return None
