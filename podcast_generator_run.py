import asyncio

import aiohttp

from core.app_state import app_state
from core.health_server import HealthServer
from core.logger import logger
from core.shutdown import shutdown
from core.worker_epoch import retire_stale_worker
from podcast_generator.podcast_generator import PodcastGenerator
from podcast_generator.text_generator import LLMTextGenerator
from redis_client.redis_manager import RedisManager
from redis_client.stream_reset import clear_tts_queues
from speech.audio_player import stop_audio


async def main():
    app_state.role = "podcaster"
    redis_manager = RedisManager()
    await redis_manager.connect()

    health = HealthServer(redis_manager)
    await health.start()

    if await retire_stale_worker(redis_manager, "podcaster"):
        return

    dropped_podcast, dropped_reacted, dropped_chat = await clear_tts_queues(
        redis_manager
    )
    stop_audio()
    await redis_manager.set_tts_busy(False)
    await redis_manager.set_chat_processing(False)
    logger.info(
        "Сброс при старте podcaster: монолог -%s, чат TTS -%s, входящий чат -%s",
        dropped_podcast,
        dropped_reacted,
        dropped_chat,
    )

    llm = LLMTextGenerator()
    podcast_generator = PodcastGenerator(llm, redis_manager)

    shutdown.register(health.stop)
    shutdown.register(redis_manager.disconnect)

    loop = asyncio.get_event_loop()
    shutdown.install_signal_handlers(loop)

    async with aiohttp.ClientSession() as session:
        generator_task = asyncio.create_task(podcast_generator.run(session))
        shutdown_task = asyncio.create_task(app_state.wait_shutdown())
        done, pending = await asyncio.wait(
            [generator_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        for task in done:
            if task is generator_task and not task.cancelled():
                exc = task.exception()
                if exc is not None:
                    logger.exception("PodcastGenerator завершился с ошибкой", exc_info=exc)
                    raise exc
        await shutdown.run("podcaster-stop")

    logger.info("Podcaster остановлен")


if __name__ == "__main__":
    asyncio.run(main())
