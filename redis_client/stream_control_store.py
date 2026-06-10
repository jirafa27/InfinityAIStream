from core.config import Config


class StreamControlStore:
    """Флаг «стрим включён» в Redis для локального supervisor."""

    _KEY = "control:stream_running"

    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    def _key(self) -> str:
        return f"{Config.REDIS_KEY_PREFIX}{self._KEY}"

    async def set_running(self, running: bool) -> None:
        await self._redis.set(self._key(), "1" if running else "0")

    async def is_running(self) -> bool:
        value = await self._redis.get(self._key())
        if value is None:
            return False
        if isinstance(value, bytes):
            value = value.decode()
        return value == "1"
