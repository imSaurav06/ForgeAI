import subprocess
from pathlib import Path
from typing import Any

import httpx

from shared.config.settings import get_settings
from shared.exceptions.handlers import ValidationException
from shared.logging.logger import logger


def _resolve_repo_path(repository_id: str | None) -> Path | None:
    if not repository_id:
        return None
    try:
        from services.repository.app.services.repository_service import RepositoryService
        repo_svc = RepositoryService()
        meta = repo_svc.get_repository_metadata(repository_id)
        if meta and meta.path:
            return Path(meta.path).resolve()
    except Exception:
        pass

    try:
        repo_url = f"http://repository:8003/v1/repositories/{repository_id}"
        resp = httpx.get(repo_url, timeout=2.0)
        if resp.status_code == 200:
            data = resp.json().get("data", {})
            p = data.get("path")
            if p:
                return Path(p).resolve()
    except Exception:
        pass
    return None


class GitService:
    """Git Service executing native version control commands on target repository workspace."""

    def __init__(self, repo_dir: str | Path | None = None) -> None:
        settings = get_settings()
        self.repo_dir = Path(repo_dir or settings.workspace_root).resolve()
        self.repo_dir.mkdir(parents=True, exist_ok=True)

    def _run_git(self, args: list[str], target_dir: Path | None = None) -> subprocess.CompletedProcess[str]:
        """Run git subprocess command inside target repository directory and return CompletedProcess."""
        cwd_dir = target_dir or self.repo_dir
        try:
            return subprocess.run(
                ["git"] + args,
                cwd=str(cwd_dir),
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as err:
            logger.warning(f"Git command execution failed in '{cwd_dir}': {err}")
            return subprocess.CompletedProcess(args=args, returncode=1, stdout="", stderr=str(err))

    def _exec_git(self, args: list[str], target_dir: Path | None = None) -> str:
        """Run git subprocess command and return stdout text."""
        res = self._run_git(args, target_dir=target_dir)
        return res.stdout.strip()

    def get_status(self, repository_id: str | None = None) -> dict[str, Any]:
        """Fetch git branch and workspace status for target repository with dual schema support."""
        target_dir = _resolve_repo_path(repository_id) or self.repo_dir
        branch = self._exec_git(["branch", "--show-current"], target_dir=target_dir)
        status_res = self._run_git(["status", "--porcelain"], target_dir=target_dir)
        status_raw = status_res.stdout

        staged: list[str] = []
        modified: list[str] = []
        untracked: list[str] = []

        for line in status_raw.splitlines():
            if not line or len(line) < 3:
                continue
            index_state = line[0]
            work_state = line[1]
            filepath = line[3:].strip()

            if index_state in ("A", "M", "R", "C", "U"):
                staged.append(filepath)
            if work_state == "M":
                modified.append(filepath)
            elif index_state == "?" and work_state == "?":
                untracked.append(filepath)

        return {
            "branch": branch,
            "clean": len(staged) == 0 and len(modified) == 0 and len(untracked) == 0,
            "staged": staged,
            "unstaged": modified,
            "untracked": untracked,
            "staged_files": staged,
            "modified_files": modified,
            "untracked_files": untracked,
        }

    def get_diff(self, repository_id: str | None = None) -> dict[str, Any]:
        """Fetch unified diff text for workspace changes."""
        target_dir = _resolve_repo_path(repository_id) or self.repo_dir
        diff_text = self._exec_git(["diff", "HEAD"], target_dir=target_dir) or self._exec_git(["diff"], target_dir=target_dir)
        changed_count = diff_text.count("diff --git") if diff_text else 0

        return {
            "diff": diff_text,
            "diff_text": diff_text,
            "files_changed": max(changed_count, 1 if diff_text else 0),
            "files_changed_count": max(changed_count, 1 if diff_text else 0),
        }

    def get_log(self, limit: int = 10, repository_id: str | None = None) -> list[dict[str, Any]]:
        """Fetch commit history log."""
        target_dir = _resolve_repo_path(repository_id) or self.repo_dir
        log_raw = self._exec_git(["log", f"-n{limit}", "--pretty=format:%H|%an|%ad|%s"], target_dir=target_dir)
        commits: list[dict[str, Any]] = []

        for line in log_raw.splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append(
                    {
                        "hash": parts[0],
                        "author": parts[1],
                        "date": parts[2],
                        "message": parts[3],
                    }
                )

        return commits

    def stage(self, files: list[str] | None = None, repository_id: str | None = None) -> dict[str, Any]:
        """Stage specific or all files (git add)."""
        target_dir = _resolve_repo_path(repository_id) or self.repo_dir
        args = ["add"]
        if files:
            args.extend(files)
        else:
            args.append(".")

        res = self._run_git(args, target_dir=target_dir)
        if res.returncode != 0:
            err_msg = res.stderr.strip() or f"git add returned code {res.returncode}"
            raise ValidationException(message=f"Git stage failed: {err_msg}")

        return {"status": "success", "success": True, "message": "Staged files successfully"}

    def unstage(self, files: list[str] | None = None, repository_id: str | None = None) -> dict[str, Any]:
        """Unstage specific or all files (git restore --staged or git rm --cached for initial repo)."""
        target_dir = _resolve_repo_path(repository_id) or self.repo_dir
        args = ["restore", "--staged"]
        if files:
            args.extend(files)
        else:
            args.append(".")

        res = self._run_git(args, target_dir=target_dir)
        if res.returncode != 0 and "could not resolve 'head'" in res.stderr.lower():
            # Initial repository with no commits yet: fallback to git rm --cached
            rm_args = ["rm", "--cached", "-r", "--ignore-unmatch"]
            if files:
                rm_args.extend(files)
            else:
                rm_args.append(".")
            res = self._run_git(rm_args, target_dir=target_dir)
            logger.info(f"UNSTAGE RM EXEC: dir={target_dir}, args={rm_args}, code={res.returncode}, out={res.stdout}, err={res.stderr}")

        if res.returncode != 0:
            err_msg = res.stderr.strip() or f"git restore --staged returned code {res.returncode}"
            raise ValidationException(message=f"Git unstage failed: {err_msg}")

        return {"status": "success", "success": True, "message": "Unstaged files successfully"}

    def create_branch(self, branch_name: str, checkout: bool = True, repository_id: str | None = None) -> dict[str, Any]:
        """Create a new branch."""
        target_dir = _resolve_repo_path(repository_id) or self.repo_dir
        clean_name = branch_name.strip()
        if not clean_name:
            raise ValidationException(message="Branch name cannot be empty")

        args = ["checkout", "-b", clean_name] if checkout else ["branch", clean_name]
        res = self._run_git(args, target_dir=target_dir)
        if res.returncode != 0:
            err_msg = res.stderr.strip() or f"git branch creation returned code {res.returncode}"
            raise ValidationException(message=f"Git branch creation failed: {err_msg}")

        return {"status": "success", "success": True, "message": f"Branch '{clean_name}' created successfully"}

    def checkout(self, target: str, repository_id: str | None = None) -> dict[str, Any]:
        """Checkout existing branch or commit."""
        target_dir = _resolve_repo_path(repository_id) or self.repo_dir
        res = self._run_git(["checkout", target], target_dir=target_dir)
        if res.returncode != 0:
            err_msg = res.stderr.strip() or f"git checkout returned code {res.returncode}"
            raise ValidationException(message=f"Git checkout failed: {err_msg}")

        return {"status": "success", "success": True, "message": f"Checked out target '{target}'"}

    def commit(self, message: str, author: str | None = None, files: list[str] | None = None, repository_id: str | None = None) -> dict[str, Any]:
        """Stage files and create commit."""
        target_dir = _resolve_repo_path(repository_id) or self.repo_dir
        if files:
            stage_res = self._run_git(["add"] + files, target_dir=target_dir)
            if stage_res.returncode != 0:
                raise ValidationException(message=f"Git commit staging failed: {stage_res.stderr.strip()}")
        else:
            stage_res = self._run_git(["add", "."], target_dir=target_dir)
            if stage_res.returncode != 0:
                raise ValidationException(message=f"Git commit staging failed: {stage_res.stderr.strip()}")

        cmd = ["commit", "-m", message]
        if author:
            cmd.extend(["--author", author])

        res = self._run_git(cmd, target_dir=target_dir)
        if res.returncode != 0:
            err_msg = res.stderr.strip() or f"git commit returned code {res.returncode}"
            raise ValidationException(message=f"Git commit failed: {err_msg}")

        return {"status": "success", "success": True, "message": f"Committed changes: '{message}'"}

    def restore(self, staged: bool = False, files: list[str] | None = None, repository_id: str | None = None) -> dict[str, Any]:
        """Restore files or discard workspace changes."""
        target_dir = _resolve_repo_path(repository_id) or self.repo_dir
        cmd = ["restore"]
        if staged:
            cmd.append("--staged")

        if files:
            cmd.extend(files)
        else:
            cmd.append(".")

        res = self._run_git(cmd, target_dir=target_dir)
        if res.returncode != 0:
            err_msg = res.stderr.strip() or f"git restore returned code {res.returncode}"
            raise ValidationException(message=f"Git restore failed: {err_msg}")

        return {"status": "success", "success": True, "message": "Restored workspace files"}
