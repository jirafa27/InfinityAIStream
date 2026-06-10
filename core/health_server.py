import time

from aiohttp import web

from core.app_state import app_state
from core.config import Config
from core.disk_guard import DiskGuard
from core.ffmpeg_manager import ffmpeg_manager
from core.logger import logger
from core.metrics import metrics


class HealthServer:
    """HTTP /health и /metrics для мониторинга без вызова Gemini."""

    def __init__(self, redis_manager=None) -> None:
        self._redis_manager = redis_manager
        self._runner: web.AppRunner | None = None

    async def _collect_queue_sizes(self) -> tuple[int, int]:
        ai_size = app_state.ai_queue_size
        tts_size = app_state.tts_queue_size
        if self._redis_manager is None or not self._redis_manager.redis_client:
            return ai_size, tts_size
        try:
            ai_size = await self._redis_manager.get_ai_pending_count()
            tts_size = await self._redis_manager.get_tts_pending_count()
            app_state.ai_queue_size = ai_size
            app_state.tts_queue_size = tts_size
        except Exception as exc:
            logger.debug("Не удалось получить размеры очередей: %s", exc)
        return ai_size, tts_size

    async def health_handler(self, _request: web.Request) -> web.Response:
        free_gb = DiskGuard.free_disk_gb()
        low_disk = DiskGuard.is_low_disk()
        ai_size, tts_size = await self._collect_queue_sizes()

        heartbeat_age = time.time() - app_state.last_heartbeat
        heartbeat_ok = heartbeat_age < Config.HEARTBEAT_TIMEOUT_MINUTES * 60

        queues_ok = (
            ai_size <= Config.AI_QUEUE_MAX_SIZE
            and tts_size <= Config.TTS_QUEUE_MAX_SIZE
        )
        disk_ok = not low_disk

        status = "ok"
        if app_state.shutting_down:
            status = "shutting_down"
        elif not heartbeat_ok or not queues_ok or not disk_ok:
            status = "degraded"

        payload = {
            "status": status,
            "role": app_state.role,
            "twitch_connected": app_state.twitch_connected,
            "ffmpeg_running": ffmpeg_manager.running or app_state.ffmpeg_running,
            "tts_queue_size": tts_size,
            "ai_queue_size": ai_size,
            "free_disk_gb": round(free_gb, 2),
            "uptime_seconds": app_state.uptime_seconds(),
            "monologues_enabled": app_state.monologues_enabled,
            "accept_new_events": app_state.accept_new_events,
        }
        code = 200 if status == "ok" else 503
        return web.json_response(payload, status=code)

    async def metrics_handler(self, _request: web.Request) -> web.Response:
        ai_size, tts_size = await self._collect_queue_sizes()
        extra = {
            "ai_queue_size": ai_size,
            "tts_queue_size": tts_size,
            "twitch_connected": app_state.twitch_connected,
            "ffmpeg_running": ffmpeg_manager.running or app_state.ffmpeg_running,
            "free_disk_gb": round(DiskGuard.free_disk_gb(), 2),
            "stream_uptime_seconds": app_state.uptime_seconds(),
        }
        extra.update(ffmpeg_manager.status_dict())
        return web.json_response(metrics.as_dict(extra))

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/health", self.health_handler)
        app.router.add_get("/metrics", self.metrics_handler)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(
            self._runner, Config.HEALTH_HOST, Config.HEALTH_PORT
        )
        await site.start()
        logger.info(
            "Health server: http://%s:%s/health",
            Config.HEALTH_HOST,
            Config.HEALTH_PORT,
        )

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
