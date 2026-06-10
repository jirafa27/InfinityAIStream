import asyncio
import signal
from typing import Awaitable, Callable

from core.app_state import app_state
from core.disk_guard import DiskGuard
from core.ffmpeg_manager import ffmpeg_manager
from core.logger import logger


ShutdownHook = Callable[[], Awaitable[None] | None]


class GracefulShutdown:
    """Координатор корректной остановки процесса."""

    def __init__(self) -> None:
        self._hooks: list[ShutdownHook] = []

    def register(self, hook: ShutdownHook) -> None:
        self._hooks.append(hook)

    def install_signal_handlers(self, loop: asyncio.AbstractEventLoop) -> None:
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.run(s.name)))
            except NotImplementedError:
                signal.signal(sig, lambda *_: asyncio.create_task(self.run(sig.name)))

    async def run(self, reason: str = "signal") -> None:
        if app_state.shutting_down:
            return
        logger.info("Graceful shutdown (%s)...", reason)
        app_state.request_shutdown()

        for hook in reversed(self._hooks):
            try:
                result = hook()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.warning("Ошибка shutdown hook: %s", exc)

        DiskGuard.cleanup_tts_directory()
        ffmpeg_manager.stop()
        logger.info("Graceful shutdown завершён")


shutdown = GracefulShutdown()
