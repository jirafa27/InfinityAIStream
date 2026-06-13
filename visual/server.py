"""HTTP-сервер визуала: статика React + API для WAV и конфигурации."""

from __future__ import annotations

import logging
from pathlib import Path

from aiohttp import web

from core.config import Config
from redis_client.redis_manager import RedisManager
from redis_client.topic_control_store import TopicControlStore
from redis_client.visual_overlay_store import VisualOverlayStore

logger = logging.getLogger(__name__)

PROJECT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = PROJECT_DIR / "visual-web" / "dist"


def _is_complete_wav(path: Path) -> bool:
    if path.suffix.lower() != ".wav":
        return False
    return not path.with_suffix(".wav.part").exists()


def _list_wav_files(watch_dir: Path) -> list[str]:
    if not watch_dir.is_dir():
        return []
    files = [p.name for p in watch_dir.glob("*.wav") if _is_complete_wav(p)]
    return sorted(files)


async def handle_health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def handle_overlay(request: web.Request) -> web.Response:
    redis_manager: RedisManager | None = request.app.get("redis_manager")
    if redis_manager is None or redis_manager.redis_client is None:
        return web.json_response({"topic": "", "imageUrl": "", "quote": "", "chat": None})

    topic_store = TopicControlStore(redis_manager.redis_client)
    overlay_store = VisualOverlayStore(redis_manager.redis_client)
    try:
        topic = await topic_store.get_current_topic()
        image_url = await overlay_store.get_page_image() or ""
        quote = await overlay_store.get_page_quote() or ""
        if not quote:
            topic = ""
            image_url = ""
        chat_active = (
            await redis_manager.get_reacted_to_chat_messages_queue_length() > 0
            or await redis_manager.is_chat_processing()
        )
        chat = await overlay_store.get_chat_overlay() if chat_active else None
        if not chat_active:
            await overlay_store.clear_chat_overlay()
    except Exception:
        logger.exception("Ошибка чтения overlay из Redis")
        return web.json_response({"topic": "", "imageUrl": "", "quote": "", "chat": None})

    return web.json_response({"topic": topic, "imageUrl": image_url, "quote": quote, "chat": chat})


async def handle_config(_request: web.Request) -> web.Response:
    return web.json_response(
        {
            "mode": Config.VISUAL_MODE,
            "complexity": Config.VISUAL_COMPLEXITY,
            "volumeSmoothing": Config.VISUAL_VOLUME_SMOOTHING,
            "playAudio": Config.VISUAL_PLAY_AUDIO,
            "targetFps": Config.VISUAL_TARGET_FPS,
        }
    )


async def handle_wav_list(request: web.Request) -> web.Response:
    watch_dir = Path(Config.TTS_OUTPUT_DIR)
    return web.json_response(_list_wav_files(watch_dir))


async def handle_wav_file(request: web.Request) -> web.Response:
    filename = request.match_info.get("filename", "")
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        raise web.HTTPBadRequest(text="Invalid filename")

    path = Path(Config.TTS_OUTPUT_DIR) / filename
    if not path.is_file() or not _is_complete_wav(path):
        raise web.HTTPNotFound()

    return web.FileResponse(path)


async def handle_index(_request: web.Request) -> web.Response:
    index = DIST_DIR / "index.html"
    if not index.is_file():
        raise web.HTTPNotFound(
            text="visual-web/dist не найден. Выполните: cd visual-web && npm install && npm run build"
        )
    return web.FileResponse(index)


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/api/health", handle_health)
    app.router.add_get("/api/config", handle_config)
    app.router.add_get("/api/overlay", handle_overlay)
    app.router.add_get("/api/wav/list", handle_wav_list)
    app.router.add_get("/api/wav/{filename}", handle_wav_file)
    app.router.add_get("/", handle_index)

    if DIST_DIR.is_dir():
        assets_dir = DIST_DIR / "assets"
        if assets_dir.is_dir():
            app.router.add_static("/assets", assets_dir, show_index=False)

    return app


async def serve_visual(host: str, port: int) -> None:
    if not DIST_DIR.is_dir():
        logger.error(
            "Каталог %s не найден. Соберите frontend: cd visual-web && npm install && npm run build",
            DIST_DIR,
        )
        raise FileNotFoundError(f"Missing visual build: {DIST_DIR}")

    redis_manager = RedisManager()
    try:
        await redis_manager.connect()
        logger.info("Визуал подключён к Redis")
    except Exception:
        logger.warning("Redis недоступен — оверлей темы/чата не будет обновляться")

    app = create_app()
    app["redis_manager"] = redis_manager
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info(
        "Визуал доступен: %s (OBS: Browser Source → этот URL)",
        Config.VISUAL_URL,
    )

    import asyncio

    stop = asyncio.Event()
    try:
        await stop.wait()
    finally:
        await redis_manager.disconnect()
        await runner.cleanup()
