"""Одноразовый генератор списка иноагентов из дампа Wikipedia."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(
    r"C:\Users\jirafa\.cursor\projects\c-Users-jirafa-Desktop-InfinityAIStream"
    r"\agent-tools\df00aeb1-adf5-4dc4-8521-afe012b39469.txt"
)
OUT = ROOT / "podcast_generator" / "foreign_agents_data.py"

SKIP_MARKERS = (
    "Общество",
    "организа",
    "Медиапроект",
    "Проект",
    "Независим",
    "интернет",
    "Телеканал",
    "премия",
)


def normalize(name: str) -> str:
    name = name.lower().replace("ё", "е")
    name = re.sub(r"\([^)]*\)", "", name)
    name = re.sub(r"[^\w\s\-]", " ", name, flags=re.UNICODE)
    return re.sub(r"\s+", " ", name).strip()


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    names: set[str] = set()
    for match in re.finditer(
        r"\|\s*\d+\s*\|\s*"
        r"([А-ЯЁ][а-яё]+(?:\s*\([^)]+\))?\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)\s*\|",
        text,
    ):
        raw = re.sub(r"\s+", " ", match.group(1).strip())
        if any(marker.lower() in raw.lower() for marker in SKIP_MARKERS):
            continue
        names.add(normalize(raw))

    # Дополнительно известные фигуры, часто запрашиваемые в эфире.
    names.update(
        {
            "навальный алексей анатольевич",
            "навальная юлия абрамовна",
        }
    )

    ordered = sorted(names)
    lines = [
        '"""Список ФИО из публичного реестра иноагентов (обновляйте вручную)."""',
        "from __future__ import annotations",
        "",
        "FOREIGN_AGENT_NAMES: tuple[str, ...] = (",
    ]
    for name in ordered:
        lines.append(f'    "{name}",')
    lines.append(")")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written {len(ordered)} names -> {OUT}")


if __name__ == "__main__":
    main()
