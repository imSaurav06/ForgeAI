from typing import Any

from fastapi import APIRouter, Header, Query, status

from services.repository.app.schemas.repository import (
    DependencyGraphResponse,
    FilesystemBrowseResponse,
    RepoCloneRequest,
    RepoIndexRequest,
    RepoIndexResponse,
    RepoOpenRequest,
    RepoRegisterRequest,
    RepoScanResponse,
    RepositoryMetadata,
    SymbolItem,
)
from services.repository.app.services.repository_service import RepositoryService
from shared.schemas.responses import ErrorResponse, SuccessResponse

router = APIRouter(prefix="/v1/repositories", tags=["Repository Intelligence"])
repo_service = RepositoryService()


@router.get(
    "/browse",
    response_model=SuccessResponse[FilesystemBrowseResponse],
    summary="Browse Local Filesystem Directories",
    description="Returns available drives, current path, parent, and subdirectories for folder navigation.",
)
async def browse_filesystem(
    path: str | None = Query(default=None, description="Optional directory path to browse"),
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
) -> SuccessResponse[FilesystemBrowseResponse]:
    data = repo_service.browse_filesystem(path=path)
    return SuccessResponse(data=data, message="Filesystem directory listing retrieved")



@router.post(
    "/open",
    response_model=SuccessResponse[RepositoryMetadata],
    summary="Open Repository",
    description="Registers and inspects a local repository directory path.",
    responses={
        200: {"model": SuccessResponse[RepositoryMetadata], "description": "Repository opened"},
        400: {"model": ErrorResponse, "description": "Invalid directory path"},
    },
)
async def open_repository(
    payload: RepoOpenRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
) -> SuccessResponse[RepositoryMetadata]:
    meta = repo_service.open_repository(payload.path, user_id=x_user_id)
    return SuccessResponse(data=meta, message="Repository opened successfully")


@router.post(
    "/register",
    response_model=SuccessResponse[RepositoryMetadata],
    status_code=status.HTTP_201_CREATED,
    summary="Register Repository Metadata",
    description="Registers repository workspace path, branch, and metadata.",
    responses={
        201: {"model": SuccessResponse[RepositoryMetadata], "description": "Repository registered successfully"},
        400: {"model": ErrorResponse, "description": "Invalid directory path"},
    },
)
async def register_repository(
    payload: RepoRegisterRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
) -> SuccessResponse[RepositoryMetadata]:
    meta = repo_service.register_repository(
        name=payload.name,
        path=payload.path,
        git_remote=payload.git_remote,
        branch=payload.branch,
        user_id=x_user_id,
    )
    return SuccessResponse(data=meta, message="Repository registered successfully")


@router.get(
    "",
    response_model=SuccessResponse[list[RepositoryMetadata]],
    summary="List Repositories",
    description="Returns all registered repository metadata records.",
)
async def list_repositories(
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
) -> SuccessResponse[list[RepositoryMetadata]]:
    repos = await repo_service.list_repositories_async(user_id=x_user_id)
    return SuccessResponse(data=repos, message="Repositories list retrieved")


@router.get(
    "/{id}/tree",
    response_model=SuccessResponse[list[dict[str, Any]]],
    summary="Get Repository Tree",
    description="Returns filtered directory file tree hierarchy.",
)
async def get_repository_tree(
    id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
) -> SuccessResponse[list[dict[str, Any]]]:
    meta = await repo_service.get_repository_metadata_async(id, user_id=x_user_id)
    scan = repo_service.scan_repository(meta.id)
    return SuccessResponse(data=scan.get("tree", []), message="Repository file tree retrieved")


@router.get(
    "/{id}/status",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Get Repository Status",
    description="Retrieves scan and indexing status for a repository.",
)
async def get_repository_status(
    id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
) -> SuccessResponse[dict[str, Any]]:
    meta = await repo_service.get_repository_metadata_async(id, user_id=x_user_id)
    scan = repo_service.scan_repository(meta.id)
    return SuccessResponse(
        data={
            "repository_id": meta.id,
            "path": meta.path,
            "total_files": scan.get("total_files", len(scan.get("files", []))),
            "indexed_files": len(scan.get("files", [])),
            "status": "completed" if meta.indexed_at else "idle",
            "languages": list(scan.get("languages", {}).keys()),
            "metadata": meta.model_dump(),
        },
        message="Repository status retrieved",
    )


@router.get(
    "/{id}/file",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Get File Content",
    description="Returns content of a file within the repository by its relative path.",
    responses={
        200: {"model": SuccessResponse[dict[str, Any]], "description": "File content retrieved"},
        404: {"model": ErrorResponse, "description": "File not found"},
        400: {"model": ErrorResponse, "description": "Path invalid or outside repository"},
    },
)
async def get_repository_file_content(
    id: str,
    path: str = Query(..., description="Relative file path within the repository"),
) -> SuccessResponse[dict[str, Any]]:
    file_data = repo_service.get_file_content(id, path)
    return SuccessResponse(data=file_data, message="File content retrieved")


@router.get(
    "/{id}/symbols",
    response_model=SuccessResponse[list[dict[str, Any]]],
    summary="Get AST Symbols",
    description="Returns extracted classes, functions, and interfaces.",
)
async def get_repository_symbols(
    id: str,
    symbol_type: str | None = Query(default=None),
    file_path: str | None = Query(default=None),
) -> SuccessResponse[list[dict[str, Any]]]:
    symbols = repo_service.get_symbols(id, symbol_type=symbol_type, file_path=file_path)
    return SuccessResponse(data=symbols, message="AST symbols retrieved")


@router.get(
    "/{id}",
    response_model=SuccessResponse[RepositoryMetadata],
    summary="Get Repository Details",
    description="Returns metadata for the repository ID.",
)
async def get_repository_details(
    id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
) -> SuccessResponse[RepositoryMetadata]:
    meta = await repo_service.get_repository_metadata_async(id, user_id=x_user_id)
    return SuccessResponse(data=meta, message="Repository details retrieved")


@router.post(
    "/{id}/scan",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Scan Repository Filesystem",
    description="Scans files and detects languages in workspace.",
)
async def scan_repository(id: str) -> SuccessResponse[dict[str, Any]]:
    scan = repo_service.scan_repository(id)
    return SuccessResponse(data=scan, message="Repository scanned successfully")


@router.post(
    "/{id}/index",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Index AST Symbols",
    description="Parses AST symbols and extracts dependencies for repository.",
)
async def index_repository(
    id: str,
    payload: RepoIndexRequest | None = None,
) -> SuccessResponse[dict[str, Any]]:
    force = payload.force_reindex if payload else False
    result = repo_service.index_repository(id, force_reindex=force)
    return SuccessResponse(data=result, message="Repository indexed successfully")


@router.get(
    "/{id}/languages",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Get Detected Languages",
    description="Returns detected languages and file counts.",
)
async def get_repository_languages(id: str) -> SuccessResponse[dict[str, Any]]:
    scan = repo_service.scan_repository(id)
    return SuccessResponse(data=scan.get("languages", {}), message="Repository languages retrieved")


@router.get(
    "/{id}/files",
    response_model=SuccessResponse[list[dict[str, Any]]],
    summary="List Repository Files",
    description="Returns list of all source files in repository.",
)
async def get_repository_files(id: str) -> SuccessResponse[list[dict[str, Any]]]:
    scan = repo_service.scan_repository(id)
    return SuccessResponse(data=scan.get("files", []), message="Repository files retrieved")


@router.get(
    "/{id}/dependencies",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Get Dependency Graph",
    description="Returns static dependency graph links.",
)
async def get_repository_dependencies(id: str) -> SuccessResponse[dict[str, Any]]:
    graph = repo_service.get_dependencies(id)
    return SuccessResponse(data=graph, message="Dependency graph retrieved")


@router.get(
    "/{id}/references",
    response_model=SuccessResponse[list[dict[str, Any]]],
    summary="Find Symbol References",
    description="Finds all file references to a symbol identifier.",
)
async def get_repository_references(
    id: str,
    symbol_name: str = Query(..., description="Target symbol identifier to locate"),
) -> SuccessResponse[list[dict[str, Any]]]:
    refs = repo_service.find_references(id, symbol_name)
    return SuccessResponse(data=refs, message="Symbol references found")


@router.get(
    "/{id}/imports",
    response_model=SuccessResponse[list[dict[str, Any]]],
    summary="Get Repository Imports",
    description="Lists module dependencies and import relationships.",
)
async def get_repository_imports(
    id: str,
    file_path: str | None = Query(default=None),
) -> SuccessResponse[list[dict[str, Any]]]:
    imports = repo_service.get_imports(id, file_path=file_path)
    return SuccessResponse(data=imports, message="Imports retrieved")


@router.post(
    "/search/code",
    response_model=SuccessResponse[list[dict[str, Any]]],
    summary="Search Code in Repository",
    description="Finds text/regex occurrences across repository files.",
)
async def search_code_endpoint(
    payload: dict[str, Any],
) -> SuccessResponse[list[dict[str, Any]]]:
    repo_id = payload.get("repository_id") or payload.get("project_id", "")
    query = payload.get("query", "")
    limit = payload.get("limit", 50)
    matches = repo_service.search_code(repo_id, query, limit=limit)
    return SuccessResponse(data=matches, message="Code search completed")


@router.post(
    "/search/symbol",
    response_model=SuccessResponse[list[dict[str, Any]]],
    summary="Search Symbols in Repository",
    description="Finds AST symbols matching identifier query.",
)
async def search_symbol_endpoint(
    payload: dict[str, Any],
) -> SuccessResponse[list[dict[str, Any]]]:
    repo_id = payload.get("repository_id") or payload.get("project_id", "")
    symbol_name = payload.get("symbol_name") or payload.get("query", "")
    limit = payload.get("limit", 20)
    matches = repo_service.search_symbol(repo_id, symbol_name, limit=limit)
    return SuccessResponse(data=matches, message="Symbol search completed")


@router.get(
    "/projects/{id}",
    response_model=SuccessResponse[RepositoryMetadata],
    summary="Get Project Details",
    description="Retrieves metadata for a specific project/repository ID.",
)
async def get_project_details(
    id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
) -> SuccessResponse[RepositoryMetadata]:
    meta = await repo_service.get_repository_metadata_async(id, user_id=x_user_id)
    return SuccessResponse(data=meta, message="Project details found")


@router.delete(
    "/projects/{id}",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Delete Project Registration",
    description="Deletes project repository registration.",
)
async def delete_project_endpoint(
    id: str,
) -> SuccessResponse[dict[str, Any]]:
    res = await repo_service.delete_repository(id)
    return SuccessResponse(data=res, message="Project deleted successfully")

