from __future__ import annotations

import re

_REJECT_VERDICT_RE = re.compile(
    r"^(?:да|yes|отклонить|reject|запретить|block|discard)\b",
    re.IGNORECASE,
)
_ALLOW_VERDICT_RE = re.compile(
    r"^(?:нет|no|разрешить|allow|можно|ok|пропустить)\b",
    re.IGNORECASE,
)

_EXCLUDED_REGION_CATEGORY_MARKERS = (
    "категория:африкан",
    "латиноамерикан",
    "южноамерикан",
    "категория:араб",
    "ближневосточ",
    "австралий",
    "новозеландск",
    "категория:океани",
    "персид",
    "исламск",
    "мусульман",
    "богослов",
    "суфий",
    "суннит",
    "шиит",
)

_ALLOWED_REGION_CATEGORY_MARKERS = (
    "русск",
    "росси",
    "советск",
    "американ",
    ":сша",
    "украин",
    "белорус",
    "молдаван",
    "немец",
    "француз",
    "англи",
    "британ",
    "италь",
    "испан",
    "поль",
    "чеш",
    "швед",
    "норвеж",
    "финск",
    "греческ",
    "португаль",
    "австрий",
    "швейцар",
    "ирланд",
    "венгер",
    "румын",
    "болгар",
    "серб",
    "хорват",
    "словак",
    "словен",
    "эстон",
    "латвий",
    "литов",
    "датск",
    "исланд",
    "бельгий",
    "нидерланд",
    "голланд",
    "люксембург",
    "европей",
    "китай",
    "япон",
    "корей",
    "индий",
    "тайск",
    "вьетнам",
    "монгол",
    "тибет",
    "узбек",
    "казах",
    "таджик",
    "киргиз",
    "туркмен",
    "грузин",
    "армян",
    "азербайджан",
    "индонез",
    "малайз",
    "филиппин",
    "пакистан",
    "бенгаль",
    "непаль",
    "сингапур",
    "камбодж",
    "лаос",
    "бирман",
    "шри-ланк",
)


def region_verdict_from_categories(categories: list[str]) -> bool | None:
    """
    True — регион подходит.
    False — регион не подходит.
    None — по категориям неясно.
    """
    lowered = [category.lower() for category in categories]
    if any(
        marker in category
        for category in lowered
        for marker in _EXCLUDED_REGION_CATEGORY_MARKERS
    ):
        return False
    if any(
        marker in category
        for category in lowered
        for marker in _ALLOWED_REGION_CATEGORY_MARKERS
    ):
        return True
    return None


def parse_person_eligibility_verdict(raw: str | None) -> bool | None:
    """
    Разбирает ответ LLM.

    True — персону можно использовать.
    False — цитату нужно отбросить.
    None — ответ непонятен.
    """
    text = (raw or "").strip()
    if not text:
        return None

    first_token = text.split(maxsplit=1)[0]
    if _REJECT_VERDICT_RE.match(first_token) or _REJECT_VERDICT_RE.match(text):
        return False
    if _ALLOW_VERDICT_RE.match(first_token) or _ALLOW_VERDICT_RE.match(text):
        return True
    return None


def person_is_allowed(raw_verdict: str | None, *, fail_closed: bool = True) -> bool:
    parsed = parse_person_eligibility_verdict(raw_verdict)
    if parsed is None:
        return not fail_closed
    return parsed
