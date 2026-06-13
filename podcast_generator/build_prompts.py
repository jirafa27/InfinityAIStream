from core.config import Config
from podcast_generator.wikiquote_client import WikiquoteQuote, WikiquoteClient
from podcast_generator.quote_selection import WikiquoteQuoteCandidate


class PromptsBuilder:
    """Класс для построения промптов."""

    def build_prompt_for_wikiquote_commentary(self, item: WikiquoteQuote) -> str:
        quote_line = WikiquoteClient.format_quote_for_prompt(item)
        max_chars = Config.WIKIQUOTE_COMMENTARY_MAX_CHARS
        return (
            "Ты ведёшь стрим с цитатами известных людей.\n"
            f"Сейчас звучит одна цитата:\n{quote_line}\n\n"
            "Прокомментируй именно эту цитату — остроумно, в духе философского стендапа.\n"
            "Один острый угол: поспорь, подколи или сделай неожиданный вывод.\n"
            "Не уходи в другие темы и не придумывай другие цитаты.\n\n"
            "Начинай сразу с сути — без приветствий и вступлений. "
            "Запрещено: «привет», «друзья», «добрый день/вечер», «сегодня поговорим», "
            "«давайте начнём», обращения к аудитории в начале.\n\n"
            f"350–{max_chars} символов, строго не больше {max_chars}. "
            "Коротко и ёмко — 2–4 предложения. "
            "Один связный текст, без списков. "
            "Без markdown. Только текст комментария."
        )

    def build_prompt_for_manual_quote_selection(
        self,
        request: str,
        candidates: list[WikiquoteQuoteCandidate],
    ) -> str:
        lines: list[str] = []
        for index, candidate in enumerate(candidates, start=1):
            quote = candidate.quote.replace("\n", " ").strip()
            if len(quote) > 360:
                quote = quote[:357] + "..."
            label = WikiquoteClient.format_person_label(
                candidate.page_title,
                work_title=candidate.work_title,
                requested_author=request,
            )
            lines.append(f'{index}. [{label}] «{quote}»')

        options = "\n".join(lines)
        return (
            f"Зритель запросил автора или тему: «{request}».\n"
            "Ниже — реальные цитаты с ru.wikiquote.org с разных страниц.\n"
            "Выбери ОДНУ цитату, которая лучше всего соответствует запросу.\n"
            "Нельзя придумывать, сокращать или перефразировать цитату.\n\n"
            f"{options}\n\n"
            "Ответь ТОЛЬКО JSON без markdown и пояснений:\n"
            '{"index": N}\n'
            "где N — номер из списка."
        )

    def build_prompt_for_person_eligibility(
        self,
        person: str,
        *,
        manual_request: bool = False,
    ) -> str:
        region_rule = ""
        if not manual_request:
            region_rule = (
                "- НЕ из разрешённых регионов: только русские, американцы, европейцы "
                "или азиаты (отбрось африканцев, латиноамериканцев, арабов Ближнего Востока, "
                "исламских богословов, австралийцев и прочих).\n\n"
                "НЕ отбрасывай: писателей, поэтов, философов, учёных, художников, "
                "музыкантов, актёров, спортсменов, бизнесменов без политического статуса, "
                "если они русские, американские, европейские или азиаты.\n\n"
            )
        else:
            region_rule = (
                "Регион и происхождение НЕ проверяй — автора выбрали вручную через чат.\n\n"
                "НЕ отбрасывай только из-за религии, эпохи или исламского/восточного происхождения.\n\n"
            )

        return (
            f"Персона: «{person}».\n\n"
            "Нужно ли ОТБРОСИТЬ её цитату для публичного эфира в РФ, если человек:\n"
            "- действующий или бывший глава государства, монарх, правитель;\n"
            "- политик, депутат, министр, губернатор, мэр, дипломат высокого уровня;\n"
            "- военный или партийный лидер с политическим статусом;\n"
            "- политический журналист, пропагандист, военкор о текущих конфликтах;\n"
            "- экстремист или террорист по законам РФ "
            "(реестр экстремистских материалов/организаций, запрещённые движения);\n"
            "- однозначно известен преимущественно как политическая фигура;\n"
            f"{region_rule}"
            "Политику в тексте цитаты отсекают отдельно — здесь оценивай только персону.\n\n"
            "Ответь одним словом без пояснений:\n"
            "ДА — отбросить\n"
            "НЕТ — можно использовать"
        )

    def build_prompt_for_person_eligibility_manual(self, person: str) -> str:
        return self.build_prompt_for_person_eligibility(person, manual_request=True)

    def build_prompt_for_comment(self, current_person, content, author):
        return (
            f"Сейчас в эфире цитата автора «{current_person}». "
            f"В чате написали: «{content}» от пользователя {author}.\n\n"
            f"Ответь коротко, остро и с юмором — 1–2 предложения, максимум 180 символов. "
            f"Обратись по нику ({author}). Без пересказа всей фразы зрителя.\n\n"
            f"Если оскорбление — короткий жёсткий подкол.\n\n"
            f"Только текст ответа, без markdown."
        )
