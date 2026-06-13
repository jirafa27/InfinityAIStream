from __future__ import annotations

import aiohttp

from core.config import Config
from core.logger import logger
from podcast_generator.build_prompts import PromptsBuilder
from podcast_generator.foreign_agents_registry import person_is_foreign_agent
from podcast_generator.person_eligibility import person_is_allowed
from podcast_generator.text_generator import LLMTextGenerator
from podcast_generator.wikiquote_client import WikiquoteClient


async def preflight_manual_topic(person: str) -> tuple[bool, str]:
    """
    Проверяет, можно ли поставить автора в эфир.
    Все проверки — до прерывания текущей озвучки.
    """
    person = person.strip()
    if not person:
        return False, "empty"
    if person_is_foreign_agent(person):
        logger.info("Preflight: «%s» — иноагент", person)
        return False, "foreign_agent"

    client = WikiquoteClient()
    timeout = aiohttp.ClientTimeout(total=Config.WIKIQUOTE_REQUEST_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        if not await client.probe_manual_quotes(session, person):
            return False, "no_quotes"

        if not Config.WIKIQUOTE_PERSON_AI_FILTER:
            return True, "ok"

        prompts = PromptsBuilder()
        llm = LLMTextGenerator()
        prompt = prompts.build_prompt_for_person_eligibility(
            person,
            manual_request=True,
        )
        raw = await llm.generate_text(
            prompt,
            session,
            max_tokens=Config.WIKIQUOTE_PERSON_FILTER_MAX_TOKENS,
        )
        if raw is None:
            logger.warning(
                "Preflight AI-фильтр: нет ответа LLM для «%s» — пропускаем без блокировки",
                person,
            )
            return True, "ok"

        if not person_is_allowed(raw, fail_closed=True):
            logger.info(
                "Preflight AI-фильтр: «%s» не прошёл (ответ: %s)",
                person,
                (raw or "").strip()[:60],
            )
            return False, "person_filter"

    return True, "ok"


def manual_topic_rejection_message(topic: str, reason: str) -> str:
    topic = topic.strip()
    if reason == "no_quotes":
        return (
            f"Не удалось найти цитату для «{topic}» на ru.wikiquote.org. "
            "Проверьте точное имя (полное ФИО или латиница). "
            "Озвучка не прервана."
        )
    return (
        f"Автор «{topic}» недоступен для эфира. "
        "Озвучка не прервана."
    )
