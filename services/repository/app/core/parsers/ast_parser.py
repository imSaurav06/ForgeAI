"""
AST Symbol Parser — primary symbol extraction interface for the Repository Service.

Uses **real Tree-sitter bindings** via ``tree_sitter_parser`` and ``symbol_extractor``
for Python, JavaScript, TypeScript, and TSX/JSX.

This module preserves the public ``ASTSymbolParser.parse_file()`` interface so that
all existing callers (IncrementalIndexer, tests, etc.) continue to work unchanged.
"""

from pathlib import Path
from typing import Any

from services.repository.app.core.parsers.language_registry import SUPPORTED_LANGUAGES
from services.repository.app.core.parsers.symbol_extractor import extract_symbols
from services.repository.app.core.parsers.tree_sitter_parser import parse_source
from shared.logging.logger import logger

# Canonical language names recognised by the scanner that map to Tree-sitter languages.
_SCANNER_TO_TS_LANGUAGE: dict[str, str] = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "jsx": "javascript",   # JSX files use the JavaScript grammar
    "tsx": "tsx",
}


class ASTSymbolParser:
    """
    AST and Symbol Extraction Parser backed by **Tree-sitter**.

    Extracts classes, functions, methods, interfaces, enums, imports, exports,
    decorators, components, type aliases, and variables from source files using
    actual Tree-sitter parse trees.
    """

    @classmethod
    def parse_file(
        cls,
        file_path: str | Path,
        relative_path: str,
        language: str,
        repository_id: str = "repo",
    ) -> list[dict[str, Any]]:
        """
        Parse a source-code file and return extracted symbol records.

        Parameters
        ----------
        file_path : str | Path
            Absolute path to the source file on disk.
        relative_path : str
            Repository-relative path used in symbol records.
        language : str
            Canonical language name as reported by the scanner / LanguageDetector
            (``"python"``, ``"javascript"``, ``"typescript"``, ``"jsx"``, ``"tsx"``).
        repository_id : str
            Parent repository identifier embedded in each symbol dict.

        Returns
        -------
        list[dict[str, Any]]
            A list of symbol dicts, each containing at least:
            ``repository_id``, ``file``, ``symbol``, ``type``, ``language``,
            ``start_line``, ``end_line``, ``signature``, ``parent_symbol``.
        """
        path = Path(file_path)
        if not path.is_file():
            return []

        # Map scanner language to Tree-sitter canonical name
        ts_lang = _SCANNER_TO_TS_LANGUAGE.get(language)
        if ts_lang is None or ts_lang not in SUPPORTED_LANGUAGES:
            logger.debug(f"Tree-sitter: language '{language}' not supported, skipping {relative_path}")
            return []

        # Read source bytes
        try:
            source_bytes = path.read_bytes()
        except Exception as err:
            logger.warning(f"Tree-sitter: failed reading {relative_path}: {err}")
            return []

        # Parse with Tree-sitter
        # Determine extension from path for grammar lookup
        extension = path.suffix.lower()
        # For .jsx files, ensure we use javascript grammar via extension map
        parse_result = parse_source(file_path=path, source_bytes=source_bytes)

        if parse_result is None:
            logger.debug(f"Tree-sitter: no grammar for extension '{extension}', skipping {relative_path}")
            return []

        if not parse_result.success:
            logger.warning(f"Tree-sitter: parse failed for {relative_path}")
            return []

        if parse_result.error_count > 0:
            logger.debug(
                f"Tree-sitter: {parse_result.error_count} error node(s) in {relative_path} — "
                f"extracting symbols from partial tree"
            )

        # Extract symbols from the tree
        symbols = extract_symbols(
            parse_result=parse_result,
            relative_path=relative_path,
            repository_id=repository_id,
        )

        return symbols

    @classmethod
    def get_parser_backend(cls) -> str:
        """Return the name of the parsing backend in use. Useful for verification tests."""
        return "tree-sitter"
