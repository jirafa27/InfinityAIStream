"""Запуск/остановка трансляции OBS (Twitch Go Live)."""

from __future__ import annotations

import logging

from core.config import Config
from obs.obs_client import ObsWebSocketClient

logger = logging.getLogger(__name__)


class ObsStreamService:
    def __init__(self) -> None:
        self._client = ObsWebSocketClient(
            Config.OBS_WEBSOCKET_HOST,
            Config.OBS_WEBSOCKET_PORT,
            password=Config.OBS_WEBSOCKET_PASSWORD,
        )

    async def start_broadcast(self) -> str:
        if not Config.OBS_ENABLED or not Config.OBS_AUTO_START_STREAM:
            return ""
        try:
            if await self._client.get_stream_active():
                return "OBS: трансляция уже идёт"
            await self._client.start_stream()
            logger.info("OBS: StartStream — трансляция на Twitch запущена")
            return "OBS: трансляция на Twitch запущена"
        except Exception as exc:
            logger.warning("OBS StartStream не удался: %s", exc)
            return f"OBS: не удалось начать трансляцию ({exc})"

    async def stop_broadcast(self) -> str:
        if not Config.OBS_ENABLED or not Config.OBS_AUTO_STOP_STREAM:
            return ""
        try:
            if not await self._client.get_stream_active():
                return "OBS: трансляция уже остановлена"
            await self._client.stop_stream()
            logger.info("OBS: StopStream — трансляция остановлена")
            return "OBS: трансляция на Twitch остановлена"
        except Exception as exc:
            logger.warning("OBS StopStream не удался: %s", exc)
            return f"OBS: не удалось остановить трансляцию ({exc})"
