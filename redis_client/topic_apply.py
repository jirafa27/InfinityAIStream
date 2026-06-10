from redis_client.chat_outbound_store import ChatOutboundStore
from redis_client.redis_manager import RedisManager
from redis_client.topic_control_store import TopicControlStore
from redis_client.visual_overlay_store import VisualOverlayStore


async def apply_topic_with_interrupt(
    topic_store: TopicControlStore,
    redis_manager: RedisManager,
    topic: str,
    *,
    announce_in_chat: bool = False,
) -> int:
    """Меняет тему на экране и сразу очищает очередь озвучки монолога."""
    from speech.audio_player import stop_audio

    overlay = VisualOverlayStore(redis_manager.redis_client)
    outbound = ChatOutboundStore(redis_manager.redis_client)
    await overlay.clear_chat_overlay()
    await outbound.clear()
    await topic_store.apply_topic_now(topic)
    if announce_in_chat:
        await outbound.enqueue_topic_announcement(topic)
    stop_audio()
    return await redis_manager.clear_podcast_messages_queue()
