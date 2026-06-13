from __future__ import annotations

import re
from collections import defaultdict

from podcast_generator.foreign_agents_data import FOREIGN_AGENT_NAMES

_SURNAME_RE = re.compile(r"^[а-яa-z\-]+$", re.UNICODE)


def normalize_person_name(name: str) -> str:
    text = (name or "").strip().lower().replace("ё", "е")
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"[^\w\s\-]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _build_indexes() -> tuple[
    frozenset[str],
    dict[str, list[str]],
    frozenset[str],
]:
    full_names: set[str] = set()
    by_surname: dict[str, list[str]] = defaultdict(list)

    for raw in FOREIGN_AGENT_NAMES:
        norm = normalize_person_name(raw)
        if not norm:
            continue
        full_names.add(norm)
        tokens = norm.split()
        if not tokens:
            continue
        surname = tokens[0]
        by_surname[surname].append(norm)

    distinctive = {
        surname
        for surname, entries in by_surname.items()
        if len(entries) == 1 or len(surname) >= 8
    }
    return frozenset(full_names), dict(by_surname), frozenset(distinctive)


_FULL_NAMES, _BY_SURNAME, _DISTINCTIVE_SURNAMES = _build_indexes()


def person_is_foreign_agent(name: str) -> bool:
    norm = normalize_person_name(name)
    if not norm:
        return False
    if norm in _FULL_NAMES:
        return True

    tokens = [token for token in norm.split() if _SURNAME_RE.match(token)]
    if not tokens:
        return False

    if len(tokens) == 1:
        surname = tokens[0]
        return surname in _BY_SURNAME and surname in _DISTINCTIVE_SURNAMES

    for surname in tokens:
        entries = _BY_SURNAME.get(surname)
        if not entries:
            continue
        for entry in entries:
            entry_tokens = entry.split()
            if len(entry_tokens) < 2:
                continue
            given = entry_tokens[1]
            if given in tokens:
                return True
    return False
