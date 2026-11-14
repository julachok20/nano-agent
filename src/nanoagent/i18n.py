"""Text in English and Thai. Keys are dotted ids; locale files are JSON in nanoagent/locales/.

`t("setup.intro")` uses the language from config (en or th); a missing Thai key falls back to English, a missing
English key falls back to the key itself so a gap is visible, never a crash. `ui_strings()` returns the `ui.*` keys the
web console needs, sent to the browser as one JSON object.
"""
from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

SUPPORTED = ("en", "th")
_override: str | None = None


@lru_cache(maxsize=8)
def _load(lang: str) -> dict[str, str]:
    try:
        text = resources.files("nanoagent").joinpath("locales", f"{lang}.json").read_text(encoding="utf-8")
        return json.loads(text)
    except Exception:
        return {}


def set_language(lang: str | None) -> None:
    global _override
    _override = lang if lang in SUPPORTED else None


def language() -> str:
    if _override:
        return _override
    try:
        from . import config

        lang = config.get(config.load(), "general.language", "en")
    except Exception:
        lang = "en"
    return lang if lang in SUPPORTED else "en"


def t(key: str, lang: str | None = None, **kw) -> str:
    lang = lang or language()
    s = _load(lang).get(key) or _load("en").get(key) or key
    if kw:
        try:
            return s.format(**kw)
        except (KeyError, IndexError):
            return s
    return s


def ui_strings(lang: str | None = None) -> dict[str, str]:
    lang = lang or language()
    en, cur = _load("en"), _load(lang)
    return {k[3:]: cur.get(k) or v for k, v in en.items() if k.startswith("ui.")}


def missing_keys() -> dict[str, list[str]]:
    """Keys present in English but absent from another locale (a test keeps this empty)."""
    en = set(_load("en"))
    return {lang: sorted(en - set(_load(lang))) for lang in SUPPORTED if lang != "en"}
