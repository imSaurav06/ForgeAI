from pathlib import Path

from fastapi.testclient import TestClient

from services.repository.app.core.graph.dependency_builder import DependencyGraphBuilder
from services.repository.app.core.indexers.incremental_indexer import IncrementalIndexer
from services.repository.app.core.parsers.ast_parser import ASTSymbolParser
from services.repository.app.core.scanners.ignore_engine import IgnoreEngine
from services.repository.app.core.scanners.language_detector import LanguageDetector
from services.repository.app.core.scanners.repo_scanner import RepoScanner
from services.repository.app.main import app

client = TestClient(app)
repo_root = Path(".").resolve()


def test_ignore_engine():
    """Test .gitignore and mandatory directory exclusions."""
    engine = IgnoreEngine(repo_root)
    assert engine.is_ignored("node_modules/express/index.js") is True
    assert engine.is_ignored(".git/config") is True
    assert engine.is_ignored("dist/main.js") is True
    assert engine.is_ignored("__pycache__/app.pyc") is True
    assert engine.is_ignored("shared/config/settings.py") is False


def test_language_detector():
    """Test language detection mapping and statistics calculator."""
    assert LanguageDetector.detect_language("main.py") == "python"
    assert LanguageDetector.detect_language("index.ts") == "typescript"
    assert LanguageDetector.detect_language("app.jsx") == "jsx"

    files_sample = [
        {"language": "python", "size_bytes": 1000},
        {"language": "python", "size_bytes": 1000},
        {"language": "typescript", "size_bytes": 2000},
    ]
    stats = LanguageDetector.calculate_language_stats(files_sample)
    assert stats["python"]["file_count"] == 2
    assert stats["python"]["percentage"] == 50.0
    assert stats["typescript"]["percentage"] == 50.0


def test_ast_symbol_parser():
    """Test AST symbol parsing on Python code."""
    sample_code = """
import os
from datetime import datetime

class UserEngine:
    def __init__(self, name: str):
        self.name = name

    def validate_name(self) -> bool:
        return len(self.name) > 0

def standalone_func():
    pass
"""
    tmp_file = Path("./tmp_sample_test.py")
    tmp_file.write_text(sample_code, encoding="utf-8")

    try:
        symbols = ASTSymbolParser.parse_file(
            file_path=tmp_file,
            relative_path="tmp_sample_test.py",
            language="python",
            repository_id="test_repo",
        )
        sym_names = [s["symbol"] for s in symbols]
        sym_types = [s["type"] for s in symbols]

        assert "os" in sym_names
        assert "datetime" in sym_names
        assert "UserEngine" in sym_names
        assert "class" in sym_types
        assert "UserEngine.validate_name" in sym_names or "validate_name" in sym_names
        assert "standalone_func" in sym_names
    finally:
        if tmp_file.exists():
            tmp_file.unlink()


def test_dependency_graph_builder():
    """Test dependency graph builder and cycle detection."""
    scanned_files = [
        {"path": "auth/service.py", "language": "python", "size_bytes": 100},
        {"path": "auth/jwt.py", "language": "python", "size_bytes": 100},
        {"path": "utils/logger.py", "language": "python", "size_bytes": 100},
    ]
    symbols = [
        {"file": "auth/service.py", "type": "import", "symbol": "auth.jwt"},
        {"file": "auth/jwt.py", "type": "import", "symbol": "auth.service"},
        {"file": "auth/service.py", "type": "import", "symbol": "fastapi"},
    ]

    builder = DependencyGraphBuilder(scanned_files, symbols)
    graph = builder.build_graph()

    assert "auth/service.py" in graph["nodes"]
    assert "fastapi" in graph["external_packages"]
    assert len(graph["internal_edges"]) >= 1


def test_incremental_indexer():
    """Test SHA256 file hash diff calculation."""
    prev_hashes = {"file1.py": "hash_a", "file2.py": "hash_b"}
    current_files = [
        {"path": "file1.py", "sha256": "hash_a"},  # Unchanged
        {"path": "file2.py", "sha256": "hash_b_modified"},  # Modified
        {"path": "file3.py", "sha256": "hash_c"},  # Added
    ]

    diff = IncrementalIndexer.compute_diff(prev_hashes, current_files)
    assert diff["added"] == ["file3.py"]
    assert diff["modified"] == ["file2.py"]
    assert diff["deleted"] == []


def test_repo_scanner():
    """Test RepoScanner scanning local repository."""
    scanner = RepoScanner(repo_root)
    result = scanner.scan()

    assert result["total_files"] > 0
    assert len(result["tree"]) > 0
    assert "python" in result["languages"]


def test_repository_api_endpoints():
    """Test Repository Service API endpoints."""
    from services.gateway.app.core.internal_auth import InternalAuthManager
    headers = {"X-Internal-Service-Token": InternalAuthManager().generate_internal_token("test-client")}

    # Register Repo
    reg_resp = client.post(
        "/v1/repositories/register",
        headers=headers,
        json={"name": "ForgeAI Repo", "path": str(repo_root).replace("\\", "/")},
    )
    assert reg_resp.status_code == 201
    repo_id = reg_resp.json()["data"]["id"]

    # Scan Repo
    scan_resp = client.post(f"/v1/repositories/{repo_id}/scan", headers=headers)
    assert scan_resp.status_code == 200
    assert scan_resp.json()["data"]["total_files"] > 0

    # Index Repo
    idx_resp = client.post(f"/v1/repositories/{repo_id}/index", headers=headers, json={"force_reindex": True})
    assert idx_resp.status_code == 200
    assert idx_resp.json()["data"]["total_symbols"] > 0

    # Get Details
    get_resp = client.get(f"/v1/repositories/{repo_id}", headers=headers)
    assert get_resp.status_code == 200

    # Get Tree
    tree_resp = client.get(f"/v1/repositories/{repo_id}/tree", headers=headers)
    assert tree_resp.status_code == 200

    # Get Symbols
    sym_resp = client.get(f"/v1/repositories/{repo_id}/symbols", headers=headers)
    assert sym_resp.status_code == 200

    # Get Languages
    lang_resp = client.get(f"/v1/repositories/{repo_id}/languages", headers=headers)
    assert lang_resp.status_code == 200

    # Get Dependencies
    dep_resp = client.get(f"/v1/repositories/{repo_id}/dependencies", headers=headers)
    assert dep_resp.status_code == 200

    # List Files
    files_resp = client.get(f"/v1/repositories/{repo_id}/files", headers=headers)
    assert files_resp.status_code == 200
