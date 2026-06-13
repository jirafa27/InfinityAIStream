import json
import logging

import redis.asyncio as aioredis

from core.config import Config

logger = logging.getLogger(__name__)


class RedisManager:
    def __init__(self):
        self.redis_client = None

    def _key(self, name: str) -> str:
        return f"{Config.REDIS_KEY_PREFIX}{name}"

    async def connect(self):
        """Подключение к Redis с проверкой доступности."""
        redis_url = f"redis://{Config.REDIS_HOST}:{Config.REDIS_PORT}/{Config.REDIS_DB}"
        self.redis_client = aioredis.from_url(redis_url)
        await self.redis_client.ping()

    async def disconnect(self):
        """Отключение от Redis"""
        if self.redis_client:
            await self.redis_client.close()

    async def _bounded_rpush(self, key: str, value: str, max_size: int) -> None:
        await self.redis_client.rpush(key, value)
        length = await self.redis_client.llen(key)
        if length > max_size:
            dropped = length - max_size
            await self.redis_client.ltrim(key, dropped, -1)
            logger.warning(
                "Очередь %s переполнена — отброшено %s старых реплик с начала",
                key,
                dropped,
            )

    async def get_podcast_message(self):
        return await self.redis_client.lpop(self._key("podcast_messages_queue"))

    async def get_chat_message(self):
        return await self.redis_client.lpop(self._key("chat_messages_queue"))

    async def list_chat_messages(self, limit: int = 50) -> list:
        return await self.redis_client.lrange(
            self._key("chat_messages_queue"), 0, max(0, limit - 1)
        )

    async def remove_chat_message_raw(self, payload) -> bool:
        removed = await self.redis_client.lrem(
            self._key("chat_messages_queue"), 1, payload
        )
        return int(removed) > 0

    @staticmethod
    def encode_podcast_message(text: str, topic_revision: int) -> str:
        return json.dumps(
            {"text": text, "rev": topic_revision},
            ensure_ascii=False,
        )

    @staticmethod
    def decode_podcast_message(raw) -> tuple[str, int]:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "text" in data:
                return str(data["text"]), int(data.get("rev", 0))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return str(raw), 0

    async def add_podcast_message(
        self,
        message: str,
        priority: bool = False,
        *,
        topic_revision: int = 0,
    ):
        payload = self.encode_podcast_message(message, topic_revision)
        key = self._key("podcast_messages_queue")
        if priority:
            await self.redis_client.lpush(key, payload)
        else:
            await self._bounded_rpush(
                key, payload, Config.TTS_QUEUE_MAX_SIZE * 2
            )

    async def claim_chat_dedupe(self, dedupe_key: str, *, ttl: int = 86400) -> bool:
        """True — сообщение ещё не обрабатывали (атомарно помечает)."""
        key = self._key(f"chat:dedupe:{dedupe_key}")
        return bool(await self.redis_client.set(key, "1", nx=True, ex=ttl))

    async def clear_reacted_to_chat_messages_queue(self) -> int:
        key = self._key("reacted_to_chat_messages_queue")
        length = await self.redis_client.llen(key)
        if length:
            await self.redis_client.delete(key)
        return int(length)

    async def add_chat_message(self, message: dict):
        payload = json.dumps(message, ensure_ascii=False)
        await self._bounded_rpush(
            self._key("chat_messages_queue"),
            payload,
            Config.AI_QUEUE_MAX_SIZE,
        )

    async def get_podcast_messages_queue_length(self):
        return await self.redis_client.llen(self._key("podcast_messages_queue"))

    async def get_chat_messages_queue_length(self):
        return await self.redis_client.llen(self._key("chat_messages_queue"))

    async def add_reacted_to_chat_message(self, message: str, priority: bool = False):
        key = self._key("reacted_to_chat_messages_queue")
        max_size = Config.CHAT_TTS_QUEUE_MAX_SIZE
        if priority:
            await self.redis_client.lpush(key, message)
            length = await self.redis_client.llen(key)
            if length > max_size:
                await self.redis_client.ltrim(key, 0, max_size - 1)
        else:
            await self._bounded_rpush(key, message, max_size)

    async def clear_podcast_messages_queue(self) -> int:
        key = self._key("podcast_messages_queue")
        length = await self.redis_client.llen(key)
        if length:
            await self.redis_client.delete(key)
        return int(length)

    async def clear_chat_messages_queue(self) -> int:
        key = self._key("chat_messages_queue")
        length = await self.redis_client.llen(key)
        if length:
            await self.redis_client.delete(key)
        return int(length)

    async def get_stream_epoch(self) -> str | None:
        raw = await self.redis_client.get(self._key("control:stream_epoch"))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        return str(raw)

    async def set_stream_epoch(self, epoch: str) -> None:
        await self.redis_client.set(self._key("control:stream_epoch"), epoch)

    async def set_chat_processing(self, active: bool) -> None:
        key = self._key("control:chat_processing")
        if active:
            await self.redis_client.set(key, "1", ex=600)
        else:
            await self.redis_client.delete(key)

    async def is_chat_processing(self) -> bool:
        return bool(await self.redis_client.exists(self._key("control:chat_processing")))

    async def get_reacted_to_chat_message(self):
        return await self.redis_client.lpop(
            self._key("reacted_to_chat_messages_queue")
        )

    async def get_reacted_to_chat_messages_queue_length(self):
        return await self.redis_client.llen(
            self._key("reacted_to_chat_messages_queue")
        )

    async def add_podcast_topic(self, topic):
        """Добавить новую тему в список (без дубликата в начале)."""
        key = self._key("podcast_topics")
        head = await self.redis_client.lindex(key, 0)
        if head is not None:
            head_text = head.decode("utf-8") if isinstance(head, bytes) else str(head)
            if head_text.strip() == topic.strip():
                return
        await self.redis_client.lpush(key, topic)
        await self.redis_client.ltrim(key, 0, 100)

    async def set_tts_busy(self, busy: bool) -> None:
        key = self._key("control:tts_busy")
        if busy:
            await self.redis_client.set(key, "1", ex=900)
        else:
            await self.redis_client.delete(key)

    async def is_tts_busy(self) -> bool:
        return bool(await self.redis_client.exists(self._key("control:tts_busy")))

    async def get_podcast_topics(self):
        """Получить список тем"""
        return await self.redis_client.lrange(self._key("podcast_topics"), 0, -1)

    async def clear_podcast_topics(self) -> None:
        await self.redis_client.delete(self._key("podcast_topics"))

    async def get_ai_pending_count(self) -> int:
        chat_len = await self.get_chat_messages_queue_length()
        return chat_len

    async def get_tts_pending_count(self) -> int:
        reacted = await self.get_reacted_to_chat_messages_queue_length()
        podcast = await self.get_podcast_messages_queue_length()
        return reacted + podcast
