from typing import Any

from services.repository.app.core.parsers.ast_parser import ASTSymbolParser


class IncrementalIndexer:
    """
    Incremental Indexer comparing SHA256 file hashes to detect added, modified,
    and deleted files, re-parsing only changed files to optimize indexing time.
    """

    @classmethod
    def compute_diff(
        cls,
        previous_file_hashes: dict[str, str],
        current_scanned_files: list[dict[str, Any]],
    ) -> dict[str, list[str]]:
        """
        Compare previous file SHA256 hashes against current scan to compute delta.
        Returns dict containing 'added', 'modified', and 'deleted' file path lists.
        """
        current_map = {f["path"]: f["sha256"] for f in current_scanned_files}
        prev_map = previous_file_hashes

        added = [path for path in current_map if path not in prev_map]
        deleted = [path for path in prev_map if path not in current_map]
        modified = [
            path
            for path in current_map
            if path in prev_map and current_map[path] != prev_map[path]
        ]

        return {"added": added, "modified": modified, "deleted": deleted}

    @classmethod
    def update_symbol_index(
        cls,
        previous_symbols: list[dict[str, Any]],
        diff: dict[str, list[str]],
        scanned_files_map: dict[str, dict[str, Any]],
        repository_id: str,
    ) -> list[dict[str, Any]]:
        """
        Incrementally update symbol index by purging deleted/modified file symbols
        and parsing only added/modified files.
        """
        files_to_purge = set(diff["modified"]) | set(diff["deleted"])
        retained_symbols = [s for s in previous_symbols if s.get("file") not in files_to_purge]

        files_to_parse = set(diff["added"]) | set(diff["modified"])
        new_symbols: list[dict[str, Any]] = []

        for rel_path in files_to_parse:
            file_meta = scanned_files_map.get(rel_path)
            if not file_meta:
                continue

            parsed = ASTSymbolParser.parse_file(
                file_path=file_meta["absolute_path"],
                relative_path=rel_path,
                language=file_meta["language"],
                repository_id=repository_id,
            )
            new_symbols.extend(parsed)

        return retained_symbols + new_symbols
