from pathlib import Path


class LanguageDetector:
    """Language detection engine mapping file extensions to canonical language identifiers."""

    EXTENSION_MAP: dict[str, str] = {
        ".py": "python",
        ".pyi": "python",
        ".js": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".ts": "typescript",
        ".mts": "typescript",
        ".cts": "typescript",
        ".jsx": "jsx",
        ".tsx": "tsx",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".md": "markdown",
        ".markdown": "markdown",
        ".html": "html",
        ".css": "css",
        ".sh": "bash",
        ".bash": "bash",
        ".sql": "sql",
        ".toml": "toml",
        ".dockerfile": "dockerfile",
    }

    @classmethod
    def detect_language(cls, file_path: str | Path) -> str:
        """Detect canonical programming language name from file extension."""
        path = Path(file_path)
        filename_lower = path.name.lower()

        if filename_lower == "dockerfile":
            return "dockerfile"

        suffix = path.suffix.lower()
        return cls.EXTENSION_MAP.get(suffix, "unknown")

    @classmethod
    def calculate_language_stats(cls, files_data: list[dict]) -> dict[str, dict]:
        """
        Calculate language statistics (file count, total bytes, percentage) across scanned files.
        """
        stats: dict[str, dict] = {}
        total_bytes = 0

        for f in files_data:
            lang = f.get("language", "unknown")
            size = f.get("size_bytes", 0)

            if lang not in stats:
                stats[lang] = {"file_count": 0, "total_bytes": 0, "percentage": 0.0}

            stats[lang]["file_count"] += 1
            stats[lang]["total_bytes"] += size
            total_bytes += size

        if total_bytes > 0:
            for _lang, data in stats.items():
                data["percentage"] = round((data["total_bytes"] / total_bytes) * 100.0, 2)

        return stats
