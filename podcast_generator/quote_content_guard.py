from __future__ import annotations

import re

_FORBIDDEN_QUOTE_RE = re.compile(
    r"(?:"
    r"путин\w*|"
    r"украин\w*|"
    r"\bвойн\w*|"
    r"донбас\w*|донецк|луганск|"
    r"крым\w*|севастопол|"
    r"санкци\w*|"
    r"сепаратист\w*|"
    r"спецоперац\w*|"
    r"мобилизац\w*|"
    r"зеленск\w*|"
    r"навальн\w*|"
    r"лукашенко|"
    r"меркел\w*|"
    r"байден|трамп|"
    r"\bнато\b|nato|"
    r"кремл\w*|"
    r"оккупац\w*|"
    r"аннекси\w*|"
    r"обстрел\w*|"
    r"артиллери\w*|"
    r"фронт\w*|"
    r"геноцид|"
    r"бахмут|мариупол\w*|херсон|запорож\w*|"
    r"референдум\w*|"
    r"госпереворот|государственн\w+\s+переворот|"
    r"депутат\w*\s+госдум|госдум\w*|"
    r"министр\w*\s+обороны|"
    r"президент\w*\s+росси|"
    r"премьер[\s-]?министр\s+росси"
    r")",
    re.IGNORECASE | re.UNICODE,
)

_WAR_AND_PEACE_RE = re.compile(r"войн[аы]\s+и\s+мир", re.IGNORECASE | re.UNICODE)


def quote_contains_forbidden_content(text: str) -> bool:
    if not text or not text.strip():
        return False
    lowered = text.lower()
    if _WAR_AND_PEACE_RE.search(lowered):
        return False
    return bool(_FORBIDDEN_QUOTE_RE.search(text))
