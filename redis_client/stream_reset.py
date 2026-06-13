import logging
import os

from redis_client.prepared_monologue_store import PreparedMonologueStore
from redis_client.redis_manager import RedisManager
from redis_client.topic_control_store import TopicControlStore
from redis_client.visual_overlay_store import VisualOverlayStore

logger = logging.getLogger(__name__)


async def clear_tts_queues(redis_manager: RedisManager) -> tuple[int, int, int]:
    """Очищает все очереди озвучки и входящего чата."""
    dropped_podcast = await redis_manager.clear_podcast_messages_queue()
    dropped_reacted = await redis_manager.clear_reacted_to_chat_messages_queue()
    dropped_chat = await redis_manager.clear_chat_messages_queue()
    return dropped_podcast, dropped_reacted, dropped_chat


async def reset_stream_on_start(
    redis_manager: RedisManager,
    *,
    reset_topic: bool | None = None,
) -> None:
    """Очищает очереди TTS и сбрасывает визуал при старте стрима."""
    if reset_topic is None:
        reset_topic = os.getenv("LOCAL_SUPERVISOR_RESET_TOPIC", "1") == "1"

    topic_store = TopicControlStore(redis_manager.redis_client)
    overlay = VisualOverlayStore(redis_manager.redis_client)
    prepared = PreparedMonologueStore(redis_manager.redis_client)

    dropped_podcast, dropped_reacted, dropped_chat = await clear_tts_queues(
        redis_manager
    )
    await overlay.clear_chat_overlay()
    await overlay.clear_page_image()
    await overlay.clear_page_quote()
    await prepared.clear()
    await topic_store.clear_pending_topic()
    await redis_manager.set_tts_busy(False)
    await redis_manager.set_chat_processing(False)

    from speech.audio_player import stop_audio

    stop_audio()

    if reset_topic:
        await topic_store.clear_current_topic()
        await redis_manager.clear_podcast_topics()
        await topic_store.bump_revision()
        await topic_store.clear_manual_topic_lock()

    logger.info(
        "Сброс при старте стрима: монолог -%s, чат TTS -%s, входящий чат -%s, тема=%s",
        dropped_podcast,
        dropped_reacted,
        dropped_chat,
        "AI при старте podcaster" if reset_topic else "(без изменений)",
    )
