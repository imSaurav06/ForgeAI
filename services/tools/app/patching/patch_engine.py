from pathlib import Path
from typing import Any

from services.tools.app.sandbox.security_sandbox import SecuritySandbox
from shared.exceptions.handlers import ValidationException
from shared.logging.logger import logger


class PatchEngine:
    """
    Patch Engine executing atomic multi-file patch modifications with
    pre-patch backup snapshots and automatic rollback on conflict/failure.
    """

    def __init__(self, sandbox: SecuritySandbox | None = None) -> None:
        self.sandbox = sandbox or SecuritySandbox()

    def apply_patch(
        self,
        repository_root: Path | None = None,
        base_root: Path | None = None,
        files_to_create: list[dict[str, str]] | None = None,
        files_to_modify: list[dict[str, str]] | None = None,
        files_to_delete: list[str] | None = None,
    ) -> dict[str, Any]:
        root = repository_root or base_root or self.sandbox.workspace_root
        return self.apply_file_patches(
            repository_root=root,
            files_to_create=files_to_create,
            files_to_modify=files_to_modify,
            files_to_delete=files_to_delete,
        )

    def apply_file_patches(
        self,
        repository_root: Path,
        files_to_create: list[dict[str, str]] | None = None,
        files_to_modify: list[dict[str, str]] | None = None,
        files_to_delete: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Apply an atomic multi-file patch operation inside the selected
        repository with pre-patch backups and automatic rollback.
        """
        files_to_create = files_to_create or []
        files_to_modify = files_to_modify or []
        files_to_delete = files_to_delete or []

        repository_root = repository_root.resolve()

        if not repository_root.is_dir():
            raise ValidationException(
                message=f"Repository root does not exist: {repository_root}"
            )

        backup_snapshots: dict[Path, str | None] = {}
        modified_paths: list[Path] = []
        created_paths: list[Path] = []
        deleted_paths: list[Path] = []

        try:
            create_paths: list[tuple[Path, dict[str, str]]] = []
            modify_paths: list[tuple[Path, dict[str, str]]] = []
            delete_paths: list[Path] = []

            # Step 1: Validate every requested path before changing anything.
            for item in files_to_create:
                path = self.sandbox.validate_safe_path(
                    item["path"],
                    base_root=repository_root,
                )

                if path.exists():
                    raise ValidationException(
                        message=(
                            f"Cannot create '{item['path']}': "
                            "file already exists"
                        )
                    )

                create_paths.append((path, item))

            for item in files_to_modify:
                path = self.sandbox.validate_safe_path(
                    item["path"],
                    base_root=repository_root,
                )

                if not path.exists():
                    raise ValidationException(
                        message=(
                            f"Cannot modify '{item['path']}': "
                            "file does not exist"
                        )
                    )

                if not path.is_file():
                    raise ValidationException(
                        message=(
                            f"Cannot modify '{item['path']}': "
                            "path is not a file"
                        )
                    )

                modify_paths.append((path, item))

            for rel_path in files_to_delete:
                path = self.sandbox.validate_safe_path(
                    rel_path,
                    base_root=repository_root,
                )

                if not path.exists():
                    raise ValidationException(
                        message=(
                            f"Cannot delete '{rel_path}': "
                            "file does not exist"
                        )
                    )

                if not path.is_file():
                    raise ValidationException(
                        message=(
                            f"Cannot delete '{rel_path}': "
                            "path is not a file"
                        )
                    )

                delete_paths.append(path)

            # Step 2: Snapshot every existing file that may be changed/deleted.
            for path, _ in modify_paths:
                backup_snapshots[path] = path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )

            for path in delete_paths:
                backup_snapshots[path] = path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )

            # Step 3: Create files.
            for path, item in create_paths:
                path.parent.mkdir(parents=True, exist_ok=True)

                path.write_text(
                    item.get("content", ""),
                    encoding="utf-8",
                )

                created_paths.append(path)

            # Step 4: Modify files.
            for path, item in modify_paths:
                patch_content = (
                    item.get("patch")
                    or item.get("content", "")
                )

                path.write_text(
                    patch_content,
                    encoding="utf-8",
                )

                modified_paths.append(path)

            # Step 5: Delete files.
            for path in delete_paths:
                path.unlink()
                deleted_paths.append(path)

            return {
                "success": True,
                "created_count": len(created_paths),
                "modified_count": len(modified_paths),
                "deleted_count": len(deleted_paths),
            }

        except Exception as err:
            logger.error(
                "Patch execution failed, initiating automatic rollback: "
                f"{err}",
                exc_info=True,
            )

            # Roll back modified/deleted files.
            for path, original_content in backup_snapshots.items():
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        original_content or "",
                        encoding="utf-8",
                    )
                except Exception as rollback_err:
                    logger.error(
                        f"Failed rolling back file {path}: "
                        f"{rollback_err}",
                        exc_info=True,
                    )

            # Remove files that were created during the failed operation.
            for path in created_paths:
                try:
                    if path.is_file():
                        path.unlink()
                except Exception as rollback_err:
                    logger.error(
                        f"Failed removing created file {path}: "
                        f"{rollback_err}",
                        exc_info=True,
                    )

            if isinstance(err, ValidationException):
                raise

            raise ValidationException(
                message=(
                    "Patch application failed. "
                    f"All possible changes were rolled back: {err}"
                )
            ) from err