import json

from core.config import Config


class VisualOverlayStore:
    """Данные для текстового оверлея на визуале (OBS Browser Source)."""

    _CHAT = "visual:chat_overlay"

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def _key(self) -> str:
        return f"{Config.REDIS_KEY_PREFIX}{self._CHAT}"

    async def set_chat_overlay(self, author: str, content: str) -> None:
        payload = json.dumps(
            {
                "author": author.strip(),
                "content": content.strip(),
            },
            ensure_ascii=False,
        )
        await self._redis.set(self._key(), payload)

    async def get_chat_overlay(self) -> dict | None:
        raw = await self._redis.get(self._key())
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
        if not author and not content:
            return None
        return {"author": author, "content": content}

    async def clear_chat_overlay(self) -> None:
        await self._redis.delete(self._key())
