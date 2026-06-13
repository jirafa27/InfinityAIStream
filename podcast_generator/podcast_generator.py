import asyncio
import json
import random
import time
from dataclasses import dataclass

from podcast_generator.person_eligibility import person_is_allowed
from podcast_generator.foreign_agents_registry import person_is_foreign_agent
from podcast_generator.quote_content_guard import quote_contains_forbidden_content
from podcast_generator.quote_selection import parse_llm_quote_selection
from podcast_generator.text_generator import LLMTextGenerator
from podcast_generator.wikiquote_client import WikiquoteClient, WikiquoteQuote
from core.utils import transliterate_and_replace_symbols
from core.text_split import split_sentences
from core.chat_dedupe import chat_dedupe_key
from core.logger import logger
from core.config import Config
from core.app_state import app_state
from core.worker_epoch import retire_stale_worker
from core.chat_guard import chat_guard
from core.chat_queue import has_actionable_chat_messages, parse_chat_payload
from core.disk_guard import DiskGuard
from redis_client.redis_manager import RedisManager
from redis_client.topic_apply import apply_topic_with_interrupt
from redis_client.topic_control_store import TopicControlStore
from redis_client.chat_notify_store import ChatNotifyStore
from redis_client.chat_outbound_store import ChatOutboundStore
from redis_client.prepared_monologue_store import PreparedMonologueStore
from redis_client.visual_overlay_store import VisualOverlayStore
from podcast_generator.build_prompts import PromptsBuilder
from podcast_generator.topic_rules import decode_topic_list


@dataclass
class _PreparedMonologue:
    quote_item: WikiquoteQuote
    commentary: str
    gen_rev: int


class PodcastGenerator:
    """
    Берёт случайную цитату известного человека с ru.wikiquote.org и комментирует её.
    """

    def __init__(self, llm: LLMTextGenerator, redis_manager: RedisManager):
        self.llm = llm
        self.redis_manager = redis_manager
        self.topic_store = TopicControlStore(redis_manager.redis_client)
        self.chat_notify_store = ChatNotifyStore(redis_manager.redis_client)
        self.chat_outbound_store = ChatOutboundStore(redis_manager.redis_client)
        self.visual_overlay_store = VisualOverlayStore(redis_manager.redis_client)
        self.prepared_store = PreparedMonologueStore(redis_manager.redis_client)
        self.prompts_builder = PromptsBuilder()
        self.wikiquote = WikiquoteClient()
        self._last_monologue_at = 0.0
        self._current_person = ""
        self._last_topic_revision = 0
        self._last_queue_wait_log = 0.0
        self._consecutive_fetch_failures = 0
        self._forced_fetch_failures = 0
        self._manual_fetch_cooldown_until = 0.0
        self._last_manual_fail_announced = ""
        self._stale_queue_since: float | None = None
        self._last_stale_queue_log = 0.0
        self._tts_busy_stale_since: float | None = None
        self._last_tts_busy_log = 0.0
        self._prep_task: asyncio.Task | None = None
        self._wikiquote_fetch_lock = asyncio.Lock()

    def _manual_fetch_on_cooldown(self) -> bool:
        return time.monotonic() < self._manual_fetch_cooldown_until

    def _set_manual_fetch_cooldown(self, seconds: float = 15.0) -> None:
        self._manual_fetch_cooldown_until = time.monotonic() + seconds

    async def _peek_prepared(self, gen_rev: int) -> _PreparedMonologue | None:
        data = await self.prepared_store.peek(gen_rev)
        if data is None:
            return None
        return _PreparedMonologue(
            WikiquoteQuote(
                person=data["person"],
                quote=data["quote"],
                image_url=data.get("image_url"),
            ),
            data["commentary"],
            gen_rev,
        )

    async def _take_prepared(self, gen_rev: int) -> _PreparedMonologue | None:
        data = await self.prepared_store.take(gen_rev)
        if data is None:
            return None
        return _PreparedMonologue(
            WikiquoteQuote(
                person=data["person"],
                quote=data["quote"],
                image_url=data.get("image_url"),
            ),
            data["commentary"],
            gen_rev,
        )

    async def _store_prepared(self, prepared: _PreparedMonologue) -> None:
        if await self.prepared_store.has_for_revision(prepared.gen_rev):
            return
        await self.prepared_store.set(
            gen_rev=prepared.gen_rev,
            person=prepared.quote_item.person,
            quote=prepared.quote_item.quote,
            image_url=prepared.quote_item.image_url,
            commentary=prepared.commentary,
        )

    async def _clear_prepared(self) -> None:
        await self.prepared_store.clear()

    async def _kick_prep(self, session) -> None:
        if await self.topic_store.is_manual_topic_active():
            return
        if self._prep_task and not self._prep_task.done():
            return
        gen_rev = await self.topic_store.get_topic_revision()
        if await self.prepared_store.has_for_revision(gen_rev):
            return
        if not await self._can_prepare_monologue():
            return
        forced_person = None
        if await self.topic_store.is_manual_topic_active():
            forced_person = (await self.topic_store.get_manual_person()).strip()
            if forced_person and self._manual_fetch_on_cooldown():
                return
        self._prep_task = asyncio.create_task(
            self._prepare_one_monologue(session, forced_person or None)
        )

    async def _can_prepare_monologue(self) -> bool:
        if app_state.shutting_down or not app_state.monologues_enabled:
            return False
        if DiskGuard.low_disk_mode():
            return False
        if chat_guard.is_chat_busy():
            return False
        if await has_actionable_chat_messages(self.redis_manager):
            return False
        if await self.redis_manager.is_chat_processing():
            return False
        return True

    async def _prepare_one_monologue(self, session, forced_person: str | None) -> None:
        gen_rev = await self.topic_store.get_topic_revision()
        quote_item = await self._fetch_wikiquote_quote(session, forced_person)
        if quote_item is None:
            return
        if await self.topic_store.get_topic_revision() != gen_rev:
            return
        if await has_actionable_chat_messages(self.redis_manager):
            return
        if await self.redis_manager.is_chat_processing():
            return
        commentary = await self.generate_wikiquote_commentary(
            session,
            quote_item,
            for_background_prep=True,
        )
        if not commentary or not commentary.strip():
            return
        if await self.topic_store.get_topic_revision() != gen_rev:
            return
        await self._store_prepared(
            _PreparedMonologue(quote_item, commentary.strip(), gen_rev)
        )
        logger.info("Фоном подготовлен монолог в Redis: %s", quote_item.person)

    async def _monologue_prep_loop(self, session) -> None:
        """Параллельно готовит следующий монолог, пока озвучивается текущий или чат."""
        while not app_state.shutting_down:
            try:
                await asyncio.sleep(Config.STREAMER_POLL_INTERVAL)
                if await self.topic_store.is_manual_topic_active():
                    continue
                gen_rev = await self.topic_store.get_topic_revision()
                if await self.prepared_store.has_for_revision(gen_rev):
                    continue
                if not await self._can_prepare_monologue():
                    continue
                await self._kick_prep(session)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Ошибка цикла подготовки монолога")

    async def _monologue_emit_allowed(self, gen_rev: int) -> bool:
        if await has_actionable_chat_messages(self.redis_manager):
            return False
        if await self.redis_manager.is_chat_processing():
            return False
        if await self._has_pending_chat():
            return False
        if await self.topic_store.get_topic_revision() != gen_rev:
            return False
        return True

    async def _emit_monologue(
        self,
        quote_item: WikiquoteQuote,
        commentary: str,
        gen_rev: int,
    ) -> bool:
        if quote_contains_forbidden_content(quote_item.quote):
            logger.info(
                "Озвучка отменена — запрещённые темы в цитате: %s",
                quote_item.quote[:80],
            )
            return False
        if quote_contains_forbidden_content(commentary):
            logger.info("Озвучка отменена — запрещённые темы в комментарии")
            return False
        if person_is_foreign_agent(quote_item.person):
            logger.info(
                "Озвучка отменена — иноагент: %s",
                quote_item.person,
            )
            return False

        enqueue_rev = await self.topic_store.get_topic_revision()
        if enqueue_rev != gen_rev:
            return False

        self._current_person = quote_item.person
        await self.visual_overlay_store.set_page_image(quote_item.image_url)
        await self.visual_overlay_store.set_page_quote(quote_item.quote)
        await self.topic_store.set_current_topic(quote_item.person, notify=False)
        await self.visual_overlay_store.clear_chat_overlay()
        await self._wait_podcast_queue_slot()
        if await self.topic_store.get_topic_revision() != enqueue_rev:
            logger.info("Цитата отменена — смена перед озвучкой")
            return False

        await self._enqueue_sentences(
            quote_item.spoken_line(),
            topic_revision=enqueue_rev,
            priority=True,
        )
        if not await self.topic_store.is_manual_topic_active():
            await self.chat_outbound_store.enqueue_quote_announcement(
                quote_item.person,
                quote_item.quote,
            )
        else:
            logger.info(
                "Анонс в чат пропущен — автор задан вручную: %s",
                quote_item.person,
            )
        logger.info("Озвучка цитаты: %s", quote_item.person)
        await self._enqueue_sentences(commentary, topic_revision=enqueue_rev)
        return True

    async def _sync_external_topic(self) -> bool:
        revision = await self.topic_store.get_topic_revision()
        if revision == self._last_topic_revision:
            return False

        self._last_topic_revision = revision
        self._manual_fetch_cooldown_until = 0.0
        self._last_manual_fail_announced = ""
        self._forced_fetch_failures = 0
        if self._prep_task and not self._prep_task.done():
            self._prep_task.cancel()
            self._prep_task = None
        self._current_person = await self.topic_store.get_current_topic()
        await self._clear_prepared()
        await self.visual_overlay_store.clear_chat_overlay()
        await self.visual_overlay_store.clear_page_image()
        await self.visual_overlay_store.clear_page_quote()

        from speech.audio_player import stop_audio

        dropped = await self.redis_manager.clear_podcast_messages_queue()
        stop_audio()
        logger.info(
            "Комментарий прерван сменой автора (%s предложений в очереди)",
            dropped,
        )

        self._last_monologue_at = 0.0
        logger.info("Синхронизирован автор: %s", self._current_person)
        return True

    async def _has_pending_chat(self) -> bool:
        return await self.redis_manager.get_chat_messages_queue_length() > 0

    async def _chat_watch_loop(self, session) -> None:
        """Обрабатывает чат независимо от комментариев к викицитатам."""
        while not app_state.shutting_down:
            await self._flush_chat_batch(session, self._current_person)
            interval = (
                Config.CHAT_POLL_INTERVAL_SECONDS
                if await self._has_pending_chat()
                else Config.STREAMER_POLL_INTERVAL
            )
            await asyncio.sleep(interval)

    async def run(self, session):
        """Основной цикл: цитата → комментарий → озвучка."""
        self._current_person = await self.topic_store.get_current_topic()
        self._last_topic_revision = await self.topic_store.get_topic_revision()
        chat_task = asyncio.create_task(self._chat_watch_loop(session))
        prep_task = asyncio.create_task(self._monologue_prep_loop(session))
        await self._kick_prep(session)
        try:
            while not app_state.shutting_down:
                app_state.touch_heartbeat()
                if await retire_stale_worker(self.redis_manager, "podcaster"):
                    break

                await self._sync_external_topic()

                pending = await self.topic_store.consume_pending_topic()
                if pending:
                    await apply_topic_with_interrupt(
                        self.topic_store, self.redis_manager, pending
                    )
                    await self._sync_external_topic()

                gen_rev = await self.topic_store.get_topic_revision()
                prepared = await self._peek_prepared(gen_rev)
                if (
                    prepared
                    and await self._can_start_commentary()
                    and await self._monologue_emit_allowed(gen_rev)
                ):
                    taken = await self._take_prepared(gen_rev)
                    if taken is None:
                        continue
                    prepared = taken
                    self._last_monologue_at = time.time()
                    await self._remember_quote(prepared.quote_item)
                    logger.info(
                        "Готовый монолог: %s, комментарий %s символов",
                        prepared.quote_item.person,
                        len(prepared.commentary),
                    )
                    if await self._emit_monologue(
                        prepared.quote_item,
                        prepared.commentary,
                        gen_rev,
                    ):
                        self._consecutive_fetch_failures = 0
                        self._forced_fetch_failures = 0
                        await self._kick_prep(session)
                        await asyncio.sleep(Config.CHAT_POLL_INTERVAL_SECONDS)
                        continue

                if await has_actionable_chat_messages(self.redis_manager):
                    await asyncio.sleep(Config.CHAT_POLL_INTERVAL_SECONDS)
                    continue

                if not await self._recover_stale_tts_queue():
                    await asyncio.sleep(Config.STREAMER_POLL_INTERVAL)
                    continue

                if not await self._recover_stale_tts_busy():
                    await asyncio.sleep(Config.STREAMER_POLL_INTERVAL)
                    continue

                if not await self._can_start_commentary():
                    await asyncio.sleep(Config.STREAMER_POLL_INTERVAL)
                    continue

                forced_person = None
                if await self.topic_store.is_manual_topic_active():
                    forced_person = (await self.topic_store.get_manual_person()).strip()
                    if forced_person and self._manual_fetch_on_cooldown():
                        await asyncio.sleep(Config.STREAMER_POLL_INTERVAL)
                        continue

                quote_item = await self._fetch_wikiquote_quote(session, forced_person)
                if quote_item is None:
                    self._consecutive_fetch_failures += 1
                    if forced_person:
                        self._forced_fetch_failures += 1
                        self._set_manual_fetch_cooldown(15.0)
                        fail_key = forced_person.strip().lower()
                        if self._last_manual_fail_announced != fail_key:
                            self._last_manual_fail_announced = fail_key
                            await self.chat_outbound_store.enqueue(
                                f"Не удалось взять цитату для «{forced_person}». "
                                "Попробуйте полное ФИО (как на ru.wikiquote.org) "
                                "или !set_topic сброс для случайных авторов."
                            )
                        if self._forced_fetch_failures >= 2:
                            await self.topic_store.release_to_random_authors()
                            self._forced_fetch_failures = 0
                            await self.chat_outbound_store.enqueue(
                                "Переключаюсь на случайных авторов. "
                                "Повторите !set_topic с полным именем."
                            )
                            logger.info("Ручной автор сброшен после серии неудач")
                    elif self._consecutive_fetch_failures >= 8:
                        await self.redis_manager.clear_podcast_topics()
                        self._consecutive_fetch_failures = 0
                        logger.warning(
                            "Сброшен список недавних авторов — не удаётся найти цитату"
                        )
                        await self.chat_outbound_store.enqueue(
                            "Ищу новых авторов на Викицитатах…"
                        )
                    await asyncio.sleep(Config.STREAMER_POLL_INTERVAL)
                    continue

                self._consecutive_fetch_failures = 0
                self._forced_fetch_failures = 0
                self._last_manual_fail_announced = ""

                if await self.topic_store.get_topic_revision() != gen_rev:
                    logger.info("Цитата отменена — смена во время загрузки")
                    continue

                if await self._has_pending_chat():
                    logger.info("Чат ожидает — загрузка цитаты отменена")
                    continue

                logger.info(
                    "Генерация комментария к цитате %s: %s…",
                    quote_item.person,
                    quote_item.quote[:80],
                )
                commentary = await self.generate_wikiquote_commentary(session, quote_item)
                if commentary is None:
                    await asyncio.sleep(Config.MONOLOGUE_MIN_INTERVAL_SECONDS)
                    continue

                if await self.topic_store.get_topic_revision() != gen_rev:
                    logger.info("Комментарий отменён — автор сменился во время генерации")
                    continue

                if await self._has_pending_chat():
                    logger.info("Чат ожидает — сгенерированный комментарий отменён")
                    continue

                commentary = (commentary or "").strip()
                if not commentary:
                    logger.warning("LLM вернул пустой комментарий")
                    await asyncio.sleep(Config.MONOLOGUE_MIN_INTERVAL_SECONDS)
                    continue

                self._last_monologue_at = time.time()
                await self._remember_quote(quote_item)
                logger.info("Комментарий: %s символов", len(commentary))

                if not await self._monologue_emit_allowed(gen_rev):
                    logger.info("Монолог отменён — чат или смена автора перед озвучкой")
                    continue

                if not await self._emit_monologue(quote_item, commentary, gen_rev):
                    continue

                await self._kick_prep(session)
                await asyncio.sleep(Config.CHAT_POLL_INTERVAL_SECONDS)
        finally:
            prep_task.cancel()
            chat_task.cancel()
            if self._prep_task and not self._prep_task.done():
                self._prep_task.cancel()
            for task in (prep_task, chat_task, self._prep_task):
                if task is None:
                    continue
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _recover_stale_tts_queue(self) -> bool:
        """
        True — можно продолжать цикл.
        False — в очереди TTS ещё есть реплики, ждём озвучки.
        """
        queue_len = await self.redis_manager.get_podcast_messages_queue_length()
        if queue_len <= 0:
            self._stale_queue_since = None
            return True

        if await self.redis_manager.is_tts_busy():
            self._stale_queue_since = None
            return False

        now = time.time()
        if self._stale_queue_since is None:
            self._stale_queue_since = now

        stale_for = now - self._stale_queue_since
        if stale_for >= 120:
            from speech.audio_player import stop_audio

            dropped = await self.redis_manager.clear_podcast_messages_queue()
            stop_audio()
            self._stale_queue_since = None
            logger.warning(
                "Очередь TTS зависла %ss без синтеза — очищено %s реплик",
                int(stale_for),
                dropped,
            )
            return True

        if now - self._last_stale_queue_log >= 15.0:
            logger.info(
                "Ожидание озвучки: в очереди %s реплик (%ss)",
                queue_len,
                int(stale_for),
            )
            self._last_stale_queue_log = now
        return False

    async def _recover_stale_tts_busy(self) -> bool:
        """True — можно продолжать; сбрасывает зависший tts_busy без работы в очередях."""
        if not await self.redis_manager.is_tts_busy():
            self._tts_busy_stale_since = None
            return True

        podcast_len = await self.redis_manager.get_podcast_messages_queue_length()
        reacted_len = (
            await self.redis_manager.get_reacted_to_chat_messages_queue_length()
        )
        if (
            podcast_len > 0
            or reacted_len > 0
            or await has_actionable_chat_messages(self.redis_manager)
        ):
            self._tts_busy_stale_since = None
            return False

        now = time.time()
        if self._tts_busy_stale_since is None:
            self._tts_busy_stale_since = now

        stale_for = now - self._tts_busy_stale_since
        if stale_for >= 90:
            from speech.audio_player import stop_audio

            await self.redis_manager.set_tts_busy(False)
            stop_audio()
            self._tts_busy_stale_since = None
            logger.warning(
                "Сброшен зависший tts_busy (%ss без очереди озвучки)",
                int(stale_for),
            )
            return True

        if now - self._last_tts_busy_log >= 15.0:
            logger.info("Ожидание сброса tts_busy (%ss)", int(stale_for))
            self._last_tts_busy_log = now
        return False

    async def _can_start_commentary(self) -> bool:
        if app_state.shutting_down or not app_state.monologues_enabled:
            return False
        if DiskGuard.low_disk_mode():
            return False
        if chat_guard.is_chat_busy():
            logger.info("Комментарии отключены — высокая активность чата")
            return False
        if time.time() - self._last_monologue_at < Config.MONOLOGUE_MIN_INTERVAL_SECONDS:
            gen_rev = await self.topic_store.get_topic_revision()
            prepared = await self.prepared_store.peek(gen_rev)
            queue_empty = (
                await self.redis_manager.get_podcast_messages_queue_length() == 0
            )
            if not (prepared and queue_empty):
                return False
        return True

    async def _recent_quote_keys(self) -> tuple[set[str], set[str]]:
        raw = decode_topic_list(await self.redis_manager.get_podcast_topics())
        people: list[str] = []
        quote_keys: list[str] = []
        seen_people: set[str] = set()
        seen_quotes: set[str] = set()
        people_limit = max(1, Config.WIKIQUOTE_RECENT_PAGES_LIMIT)
        quotes_limit = people_limit * 4

        for item in raw:
            text = item.strip()
            if not text:
                continue
            if "|" in text:
                key = text.lower()
                if key in seen_quotes:
                    continue
                seen_quotes.add(key)
                quote_keys.append(key)
            else:
                key = text.lower()
                if key in seen_people:
                    continue
                seen_people.add(key)
                people.append(key)

        return set(people[:people_limit]), set(quote_keys[:quotes_limit])

    async def _fetch_manual_wikiquote_quote(
        self,
        session,
        forced_person: str,
        recent_quote_keys: set[str],
    ) -> WikiquoteQuote | None:
        pool = await self.wikiquote.collect_manual_quote_pool(
            session,
            forced_person,
            exclude_quote_keys=recent_quote_keys,
        )
        pool = [
            item
            for item in pool
            if not quote_contains_forbidden_content(item.quote)
        ]
        if not pool:
            return None

        unique_pages = {candidate.page_title for candidate in pool}
        if len(unique_pages) >= 2:
            prompt = self.prompts_builder.build_prompt_for_manual_quote_selection(
                forced_person,
                pool,
            )
            raw = await self.llm.generate_text(
                prompt,
                session,
                max_tokens=Config.WIKIQUOTE_MANUAL_QUOTE_SELECT_MAX_TOKENS,
            )
            chosen = parse_llm_quote_selection(raw, pool)
            if chosen is None:
                logger.warning(
                    "LLM не выбрала цитату для «%s», берём случайную из пула",
                    forced_person,
                )
                chosen = random.choice(pool)
            else:
                logger.info(
                    "LLM выбрала цитату для «%s» со страницы «%s»",
                    forced_person,
                    chosen.page_title,
                )
        else:
            chosen = random.choice(pool)
            logger.info(
                "Цитата для «%s» со страницы «%s» (одна страница)",
                forced_person,
                chosen.page_title,
            )

        author_page = await self.wikiquote.resolve_person_title(session, forced_person)
        if self.wikiquote._is_plausible_author_page(forced_person, chosen.page_title):
            image_page = chosen.page_title
        else:
            image_page = author_page or chosen.page_title
        label_page = chosen.page_title

        person_label = self.wikiquote.format_person_label(
            label_page,
            work_title=chosen.work_title,
            requested_author=forced_person,
        )
        image_url = await self.wikiquote.fetch_page_image(session, image_page)
        return WikiquoteQuote(
            person=person_label,
            quote=chosen.quote,
            image_url=image_url,
        )

    async def _remember_quote(self, item: WikiquoteQuote) -> None:
        await self.redis_manager.add_podcast_topic(item.cache_key)
        await self.redis_manager.add_podcast_topic(item.person)

    async def _fetch_wikiquote_quote(
        self,
        session,
        forced_person: str | None,
    ) -> WikiquoteQuote | None:
        async with self._wikiquote_fetch_lock:
            recent_people, recent_quote_keys = await self._recent_quote_keys()

            if forced_person:
                if person_is_foreign_agent(forced_person):
                    logger.info(
                        "Запрошенный автор — иноагент: %s",
                        forced_person,
                    )
                    return None
                item = await self._fetch_manual_wikiquote_quote(
                    session,
                    forced_person,
                    recent_quote_keys,
                )
                if item is None:
                    return None
                if quote_contains_forbidden_content(item.quote):
                    logger.info(
                        "Цитата отклонена — запрещённые темы: %s",
                        item.quote[:80],
                    )
                    return None
                if not await self._is_person_eligible(
                    session, forced_person, manual_request=True
                ):
                    logger.info(
                        "Запрошенный автор отклонён AI-фильтром: %s",
                        forced_person,
                    )
                    return None
                return item

            exclude_people = set(recent_people)
            max_attempts = max(1, Config.WIKIQUOTE_PERSON_FILTER_MAX_ATTEMPTS)

            for attempt in range(1, max_attempts + 1):
                item = await self.wikiquote.fetch_random_quote(
                    session,
                    exclude_people=exclude_people,
                    exclude_quote_keys=recent_quote_keys,
                )
                if item is None:
                    break
                if await self._is_person_eligible(session, item.person):
                    return item

                logger.info(
                    "AI-фильтр отклонил «%s» (попытка %s/%s)",
                    item.person,
                    attempt,
                    max_attempts,
                )
                exclude_people.add(item.person.strip().lower())

            return None

    async def _is_person_eligible(
        self,
        session,
        person: str,
        *,
        manual_request: bool = False,
    ) -> bool:
        person = person.strip()
        if not person:
            return False
        if person_is_foreign_agent(person):
            logger.info("Иноагент в реестре Минюста: %s", person)
            return False

        if not Config.WIKIQUOTE_PERSON_AI_FILTER:
            return True

        prompt = self.prompts_builder.build_prompt_for_person_eligibility(
            person,
            manual_request=manual_request,
        )
        raw = await self.llm.generate_text(
            prompt,
            session,
            max_tokens=Config.WIKIQUOTE_PERSON_FILTER_MAX_TOKENS,
        )
        if raw is None:
            logger.warning(
                "AI-фильтр: нет ответа LLM для «%s» — пропускаем без блокировки",
                person,
            )
            return True

        allowed = person_is_allowed(raw, fail_closed=True)
        if not allowed:
            logger.info(
                "AI-фильтр: «%s» не прошёл (ответ: %s)",
                person,
                (raw or "").strip()[:60],
            )
        return allowed

    @staticmethod
    def _parse_chat_payload(raw) -> dict | None:
        return parse_chat_payload(raw)

    async def _flush_chat_batch(self, session, current_person) -> None:
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
                    await self.react_to_chat(raw, session, current_person)
                finally:
                    await self.redis_manager.set_chat_processing(False)
                handled = True
                break

            if not handled:
                break

    async def generate_wikiquote_commentary(
        self,
        session,
        item: WikiquoteQuote,
        *,
        for_background_prep: bool = False,
    ) -> str | None:
        """Генерирует комментарий к одной цитате."""
        if await has_actionable_chat_messages(self.redis_manager):
            return None
        if await self.redis_manager.is_chat_processing():
            return None
        if not for_background_prep:
            if await self._has_pending_chat():
                return None
            if (
                await self.redis_manager.get_reacted_to_chat_messages_queue_length()
                > 0
            ):
                return None
        prompt = self.prompts_builder.build_prompt_for_wikiquote_commentary(item)
        return await self.llm.generate_text(
            prompt,
            session,
            max_tokens=Config.WIKIQUOTE_COMMENTARY_MAX_TOKENS,
        )

    async def _wait_podcast_queue_slot(self) -> None:
        """Ждёт, пока в очереди есть место — иначе ltrim отрежет начало реплики."""
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
        priority: bool = False,
    ) -> int:
        """Кладёт в очередь TTS каждое предложение отдельно."""
        sentences = split_sentences(text)
        # priority=LPUSH кладёт в начало списка — идём в обратном порядке, чтобы LPOP читал с начала.
        ordered = list(reversed(sentences)) if priority else sentences
        enqueued = 0
        for sentence in ordered:
            if await self.topic_store.get_topic_revision() != topic_revision:
                logger.info(
                    "Постановка в очередь прервана — автор сменился (rev %s)",
                    topic_revision,
                )
                break
            await self._wait_podcast_queue_slot()
            await self.redis_manager.add_podcast_message(
                sentence, priority=priority, topic_revision=topic_revision
            )
            enqueued += 1
        logger.info(
            "Озвучка по предложениям: %s шт., %s символов всего",
            enqueued,
            len(text),
        )
        return enqueued

    async def react_to_chat(self, msg_data, session, current_person):
        """Добавляет в очередь Redis реакцию на сообщение в чате."""
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
                    "Комментарий прерван (%s предложений в очереди) — приоритет чату",
                    dropped,
                )
            await self._clear_prepared()

            await self.visual_overlay_store.set_chat_overlay(author, content)

            chat_message = f"{author} пишет в чате: {content}"
            await self.redis_manager.add_reacted_to_chat_message(chat_message, priority=True)

            prompt = self.prompts_builder.build_prompt_for_comment(
                current_person, content, author
            )
            response_message = await self.llm.generate_text(
                prompt,
                session,
                max_tokens=Config.CHAT_RESPONSE_MAX_TOKENS,
            )
            if not response_message:
                logger.warning("AI не вернул ответ — реплика пропущена")
                await self.visual_overlay_store.clear_chat_overlay()
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
