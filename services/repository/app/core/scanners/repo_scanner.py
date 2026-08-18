import hashlib
from pathlib import Path
from typing import Any

from services.repository.app.core.scanners.ignore_engine import IgnoreEngine
from services.repository.app.core.scanners.language_detector import LanguageDetector


class RepoScanner:
    """
    Repository Scanner recursively discovering files, hashing contents with SHA256,
    generating directory tree structures, and computing language breakdowns.
    """

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.ignore_engine = IgnoreEngine(self.repo_root)

    @staticmethod
    def compute_sha256(file_path: Path) -> str:
        """Compute SHA256 hex digest of file contents."""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(65536), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception:
            return ""

    def scan(self) -> dict[str, Any]:
        """
        Scan repository, returning list of files with metadata, directory tree,
        and language statistics. Uses directory-level pruning to skip ignored
        directories (e.g. node_modules) entirely before descending into them,
        preventing timeout on large dependency trees.
        """
        import os

        if not self.repo_root.is_dir():
            raise FileNotFoundError(f"Repository directory does not exist: {self.repo_root}")

        scanned_files: list[dict[str, Any]] = []

        for dirpath, dirnames, filenames in os.walk(self.repo_root):
            current_dir = Path(dirpath)

            # Prune ignored directories IN-PLACE so os.walk does not descend into them
            try:
                rel_dir = current_dir.relative_to(self.repo_root)
            except ValueError:
                rel_dir = Path(".")

            # Filter out directories that are mandatory exclusions
            dirnames[:] = [
                d for d in dirnames
                if d not in self.ignore_engine.MANDATORY_EXCLUDED_DIRS
                and not self.ignore_engine.is_ignored(rel_dir / d)
            ]

            for filename in filenames:
                abs_path = current_dir / filename
                try:
                    rel_path = abs_path.relative_to(self.repo_root)
                except ValueError:
                    continue

                if self.ignore_engine.is_ignored(rel_path):
                    continue

                try:
                    size_bytes = abs_path.stat().st_size
                except OSError:
                    continue

                language = LanguageDetector.detect_language(abs_path)
                file_hash = self.compute_sha256(abs_path)

                scanned_files.append(
                    {
                        "path": str(rel_path).replace("\\", "/"),
                        "absolute_path": str(abs_path.resolve()).replace("\\", "/"),
                        "size_bytes": size_bytes,
                        "language": language,
                        "sha256": file_hash,
                    }
                )

        tree = self.build_tree(scanned_files)
        language_stats = LanguageDetector.calculate_language_stats(scanned_files)

        return {
            "total_files": len(scanned_files),
            "files": scanned_files,
            "tree": tree,
            "languages": language_stats,
        }

    def build_tree(self, scanned_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Construct directory tree hierarchy from flat list of scanned files."""
        tree_map: dict[str, dict[str, Any]] = {}

        for file_item in scanned_files:
            rel_path = file_item["path"]
            parts = rel_path.split("/")

            curr_path = ""
            for i, part in enumerate(parts):
                parent_path = curr_path
                curr_path = f"{curr_path}/{part}" if curr_path else part
                is_file = i == len(parts) - 1

                if curr_path not in tree_map:
                    tree_map[curr_path] = {
                        "name": part,
                        "path": curr_path,
                        "type": "file" if is_file else "directory",
                        "size_bytes": file_item["size_bytes"] if is_file else 0,
                        "language": file_item["language"] if is_file else None,
                        "children": [] if not is_file else None,
                        "_parent": parent_path,
                    }

        # Build parent-child relationships
        roots: list[dict[str, Any]] = []
        for _path_key, node in tree_map.items():
            parent = node.pop("_parent")
            if not parent:
                roots.append(node)
            else:
                if parent in tree_map and tree_map[parent]["children"] is not None:
                    tree_map[parent]["children"].append(node)

        return roots
