"""
Tree-sitter Parser — thin wrapper around tree-sitter that parses source bytes
and returns a syntax tree with diagnostic metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from services.repository.app.core.parsers.language_registry import (
    get_language_for_extension,
    language_name_for_extension,
)
from shared.logging.logger import logger

if TYPE_CHECKING:
    from tree_sitter import Node, Tree


@dataclass
class ParseResult:
    """Result of parsing a single source file with Tree-sitter."""

    tree: Tree | None
    language: str
    file_path: str
    source_bytes: bytes
    error_count: int = 0
    error_ranges: list[dict] = field(default_factory=list)
    success: bool = True


def _count_errors(node: Node) -> tuple[int, list[dict]]:
    """Walk the tree and count ERROR / MISSING nodes."""
    error_count = 0
    error_ranges: list[dict] = []

    def _walk(n: Node) -> None:
        nonlocal error_count
        if n.type == "ERROR" or n.is_missing:
            error_count += 1
            error_ranges.append(
                {
                    "type": n.type,
                    "start_line": n.start_point[0] + 1,
                    "end_line": n.end_point[0] + 1,
                    "start_col": n.start_point[1],
                    "end_col": n.end_point[1],
                }
            )
        for child in n.children:
            _walk(child)

    _walk(node)
    return error_count, error_ranges


def parse_source(
    file_path: str | Path,
    source_bytes: bytes | None = None,
) -> ParseResult | None:
    """
    Parse a source file with the appropriate Tree-sitter grammar.

    Returns a ``ParseResult`` containing the syntax tree, or ``None`` if the
    file extension is not supported by any registered grammar.

    Malformed source does **not** raise — Tree-sitter produces a partial tree
    with ERROR nodes that are counted in ``ParseResult.error_count``.
    """
    from tree_sitter import Parser

    path = Path(file_path)
    extension = path.suffix.lower()
    lang_name = language_name_for_extension(extension)

    if lang_name is None:
        return None  # Unsupported language

    language = get_language_for_extension(extension)
    if language is None:
        return None  # Grammar failed to load

    if source_bytes is None:
        try:
            source_bytes = path.read_bytes()
        except Exception as err:  # noqa: BLE001
            logger.warning(f"Tree-sitter: could not read file {file_path}: {err}")
            return ParseResult(
                tree=None,
                language=lang_name,
                file_path=str(file_path),
                source_bytes=b"",
                success=False,
            )

    parser = Parser(language)
    tree = parser.parse(source_bytes)

    error_count, error_ranges = _count_errors(tree.root_node)
    if error_count > 0:
        logger.debug(
            f"Tree-sitter: {error_count} parse error(s) in {file_path}"
        )

    return ParseResult(
        tree=tree,
        language=lang_name,
        file_path=str(file_path),
        source_bytes=source_bytes,
        error_count=error_count,
        error_ranges=error_ranges,
        success=True,
    )
