"""
Map client language hints (BCP-47, aliases) to pocket-tts `load_model(language=...)` ids.
See https://github.com/kyutai-labs/pocket-tts — supported locales use per-language configs.
"""

from __future__ import annotations

# Canonical pocket-tts language ids (see pocket_tts.models.tts_model.TTSModel.load_model docstring).
# We default to the newer 24-layer variants where available for consistency and quality.
CANONICAL_LANGUAGES: frozenset[str] = frozenset(
    {
        'english',
        'french_24l',
        'german_24l',
        'italian_24l',
        'portuguese_24l',
        'spanish_24l',
    }
)

# Primary subtag (ISO 639-1) -> canonical
_PRIMARY_TO_CANONICAL: dict[str, str] = {
    'en': 'english',
    'fr': 'french_24l',
    'de': 'german_24l',
    'it': 'italian_24l',
    'pt': 'portuguese_24l',
    'es': 'spanish_24l',
}

# Common English names -> canonical
_NAME_TO_CANONICAL: dict[str, str] = {
    'english': 'english',
    'french': 'french_24l',
    'german': 'german_24l',
    'italian': 'italian_24l',
    'portuguese': 'portuguese_24l',
    'spanish': 'spanish_24l',
    # Legacy 12-layer ids — accept them but transparently upgrade to the _24l variant
    # so clients that hardcode the old name don't have to change.
    'italian_12l': 'italian_24l',
    'portuguese_12l': 'portuguese_24l',
}


def normalize_language(raw: str | None, default: str) -> str:
    """
    Return a canonical pocket-tts language id.

    Accepts BCP-47 tags (e.g. en-US, fr-FR), ISO 639-1 codes, or canonical ids.
    Empty / None uses `default` (must already be canonical).
    """
    if raw is None:
        return default
    s = str(raw).strip().lower()
    if not s:
        return default

    # BCP-47: use language subtag only
    if '-' in s:
        s = s.split('-', 1)[0]

    if s in CANONICAL_LANGUAGES:
        return s
    if s in _PRIMARY_TO_CANONICAL:
        return _PRIMARY_TO_CANONICAL[s]
    if s in _NAME_TO_CANONICAL:
        return _NAME_TO_CANONICAL[s]

    raise ValueError(
        f"Unsupported language {raw!r}. "
        f"Use one of: {', '.join(sorted(CANONICAL_LANGUAGES))}, "
        'or BCP-47 tags like en-US, fr-FR, de-DE, it-IT, pt-PT, es-ES.'
    )


def parse_preload_list(raw: str | None) -> list[str]:
    """Comma-separated canonical language ids from env."""
    if not raw or not str(raw).strip():
        return []
    out: list[str] = []
    for part in str(raw).split(','):
        p = part.strip().lower()
        if not p:
            continue
        out.append(normalize_language(p, 'english'))
    return out
