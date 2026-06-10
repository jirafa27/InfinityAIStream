"""Сигналы в OBS по событиям (Telegram-команды и т.д.)."""

from __future__ import annotations

import asyncio
import logging

from core.config import Config
from obs.obs_client import ObsWebSocketClient

logger = logging.getLogger(__name__)


class ObsSignalService:
    def __init__(self) -> None:
        self._enabled = Config.OBS_ENABLED
        self._commands = Config.obs_signal_commands()
        self._client = ObsWebSocketClient(
            Config.OBS_WEBSOCKET_HOST,
            Config.OBS_WEBSOCKET_PORT,
            password=Config.OBS_WEBSOCKET_PASSWORD,
        )
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled and (
            bool(Config.OBS_HOTKEY_NAME) or bool(Config.OBS_SCENE_NAME)
        )

    def should_signal(self, command: str) -> bool:
        if not self.enabled:
            return False
        name = command.lstrip("/").split("@")[0].lower()
        if "*" in self._commands:
            return name not in ("start", "status", "topic", "start_stream", "stop_stream")
        return name in self._commands

    def signal_telegram_command(self, command: str) -> None:
        """Fire-and-forget: не блокирует хендлер Telegram."""
        if not self.should_signal(command):
            return
        asyncio.create_task(
            self._send_signal(command),
            name=f"obs-signal-{command.lstrip('/')}",
        )

    async def _send_signal(self, command: str) -> None:
        async with self._lock:
            try:
                if Config.OBS_HOTKEY_NAME:
                    await self._client.trigger_hotkey(Config.OBS_HOTKEY_NAME)
                    logger.info("OBS: hotkey «%s» (команда %s)", Config.OBS_HOTKEY_NAME, command)
                    return

                scene = Config.OBS_SCENE_NAME
                if not scene:
                    return

                return_scene = Config.OBS_SCENE_RETURN_TO.strip()
                previous = ""
                if return_scene:
                    previous = await self._client.get_current_program_scene()

                await self._client.set_program_scene(scene)
                logger.info("OBS: сцена «%s» (команда %s)", scene, command)

                if return_scene:
                    await asyncio.sleep(Config.OBS_SIGNAL_DURATION)
                    target = return_scene if return_scene != scene else previous
                    if target:
                        await self._client.set_program_scene(target)
                        logger.info("OBS: возврат на сцену «%s»", target)
            except Exception as exc:
                logger.warning("OBS сигнал не отправлен (%s): %s", command, exc)
