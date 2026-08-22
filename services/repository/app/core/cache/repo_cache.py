from typing import Any


class RepositoryCache:
    """In-memory cache storing scanned repository tree, symbols, dependency graph, and file hashes."""

    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}

    def get(self, repository_id: str) -> dict[str, Any] | None:
        """Retrieve cached repository knowledge payload."""
        return self._cache.get(repository_id)

    def set(self, repository_id: str, data: dict[str, Any]) -> None:
        """Store repository knowledge in cache."""
        self._cache[repository_id] = data

    def invalidate(self, repository_id: str) -> None:
        """Clear cache entry for a repository."""
        if repository_id in self._cache:
            del self._cache[repository_id]

    def delete(self, repository_id: str) -> None:
        """Alias for invalidate."""
        self.invalidate(repository_id)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()


_repo_cache_instance: RepositoryCache | None = None


def get_repository_cache() -> RepositoryCache:
    """Accessor for global RepositoryCache instance."""
    global _repo_cache_instance
    if _repo_cache_instance is None:
        _repo_cache_instance = RepositoryCache()
    return _repo_cache_instance
