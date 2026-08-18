import re
from pathlib import Path

from shared.config.settings import get_settings
from shared.exceptions.handlers import UnauthorizedException, ValidationException


class SecuritySandbox:
    """Path/command security boundary for tool execution."""

    DANGEROUS_COMMAND_PATTERNS: list[str] = [
        r"rm\s+-rf\s+/", r"mkfs", r"dd\s+if=", r"shutdown", r"reboot",
        r"format\s+[a-z]:", r":\(\)\s*{\s*:\s*\|\s*:\s*&\s*}\s*;",
        r"chmod\s+-R\s+777\s+/",
    ]

    SECRET_MASK_PATTERNS: list[tuple[str, str]] = [
        (r'(?i)(secret_key|password|api_key|token|access_token)="?[^\s"]+"?', r"\1=***MASKED***"),
        (r"(?i)(bearer\s+)[a-zA-Z0-9_\-\.]+", r"\1***MASKED***"),
    ]

    def __init__(self, workspace_root: str | Path | None = None) -> None:
        root = workspace_root or get_settings().workspace_root
        self.workspace_root = Path(root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _resolve_base_root(base_root: str | Path) -> Path:
        raw = str(base_root).replace("\\", "/")
        root = Path(raw)
        if not root.is_dir():
            if raw.lower().startswith("e:/") and Path("/host_e/" + raw[3:]).is_dir():
                root = Path("/host_e/" + raw[3:]).resolve()
            elif raw.lower().startswith("f:/") and Path("/host_f/" + raw[3:]).is_dir():
                root = Path("/host_f/" + raw[3:]).resolve()
            elif raw.lower().startswith("c:/") and Path("/host_c/" + raw[3:]).is_dir():
                root = Path("/host_c/" + raw[3:]).resolve()
        if not root.is_dir():
            raise ValidationException(message=f"Invalid sandbox base root: {base_root}")
        return root.resolve()

    def validate_safe_path(self, target_path: str | Path, base_root: str | Path | None = None) -> Path:
        root = self._resolve_base_root(base_root) if base_root is not None else self.workspace_root
        if target_path is None or str(target_path).strip() in ("", "."):
            return root

        raw = str(target_path).strip().replace("\\", "/")
        if bool(re.match(r"^[a-zA-Z]:", raw)):
            raise UnauthorizedException(
                message=f"Absolute external path blocked: '{target_path}' contains drive specifier outside sandbox"
            )

        target = Path(raw)
        if target.is_absolute():
            try:
                resolved = target.resolve()
                if resolved == root or resolved.is_relative_to(root):
                    return resolved
            except Exception:
                pass
            raise UnauthorizedException(
                message=f"Absolute external path blocked: '{target_path}' contains drive specifier outside sandbox"
            )

        if raw.startswith("/") or raw.startswith("//"):
            raise UnauthorizedException(
                message=f"Absolute path blocked: '{target_path}' cannot start with root slash"
            )

        try:
            resolved = (root / target).resolve()
        except Exception as err:
            raise ValidationException(message=f"Invalid path format: {target_path}") from err

        if not resolved.is_relative_to(root):
            raise UnauthorizedException(
                message=f"Path traversal blocked: target path '{target_path}' escapes sandbox boundary '{root}'"
            )
        return resolved

    def validate_execution_path(self, target_path: str | Path, base_root: str | Path) -> Path:
        resolved = self.validate_safe_path(target_path, base_root=base_root)
        if not resolved.is_dir():
            raise ValidationException(message=f"Execution directory does not exist: {resolved}")
        return resolved

    def validate_safe_command(self, command: str) -> str:
        clean = command.strip()
        for pattern in self.DANGEROUS_COMMAND_PATTERNS:
            if re.search(pattern, clean):
                raise UnauthorizedException(
                    message=f"Command execution blocked: dangerous system pattern '{pattern}' detected in command"
                )
        return clean

    def validate_terminal_workspace(self, workspace_path: str | Path) -> Path:
        resolved = Path(workspace_path).resolve()
        root = self.workspace_root.resolve()
        if not resolved.is_relative_to(root):
            raise UnauthorizedException(
                message=f"Terminal workspace blocked: '{workspace_path}' is outside the allowed workspace boundary '{root}'"
            )
        if not resolved.is_dir():
            raise ValidationException(message=f"Terminal workspace does not exist: {resolved}")
        return resolved

    @classmethod
    def mask_secrets(cls, text: str) -> str:
        masked = text
        for pattern, replacement in cls.SECRET_MASK_PATTERNS:
            masked = re.sub(pattern, replacement, masked)
        return masked