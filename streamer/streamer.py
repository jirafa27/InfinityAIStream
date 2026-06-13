import asyncio
import time

from core.app_state import app_state
from core.worker_epoch import retire_stale_worker
from core.config import Config
from core.disk_guard import DiskGuard
from core.logger import logger
from core.chat_queue import has_actionable_chat_messages
from redis_client.redis_manager import RedisManager
from redis_client.topic_control_store import TopicControlStore
from redis_client.visual_overlay_store import VisualOverlayStore
from speech.speech_synthesizer import SpeechSynthesizer


class Streamer:
    """
    Берет сообщения из очередей Redis и синтезирует их в речь.
    """

    def __init__(self, redis_manager: RedisManager):
        self.redis_manager = redis_manager
        self.visual_overlay_store = VisualOverlayStore(redis_manager.redis_client)
        self.topic_store = TopicControlStore(redis_manager.redis_client)
        self.speech_synthesizer = SpeechSynthesizer()
        self._topic_intro_prefix = "Следующая тема: "
        self._file_output = Config.TTS_OUTPUT_MODE == "file"
        self._tts_lock = asyncio.Semaphore(Config.TTS_MAX_CONCURRENCY)
        self._cleanup_interval = max(60, Config.TTS_TEMP_MAX_AGE_MINUTES * 30)
        self._reacted_stale_since: float | None = None

    async def _recover_stale_reacted_queue(self) -> None:
        length = await self.redis_manager.get_reacted_to_chat_messages_queue_length()
        if length <= 0:
            self._reacted_stale_since = None
            return
        if await self.redis_manager.is_tts_busy():
            self._reacted_stale_since = None
            return

        now = time.time()
        if self._reacted_stale_since is None:
            self._reacted_stale_since = now
            return

        stale_for = now - self._reacted_stale_since
        if stale_for < 90:
            return

        dropped = await self.redis_manager.clear_reacted_to_chat_messages_queue()
        await self.visual_overlay_store.clear_chat_overlay()
        self._reacted_stale_since = None
        logger.warning(
            "Очередь озвучки чата зависла %ss — очищено %s реплик",
            int(stale_for),
            dropped,
        )

    async def _synthesize(self, text: str) -> None:
        """Озвучивает одну реплику (обычно одно предложение из очереди)."""
        async with self._tts_lock:
            await self.redis_manager.set_tts_busy(True)
            try:
                if self._file_output:
                    await self.speech_synthesizer.synthesize_to_file_async(text)
                else:
                    await self.speech_synthesizer.synthesize_and_play_async(text)
            finally:
                await self.redis_manager.set_tts_busy(False)

    async def _cleanup_loop(self) -> None:
        while not app_state.shutting_down:
            removed = DiskGuard.cleanup_tts_directory()
            if removed:
                logger.info("Очищено временных TTS-файлов: %s", removed)
            if DiskGuard.low_disk_mode():
                app_state.monologues_enabled = False
            await asyncio.sleep(self._cleanup_interval)

    async def _chat_has_priority(self) -> bool:
        return (
            await has_actionable_chat_messages(self.redis_manager)
            or await self.redis_manager.get_reacted_to_chat_messages_queue_length() > 0
        )

    async def _on_chat_playback_finished(self) -> None:
        """Чат озвучен — убираем оверлей комментария, опционально возвращаемся к теме."""
        if await self.redis_manager.is_chat_processing():
            return

        await self.visual_overlay_store.clear_chat_overlay()

        transition = Config.CHAT_RETURN_TRANSITION
        if not transition:
            return
        if await has_actionable_chat_messages(self.redis_manager):
            return
        if await self.redis_manager.get_reacted_to_chat_messages_queue_length() > 0:
            return
        rev = await self.topic_store.get_topic_revision()
        await self.redis_manager.add_podcast_message(
            transition, priority=True, topic_revision=rev
        )
        logger.info("Возврат к теме: %s", transition)

    async def run(self):
        cleanup_task = asyncio.create_task(self._cleanup_loop())
        try:
            while not app_state.shutting_down:
                app_state.touch_heartbeat()
                if await retire_stale_worker(self.redis_manager, "streamer"):
                    break
                await self._recover_stale_reacted_queue()
                processed = False

                while (
                    not app_state.shutting_down
                    and await self.redis_manager.get_reacted_to_chat_messages_queue_length()
                    > 0
                ):
                    processed = True
                    msg_data = await self.redis_manager.get_reacted_to_chat_message()
                    if not msg_data:
                        continue
                    text = (
                        msg_data.decode("utf-8")
                        if isinstance(msg_data, bytes)
                        else msg_data
                    )
                    logger.info(f"Реакция на чат: {text}")
                    is_citation = " пишет в чате: " in text
                    try:
                        if is_citation and Config.CHAT_TTS_PRE_PAUSE_SECONDS > 0:
                            await asyncio.sleep(Config.CHAT_TTS_PRE_PAUSE_SECONDS)
                        await self._synthesize(text)
                        self._reacted_stale_since = None
                        remaining = (
                            await self.redis_manager.get_reacted_to_chat_messages_queue_length()
                        )
                        if remaining == 0:
                            await self._on_chat_playback_finished()
                            if (
                                not is_citation
                                and Config.CHAT_TTS_POST_PAUSE_SECONDS > 0
                            ):
                                await asyncio.sleep(
                                    Config.CHAT_TTS_POST_PAUSE_SECONDS
                                )
                    except asyncio.TimeoutError:
                        logger.error("TTS timeout — реплика пропущена")

                if (
                    not app_state.shutting_down
                    and app_state.monologues_enabled
                    and await self.redis_manager.get_podcast_messages_queue_length() > 0
                ):
                    if await self._chat_has_priority():
                        processed = True
                        await asyncio.sleep(Config.CHAT_POLL_INTERVAL_SECONDS)
                        continue
                    processed = True
                    msg_data = await self.redis_manager.get_podcast_message()
                    if msg_data:
                        text, msg_rev = self.redis_manager.decode_podcast_message(
                            msg_data
                        )
                        current_rev = await self.topic_store.get_topic_revision()
                        if msg_rev < current_rev:
                            logger.info(
                                "Пропуск устаревшей реплики (rev %s < %s): %s",
                                msg_rev,
                                current_rev,
                                text[:80],
                            )
                            continue
                        await self.visual_overlay_store.clear_chat_overlay()
                        logger.info(f"Монолог: {text}")
                        if text.startswith(self._topic_intro_prefix):
                            on_air_topic = text[len(self._topic_intro_prefix) :].strip()
                            if on_air_topic:
                                await self.topic_store.set_current_topic(
                                    on_air_topic, notify=False
                                )
                        try:
                            await self._synthesize(text)
                        except asyncio.TimeoutError:
                            logger.error("TTS timeout — монолог пропущен")

                if not processed:
                    await asyncio.sleep(Config.STREAMER_POLL_INTERVAL)
        finally:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            DiskGuard.cleanup_tts_directory()
