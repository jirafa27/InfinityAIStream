from redis_client.chat_outbound_store import ChatOutboundStore
from redis_client.prepared_monologue_store import PreparedMonologueStore
from redis_client.redis_manager import RedisManager
from redis_client.topic_control_store import TopicControlStore
from redis_client.visual_overlay_store import VisualOverlayStore


async def manual_author_has_quotes(person: str) -> bool:
    from podcast_generator.manual_topic_preflight import preflight_manual_topic

    ok, _reason = await preflight_manual_topic(person)
    return ok


async def apply_topic_if_quotes_available(
    topic_store: TopicControlStore,
    redis_manager: RedisManager,
    topic: str,
    *,
    announce_in_chat: bool = False,
) -> tuple[bool, int, str]:
    """
    Сначала полная preflight-проверка, затем прерывание озвучки.
    False — автор недоступен, очередь и эфир не трогаем.
    """
    from podcast_generator.manual_topic_preflight import preflight_manual_topic

    topic = topic.strip()
    if not topic:
        return False, 0, "empty"
    ok, reason = await preflight_manual_topic(topic)
    if not ok:
        return False, 0, reason
    dropped = await apply_topic_with_interrupt(
        topic_store,
        redis_manager,
        topic,
        announce_in_chat=announce_in_chat,
    )
    return True, dropped, "ok"


async def apply_topic_with_interrupt(
    topic_store: TopicControlStore,
    redis_manager: RedisManager,
    topic: str,
    *,
    announce_in_chat: bool = False,
) -> int:
    """Запрашивает автора и прерывает текущую озвучку; экран обновится после фильтров."""
    from speech.audio_player import stop_audio

    overlay = VisualOverlayStore(redis_manager.redis_client)
    outbound = ChatOutboundStore(redis_manager.redis_client)
    prepared = PreparedMonologueStore(redis_manager.redis_client)
    await overlay.clear_chat_overlay()
    await overlay.clear_page_image()
    await overlay.clear_page_quote()
    await prepared.clear()
    await outbound.clear()
    await topic_store.apply_topic_now(topic)
    if announce_in_chat:
        await outbound.enqueue_topic_announcement(topic)
    stop_audio()
    return await redis_manager.clear_podcast_messages_queue()


async def apply_random_authors_with_interrupt(
    topic_store: TopicControlStore,
    redis_manager: RedisManager,
    *,
    announce_in_chat: bool = False,
) -> int:
    """Возврат к случайным авторам с прерыванием текущей озвучки."""
    from speech.audio_player import stop_audio

    overlay = VisualOverlayStore(redis_manager.redis_client)
    outbound = ChatOutboundStore(redis_manager.redis_client)
    prepared = PreparedMonologueStore(redis_manager.redis_client)
    await overlay.clear_chat_overlay()
    await overlay.clear_page_image()
    await overlay.clear_page_quote()
    await prepared.clear()
    await outbound.clear()
    await topic_store.release_to_random_authors()
    if announce_in_chat:
        await outbound.enqueue("Снова случайные авторы. !set_topic ИМЯ — выбрать автора.")
    stop_audio()
    return await redis_manager.clear_podcast_messages_queue()
