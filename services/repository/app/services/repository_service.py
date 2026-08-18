import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import os
from services.repository.app.core.cache.repo_cache import get_repository_cache
from services.repository.app.core.graph.dependency_builder import DependencyGraphBuilder
from services.repository.app.core.indexers.incremental_indexer import IncrementalIndexer
from services.repository.app.core.scanners.repo_scanner import RepoScanner
from services.repository.app.schemas.repository import (
    DirectoryItem,
    DriveItem,
    FilesystemBrowseResponse,
    RepositoryMetadata,
)
from services.repository.app.storage.mongo_repository import MongoRepositoryMetadataRepository
from shared.exceptions.handlers import NotFoundException, UnauthorizedException, ValidationException


class RepositoryService:
    """Repository Intelligence Service orchestrating scanning, parsing, indexing, and dependency analysis with MongoDB persistence."""

    _REGISTRY: dict[str, RepositoryMetadata] = {}

    def __init__(self) -> None:
        self.cache = get_repository_cache()
        self.mongo_repo = MongoRepositoryMetadataRepository()
        self._registered_repos = RepositoryService._REGISTRY

    def register_repository(
        self,
        name: str,
        path: str,
        git_remote: str | None = None,
        branch: str = "main",
        user_id: str | None = None,
    ) -> RepositoryMetadata:
        """Register repository workspace metadata."""
        repo_id = f"repo_{uuid.uuid4().hex[:8]}"
        meta = RepositoryMetadata(
            id=repo_id,
            name=name,
            path=path,
            git_remote=git_remote,
            branch=branch,
            user_id=user_id,
        )
        self._registered_repos[repo_id] = meta

        # Persist to MongoDB synchronously/asynchronously via background task or helper
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.mongo_repo.save_repository(meta))
        except Exception:
            pass

        return meta

    def list_repositories(self, user_id: str | None = None) -> list[RepositoryMetadata]:
        """List registered repositories filtered by user ownership."""
        if not user_id:
            return list(self._registered_repos.values())
        return [r for r in self._registered_repos.values() if not r.user_id or r.user_id == user_id]

    async def list_repositories_async(self, user_id: str | None = None) -> list[RepositoryMetadata]:
        """List registered repositories from MongoDB filtered by user ownership."""
        try:
            mongo_repos = await self.mongo_repo.list_repositories(user_id=user_id)
            for repo in mongo_repos:
                if repo.id not in self._registered_repos:
                    self._registered_repos[repo.id] = repo
            return mongo_repos
        except Exception:
            pass
        return self.list_repositories(user_id=user_id)

    def open_repository(self, path: str, user_id: str | None = None) -> RepositoryMetadata:
        """Open an existing local repository path."""
        p_str = path.replace("\\", "/")
        repo_path = Path(p_str)

        if not repo_path.is_dir():
            if p_str.lower().startswith("f:/") and Path("/host_f/" + p_str[3:]).is_dir():
                repo_path = Path("/host_f/" + p_str[3:]).resolve()
            elif p_str.lower().startswith("e:/") and Path("/host_e/" + p_str[3:]).is_dir():
                repo_path = Path("/host_e/" + p_str[3:]).resolve()
            elif p_str.lower().startswith("c:/") and Path("/host_c/" + p_str[3:]).is_dir():
                repo_path = Path("/host_c/" + p_str[3:]).resolve()

        if not repo_path.is_dir():
            raise ValidationException(message=f"Local path '{path}' does not exist or is not a valid accessible directory")

        # Check if already registered in memory or cache
        for meta in self._registered_repos.values():
            if Path(meta.path).resolve() == repo_path and (not user_id or not meta.user_id or meta.user_id == user_id):
                return meta

        return self.register_repository(name=repo_path.name, path=str(repo_path), user_id=user_id)

    def get_repository_metadata(self, repository_id: str, user_id: str | None = None) -> RepositoryMetadata:
        """Retrieve metadata for a registered repository ID."""
        meta = self._registered_repos.get(repository_id)
        if not meta:
            raise NotFoundException(message=f"Repository ID '{repository_id}' not found")
        if user_id and meta.user_id and meta.user_id != user_id:
            raise UnauthorizedException(message=f"Access denied: You do not own repository '{repository_id}'")
        return meta

    async def get_repository_metadata_async(self, repository_id: str, user_id: str | None = None) -> RepositoryMetadata:
        """Retrieve metadata from MongoDB or in-memory cache with ownership enforcement."""
        meta = self._registered_repos.get(repository_id)
        if not meta:
            try:
                meta = await self.mongo_repo.get_repository(repository_id)
                if meta:
                    self._registered_repos[meta.id] = meta
            except Exception:
                pass
        if not meta:
            raise NotFoundException(message=f"Repository ID '{repository_id}' not found")
        if user_id and meta.user_id and meta.user_id != user_id:
            raise UnauthorizedException(message=f"Access denied: You do not own repository '{repository_id}'")
        return meta

    def scan_repository(self, repository_id: str) -> dict[str, Any]:
        """Scan repository files, tree structure, and language statistics."""
        meta = self.get_repository_metadata(repository_id)
        scanner = RepoScanner(meta.path)
        scan_result = scanner.scan()

        # Update cache with scan result
        cached_data = self.cache.get(repository_id) or {}
        cached_data.update(
            {
                "repository_id": repository_id,
                "scanned_files": scan_result["files"],
                "tree": scan_result["tree"],
                "languages": scan_result["languages"],
            }
        )
        self.cache.set(repository_id, cached_data)
        return scan_result

    def index_repository(self, repository_id: str, force_reindex: bool = False) -> dict[str, Any]:
        """Perform full or incremental AST symbol indexing on repository files."""
        meta = self.get_repository_metadata(repository_id)
        scan_result = self.scan_repository(repository_id)

        cached_data = self.cache.get(repository_id) or {}
        prev_file_hashes: dict[str, str] = cached_data.get("file_hashes", {}) if not force_reindex else {}
        prev_symbols: list[dict[str, Any]] = cached_data.get("symbols", []) if not force_reindex else []

        scanned_files = scan_result["files"]
        scanned_files_map = {f["path"]: f for f in scanned_files}

        # Calculate incremental diff based on SHA256 file hashes
        diff = IncrementalIndexer.compute_diff(prev_file_hashes, scanned_files)

        # Update AST Symbols incrementally
        symbols = IncrementalIndexer.update_symbol_index(
            previous_symbols=prev_symbols,
            diff=diff,
            scanned_files_map=scanned_files_map,
            repository_id=repository_id,
        )

        # Build Dependency Graph
        dep_builder = DependencyGraphBuilder(scanned_files, symbols)
        graph = dep_builder.build_graph()

        # Store updated hashes and results in cache
        new_file_hashes = {f["path"]: f["sha256"] for f in scanned_files}
        completion_time = datetime.now(UTC).isoformat()

        cached_data.update(
            {
                "symbols": symbols,
                "graph": graph,
                "file_hashes": new_file_hashes,
                "indexed_at": completion_time,
            }
        )
        self.cache.set(repository_id, cached_data)

        # Update metadata timestamp
        meta.indexed_at = completion_time

        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.mongo_repo.save_repository(meta))
        except Exception:
            pass

        return {
            "repository_id": repository_id,
            "total_files": len(scanned_files),
            "total_symbols": len(symbols),
            "indexed_at": completion_time,
            "delta": diff,
        }

    def get_symbols(
        self, repository_id: str, symbol_type: str | None = None, file_path: str | None = None
    ) -> list[dict[str, Any]]:
        """Retrieve indexed AST symbols with optional filtering."""
        cached_data = self.cache.get(repository_id)
        if not cached_data or "symbols" not in cached_data:
            self.index_repository(repository_id)
            cached_data = self.cache.get(repository_id) or {}

        symbols = cached_data.get("symbols", [])

        if symbol_type:
            symbols = [s for s in symbols if s.get("type") == symbol_type]
        if file_path:
            symbols = [s for s in symbols if s.get("file") == file_path]

        return symbols

    def get_dependencies(self, repository_id: str) -> dict[str, Any]:
        """Retrieve static dependency graph analysis."""
        cached_data = self.cache.get(repository_id)
        if not cached_data or "graph" not in cached_data:
            self.index_repository(repository_id)
            cached_data = self.cache.get(repository_id) or {}

        return cached_data.get("graph", {"nodes": [], "internal_edges": [], "external_packages": [], "circular_dependencies": [], "orphan_files": []})

    def get_file_content(self, repository_id: str, file_path: str) -> dict[str, Any]:
        """Read actual file content from the repository workspace."""
        meta = self.get_repository_metadata(repository_id)
        repo_root = Path(meta.path).resolve()

        # Resolve path safely (prevent directory traversal)
        safe_path = (repo_root / file_path.lstrip("/")).resolve()
        if not safe_path.is_relative_to(repo_root):
            raise ValidationException(message=f"Path '{file_path}' is outside the repository")
        if not safe_path.exists():
            raise NotFoundException(message=f"File '{file_path}' not found in repository")
        if not safe_path.is_file():
            raise ValidationException(message=f"Path '{file_path}' is not a file")

        # Detect language from extension
        ext_to_lang = {
            ".py": "python", ".ts": "typescript", ".tsx": "typescript",
            ".js": "javascript", ".jsx": "javascript", ".json": "json",
            ".md": "markdown", ".html": "html", ".css": "css",
            ".scss": "scss", ".yaml": "yaml", ".yml": "yaml",
            ".toml": "toml", ".sh": "bash", ".txt": "plaintext",
            ".rs": "rust", ".go": "go", ".java": "java",
            ".cpp": "cpp", ".c": "c", ".h": "c",
        }
        suffix = safe_path.suffix.lower()
        language = ext_to_lang.get(suffix, "plaintext")

        try:
            content = safe_path.read_text(encoding="utf-8", errors="replace")
        except Exception as err:
            raise ValidationException(message=f"Cannot read file '{file_path}': {err}") from err

        return {
            "path": file_path,
            "content": content,
            "language": language,
        }

    def browse_filesystem(self, path: str | None = None) -> FilesystemBrowseResponse:
        """Browse host filesystem directories for IDE-style workspace folder selection."""
        # 1. Available root drives
        drives: list[DriveItem] = []
        if os.name == "nt":
            import string
            for letter in string.ascii_uppercase:
                drive_path = f"{letter}:\\"
                if os.path.exists(drive_path):
                    drives.append(DriveItem(name=f"{letter}:", path=drive_path))
        else:
            has_host_mounts = False
            for letter in ["c", "e", "f"]:
                mount = Path(f"/host_{letter}")
                if mount.is_dir():
                    has_host_mounts = True
                    drives.append(DriveItem(name=f"{letter.upper()}:", path=f"{letter.upper()}:/"))
            if Path("/app/workspace").is_dir():
                drives.append(DriveItem(name="Workspace", path="/app/workspace"))
            if not has_host_mounts:
                drives.append(DriveItem(name="/", path="/"))

        # 2. Determine target path
        if not path or not path.strip():
            if drives:
                d_path = drives[0].path
                if d_path.startswith(("C:/", "E:/", "F:/")):
                    target_path = Path(f"/host_{d_path[0].lower()}").resolve()
                elif os.path.exists(d_path):
                    target_path = Path(d_path).resolve()
                else:
                    target_path = Path("/app/workspace") if Path("/app/workspace").exists() else Path.home()
            else:
                target_path = Path("/app/workspace") if Path("/app/workspace").exists() else Path.home()
        else:
            clean_path = path.strip().replace("\0", "").replace("\\", "/")
            target_path = Path(clean_path)

            if not target_path.is_dir():
                if clean_path.lower().startswith("f:/") and Path("/host_f/" + clean_path[3:]).is_dir():
                    target_path = Path("/host_f/" + clean_path[3:]).resolve()
                elif clean_path.lower().startswith("e:/") and Path("/host_e/" + clean_path[3:]).is_dir():
                    target_path = Path("/host_e/" + clean_path[3:]).resolve()
                elif clean_path.lower().startswith("c:/") and Path("/host_c/" + clean_path[3:]).is_dir():
                    target_path = Path("/host_c/" + clean_path[3:]).resolve()
                elif clean_path.lower() in ["c:", "c:/"] and Path("/host_c").is_dir():
                    target_path = Path("/host_c").resolve()
                elif clean_path.lower() in ["e:", "e:/"] and Path("/host_e").is_dir():
                    target_path = Path("/host_e").resolve()
                elif clean_path.lower() in ["f:", "f:/"] and Path("/host_f").is_dir():
                    target_path = Path("/host_f").resolve()

        # Ensure target_path is within allowed mounts or workspace
        resolved_target = target_path.resolve()
        allowed_roots = [Path("/host_c"), Path("/host_e"), Path("/host_f"), Path("/app/workspace")]
        if os.name == "nt":
            import string
            allowed_roots = [Path(f"{l}:/") for l in string.ascii_uppercase if os.path.exists(f"{l}:/")]

        is_allowed = any(
            str(resolved_target).lower().startswith(str(root.resolve()).lower())
            for root in allowed_roots
            if root.exists()
        )

        if not is_allowed:
            raise ValidationException(message=f"Path '{path}' is outside allowed drives and workspaces")

        if not target_path.exists() or not target_path.is_dir():
            if target_path.parent.exists() and target_path.parent.is_dir():
                target_path = target_path.parent
            else:
                target_path = Path("/app/workspace") if Path("/app/workspace").exists() else Path.home()

        canonical_path = str(target_path).replace("\\", "/")
        parent_path = str(target_path.parent).replace("\\", "/") if target_path.parent != target_path else None

        display_path = canonical_path
        if display_path.startswith("/host_c"):
            display_path = "C:/" + display_path[7:].lstrip("/")
        elif display_path.startswith("/host_e"):
            display_path = "E:/" + display_path[7:].lstrip("/")
        elif display_path.startswith("/host_f"):
            display_path = "F:/" + display_path[7:].lstrip("/")

        display_parent = parent_path
        if display_parent:
            if display_parent.startswith("/host_c"):
                display_parent = "C:/" + display_parent[7:].lstrip("/")
            elif display_parent.startswith("/host_e"):
                display_parent = "E:/" + display_parent[7:].lstrip("/")
            elif display_parent.startswith("/host_f"):
                display_parent = "F:/" + display_parent[7:].lstrip("/")

        # 3. List child directories safely
        subdirs: list[DirectoryItem] = []
        ignored_system_folders = {"$recycle.bin", "system volume information", "$winre_backup_partition.marker", ".git", "node_modules", ".venv", "__pycache__"}

        try:
            with os.scandir(target_path) as it:
                for entry in it:
                    try:
                        if entry.name.lower() in ignored_system_folders:
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            entry_p = entry.path.replace("\\", "/")
                            if entry_p.startswith("/host_c"):
                                entry_display = "C:/" + entry_p[7:].lstrip("/")
                            elif entry_p.startswith("/host_e"):
                                entry_display = "E:/" + entry_p[7:].lstrip("/")
                            elif entry_p.startswith("/host_f"):
                                entry_display = "F:/" + entry_p[7:].lstrip("/")
                            else:
                                entry_display = entry_p
                            subdirs.append(DirectoryItem(name=entry.name, path=entry_display))
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            pass

        subdirs.sort(key=lambda x: x.name.lower())

        return FilesystemBrowseResponse(
            path=display_path,
            parent=display_parent,
            drives=drives,
            directories=subdirs,
        )


