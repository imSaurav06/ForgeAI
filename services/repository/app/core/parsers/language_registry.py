"""
Tree-sitter Language Registry — deterministic mapping from file extensions to
Tree-sitter Language objects with lazy grammar loading.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from shared.logging.logger import logger

if TYPE_CHECKING:
    from tree_sitter import Language


# ---------------------------------------------------------------------------
# Extension → canonical language name
# ---------------------------------------------------------------------------
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
}


@lru_cache(maxsize=1)
def _load_python_language() -> Language:
    import tree_sitter_python
    from tree_sitter import Language as TSLanguage

    return TSLanguage(tree_sitter_python.language())


@lru_cache(maxsize=1)
def _load_javascript_language() -> Language:
    import tree_sitter_javascript
    from tree_sitter import Language as TSLanguage

    return TSLanguage(tree_sitter_javascript.language())


@lru_cache(maxsize=1)
def _load_typescript_language() -> Language:
    import tree_sitter_typescript
    from tree_sitter import Language as TSLanguage

    return TSLanguage(tree_sitter_typescript.language_typescript())


@lru_cache(maxsize=1)
def _load_tsx_language() -> Language:
    import tree_sitter_typescript
    from tree_sitter import Language as TSLanguage

    return TSLanguage(tree_sitter_typescript.language_tsx())


# Canonical language name → loader callable
_LANGUAGE_LOADERS: dict[str, callable] = {
    "python": _load_python_language,
    "javascript": _load_javascript_language,
    "typescript": _load_typescript_language,
    "tsx": _load_tsx_language,
}

# Languages supported by Tree-sitter in this registry
SUPPORTED_LANGUAGES: frozenset[str] = frozenset(_LANGUAGE_LOADERS.keys())


def get_language_for_extension(extension: str) -> Language | None:
    """Return a Tree-sitter Language for a file extension, or None if unsupported."""
    lang_name = EXTENSION_TO_LANGUAGE.get(extension.lower())
    if lang_name is None:
        return None
    return get_language(lang_name)


def get_language(name: str) -> Language | None:
    """Return a Tree-sitter Language for a canonical language name, or None if unsupported."""
    loader = _LANGUAGE_LOADERS.get(name)
    if loader is None:
        return None
    try:
        return loader()
    except Exception as err:  # noqa: BLE001
        logger.warning(f"Failed to load Tree-sitter grammar for '{name}': {err}")
        return None


def language_name_for_extension(extension: str) -> str | None:
    """Return the canonical language name for a file extension, or None."""
    return EXTENSION_TO_LANGUAGE.get(extension.lower())
