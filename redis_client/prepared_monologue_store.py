from __future__ import annotations

import json
import time

from core.config import Config


class PreparedMonologueStore:
    """Следующий монолог (цитата + комментарий), подготовленный фоном."""

    _KEY = "control:prepared_monologue"

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def _key(self) -> str:
        return f"{Config.REDIS_KEY_PREFIX}{self._KEY}"

    @staticmethod
    def _decode(value) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    @staticmethod
    def _to_payload(
        *,
        gen_rev: int,
        person: str,
        quote: str,
        image_url: str | None,
        commentary: str,
    ) -> str:
        return json.dumps(
            {
                "gen_rev": gen_rev,
                "person": person,
                "quote": quote,
                "image_url": image_url,
                "commentary": commentary.strip(),
                "prepared_at": time.time(),
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _from_payload(raw: str) -> dict | None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None

        try:
            gen_rev = int(data.get("gen_rev", -1))
        except (TypeError, ValueError):
            return None

        person = str(data.get("person", "")).strip()
        quote = str(data.get("quote", "")).strip()
        commentary = str(data.get("commentary", "")).strip()
        if gen_rev < 0 or not person or not quote or not commentary:
            return None

        image_url = data.get("image_url")
        if image_url is not None:
            image_url = str(image_url).strip() or None

        return {
            "gen_rev": gen_rev,
            "person": person,
            "quote": quote,
            "image_url": image_url,
            "commentary": commentary,
        }

    async def set(
        self,
        *,
        gen_rev: int,
        person: str,
        quote: str,
        image_url: str | None,
        commentary: str,
    ) -> None:
        payload = self._to_payload(
            gen_rev=gen_rev,
            person=person,
            quote=quote,
            image_url=image_url,
            commentary=commentary,
        )
        await self._redis.set(self._key(), payload)

    async def peek(self, gen_rev: int) -> dict | None:
        raw = self._decode(await self._redis.get(self._key()))
        if not raw:
            return None
        parsed = self._from_payload(raw)
        if parsed is None or parsed["gen_rev"] != gen_rev:
            return None
        return parsed

    async def has_for_revision(self, gen_rev: int) -> bool:
        return await self.peek(gen_rev) is not None

    async def take(self, gen_rev: int) -> dict | None:
        raw = self._decode(await self._redis.getdel(self._key()))
        if not raw:
            return None
        parsed = self._from_payload(raw)
        if parsed is None:
            return None
        if parsed["gen_rev"] != gen_rev:
            return None
        return parsed

    async def clear(self) -> None:
        await self._redis.delete(self._key())
