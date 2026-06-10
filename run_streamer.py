import asyncio

from core.app_state import app_state
from core.health_server import HealthServer
from core.logger import logger
from core.shutdown import shutdown
from core.worker_epoch import retire_stale_worker
from redis_client.redis_manager import RedisManager
from speech.audio_player import stop_audio
from streamer.streamer import Streamer


async def main():
    app_state.role = "streamer"
    redis_manager = RedisManager()
    await redis_manager.connect()

    health = HealthServer(redis_manager)
    await health.start()

    if await retire_stale_worker(redis_manager, "streamer"):
        return

    streamer = Streamer(redis_manager)
    stop_audio()
    await redis_manager.set_tts_busy(False)
    await redis_manager.set_chat_processing(False)
    logger.info("Сброс tts_busy при старте streamer")

    shutdown.register(health.stop)
    shutdown.register(redis_manager.disconnect)

    loop = asyncio.get_event_loop()
    shutdown.install_signal_handlers(loop)

    streamer_task = asyncio.create_task(streamer.run())
    shutdown_task = asyncio.create_task(app_state.wait_shutdown())
    done, pending = await asyncio.wait(
        [streamer_task, shutdown_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    await shutdown.run("streamer-stop")

    logger.info("Streamer остановлен")


if __name__ == "__main__":
    asyncio.run(main())
