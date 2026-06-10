import json

from core.config import Config


class ChatNotifyStore:
    """Очередь уведомлений о Twitch-чате для Telegram."""

    _NOTIFY = "control:chat_notifications"

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def _key(self) -> str:
        return f"{Config.REDIS_KEY_PREFIX}{self._NOTIFY}"

    async def enqueue(self, author: str, content: str, response: str) -> None:
        payload = json.dumps(
            {
                "author": author.strip(),
                "content": content.strip(),
                "response": response.strip(),
            },
            ensure_ascii=False,
        )
        await self._redis.lpush(self._key(), payload)
        await self._redis.ltrim(self._key(), 0, 99)

    async def pop_notification(self) -> dict | None:
        raw = await self._redis.rpop(self._key())
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        author = str(data.get("author", "")).strip()
        content = str(data.get("content", "")).strip()
        response = str(data.get("response", "")).strip()
        if not author and not content:
            return None
        return {"author": author, "content": content, "response": response}
