import fnmatch
from pathlib import Path


class IgnoreEngine:
    """
    Ignore engine respecting .gitignore rules and enforcing mandatory exclusions for
    build artifacts, dependency directories, virtualenvs, and binary files.
    """

    MANDATORY_EXCLUDED_DIRS: set[str] = {
        "node_modules",
        ".git",
        "dist",
        "build",
        ".next",
        "coverage",
        "__pycache__",
        "venv",
        ".venv",
        "env",
        ".env",
        ".pytest_cache",
        ".ruff_cache",
        ".idea",
        ".vscode",
    }

    BINARY_EXTENSIONS: set[str] = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".svg",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".7z",
        ".exe",
        ".dll",
        ".so",
        ".dylib",
        ".pyc",
        ".pyo",
        ".db",
        ".sqlite",
        ".bin",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".mp4",
        ".mp3",
    }

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.gitignore_patterns: list[str] = []
        self._load_gitignore()

    def _load_gitignore(self) -> None:
        """Parse .gitignore from repository root if present."""
        gitignore_path = self.repo_root / ".gitignore"
        if gitignore_path.is_file():
            try:
                content = gitignore_path.read_text(encoding="utf-8", errors="ignore")
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self.gitignore_patterns.append(line)
            except Exception:
                pass

    def is_ignored(self, relative_path: str | Path) -> bool:
        """Check if relative path should be ignored during repo scan."""
        rel_path_str = str(relative_path).replace("\\", "/")
        path_parts = Path(rel_path_str).parts

        # Check mandatory directory exclusions
        for part in path_parts:
            if part in self.MANDATORY_EXCLUDED_DIRS:
                return True

        # Check binary file extension
        suffix = Path(rel_path_str).suffix.lower()
        if suffix in self.BINARY_EXTENSIONS:
            return True

        # Check gitignore glob patterns
        for pattern in self.gitignore_patterns:
            clean_pattern = pattern.rstrip("/")
            if fnmatch.fnmatch(rel_path_str, clean_pattern) or fnmatch.fnmatch(Path(rel_path_str).name, clean_pattern):
                return True

        return False
