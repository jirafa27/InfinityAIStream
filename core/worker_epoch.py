import os
import time

from core.app_state import app_state
from redis_client.redis_manager import RedisManager


async def bump_stream_epoch(redis_manager: RedisManager) -> str:
    """Новая эпоха стрима — старые podcaster/streamer должны завершиться."""
    epoch = str(int(time.time() * 1000))
    await redis_manager.set_stream_epoch(epoch)
    os.environ["STREAM_EPOCH"] = epoch
    return epoch


async def worker_epoch_valid(redis_manager: RedisManager) -> bool:
    expected = os.getenv("STREAM_EPOCH", "").strip()
    if not expected:
        return True
    current = await redis_manager.get_stream_epoch()
    return current == expected


async def retire_stale_worker(redis_manager: RedisManager, role: str) -> bool:
    """True — воркер устарел и запрошен shutdown."""
    if await worker_epoch_valid(redis_manager):
        return False
    from core.logger import logger

    logger.warning(
        "%s: устаревшая эпоха (env=%s, redis=%s) — останавливаюсь",
        role,
        os.getenv("STREAM_EPOCH", ""),
        await redis_manager.get_stream_epoch(),
    )
    app_state.request_shutdown()
    return True
