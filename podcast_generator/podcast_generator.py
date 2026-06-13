import asyncio
import json
import re
import time

from podcast_generator.text_generator import LLMTextGenerator
from core.utils import transliterate_and_replace_symbols
from core.text_split import split_sentences
from core.chat_dedupe import chat_dedupe_key
from core.logger import logger
from core.config import Config
from core.app_state import app_state
from core.worker_epoch import retire_stale_worker
from core.chat_guard import chat_guard
from core.disk_guard import DiskGuard
from redis_client.redis_manager import RedisManager
from redis_client.topic_apply import apply_topic_with_interrupt
from redis_client.topic_control_store import TopicControlStore
from redis_client.chat_notify_store import ChatNotifyStore
from redis_client.chat_outbound_store import ChatOutboundStore
from redis_client.visual_overlay_store import VisualOverlayStore
from podcast_generator.build_prompts import PromptsBuilder
from podcast_generator.topic_rules import (
    decode_topic_list,
    is_topic_repeated,
    pick_fallback_topic,
    strip_topic_markers,
)


class PodcastGenerator:
    """
    Генерирует реплики и добавляет их в очередь Redis.
    """

    _TOPIC_LINE_RE = re.compile(
        r"[\*_#\s]*(?:НОВАЯ|Следующая)\s+ТЕМА[\*_\s]*\s*[:\-—]\s*(.+?)\s*$",
        re.IGNORECASE | re.MULTILINE,
    )

    def __init__(self, llm: LLMTextGenerator, redis_manager: RedisManager):
        self.llm = llm
        self.redis_manager = redis_manager
        self.topic_store = TopicControlStore(redis_manager.redis_client)
        self.chat_notify_store = ChatNotifyStore(redis_manager.redis_client)
        self.chat_outbound_store = ChatOutboundStore(redis_manager.redis_client)
        self.visual_overlay_store = VisualOverlayStore(redis_manager.redis_client)
        self.prompts_builder = PromptsBuilder()
        self._last_monologue_at = 0.0
        self._current_topic = ""
        self._last_topic_revision = 0
        self._last_queue_wait_log = 0.0

    async def _sync_external_topic(self) -> bool:
        revision = await self.topic_store.get_topic_revision()
        if revision == self._last_topic_revision:
            return False

        self._last_topic_revision = revision
        self._current_topic = await self.topic_store.get_current_topic()
        await self.visual_overlay_store.clear_chat_overlay()

        from speech.audio_player import stop_audio

        dropped = await self.redis_manager.clear_podcast_messages_queue()
        stop_audio()
        logger.info(
            "Монолог прерван сменой темы (%s предложений в очереди)",
            dropped,
        )

        self._last_monologue_at = 0.0
        logger.info("Синхронизирована тема: %s", self._current_topic)
        return True

    async def _generate_opening_topic(self, session) -> str:
        recent_topics = decode_topic_list(
            await self.redis_manager.get_podcast_topics()
        )
        prompt = self.prompts_builder.build_prompt_for_initial_topic(recent_topics)
        for attempt in range(2):
            raw = await self.llm.generate_text(prompt, session)
            if not raw:
                continue
            _, topic = self.extract_new_topic_and_text(raw)
            if not topic:
                first_line = raw.strip().splitlines()[0]
                topic = self._normalize_topic(
                    re.sub(
                        r"^[\*_#\s]*(?:НОВАЯ|Следующая)\s+ТЕМА[\*_\s]*\s*[:\-—]\s*",
                        "",
                        first_line,
                        flags=re.IGNORECASE,
                    )
                )
            if topic and len(topic) >= 3 and not is_topic_repeated(
                topic, recent_topics
            ):
                return topic
            if attempt == 0:
                logger.warning("LLM не предложил стартовую тему, повтор запроса")

        fallback = pick_fallback_topic(recent_topics)
        if fallback:
            logger.info("Стартовая тема из резервного списка: %s", fallback)
        return fallback

    async def _ensure_opening_topic(self, session) -> None:
        if self._current_topic.strip():
            return
        topic = await self._generate_opening_topic(session)
        if not topic:
            logger.error("Не удалось сгенерировать стартовую тему")
            return
        self._current_topic = topic
        await self.topic_store.set_current_topic(topic, notify=False)
        await self.redis_manager.add_podcast_topic(topic)
        logger.info("Стартовая тема (AI): %s", topic)

    async def _has_pending_chat(self) -> bool:
        return await self.redis_manager.get_chat_messages_queue_length() > 0

    async def _chat_watch_loop(self, session) -> None:
        """Обрабатывает чат независимо от монологов."""
        while not app_state.shutting_down:
            await self._flush_chat_batch(session, self._current_topic)
            interval = (
                Config.CHAT_POLL_INTERVAL_SECONDS
                if await self._has_pending_chat()
                else Config.STREAMER_POLL_INTERVAL
            )
            await asyncio.sleep(interval)

    async def run(self, session):
        """Основной цикл генерации подкастов"""
        self._current_topic = await self.topic_store.get_current_topic()
        self._last_topic_revision = await self.topic_store.get_topic_revision()
        await self._ensure_opening_topic(session)
        chat_task = asyncio.create_task(self._chat_watch_loop(session))
        try:
            while not app_state.shutting_down:
                app_state.touch_heartbeat()
                if await retire_stale_worker(self.redis_manager, "podcaster"):
                    break

                await self._sync_external_topic()

                if not self._current_topic.strip():
                    await self._ensure_opening_topic(session)
                    if not self._current_topic.strip():
                        await asyncio.sleep(Config.STREAMER_POLL_INTERVAL)
                        continue

                pending = await self.topic_store.consume_pending_topic()
                if pending:
                    await apply_topic_with_interrupt(
                        self.topic_store, self.redis_manager, pending
                    )
                    await self._sync_external_topic()

                if await self._has_pending_chat():
                    await asyncio.sleep(Config.CHAT_POLL_INTERVAL_SECONDS)
                    continue

                if await self.redis_manager.get_podcast_messages_queue_length() > 0:
                    await asyncio.sleep(Config.STREAMER_POLL_INTERVAL)
                    continue

                if await self.redis_manager.is_tts_busy():
                    await asyncio.sleep(Config.STREAMER_POLL_INTERVAL)
                    continue

                if (
                    await self.redis_manager.get_reacted_to_chat_messages_queue_length()
                    > 0
                ):
                    await asyncio.sleep(Config.STREAMER_POLL_INTERVAL)
                    continue

                if not self._can_start_monologue():
                    await asyncio.sleep(Config.STREAMER_POLL_INTERVAL)
                    continue

                gen_rev = await self.topic_store.get_topic_revision()
                logger.info(f"Генерация монолога на тему: {self._current_topic}")
                monologue = await self.generate_monologue(session, self._current_topic)
                if monologue is None:
                    await asyncio.sleep(Config.MONOLOGUE_MIN_INTERVAL_SECONDS)
                    continue

                if await self.topic_store.get_topic_revision() != gen_rev:
                    logger.info("Монолог отменён — тема сменилась во время генерации")
                    continue

                if await self._has_pending_chat():
                    logger.info("Чат ожидает — сгенерированный монолог отменён")
                    continue

                self._last_monologue_at = time.time()
                speaking_topic = self._current_topic.strip()
                monologue_text, _embedded_topic = self.extract_new_topic_and_text(
                    monologue
                )
                if not monologue_text:
                    logger.warning("LLM вернул пустой монолог")
                    await asyncio.sleep(Config.MONOLOGUE_MIN_INTERVAL_SECONDS)
                    continue

                recent_topics = self._forbidden_topics(
                    speaking_topic,
                    decode_topic_list(await self.redis_manager.get_podcast_topics()),
                )
                resolved_topic = await self._resolve_next_topic(
                    session, "", recent_topics
                )
                if resolved_topic:
                    self._current_topic = resolved_topic
                    await self.redis_manager.add_podcast_topic(self._current_topic)
                    logger.info(
                        "Новая тема (следующий монолог): %s",
                        self._current_topic,
                    )
                    await self.topic_store.clear_manual_topic_lock()
                else:
                    logger.warning(
                        "Следующая тема не выбрана — остаёмся на: %s",
                        speaking_topic,
                    )
                    self._current_topic = speaking_topic

                monologue_text = strip_topic_markers(monologue_text)
                logger.info("Монолог: %s символов", len(monologue_text))

                if await self._has_pending_chat():
                    logger.info("Чат ожидает — сгенерированный монолог отменён")
                    continue

                if await self.topic_store.get_topic_revision() != gen_rev:
                    logger.info("Монолог отменён — тема сменилась перед озвучкой")
                    continue

                enqueue_rev = await self.topic_store.get_topic_revision()
                redis_topic = (await self.topic_store.get_current_topic()).strip()
                if redis_topic.lower() != speaking_topic.lower():
                    manual_rev = await self.topic_store.get_manual_topic_revision()
                    if manual_rev is not None and enqueue_rev == manual_rev:
                        logger.info(
                            "Монолог отменён — установлена тема: %s",
                            redis_topic,
                        )
                        continue
                    await self.topic_store.set_current_topic(
                        speaking_topic, notify=False
                    )

                skip_topic_intro = await self.topic_store.is_manual_topic_active()
                if speaking_topic and not skip_topic_intro:
                    await self.visual_overlay_store.clear_chat_overlay()
                    intro = f"Следующая тема: {speaking_topic}"
                    await self._wait_podcast_queue_slot()
                    if (
                        await self.topic_store.get_topic_revision()
                        != enqueue_rev
                    ):
                        logger.info(
                            "Монолог отменён — тема сменилась перед intro"
                        )
                        continue
                    await self.redis_manager.add_podcast_message(
                        intro, priority=True, topic_revision=enqueue_rev
                    )
                    await self.chat_outbound_store.enqueue_topic_announcement(
                        speaking_topic
                    )
                    logger.info("Озвучка темы: %s", intro)
                elif speaking_topic and skip_topic_intro:
                    await self.visual_overlay_store.clear_chat_overlay()
                    logger.info(
                        "Intro темы пропущен — тема задана из чата: %s",
                        speaking_topic,
                    )

                await self._enqueue_sentences(
                    monologue_text,
                    topic_revision=enqueue_rev,
                )

                await asyncio.sleep(Config.CHAT_POLL_INTERVAL_SECONDS)
        finally:
            chat_task.cancel()
            try:
                await chat_task
            except asyncio.CancelledError:
                pass

    def _can_start_monologue(self) -> bool:
        if app_state.shutting_down or not app_state.monologues_enabled:
            return False
        if DiskGuard.low_disk_mode():
            return False
        if chat_guard.is_chat_busy():
            logger.info("Монологи отключены — высокая активность чата")
            return False
        if time.time() - self._last_monologue_at < Config.MONOLOGUE_MIN_INTERVAL_SECONDS:
            return False
        return True

    @staticmethod
    def _parse_chat_payload(raw) -> dict | None:
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            message = json.loads(text)
            if not isinstance(message, dict):
                return None
            return message
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            return None

    async def _flush_chat_batch(self, session, current_topic) -> None:
        while not app_state.shutting_down:
            if await self.redis_manager.get_chat_messages_queue_length() == 0:
                break
            if (
                await self.redis_manager.get_reacted_to_chat_messages_queue_length()
                >= Config.CHAT_TTS_QUEUE_MAX_SIZE
            ):
                logger.warning("Очередь ответов чата переполнена — новые AI-ответы отложены")
                break

            handled = False
            for raw in await self.redis_manager.list_chat_messages():
                message = self._parse_chat_payload(raw)
                if message is None:
                    await self.redis_manager.remove_chat_message_raw(raw)
                    logger.warning("Удалено повреждённое сообщение из очереди чата")
                    continue

                author = message.get("author", "Аноним")
                if not chat_guard.can_respond_to_user(author):
                    continue

                if not await self.redis_manager.remove_chat_message_raw(raw):
                    continue

                await self.redis_manager.set_chat_processing(True)
                try:
                    await self.react_to_chat(raw, session, current_topic)
                finally:
                    await self.redis_manager.set_chat_processing(False)
                handled = True
                break

            if not handled:
                break

    async def generate_monologue(self, session, current_topic):
        """Генерирует монолог на указанную тему"""
        if await self._has_pending_chat():
            return None
        if await self.redis_manager.get_reacted_to_chat_messages_queue_length() > 0:
            return None
        recent_topics = self._forbidden_topics(
            current_topic,
            decode_topic_list(await self.redis_manager.get_podcast_topics()),
        )
        prompt = self.prompts_builder.build_prompt_for_monologue(
            recent_topics, current_topic
        )
        text = await self.llm.generate_text(prompt, session)
        return text

    @staticmethod
    def _forbidden_topics(
        current_topic: str, recent_topics: list[str]
    ) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for topic in [current_topic, *recent_topics]:
            key = topic.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            ordered.append(topic.strip())
        return ordered

    async def _resolve_next_topic(
        self,
        session,
        new_topic: str,
        recent_topics: list[str],
    ) -> str:
        if new_topic and not is_topic_repeated(new_topic, recent_topics):
            return new_topic

        if new_topic:
            logger.warning("Тема повторяется, запрашиваем новую: %s", new_topic)

        anchor_topic = recent_topics[0] if recent_topics else self._current_topic
        fresh_prompt = self.prompts_builder.build_prompt_for_fresh_topic(
            anchor_topic, recent_topics
        )
        for attempt in range(2):
            raw = await self.llm.generate_text(fresh_prompt, session)
            if not raw:
                continue
            _, fresh_topic = self.extract_new_topic_and_text(raw)
            if fresh_topic and not is_topic_repeated(fresh_topic, recent_topics):
                return fresh_topic
            if attempt == 0:
                logger.warning("LLM не предложил уникальную тему, повтор запроса")

        fallback = pick_fallback_topic(recent_topics)
        if fallback:
            logger.info("Следующая тема из резервного списка: %s", fallback)
            return fallback

        logger.warning("Не удалось подобрать уникальную тему")
        return ""

    async def _wait_podcast_queue_slot(self) -> None:
        """Ждёт, пока в очереди есть место — иначе ltrim отрежет начало монолога."""
        while (
            not app_state.shutting_down
            and await self.redis_manager.get_podcast_messages_queue_length()
            >= Config.TTS_QUEUE_MAX_SIZE
        ):
            now = time.time()
            if now - self._last_queue_wait_log >= 10.0:
                logger.info("Очередь TTS заполнена, ожидание освобождения")
                self._last_queue_wait_log = now
            await asyncio.sleep(Config.STREAMER_POLL_INTERVAL)

    async def _enqueue_sentences(
        self,
        text: str,
        *,
        topic_revision: int,
    ) -> int:
        """Кладёт в очередь TTS каждое предложение отдельно (после полной генерации текста)."""
        sentences = split_sentences(text)
        for sentence in sentences:
            if await self.topic_store.get_topic_revision() != topic_revision:
                logger.info(
                    "Постановка в очередь прервана — тема сменилась (rev %s)",
                    topic_revision,
                )
                break
            await self._wait_podcast_queue_slot()
            await self.redis_manager.add_podcast_message(
                sentence, topic_revision=topic_revision
            )
        logger.info(
            "Озвучка по предложениям: %s шт., %s символов всего",
            len(sentences),
            len(text),
        )
        return len(sentences)

    async def react_to_chat(self, msg_data, session, current_topic):
        """Добавляет в очередь Redis реакцию на сообщение в чате"""
        try:
            raw = msg_data.decode("utf-8") if isinstance(msg_data, bytes) else msg_data
            message = json.loads(raw)
            author = message.get("author", "Аноним")
            content = message.get("content", "")
            dedupe_key = chat_dedupe_key(
                author, content, message.get("id", "")
            )

            if not chat_guard.can_respond_to_user(author):
                logger.info("Cooldown для пользователя %s — ответ пропущен", author)
                return

            if not await self.redis_manager.claim_chat_dedupe(dedupe_key):
                logger.info(
                    "Пропуск повторного сообщения от %s: %r",
                    author,
                    content[:60],
                )
                return

            logger.info(f"Новое сообщение в чате от {author}: {content}")

            dropped_tts = await self.redis_manager.clear_reacted_to_chat_messages_queue()
            if dropped_tts:
                logger.info(
                    "Прерван предыдущий ответ чата (%s реплик в TTS)",
                    dropped_tts,
                )

            from speech.audio_player import stop_audio

            dropped = await self.redis_manager.clear_podcast_messages_queue()
            if dropped:
                stop_audio()
                logger.info(
                    "Монолог прерван (%s предложений в очереди) — приоритет чату",
                    dropped,
                )

            await self.visual_overlay_store.set_chat_overlay(author, content)

            chat_message = f"{author} пишет в чате: {content}"
            await self.redis_manager.add_reacted_to_chat_message(chat_message, priority=True)

            prompt = self.prompts_builder.build_prompt_for_comment(
                current_topic, content, author
            )
            response_message = await self.llm.generate_text(
                prompt,
                session,
                max_tokens=Config.CHAT_RESPONSE_MAX_TOKENS,
            )
            if not response_message:
                logger.warning("AI не вернул ответ — реплика пропущена")
                return

            limit = Config.CHAT_RESPONSE_MAX_CHARS
            if len(response_message) > limit:
                cut = response_message[:limit].rstrip()
                for sep in (". ", "! ", "? ", "… "):
                    idx = cut.rfind(sep)
                    if idx > limit // 2:
                        cut = cut[: idx + 1]
                        break
                response_message = cut.rstrip()

            chat_guard.mark_responded(author)
            await self.chat_notify_store.enqueue(author, content, response_message)
            response_message = transliterate_and_replace_symbols(response_message)
            sentences = split_sentences(response_message)
            for sentence in sentences:
                await self.redis_manager.add_reacted_to_chat_message(
                    sentence, priority=False
                )
            logger.info(
                "Озвучка ответа чата: %s шт., %s символов",
                len(sentences),
                len(response_message),
            )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"Ошибка обработки сообщения из чата: {e}")

    @staticmethod
    def _normalize_topic(raw: str) -> str:
        return raw.strip().strip("\"'«»*#").strip()

    def _extract_topic_from_line(self, line: str) -> str:
        match = self._TOPIC_LINE_RE.match(line.strip())
        if not match:
            return ""
        new_topic = self._normalize_topic(match.group(1))
        return new_topic if len(new_topic) >= 3 else ""

    def extract_new_topic_and_text(self, text: str) -> tuple[str, str]:
        """Извлекает текст монолога и следующую тему из ответа LLM."""
        text = (text or "").strip()
        if not text:
            return "", ""

        lines = text.splitlines()

        for index, line in enumerate(lines[:5]):
            new_topic = self._extract_topic_from_line(line)
            if new_topic:
                monologue = "\n".join(lines[index + 1 :]).strip()
                return monologue or text, new_topic

        if len(lines) >= 2:
            new_topic = self._extract_topic_from_line(lines[-1])
            if new_topic:
                monologue = "\n".join(lines[:-1]).strip()
                return monologue or text, new_topic

        match = self._TOPIC_LINE_RE.search(text)
        if match:
            new_topic = self._normalize_topic(match.group(1))
            if len(new_topic) >= 3:
                monologue = self._TOPIC_LINE_RE.sub("", text).strip()
                return monologue or text, new_topic

        return text, ""
