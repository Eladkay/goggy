"""Admin-editable site settings, persisted to a JSON file.

Precedence: values saved by the admin (settings file) override the defaults,
which themselves come from environment variables / config. The blog *name* lives
here (Goggy is the software; the blog has its own name).
"""

from __future__ import annotations

import json
import threading

from . import config

SETTINGS_FILE = config.SETTINGS_FILE

_DEFAULTS: dict = {
    "blog_title": config.BLOG_TITLE,
    "blog_tagline": config.BLOG_TAGLINE,
    "default_lang": config.DEFAULT_LANG,
    "posts_per_page": config.POSTS_PER_PAGE,
    "footer_text": config.FOOTER_TEXT,
}

_lock = threading.Lock()
_cache: dict | None = None


def _load() -> dict:
    data = dict(_DEFAULTS)
    if SETTINGS_FILE.exists():
        try:
            data.update(json.loads(SETTINGS_FILE.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    return data


def all() -> dict:
    global _cache
    if _cache is None:
        with _lock:
            if _cache is None:
                _cache = _load()
    return dict(_cache)


def get(key: str):
    return all().get(key, _DEFAULTS.get(key))


def update(values: dict) -> None:
    """Persist a subset of settings. Unknown keys ignored; types coerced."""
    global _cache
    with _lock:
        current = _load()
        for key in _DEFAULTS:
            if key not in values:
                continue
            val = values[key]
            if key == "posts_per_page":
                try:
                    val = max(1, int(val))
                except (TypeError, ValueError):
                    continue
            current[key] = val
        SETTINGS_FILE.write_text(json.dumps(current, indent=2, ensure_ascii=False))
        _cache = current
