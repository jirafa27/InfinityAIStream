from __future__ import annotations

import random
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from html import unescape
from urllib.parse import urlencode

import aiohttp

from podcast_generator.person_eligibility import region_verdict_from_categories
from podcast_generator.foreign_agents_registry import person_is_foreign_agent
from podcast_generator.quote_content_guard import quote_contains_forbidden_content
from podcast_generator.quote_selection import WikiquoteQuoteCandidate
from core.config import Config
from core.logger import logger


@dataclass(frozen=True)
class WikiquoteQuote:
    person: str
    quote: str
    image_url: str | None = None

    @property
    def cache_key(self) -> str:
        return WikiquoteClient.quote_cache_key(self.person, self.quote)

    def spoken_line(self) -> str:
        quote = WikiquoteClient._strip_quote_for_speech(self.quote)
        return f"«{quote}» — {self.person}."


@dataclass(frozen=True)
class ExtractedQuote:
    text: str
    work_title: str | None = None


class WikiquoteClient:
    """Случайная цитата известного человека с ru.wikiquote.org."""

    _REFERENCE_BLOCK_RE = re.compile(
        r"<ol[^>]*\breferences\b[^>]*>.*?</ol>",
        re.IGNORECASE | re.DOTALL,
    )
    _REFERENCE_WRAP_RE = re.compile(
        r'<div[^>]*\bmw-references-wrap\b[^>]*>.*?</div>',
        re.IGNORECASE | re.DOTALL,
    )
    _FOOTNOTE_MARKER_RE = re.compile(r"\[\s*[^\]]+\s*\]")
    _BIO_DATE_RE = re.compile(
        r"\(\s*(?:\d{1,2}\s+[\w\.]+\s+)?\d{4}\s*[,—\-]"
    )
    _NAME_TOKEN_RE = re.compile(
        r"^(?:аль-|ибн-|Аль-|Ибн-)?[\w'’`´\-.]+$",
        re.UNICODE,
    )
    _LEAD_DEFINITION_RE = re.compile(
        r"^[^«»!?]{3,80} — (?:старая|старый|город|фильм|книга|страна|река|поселение)",
        re.IGNORECASE,
    )
    _BIBLIOGRAPHY_RE = re.compile(
        r"(?:"
        r"isbn|изд-во|издательство|собрание сочинений|библиотека поэта|"
        r"под ред\.|—\s*м\.:|—\s*л\.:|—\s*спб\.:|"
        r"том\s+\d+|стр\.\s*\d+|\d{4}\s*г\."
        r")",
        re.IGNORECASE,
    )
    _SOURCE_LABEL_RE = re.compile(
        r"(?:"
        r"^речь\s+(?:в|на|перед|о|об|при|из)|"
        r"^выступление\s+(?:в|на|перед|о|об|при)|"
        r"^доклад\s+(?:в|на|о|об|при|из)|"
        r"^интервью\s+(?:в|для|на|из)|"
        r"^письмо\s+(?:к|в|от|из)|"
        r"^статья\s+(?:в|для|«|из)|"
        r"^записка\s+(?:в|к|из)|"
        r"^предисловие\s+(?:к|в|из)|"
        r"^послание\s+(?:к|в|из)|"
        r"^обращение\s+(?:к|в|из)|"
        r"^вступительное\s+слово|"
        r"^заключительное\s+слово|"
        r"^заметки\s+(?:к|в|из)|"
        r"^фрагмент\s+(?:из|романа|повести|книги)|"
        r"^отрывок\s+(?:из|романа|повести|книги)|"
        r"^цитата\s+из|"
        r"^из\s+(?:книги|романа|повести|статьи|письма|речи|доклада)"
        r")",
        re.IGNORECASE,
    )
    _DATE_IN_TEXT_RE = re.compile(
        r"(?:"
        r"\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|"
        r"сентября|октября|ноября|декабря)\s+\d{4}|"
        r"\d{4}\s*г\.?"
        r")",
        re.IGNORECASE,
    )
    _DATE_PHRASE_RE = re.compile(
        r"^(?:—\s*)?(?:"
        r"(?:начало|конец|середина|вторая\s+половина|первая\s+половина)\s+"
        r"(?:\w+\s+){0,3}\d{4}|"
        r"(?:январ[ья]|феврал[ья]|март[а]?|апрел[ья]|ма[йя]|июн[ья]|июл[ья]|"
        r"август[а]?|сентябр[ья]|октябр[ья]|ноябр[ья]|декабр[ья])\s+\d{4}|"
        r"\d{4}\s*г\.?"
        r")",
        re.IGNORECASE,
    )
    _WIKI_OMISSION_RE = re.compile(
        r"<…>|&lt;…&gt;|<\.\.\.>|\[\.\.\.\]|\[…\]",
        re.IGNORECASE,
    )
    _ATTRIBUTION_CONTEXT_RE = re.compile(
        r"^(?:"
        r"о\s+\w+|"
        r"об\s+\w+|"
        r"при\s+\w+|"
        r"из\s+(?:«|книги|романа|повести|статьи|речи|доклада|письма)|"
        r"в\s+«|"
        r"к\s+«|"
        r"по\s+(?:поводу|случаю)|"
        r"на\s+(?:съезде|конференции|собрании|заседании)"
        r")",
        re.IGNORECASE,
    )
    _QUOTES_SECTION_HEADER_RE = re.compile(
        r"<h2[^>]*>(.*?)</h2>",
        re.IGNORECASE | re.DOTALL,
    )
    _NESTED_SECTION_HEADER_RE = re.compile(
        r"<h[34][^>]*>(.*?)</h[34]>",
        re.IGNORECASE | re.DOTALL,
    )
    _YEAR_SUBSECTION_RE = re.compile(r"^\d{4}\s+год", re.IGNORECASE)
    _ABOUT_PERSON_SECTION_RE = re.compile(
        r"(?:"
        r"^цитаты\s+(?:об|о|про|на|из)\b|"
        r"^изречения\s+(?:об|о|про)\b|"
        r"^высказывания\s+(?:об|о|про)\b|"
        r"^афоризмы\s+(?:об|о|про)\b|"
        r"^мнения\s+(?:о|об)\b|"
        r"^критика\b|"
        r"^биография\b"
        r")",
        re.IGNORECASE,
    )
    _OWN_QUOTES_SECTION_RE = re.compile(
        r"^(?:"
        r"цитаты(?:\s+(?:автора|из\s+произведений|и\s+изречения))?|"
        r"изречения|афоризмы|высказывания|фразы"
        r")(?:\s*\[.*)?$",
        re.IGNORECASE,
    )
    _BOOK_QUOTES_SECTION_RE = re.compile(
        r"^цитаты\s+из\s+(?:"
        r"книг|произведений|романов|повестей|рассказов|пьес|"
        r"стихотворений|поэм|фильмов|сериалов|пьес|диалогов"
        r")(?:\s*\[.*)?$",
        re.IGNORECASE,
    )
    _SKIP_SUBSECTION_RE = re.compile(
        r"^(?:ссылки|примечания|см\.?\s*также|литература|внешние\s+ссылки)",
        re.IGNORECASE,
    )
    _WORK_AUTHOR_PAGE_RE = re.compile(r"^(.+?)\s*\(([^)]+)\)\s*$")
    _JUNK_PAGE_TITLE_RE = re.compile(
        r"(?:"
        r"предуведомлен|предисловие|посвящени|"
        r"кратк(?:ое|ая)|введение\s+к\s+|"
        r"список\s+цитат|заготовка"
        r")",
        re.IGNORECASE,
    )
    _CHAPTER_TAIL_RE = re.compile(
        r"^(?:"
        r"глава|часть|раздел|параграф|"
        r"ч\.|гл\.|стр\.|с\.|scene|act"
        r")\s*[\dIVXLC]+",
        re.IGNORECASE,
    )
    _PAGE_REF_TAIL_RE = re.compile(
        r"[:;]?\s*с\.?\s*\d+(?:\s*[-–—]\s*\d+)?\s*$",
        re.IGNORECASE,
    )
    _ENCYCLOPEDIA_TAIL_RE = re.compile(
        r"(?:"
        r"широко\s+известн|регулярно\s+употребл|"
        r"классическ(?:ая|ий)\s+|"
        r"в\s+(?:православн|литературн|русск|советск)\w*\s+традици|"
        r"молитва\s+о\s+|"
        r"одна\s+из\s+(?:самых|наиболее)"
        r")",
        re.IGNORECASE,
    )
    _PRAYER_QUOTE_RE = re.compile(
        r"^(?:владыко|господи|отче|боже|господь|тебе|твоему)",
        re.IGNORECASE,
    )
    _BYLINE_ATTRIBUTION_RE = re.compile(
        r"^[\w«»\s'’\-.]+,\s*(?:"
        r"(?:специальный\s+)?(?:корреспондент|журналист|редактор|критик|"
        r"писатель|историк|публицист|обозреватель|комментатор)"
        r"(?:\s*,\s*\d{4})?"
        r")",
        re.IGNORECASE,
    )
    _BIOGRAPHY_ABOUT_RE = re.compile(
        r"(?:"
        r"по праву считается|"
        r"считается (?:одним из |классиком |выдающимся )|"
        r"является (?:одним из |классиком |выдающимся |известн)|"
        r"чь[её] (?:творчество|работа|деятельность)|"
        r"(?:оказал[а]?|оказали) (?:огромное |значительное )?влияние|"
        r"(?:родил(?:ся|ась)|умер(?:ла)?)(?:\s+в|\s+\d)|"
        r"известен(?:ным)? (?:как |в качестве |в истории)|"
        r"известна(?:ной)? (?:как |в качестве |в истории)|"
        r"(?:на|у себя на) родине|"
        r"внес(?:ён|ен|ла)? (?:большой |значительный )?вклад|"
        r"прославил(?:ся|ась)|"
        r"(?:русск(?:ий|ая|ого|ой)|советск(?:ий|ая)|японск(?:ий|ая)|"
        r"американск(?:ий|ая)|французск(?:ий|ая)|немецк(?:ий|ая)|"
        r"британск(?:ий|ая)|английск(?:ий|ая)) "
        r"(?:писател|поэт|философ|режиссёр|режиссер|композитор|учёный|ученый|"
        r"деятел|актёр|актер|художник|музыкант)"
        r")",
        re.IGNORECASE,
    )
    _WIKI_STUB_RE = re.compile(
        r"(?:"
        r"незаверш[её]нн(?:ая|ое) статья|"
        r"вы можете помочь проекту|"
        r"исправив и дополнив|"
        r"является заготовкой|"
        r"статья нуждается|"
        r"нуждается в проверке|"
        r"требует расширения|"
        r"эта страница пуста|"
        r"пока не содержит|"
        r"не содержит цитат|"
        r"в настоящее время страница|"
        r"страница удалена|"
        r"создать страницу"
        r")",
        re.IGNORECASE,
    )
    _MAINTENANCE_BLOCK_RES = (
        re.compile(
            r"<table[^>]*\bambox\b[^>]*>.*?</table>",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"<div[^>]*\b(?:hatnote|noprint|mbox)\b[^>]*>.*?</div>",
            re.IGNORECASE | re.DOTALL,
        ),
    )

    _SKIP_MARKERS = (
        "категория:",
        "см. также",
        "примечания",
        "литература",
        "ссылки",
        "перенаправление",
        "викицитатник",
        "заглавная страница",
        "медиафайлы",
        "викитеке",
        "викискладе",
        "энциклопедии",
        "критика и публицистика",
        "у этого термина существуют",
        "незавершённая статья",
        "незавершенная статья",
        "помочь проекту",
        "исправив и дополнив",
    )

    _FALLBACK_PEOPLE = (
        "Оскар Уайльд",
        "Сенека",
        "Эйнштейн",
        "Гёте",
        "Пушкин",
        "Толстой",
        "Достоевский",
        "Ницше",
        "Сократ",
        "Марк Аврелий",
        "Конфуций",
        "Вольтер",
    )

    _ARCHETYPE_TITLES = frozenset(
        {
            "старуха",
            "старик",
            "мать",
            "отец",
            "бог",
            "дьявол",
            "смерть",
            "любовь",
            "дружба",
            "детство",
            "юность",
            "старость",
            "женщина",
            "мужчина",
            "ребёнок",
            "ребенок",
            "дитя",
            "народ",
            "молодёжь",
            "молодежь",
        }
    )

    _MEDIA_WORK_MARKERS = (
        "эпизод",
        "фильм",
        "сериал",
        "мультфильм",
        "видеоигра",
        "компьютерная игра",
        "звёздные войны",
        "звездные войны",
        "star wars",
        "гарри поттер",
        "властелин колец",
        "марвел",
        "dc comics",
        "дисней",
        "pixar",
        "аниме",
        "манга",
    )

    _THEME_CATEGORY_MARKERS = (
        "категория:тематические статьи по алфавиту",
        "категория:возраст",
        "категория:семья",
        "категория:мужчина и женщина",
        "категория:религия",
    )

    _EXCLUDED_PERSON_CATEGORY_MARKERS = (
        "категория:политики",
        "категория:политики по алфавиту",
        "категория:государственные деятели",
        "категория:президенты",
    )

    _PERSON_CATEGORY_MARKERS = (
        "категория:персоналии по алфавиту",
        "категория:писатели",
        "категория:поэты",
        "категория:философы",
        "категория:деятели",
        "категория:художники",
        "категория:музыканты",
        "категория:актеры",
        "категория:актёры",
        "категория:учёные",
        "категория:ученые",
        "категория:спортсмены",
        "категория:персонажи по алфавиту",
    )

    def __init__(self) -> None:
        self._base = Config.WIKIQUOTE_API_BASE.rstrip("/")
        self._wikipedia_base = Config.WIKIPEDIA_API_BASE.rstrip("/")
        ua = Config.WIKIQUOTE_USER_AGENT.strip()
        self._headers = {
            "User-Agent": ua,
            "Accept": "application/json",
        }

    @staticmethod
    def quote_cache_key(person: str, quote: str) -> str:
        person_key = person.strip().lower()
        quote_key = re.sub(r"\s+", " ", quote.strip().lower())[:160]
        return f"{person_key}|{quote_key}"

    @staticmethod
    def format_quote_for_prompt(item: WikiquoteQuote) -> str:
        return f"«{item.quote}» — {item.person}"

    @classmethod
    def _normalize_work_title(cls, title: str) -> str:
        title = re.sub(r"\s*\[.*$", "", title.strip())
        title = re.sub(r"\s*\(\d{4}(?:\s*г\.?)?\)\s*$", "", title).strip()
        return title

    @classmethod
    def _parse_work_author_page(cls, title: str) -> tuple[str | None, str | None]:
        match = cls._WORK_AUTHOR_PAGE_RE.match(title.strip())
        if not match:
            return None, None
        work = cls._normalize_work_title(match.group(1))
        author = match.group(2).strip()
        if not work or not author:
            return None, None
        return work, author

    @classmethod
    def _is_junk_manual_page(cls, title: str) -> bool:
        return bool(cls._JUNK_PAGE_TITLE_RE.search(title.strip()))

    @classmethod
    def _query_matches_author_name(cls, query: str, name: str) -> bool:
        query = query.strip().lower().replace("ё", "е")
        name = name.strip().lower().replace("ё", "е")
        if not query or not name:
            return False
        if query in name or name in query:
            return True
        q_stem = re.sub(r"[аеиоуыэюяьй]$", "", query)
        for part in name.split():
            part_stem = re.sub(r"[аеиоуыэюяьй]$", "", part)
            if (
                q_stem in part
                or part.startswith(q_stem)
                or part_stem == q_stem
                or SequenceMatcher(None, q_stem, part_stem).ratio() >= 0.84
            ):
                return True
        return SequenceMatcher(None, q_stem, name).ratio() >= 0.78

    @classmethod
    def _is_primary_author_page(cls, query: str, title: str) -> bool:
        work, author = cls._parse_work_author_page(title)
        if work:
            return cls._query_matches_author_name(query, author)
        return cls._query_matches_author_name(query, title)

    @classmethod
    def _is_disambiguation_page_title(cls, query: str, title: str) -> bool:
        return (
            len(title.split()) == 1
            and query.strip().lower() == title.strip().lower()
        )

    @classmethod
    def _author_page_sort_priority(cls, query: str, title: str) -> int:
        work, author = cls._parse_work_author_page(title)
        if work and author:
            return 2
        if not cls._query_matches_author_name(query, title):
            return 3
        if cls._is_disambiguation_page_title(query, title):
            return 4
        if " и " in title.lower() and len(query.split()) == 1:
            return -1
        word_count = len(title.split())
        if word_count >= 3:
            return 0
        if word_count == 2:
            return 1
        return 3

    @classmethod
    def _individual_author_penalty(cls, query: str, title: str) -> int:
        if len(query.split()) != 1 or " и " in title.lower():
            return 0
        parts = title.split()
        if len(parts) >= 3 and cls._query_matches_author_name(query, parts[-1]):
            return 1
        return 0

    @classmethod
    def _homonym_title_penalty(cls, query: str, title: str) -> int:
        if len(query.split()) != 1:
            return 0
        lowered = title.lower()
        church_markers = (
            "свят",
            "епископ",
            "патриарх",
            "архимандрит",
            "великий",
            "блаженн",
            "преподоб",
            "иеромонах",
        )
        if any(marker in lowered for marker in church_markers):
            return 2
        return 0

    @classmethod
    def _is_plausible_author_page(cls, query: str, title: str) -> bool:
        """Омонимы вроде «Венедиктов» vs «Венедикт … Ерофеев» не считаем совпадением."""
        query = query.strip()
        title = title.strip()
        if not query or not title:
            return False
        if cls._parse_work_author_page(title)[0]:
            return cls._query_matches_author_name(query, title.split("(")[0].strip())
        if len(query.split()) >= 2:
            return cls._query_matches_author_name(query, title)
        q = query.lower().replace("ё", "е")
        words = [w.lower().replace("ё", "е") for w in title.split()]
        if q in words:
            return True
        if words and words[-1] == q:
            return True
        if words and abs(len(words[-1]) - len(q)) <= 1 and (
            words[-1].startswith(q) or q.startswith(words[-1])
        ):
            return True
        return False

    @classmethod
    def format_person_label(
        cls,
        page_title: str,
        *,
        work_title: str | None = None,
        requested_author: str | None = None,
    ) -> str:
        page_title = page_title.strip()
        requested = (requested_author or "").strip()
        work = cls._normalize_work_title(work_title) if work_title else ""
        display_author = requested or page_title

        if work:
            work_lower = work.lower()
            if cls._YEAR_SUBSECTION_RE.match(work):
                return f"{display_author} ({work})"
            if (
                work_lower not in {page_title.lower(), requested.lower()}
                and not cls._query_matches_author_name(work, page_title)
            ):
                return f"{display_author} ({work})"

        page_work, page_author = cls._parse_work_author_page(page_title)
        if page_work and page_author:
            author = requested or page_author
            return f"{author} ({page_work})"

        if requested:
            if cls._query_matches_author_name(requested, page_title):
                return requested
            short_page = cls._normalize_work_title(page_title)
            if short_page:
                return f"{requested} ({short_page})"

        return page_title

    async def _get_json(
        self,
        session: aiohttp.ClientSession,
        params: dict[str, str | int],
        *,
        base: str | None = None,
    ) -> dict | None:
        api_base = (base or self._base).rstrip("/")
        url = f"{api_base}?{urlencode(params)}"
        try:
            async with session.get(
                url,
                headers=self._headers,
                timeout=Config.WIKIQUOTE_REQUEST_TIMEOUT_SECONDS,
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    hint = ""
                    if resp.status == 403 and "user-agent" in body.lower():
                        hint = " — задайте WIKIQUOTE_USER_AGENT с URL/контактом (см. w.wiki/4wJS)"
                    logger.warning(
                        "Wiki API %s @ %s: HTTP %s%s",
                        params.get("action"),
                        api_base,
                        resp.status,
                        hint,
                    )
                    return None
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning("Wikiquote API ошибка (%s): %s", params.get("action"), exc)
            return None

    async def _fetch_category_page(
        self,
        session: aiohttp.ClientSession,
        *,
        batch: int,
        continue_token: str | None = None,
    ) -> tuple[list[str], str | None]:
        params: dict[str, str | int] = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": Config.WIKIQUOTE_PERSON_CATEGORY,
            "cmnamespace": 0,
            "cmlimit": batch,
            "cmtype": "page",
            "format": "json",
        }
        if continue_token:
            params["cmcontinue"] = continue_token

        data = await self._get_json(session, params)
        if not data:
            return [], None

        members = data.get("query", {}).get("categorymembers") or []
        titles = [
            (item.get("title") or "").strip()
            for item in members
            if isinstance(item, dict)
        ]
        titles = [title for title in titles if title]
        next_token = (data.get("continue") or {}).get("cmcontinue")
        return titles, next_token

    async def fetch_category_people(
        self,
        session: aiohttp.ClientSession,
        *,
        limit: int | None = None,
    ) -> list[str]:
        batch = limit or Config.WIKIQUOTE_PERSON_BATCH_SIZE
        continue_token: str | None = None
        titles: list[str] = []

        skip_pages = random.randint(0, 8)
        for page_idx in range(skip_pages + 1):
            page_titles, continue_token = await self._fetch_category_page(
                session,
                batch=batch,
                continue_token=continue_token,
            )
            if page_idx == skip_pages:
                titles = page_titles
            if not continue_token:
                break

        if not titles:
            titles, _ = await self._fetch_category_page(session, batch=batch)

        random.shuffle(titles)
        return titles

    async def _resolve_exact_title(
        self,
        session: aiohttp.ClientSession,
        title: str,
    ) -> str | None:
        data = await self._get_json(
            session,
            {
                "action": "query",
                "titles": title,
                "redirects": 1,
                "format": "json",
            },
        )
        if not data:
            return None
        pages = data.get("query", {}).get("pages") or {}
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            if int(page.get("pageid", -1)) > 0:
                resolved = (page.get("title") or "").strip()
                if resolved:
                    return resolved
        return None

    @classmethod
    def _looks_like_media_work(cls, title: str) -> bool:
        lowered = title.strip().lower()
        return any(marker in lowered for marker in cls._MEDIA_WORK_MARKERS)

    @classmethod
    def _person_search_variants(cls, query: str) -> list[str]:
        query = query.strip()
        if not query:
            return []
        variants = [query]
        stripped = re.sub(
            r"^(?:"
            r"мастер|master|доктор|dr\.?|профессор|prof\.?|"
            r"святой|св\.?|генерал|general|император|король|queen|king"
            r")\s+",
            "",
            query,
            flags=re.IGNORECASE,
        ).strip()
        if stripped and stripped.lower() != query.lower():
            variants.append(stripped)
        seen: set[str] = set()
        result: list[str] = []
        for variant in variants:
            key = variant.lower()
            if key not in seen:
                seen.add(key)
                result.append(variant)
        return result

    @classmethod
    def _score_person_candidate(
        cls,
        original_query: str,
        search_query: str,
        title: str,
    ) -> float:
        query_lower = original_query.lower()
        search_lower = search_query.lower()
        title_lower = title.lower()
        score = max(
            SequenceMatcher(None, query_lower, title_lower).ratio(),
            SequenceMatcher(None, search_lower, title_lower).ratio(),
        )
        if title_lower in {query_lower, search_lower}:
            score += 0.35
        elif search_lower in title_lower or query_lower in title_lower:
            score += 0.15
        if cls._looks_like_media_work(title):
            score -= 0.55
        if len(title) > max(len(original_query), len(search_query)) * 2 + 8:
            score -= 0.2
        if len(title.split()) <= 3:
            score += 0.05
        return score

    @classmethod
    def _pick_best_person_title(
        cls,
        original_query: str,
        search_query: str,
        candidates: list[str],
    ) -> str | None:
        if not candidates:
            return None
        non_media = [
            title for title in candidates if not cls._looks_like_media_work(title)
        ]
        pool = non_media or candidates
        best = max(
            pool,
            key=lambda title: cls._score_person_candidate(
                original_query,
                search_query,
                title,
            ),
        )
        if cls._score_person_candidate(original_query, search_query, best) >= 0.55:
            return best
        return None

    @classmethod
    def _score_manual_page_candidate(
        cls,
        original_query: str,
        search_query: str,
        title: str,
    ) -> float:
        query_lower = original_query.lower()
        search_lower = search_query.lower()
        title_lower = title.lower()
        score = max(
            SequenceMatcher(None, query_lower, title_lower).ratio(),
            SequenceMatcher(None, search_lower, title_lower).ratio(),
        )
        if title_lower in {query_lower, search_lower}:
            score += 0.4
        elif search_lower in title_lower or query_lower in title_lower:
            score += 0.2
        if len(title.split()) <= 4:
            score += 0.05
        return score

    async def _rank_manual_page_titles(
        self,
        session: aiohttp.ClientSession,
        query: str,
    ) -> list[str]:
        query = query.strip()
        if not query:
            return []

        seen: set[str] = set()
        scored: list[tuple[float, str]] = []

        def add_title(title: str, *, search_query: str) -> None:
            title = title.strip()
            if not title or self._is_junk_manual_page(title):
                return
            key = title.lower()
            if key in seen:
                return
            seen.add(key)
            score = self._score_manual_page_candidate(query, search_query, title)
            scored.append((score, title))

        for variant in self._person_search_variants(query):
            resolved = await self._resolve_exact_title(session, variant)
            if resolved and not self._is_junk_manual_page(resolved):
                add_title(resolved, search_query=variant)
            for title in await self._search_titles(
                session,
                variant,
                limit=max(20, Config.WIKIQUOTE_MANUAL_SEARCH_LIMIT),
            ):
                add_title(title, search_query=variant)

        scored.sort(
            key=lambda item: (
                self._author_page_sort_priority(query, item[1]),
                self._homonym_title_penalty(query, item[1]),
                self._individual_author_penalty(query, item[1]),
                -item[0],
            )
        )
        return [title for score, title in scored if score >= 0.35]

    def _filter_raw_quotes(
        self,
        page_title: str,
        quotes: list[ExtractedQuote],
        exclude_quote_keys: set[str],
        *,
        requested_author: str | None = None,
    ) -> list[ExtractedQuote]:
        pool = [
            item
            for item in quotes
            if self.quote_cache_key(page_title, item.text) not in exclude_quote_keys
            and not self._looks_like_attribution_name(item.text)
            and not self._looks_like_source_label(item.text)
            and not self._looks_like_source_tail(item.text)
            and not self._looks_like_byline_attribution(item.text)
            and not self._looks_like_narrative_excerpt(item.text)
            and not quote_contains_forbidden_content(item.text)
        ]
        substantive = [item for item in pool if self._has_quote_substance(item.text)]
        if substantive:
            pool = substantive

        max_chars = Config.WIKIQUOTE_MAX_QUOTE_CHARS
        result: list[ExtractedQuote] = []
        for item in pool:
            if self._looks_like_prayer_quote(item.text):
                continue
            trimmed = WikiquoteClient._trim_quote_length(item.text, max_chars)
            if not trimmed:
                continue
            finalized = WikiquoteClient._finalize_quote_text(trimmed)
            if self._looks_like_prayer_quote(finalized):
                continue
            if quote_contains_forbidden_content(finalized):
                continue
            if len(finalized) < 20 or not self._has_quote_substance(finalized):
                continue
            person_label = self.format_person_label(
                page_title,
                work_title=item.work_title,
                requested_author=requested_author,
            )
            if self.quote_cache_key(person_label, finalized) in exclude_quote_keys:
                continue
            result.append(
                ExtractedQuote(text=finalized, work_title=item.work_title)
            )
        return result

    async def collect_manual_quote_pool(
        self,
        session: aiohttp.ClientSession,
        person: str,
        *,
        exclude_quote_keys: set[str] | None = None,
    ) -> list[WikiquoteQuoteCandidate]:
        person = person.strip()
        if not person:
            return []

        exclude = exclude_quote_keys or set()
        page_titles = await self._rank_manual_page_titles(session, person)
        if not page_titles:
            logger.info("Wikiquote: для «%s» не найдено страниц", person)
            return []

        logger.info(
            "Wikiquote: для «%s» кандидаты страниц: %s",
            person,
            ", ".join(page_titles[: Config.WIKIQUOTE_MANUAL_PAGE_LIMIT]),
        )

        pool: list[WikiquoteQuoteCandidate] = []
        pool_limit = Config.WIKIQUOTE_MANUAL_QUOTE_POOL_LIMIT
        per_page = Config.WIKIQUOTE_MANUAL_QUOTES_PER_PAGE

        for page_title in page_titles[: Config.WIKIQUOTE_MANUAL_PAGE_LIMIT]:
            if person_is_foreign_agent(page_title):
                continue
            if not self._is_plausible_author_page(person, page_title):
                continue
            if len(pool) >= pool_limit:
                break
            parsed = await self._fetch_page_quotes(session, page_title)
            if not parsed:
                continue
            resolved_title, quotes = parsed
            filtered = self._filter_raw_quotes(
                resolved_title,
                quotes,
                exclude,
                requested_author=person,
            )
            for item in filtered[:per_page]:
                pool.append(
                    WikiquoteQuoteCandidate(
                        page_title=resolved_title,
                        quote=item.text,
                        work_title=item.work_title,
                    )
                )
                if len(pool) >= pool_limit:
                    break

        if not pool:
            logger.info("Wikiquote: у кандидатов «%s» нет подходящих цитат", person)
        return pool

    async def probe_manual_quotes(
        self,
        session: aiohttp.ClientSession,
        person: str,
    ) -> bool:
        """Быстрая проверка: есть ли хотя бы одна подходящая цитата на Wikiquote."""
        person = person.strip()
        if not person:
            return False
        if person_is_foreign_agent(person):
            logger.info("Wikiquote probe: «%s» — иноагент", person)
            return False

        page_titles = await self._rank_manual_page_titles(session, person)
        if not page_titles:
            logger.info("Wikiquote probe: для «%s» не найдено страниц", person)
            return False

        page_limit = min(3, max(1, Config.WIKIQUOTE_MANUAL_PAGE_LIMIT))
        for page_title in page_titles[:page_limit]:
            if not self._is_plausible_author_page(person, page_title):
                continue
            parsed = await self._fetch_page_quotes(session, page_title)
            if not parsed:
                continue
            resolved_title, quotes = parsed
            filtered = self._filter_raw_quotes(
                resolved_title,
                quotes,
                set(),
                requested_author=person,
            )
            if filtered:
                logger.info(
                    "Wikiquote probe: для «%s» есть цитаты («%s»)",
                    person,
                    resolved_title,
                )
                return True

        logger.info("Wikiquote probe: для «%s» нет подходящих цитат", person)
        return False

    async def _search_titles(
        self,
        session: aiohttp.ClientSession,
        query: str,
        *,
        limit: int = 8,
    ) -> list[str]:
        search_data = await self._get_json(
            session,
            {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srnamespace": 0,
                "srlimit": limit,
                "format": "json",
            },
        )
        if not search_data:
            return []
        candidates: list[str] = []
        for item in search_data.get("query", {}).get("search") or []:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            if title:
                candidates.append(title)
        return candidates

    async def resolve_person_title(
        self,
        session: aiohttp.ClientSession,
        query: str,
    ) -> str | None:
        query = query.strip()
        if not query:
            return None

        query_lower = query.lower()
        for variant in self._person_search_variants(query):
            resolved = await self._resolve_exact_title(session, variant)
            if resolved and not self._looks_like_media_work(resolved):
                if resolved.lower() != query_lower:
                    logger.info("Wikiquote: «%s» → %s", query, resolved)
                return resolved

            candidates = await self._search_titles(session, variant)
            best = self._pick_best_person_title(query, variant, candidates)
            if best:
                if best.lower() != query_lower:
                    logger.info("Wikiquote: «%s» → %s", query, best)
                return best

        for fallback in self._FALLBACK_PEOPLE:
            if SequenceMatcher(None, query_lower, fallback.lower()).ratio() < 0.82:
                continue
            resolved = await self._resolve_exact_title(session, fallback)
            if resolved and not self._looks_like_media_work(resolved):
                logger.info("Wikiquote: «%s» → %s (известное имя)", query, resolved)
                return resolved
        return None

    async def fetch_page_categories(
        self,
        session: aiohttp.ClientSession,
        title: str,
    ) -> list[str]:
        data = await self._get_json(
            session,
            {
                "action": "query",
                "titles": title,
                "prop": "categories",
                "cllimit": 50,
                "format": "json",
                "redirects": 1,
            },
        )
        if not data:
            return []

        pages = data.get("query", {}).get("pages") or {}
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            if int(page.get("pageid", -1)) < 0:
                continue
            categories = page.get("categories") or []
            return [
                (item.get("title") or "").strip()
                for item in categories
                if isinstance(item, dict) and (item.get("title") or "").strip()
            ]
        return []

    @classmethod
    def _is_archetype_title(cls, title: str) -> bool:
        return title.strip().lower() in cls._ARCHETYPE_TITLES

    @classmethod
    def _is_excluded_person_by_categories(cls, categories: list[str]) -> bool:
        lowered = [category.lower() for category in categories]
        return any(
            marker in category
            for category in lowered
            for marker in cls._EXCLUDED_PERSON_CATEGORY_MARKERS
        )

    @classmethod
    def _is_concrete_person_by_categories(
        cls,
        categories: list[str],
        *,
        title: str,
    ) -> bool:
        if cls._is_archetype_title(title):
            return False

        lowered = [category.lower() for category in categories]
        if cls._is_excluded_person_by_categories(categories):
            return False
        if any(
            theme in category
            for category in lowered
            for theme in cls._THEME_CATEGORY_MARKERS
        ):
            return False
        if any(
            marker in category
            for category in lowered
            for marker in cls._PERSON_CATEGORY_MARKERS
        ):
            return True
        return len(title.split()) >= 2

    async def _is_concrete_person(
        self,
        session: aiohttp.ClientSession,
        page_title: str,
        *,
        skip_region: bool = False,
    ) -> bool:
        page_title = page_title.strip()
        if not page_title or self._is_archetype_title(page_title):
            return False

        categories = await self.fetch_page_categories(session, page_title)
        if self._is_excluded_person_by_categories(categories):
            logger.info("Wikiquote: «%s» — политик, пропуск", page_title)
            return False

        if not skip_region:
            region = region_verdict_from_categories(categories)
            if region is False:
                logger.info("Wikiquote: «%s» — регион не подходит, пропуск", page_title)
                return False

        return self._is_concrete_person_by_categories(
            categories,
            title=page_title,
        )

    async def _pick_random_person(
        self,
        session: aiohttp.ClientSession,
        exclude_people: set[str],
    ) -> str | None:
        people = await self.fetch_category_people(session)
        pool = [
            person
            for person in people
            if person.strip().lower() not in exclude_people
            and not self._is_archetype_title(person)
        ]
        if pool:
            return random.choice(pool)

        fallback = [
            person
            for person in self._FALLBACK_PEOPLE
            if person.strip().lower() not in exclude_people
        ]
        if fallback:
            logger.info("Wikiquote: используем резервный список авторов")
            return random.choice(fallback)
        return None

    async def _fetch_page_quotes(
        self,
        session: aiohttp.ClientSession,
        title: str,
        *,
        _depth: int = 0,
    ) -> tuple[str, list[ExtractedQuote]] | None:
        title = title.strip()
        if not title or _depth > 2:
            return None

        data = await self._get_json(
            session,
            {
                "action": "parse",
                "page": title,
                "format": "json",
                "prop": "text|links",
            },
        )
        if not data or "parse" not in data:
            return None

        parse = data["parse"]
        page_title = (parse.get("title") or title).strip()
        html = (parse.get("text") or {}).get("*") or ""

        if "redirectMsg" in html:
            redirect = self._redirect_target(parse.get("links") or [])
            if redirect and redirect != page_title:
                logger.info("Wikiquote redirect: %s → %s", page_title, redirect)
                return await self._fetch_page_quotes(
                    session, redirect, _depth=_depth + 1
                )

        quotes = self._extract_quotes(html, page_title=page_title)
        if not quotes:
            logger.info("Wikiquote: у «%s» нет подходящих цитат", page_title)
            return None
        return page_title, quotes

    async def fetch_person_quote(
        self,
        session: aiohttp.ClientSession,
        person: str,
        *,
        exclude_quote_keys: set[str] | None = None,
        for_manual_request: bool = False,
    ) -> WikiquoteQuote | None:
        person = person.strip()
        if not person:
            return None

        page_title = await self.resolve_person_title(session, person)
        if not page_title:
            logger.info("Wikiquote: автор «%s» не найден", person)
            return None
        if person_is_foreign_agent(person) or person_is_foreign_agent(page_title):
            logger.info("Wikiquote: «%s» — иноагент", person or page_title)
            return None

        parsed = await self._fetch_page_quotes(session, page_title)
        if not parsed:
            return None

        page_title, quotes = parsed
        if not await self._is_concrete_person(
            session,
            page_title,
            skip_region=for_manual_request,
        ):
            logger.info("Wikiquote: «%s» — не конкретная личность, пропуск", page_title)
            return None

        exclude = exclude_quote_keys or set()
        pool = self._filter_raw_quotes(page_title, quotes, exclude)
        if not pool:
            logger.info(
                "Wikiquote: у «%s» нет цитат (только подписи/источники)",
                page_title,
            )
            return None

        chosen = random.choice(pool)
        person_label = self.format_person_label(
            page_title,
            work_title=chosen.work_title,
        )
        image_url = await self.fetch_page_image(session, page_title)
        return WikiquoteQuote(
            person=person_label,
            quote=chosen.text,
            image_url=image_url,
        )

    async def fetch_random_quote(
        self,
        session: aiohttp.ClientSession,
        *,
        forced_person: str | None = None,
        exclude_people: set[str] | None = None,
        exclude_quote_keys: set[str] | None = None,
    ) -> WikiquoteQuote | None:
        if forced_person:
            return await self.fetch_person_quote(
                session,
                forced_person,
                exclude_quote_keys=exclude_quote_keys,
            )

        exclude_people_set = {
            name.strip().lower() for name in (exclude_people or set()) if name.strip()
        }
        exclude_keys = exclude_quote_keys or set()
        retries = max(1, Config.WIKIQUOTE_RANDOM_RETRIES)

        for attempt in range(retries):
            person = await self._pick_random_person(session, exclude_people_set)
            if not person:
                break
            item = await self.fetch_person_quote(
                session,
                person,
                exclude_quote_keys=exclude_keys,
            )
            if item:
                return item
            logger.debug(
                "Wikiquote: попытка %s/%s — «%s» без подходящей цитаты",
                attempt + 1,
                retries,
                person,
            )
        return None

    async def fetch_page_image(
        self,
        session: aiohttp.ClientSession,
        title: str,
    ) -> str | None:
        title = title.strip()
        if not title:
            return None

        for source, base in (
            ("wikipedia", self._wikipedia_base),
            ("wikiquote", self._base),
        ):
            url = await self._query_thumbnail(session, title, base=base)
            if url:
                logger.info("Фото «%s» из %s", title, source)
                return url
        logger.debug("Фото для «%s» не найдено", title)
        return None

    async def _query_thumbnail(
        self,
        session: aiohttp.ClientSession,
        title: str,
        *,
        base: str,
    ) -> str | None:
        data = await self._get_json(
            session,
            {
                "action": "query",
                "titles": title,
                "prop": "pageimages",
                "format": "json",
                "redirects": 1,
                "pithumbsize": Config.WIKIQUOTE_IMAGE_THUMB_SIZE,
                "pilicense": "any",
            },
            base=base,
        )
        if not data:
            return None

        pages = data.get("query", {}).get("pages") or {}
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            if int(page.get("pageid", -1)) < 0:
                continue
            thumb = page.get("thumbnail") or {}
            source = (thumb.get("source") or "").strip()
            if source.startswith("https://"):
                return source
        return None

    @classmethod
    def _redirect_target(cls, links: list) -> str | None:
        for link in links:
            if not isinstance(link, dict):
                continue
            if link.get("ns") != 0:
                continue
            target = (link.get("*") or "").strip()
            if target:
                return target
        return None

    @classmethod
    def _strip_html(cls, fragment: str) -> str:
        text = re.sub(r"<br\s*/?>", " ", fragment, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def _strip_reference_sections(cls, html: str) -> str:
        html = cls._REFERENCE_WRAP_RE.sub("", html)
        html = cls._REFERENCE_BLOCK_RE.sub("", html)
        return html

    @classmethod
    def _letter_count(cls, text: str) -> int:
        return len(re.sub(r"[^a-zA-Zа-яёА-ЯЁ]", "", text))

    @classmethod
    def _clean_quote_text(cls, text: str) -> str:
        text = cls._FOOTNOTE_MARKER_RE.sub("", text)
        text = cls._WIKI_OMISSION_RE.sub(" ", text)
        text = re.sub(r"\(там же\)", "", text, flags=re.IGNORECASE)
        text = re.sub(r"[\u200b-\u200d\ufeff]", "", text)
        text = re.sub(r"\s+", " ", text).strip(" .—-")
        return text.strip()

    @classmethod
    def _trim_quote_length(cls, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        cut = text[:max_chars]
        for sep in (". ", "! ", "? ", "… ", "; "):
            idx = cut.rfind(sep)
            if idx >= int(max_chars * 0.45):
                return cut[: idx + 1].strip()
        cut = cut.strip()
        while len(cut) > 40:
            if re.search(r"[.!?…]$", cut):
                break
            if re.search(r"\b\d{1,4}$", cut) or re.search(
                r"\b(?:в|на|по|при|до|после|телефону|"
                r"январ[ея]|феврал[ея]|март[ае]?|апрел[ея]|ма[йя]|"
                r"июн[ея]|июл[ея]|август[ае]?|сентябр[ея]|"
                r"октябр[ея]|ноябр[ея]|декабр[ея])\s+\w*$",
                cut,
                re.I,
            ):
                cut = re.sub(r"\s+\S+$", "", cut).strip()
                continue
            break
        idx = cut.rfind(", ")
        if idx >= int(max_chars * 0.5) and not re.search(r"[.!?…]$", cut):
            cut = cut[:idx].strip()
        if len(cut) < 40:
            return ""
        return cut.rstrip("—-,:; ") + "…"

    @classmethod
    def _strip_quote_for_speech(cls, text: str) -> str:
        text = cls._strip_trailing_source_marks(text)
        text = text.replace("«", "").replace("»", "").strip()
        text = re.sub(r"\s*—+\s*$", "", text).strip()
        return text

    @classmethod
    def _strip_trailing_source_marks(cls, text: str) -> str:
        text = cls._clean_quote_text(text)
        text = re.sub(r"[»«]+\s*$", "", text).strip()
        text = re.sub(r"^[«»]+\s*", "", text).strip()
        while True:
            text = re.sub(r"\s*—+\s*$", "", text).strip()
            if " — " not in text:
                break
            body, tail = text.rsplit(" — ", 1)
            body = body.strip()
            tail = tail.strip().strip("«».")
            if body and (
                cls._looks_like_source_tail(tail)
                or cls._CHAPTER_TAIL_RE.match(tail.lower())
                or cls._looks_like_attribution_name(tail)
            ):
                text = body
                continue
            break
        return cls._clean_quote_text(text)

    @classmethod
    def _finalize_quote_text(cls, text: str) -> str:
        text = cls._clean_quote_text(text)
        if not text:
            return ""
        text = re.sub(r"^…\s+", "", text)
        text = re.sub(r"\s+…\s+", " ", text)
        text = cls._strip_trailing_source_marks(text)
        while cls._PAGE_REF_TAIL_RE.search(text):
            text = cls._PAGE_REF_TAIL_RE.sub("", text).strip()
        text = text.replace("«", "").replace("»", "").strip()
        if cls._DATE_PHRASE_RE.match(text.strip()):
            return ""
        return cls._clean_quote_text(text)

    @classmethod
    def _looks_like_inline_attribution(cls, text: str) -> bool:
        text = text.strip().strip("«»\"'.")
        if not text:
            return True
        if cls._looks_like_source_tail(text):
            return True
        if cls._looks_like_attribution_name(text):
            return True
        words = text.split()
        if 2 <= len(words) <= 6 and len(text) < 100:
            caps = sum(1 for word in words if word and word[0].isupper())
            if caps >= len(words) - 1:
                lowered = f" {text.lower()} "
                verbs = (
                    " что ", " не ", " и ", " в ", " на ", " я ", " мы ",
                    " он ", " она ", " быть ", " если ", " когда ",
                )
                if not any(marker in lowered for marker in verbs):
                    return True
        return False

    @classmethod
    def _looks_like_source_tail(cls, text: str) -> bool:
        """Хвост после тире: «о задачах сюрреалистического движения», «Надя» и т.п."""
        text = text.strip().strip("«»\"'.")
        if not text:
            return True

        lowered = text.lower()
        if cls._DATE_PHRASE_RE.match(lowered):
            return True
        if cls._ATTRIBUTION_CONTEXT_RE.match(lowered):
            return True
        if cls._BIBLIOGRAPHY_RE.search(text):
            return True
        if cls._DATE_IN_TEXT_RE.search(text) and len(text) < 80:
            return True
        if len(text) < 60 and lowered.startswith(("из ", "в ", "к ", "при ")):
            return True
        if re.fullmatch(r"«[^»]{1,80}»(?:\s*,\s*\d{4})?", text):
            return True
        if cls._looks_like_byline_attribution(text):
            return True
        if cls._CHAPTER_TAIL_RE.match(lowered):
            return True
        if cls._ENCYCLOPEDIA_TAIL_RE.search(lowered):
            return True
        if re.search(r"^(?:заявлени|комментари|реплик)", lowered):
            return True
        if len(text) > 50 and not re.search(r"[.!?…]", text):
            if re.search(
                r"традици|молитва|известн|употребл|литературн|православн",
                lowered,
            ):
                return True
        return False

    @classmethod
    def _looks_like_prayer_quote(cls, text: str) -> bool:
        lowered = text.strip().lower()
        if not lowered:
            return False
        if not cls._PRAYER_QUOTE_RE.search(lowered):
            return False
        return "аминь" in lowered or "господи" in lowered or "владыко" in lowered

    @classmethod
    def _looks_like_narrative_excerpt(cls, text: str) -> bool:
        lowered = text.lower()
        if lowered.count(" — ") >= 3:
            return True
        if re.search(r"\bговорил[а]?\s+\w+", lowered):
            return True
        if re.search(r"\bсказал[а]?\s+\w+", lowered) and lowered.count(" — ") >= 2:
            return True
        return False

    @classmethod
    def _normalize_quote_candidate(cls, raw: str) -> str:
        text = cls._clean_quote_text(cls._strip_html(raw))
        if not text:
            return ""

        text = re.sub(r"^—\s*", "", text).strip()

        guillemets = re.findall(r"«([^»]+)»", text)
        if guillemets and len(guillemets) == 1:
            inner = guillemets[0].strip()
            outer = re.sub(r"«[^»]+»", "", text).strip(" .—-")
            if outer and cls._looks_like_source_tail(inner) and len(outer) >= 15:
                text = outer
            elif not outer and not cls._looks_like_source_tail(inner):
                text = inner
            elif outer and len(outer) >= len(inner):
                text = outer
            else:
                text = max(guillemets, key=len).strip()

        if " — " in text:
            body, tail = text.rsplit(" — ", 1)
            body = body.strip().strip("«»")
            tail = tail.strip().strip("«».")
            if body and tail:
                if cls._looks_like_inline_attribution(tail) and len(body) >= 10:
                    text = body
                elif cls._looks_like_inline_attribution(body) and len(tail) >= 20:
                    text = tail

        return cls._finalize_quote_text(text)

    @classmethod
    def _section_title_plain(cls, header_inner_html: str) -> str:
        title = cls._strip_html(header_inner_html).strip()
        return re.sub(r"\s*\[.*$", "", title).strip()

    @classmethod
    def _is_about_person_section(cls, title: str) -> bool:
        plain = re.sub(r"\s+", " ", title.strip().lower())
        return bool(cls._ABOUT_PERSON_SECTION_RE.search(plain))

    @classmethod
    def _is_own_quotes_section(cls, title: str) -> bool:
        plain = re.sub(r"\s+", " ", title.strip().lower())
        if cls._is_about_person_section(plain):
            return False
        return bool(cls._OWN_QUOTES_SECTION_RE.match(plain))

    @classmethod
    def _split_wiki_sections(cls, html: str) -> list[tuple[str, str]]:
        matches = list(cls._QUOTES_SECTION_HEADER_RE.finditer(html))
        sections: list[tuple[str, str]] = []
        for idx, match in enumerate(matches):
            title = cls._section_title_plain(match.group(1))
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(html)
            sections.append((title, html[start:end]))
        return sections

    @classmethod
    def _split_nested_sections(cls, html: str) -> list[tuple[str, str]]:
        matches = list(cls._NESTED_SECTION_HEADER_RE.finditer(html))
        if not matches:
            return []
        sections: list[tuple[str, str]] = []
        if matches[0].start() > 0:
            preamble = html[: matches[0].start()].strip()
            if preamble:
                sections.append(("", preamble))
        for idx, match in enumerate(matches):
            title = cls._section_title_plain(match.group(1))
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(html)
            sections.append((title, html[start:end]))
        return sections

    @classmethod
    def _collect_from_own_quotes_body(
        cls,
        html: str,
        *,
        page_title: str,
    ) -> list[ExtractedQuote]:
        results: list[ExtractedQuote] = []
        for title, body in cls._split_nested_sections(html):
            if title and cls._SKIP_SUBSECTION_RE.match(title.strip().lower()):
                continue
            work_title = title.strip() if title and cls._YEAR_SUBSECTION_RE.match(title) else None
            results.extend(
                cls._collect_quotes_from_fragment(
                    body,
                    page_title=page_title,
                    work_title=work_title,
                )
            )
        if not results:
            results.extend(
                cls._collect_quotes_from_fragment(
                    html,
                    page_title=page_title,
                    work_title=None,
                )
            )
        return results

    @classmethod
    def _collect_from_book_quotes_body(
        cls,
        html: str,
        *,
        page_title: str,
    ) -> list[ExtractedQuote]:
        results: list[ExtractedQuote] = []
        nested = cls._split_nested_sections(html)
        if not nested:
            return cls._collect_quotes_from_fragment(
                html,
                page_title=page_title,
                work_title=None,
            )
        for title, body in nested:
            if not title:
                continue
            work = cls._normalize_work_title(title)
            if (
                not work
                or cls._is_about_person_section(work)
                or cls._SKIP_SUBSECTION_RE.match(work)
            ):
                continue
            results.extend(
                cls._collect_quotes_from_fragment(
                    body,
                    page_title=page_title,
                    work_title=work,
                )
            )
        return results

    @classmethod
    def _looks_like_byline_attribution(cls, text: str) -> bool:
        text = text.strip().strip("«»\"'")
        if not text:
            return True
        if cls._BYLINE_ATTRIBUTION_RE.match(text):
            return True
        lowered = text.lower()
        if re.search(
            r"корреспондент|журналист|редактор|обозреватель|публицист",
            lowered,
        ):
            if re.search(r"\d{4}", text) and len(text) < 120:
                return True
        return False

    @classmethod
    def _strip_maintenance_blocks(cls, html: str) -> str:
        for pattern in cls._MAINTENANCE_BLOCK_RES:
            html = pattern.sub("", html)
        return html

    @classmethod
    def _focus_quotes_section(cls, html: str) -> str:
        for title, body in cls._split_wiki_sections(html):
            if cls._is_own_quotes_section(title):
                logger.debug("Wikiquote: раздел собственных цитат «%s»", title)
                return body

        logger.debug("Wikiquote: на странице нет раздела собственных цитат")
        return ""

    @classmethod
    def _looks_like_bio_about_person(cls, text: str, page_title: str = "") -> bool:
        if cls._BIOGRAPHY_ABOUT_RE.search(text):
            return True

        lowered = text.lower()
        encyclopedic = (
            "считается",
            "является",
            "родился",
            "родилась",
            "умер",
            "умерла",
            "известен",
            "известна",
            "классиком",
            "выдающимся",
            "творчество",
            "оказало влияние",
            "оказал влияние",
            "на родине",
        )
        if not any(marker in lowered for marker in encyclopedic):
            return False

        if page_title:
            name = page_title.strip().lower()
            if name and lowered.startswith(name):
                return True
            parts = [part for part in name.split() if len(part) >= 4]
            if parts and lowered.startswith(parts[0]):
                return True

        if len(text) > 80 and any(
            pronoun in f" {lowered} "
            for pronoun in (" он ", " она ", " его ", " её ", " ему ", " ей ")
        ):
            if " я " not in f" {lowered} " and " мы " not in f" {lowered} ":
                return True

        return False

    @classmethod
    def _looks_like_attribution_name(cls, text: str) -> bool:
        """Отсекает подписи вида «Афифуддин аль-Яфи'и аль-Ямани» без текста цитаты."""
        text = text.strip()
        if len(text) < 12 or len(text) > 90:
            return False
        if re.search(r"[«»\"!?.;:()]", text):
            return False
        if re.search(r"\d{3,4}", text):
            return False

        words = text.split()
        if len(words) < 2 or len(words) > 7:
            return False

        lowered = f" {text.lower()} "
        sentence_markers = (
            " что ", " как ", " это ", " не ", " и ", " в ", " на ", " о ",
            " я ", " мы ", " вы ", " он ", " она ", " быть ", " если ",
            " когда ", " где ", " который ", " которая ", " потому ", " также ",
        )
        if any(marker in lowered for marker in sentence_markers):
            return False

        name_like = 0
        for word in words:
            if cls._NAME_TOKEN_RE.match(word):
                if word[0].isupper() or word.lower().startswith(("аль-", "ибн-")):
                    name_like += 1
        return name_like >= len(words) - 1

    @classmethod
    def _looks_like_source_label(cls, text: str) -> bool:
        """Подписи к источнику: «речь в ВИРе, 15 марта 1939» и т.п."""
        text = text.strip().strip("«»\"'")
        if not text:
            return True

        lowered = text.lower()
        if cls._SOURCE_LABEL_RE.search(lowered):
            return True
        if cls._ATTRIBUTION_CONTEXT_RE.match(lowered.strip().lstrip("— ")):
            return True

        source_words = (
            "речь",
            "выступление",
            "доклад",
            "интервью",
            "заявление",
            "комментарий",
            "письмо",
            "статья",
            "записка",
            "предисловие",
            "послание",
            "обращение",
            "вступительное слово",
            "заключительное слово",
            "фрагмент",
            "отрывок",
            "годовщина",
            "съезд",
            "конференц",
            "собрание",
            "заседание",
        )
        has_source_word = any(word in lowered for word in source_words)
        has_date = bool(cls._DATE_IN_TEXT_RE.search(text))

        if has_source_word and has_date and len(text) < 120:
            return True
        if has_source_word and len(text) < 55:
            return True
        if has_date and len(text) < 45 and not re.search(r"[!?…]", text):
            return True

        return False

    @classmethod
    def _has_quote_substance(cls, text: str) -> bool:
        """Есть ли в тексте содержание цитаты, а не только метаданные."""
        if cls._looks_like_source_label(text):
            return False
        if cls._looks_like_attribution_name(text):
            return False
        if cls._looks_like_source_tail(text):
            return False
        if cls._looks_like_byline_attribution(text):
            return False

        if cls._letter_count(text) < 20:
            return False

        stripped = re.sub(r"[«»\"'….\s\-—]+", "", text)
        if len(stripped) < 12:
            return False

        lowered = text.lower().strip()
        if lowered.startswith(("о ", "об ", "при ", "из ", "в ", "к ")) and len(text) < 80:
            return False
        if re.search(r"[!?]", text):
            return True

        words = [word for word in re.split(r"\s+", text.strip()) if word]
        if len(words) >= 8:
            return True

        verb_markers = (
            " что ", " как ", " это ", " не ", " я ", " мы ", " вы ",
            " он ", " она ", " они ", " быть ", " если ", " когда ",
            " где ", " который ", " которая ", " потому ", " также ",
            " нужно ", " можно ", " должен ", " должна ", " будет ",
            " было ", " были ", " есть ", " нет ", " всегда ", " никогда ",
        )
        padded = f" {lowered} "
        if any(marker in padded for marker in verb_markers):
            return True

        return len(text) >= 45 and len(words) >= 5

    @classmethod
    def _is_skippable(cls, text: str, *, page_title: str = "") -> bool:
        lowered = text.lower().strip()
        if quote_contains_forbidden_content(text):
            return True
        if len(text) < 20:
            return True
        if lowered.startswith("↑") or "↑" in text[:12]:
            return True
        if lowered.startswith("см.") or lowered.startswith("см "):
            return True
        if cls._BIBLIOGRAPHY_RE.search(text):
            return True
        if cls._LEAD_DEFINITION_RE.match(text):
            return True
        if cls._looks_like_bio_about_person(text, page_title):
            return True
        if cls._WIKI_STUB_RE.search(text):
            return True
        if cls._BIO_DATE_RE.search(text) and len(text) > 180:
            return True
        if len(text) > 260 and any(
            word in lowered
            for word in (
                "родился",
                "родилась",
                "умер",
                "умерла",
                "великий русский",
                "британский государственный",
                "премьер-министр",
                "деятель",
                "писатель",
                "поэт",
            )
        ):
            return True
        if re.match(r"^[\w«»\s\-]+ — (?:старая|старый|город|фильм|книга)\b", lowered):
            return True
        if any(marker in lowered for marker in cls._SKIP_MARKERS):
            return True
        if cls._looks_like_attribution_name(text):
            return True
        if cls._looks_like_source_label(text):
            return True
        if cls._looks_like_source_tail(text):
            return True
        if cls._looks_like_byline_attribution(text):
            return True
        if cls._looks_like_narrative_excerpt(text):
            return True
        if cls._looks_like_prayer_quote(text):
            return True
        return False

    @classmethod
    def _collect_normalized_candidates(cls, html: str) -> list[str]:
        candidates: list[str] = []
        patterns = (
            r"<li[^>]*>(.*?)</li>",
            r"<dd[^>]*>(.*?)</dd>",
            r"<p[^>]*>(.*?)</p>",
            r"<blockquote[^>]*>(.*?)</blockquote>",
            r"<td[^>]*>(.*?)</td>",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, html, flags=re.IGNORECASE | re.DOTALL):
                text = cls._normalize_quote_candidate(match.group(1))
                if text:
                    candidates.append(text)
        return candidates

    @classmethod
    def _is_book_quotes_section(cls, title: str) -> bool:
        plain = re.sub(r"\s+", " ", title.strip().lower())
        return bool(cls._BOOK_QUOTES_SECTION_RE.match(plain))

    @classmethod
    def _collect_quotes_from_fragment(
        cls,
        html: str,
        *,
        page_title: str,
        work_title: str | None,
    ) -> list[ExtractedQuote]:
        items: list[ExtractedQuote] = []
        seen: set[str] = set()
        for text in cls._collect_normalized_candidates(html):
            key = text.strip().lower()[:400]
            if key in seen:
                continue
            seen.add(key)
            if cls._is_skippable(text, page_title=page_title):
                continue
            items.append(ExtractedQuote(text, work_title=work_title))
        return items

    @classmethod
    def _extract_quotes(cls, html: str, *, page_title: str = "") -> list[ExtractedQuote]:
        if not html.strip():
            return []

        html = cls._strip_reference_sections(html)
        html = cls._strip_maintenance_blocks(html)

        sections = cls._split_wiki_sections(html)
        results: list[ExtractedQuote] = []

        for title, body in sections:
            if cls._is_about_person_section(title):
                continue
            if cls._is_own_quotes_section(title):
                results.extend(
                    cls._collect_from_own_quotes_body(body, page_title=page_title)
                )
                continue
            if cls._is_book_quotes_section(title):
                results.extend(
                    cls._collect_from_book_quotes_body(body, page_title=page_title)
                )

        if not results:
            focused = cls._focus_quotes_section(html)
            if focused.strip():
                results.extend(
                    cls._collect_from_own_quotes_body(focused, page_title=page_title)
                )

        seen: set[str] = set()
        quotes: list[ExtractedQuote] = []
        for item in results:
            key = item.text.lower()
            if key in seen:
                continue
            seen.add(key)
            quotes.append(item)
        return quotes
