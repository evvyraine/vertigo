"""Turn arbitrary text into safe, readable file names."""

from __future__ import annotations

import re

_TRANSLITERATION = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "і": "i", "ї": "yi", "є": "ye", "ґ": "g",
}


def slugify(text: str | None, *, max_length: int = 60, fallback: str = "output") -> str:
    """Return a lowercase, hyphenated ASCII file-name stem.

    Cyrillic is transliterated (``привет это я`` → ``privet-eto-ya``), other
    non-ASCII characters are dropped, and runs of separators collapse to ``-``.
    """
    source = (text or "").strip().lower()
    if not source:
        return fallback

    pieces: list[str] = []
    for char in source:
        translit = _TRANSLITERATION.get(char)
        if translit is not None:
            pieces.append(translit)
        elif char.isascii() and char.isalnum():
            pieces.append(char)
        else:
            pieces.append(" ")

    slug = re.sub(r"[^a-z0-9]+", "-", "".join(pieces)).strip("-")
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip("-")
    return slug or fallback
