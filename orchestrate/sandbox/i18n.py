"""Resource-file backed messages for sandbox reports."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_LOCALE_DIR = Path(__file__).parent / "locales"


class _SafeFormatDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


def normalize_language(lang: str | None) -> str:
    value = str(lang or "zh").lower()
    return "zh" if value.startswith("zh") else "en"


def _lookup(resource: dict[str, Any], key: str) -> str | None:
    value: Any = resource
    for part in key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value if isinstance(value, str) else None


@lru_cache(maxsize=8)
def _load_language(language: str) -> dict[str, Any]:
    path = _LOCALE_DIR / f"{language}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def translate(lang: str | None, key: str, **params: Any) -> str:
    """Return a resource message with safe named interpolation."""
    language = normalize_language(lang)
    template = _lookup(_load_language(language), key)
    if template is None:
        template = _lookup(_load_language("en"), key)
    if template is None:
        return key
    if params:
        return template.format_map(_SafeFormatDict(**params))
    return template
