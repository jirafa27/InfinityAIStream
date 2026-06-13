import json

from core.config import Config


class VisualOverlayStore:
    """Данные для текстового оверлея на визуале (OBS Browser Source)."""

    _CHAT = "visual:chat_overlay"
    _PAGE_IMAGE = "visual:page_image"
    _PAGE_QUOTE = "visual:page_quote"

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def _key(self) -> str:
        return f"{Config.REDIS_KEY_PREFIX}{self._CHAT}"

    def _image_key(self) -> str:
        return f"{Config.REDIS_KEY_PREFIX}{self._PAGE_IMAGE}"

    def _quote_key(self) -> str:
        return f"{Config.REDIS_KEY_PREFIX}{self._PAGE_QUOTE}"

    async def set_page_quote(self, quote: str | None) -> None:
        quote = (quote or "").strip()
        if quote:
            await self._redis.set(self._quote_key(), quote)
        else:
            await self._redis.delete(self._quote_key())

    async def get_page_quote(self) -> str | None:
        raw = await self._redis.get(self._quote_key())
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        quote = str(raw).strip()
        return quote or None

    async def clear_page_quote(self) -> None:
        await self._redis.delete(self._quote_key())

    async def set_page_image(self, image_url: str | None) -> None:
        image_url = (image_url or "").strip()
        if image_url:
            await self._redis.set(self._image_key(), image_url)
        else:
            await self._redis.delete(self._image_key())

    async def get_page_image(self) -> str | None:
        raw = await self._redis.get(self._image_key())
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        url = str(raw).strip()
        return url if url.startswith("https://") else None

    async def clear_page_image(self) -> None:
        await self._redis.delete(self._image_key())

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
