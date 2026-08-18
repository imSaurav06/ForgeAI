from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from shared.exceptions.handlers import ValidationException
from shared.logging.logger import logger


@dataclass
class CanonicalPatch:
    """Canonical internal patch and filesystem modification representation."""

    files_to_create: list[dict[str, str]] = field(default_factory=list)
    files_to_modify: list[dict[str, str]] = field(default_factory=list)
    files_to_delete: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.files_to_create or self.files_to_modify or self.files_to_delete)

    def to_dict(self, repository_id: str) -> dict[str, Any]:
        return {
            "repository_id": repository_id,
            "files_to_create": self.files_to_create,
            "files_to_modify": self.files_to_modify,
            "files_to_delete": self.files_to_delete,
        }


class CanonicalPatchNormalizer:
    """
    Normalizes diverse LLM output schemas (CODE, DEBUG, TEST, repair loops, single-file patches)
    into a canonical internal representation (files_to_create, files_to_modify, files_to_delete)
    expected by the PatchEngine.

    Enforces strict fail-closed validation on invalid, empty, or malformed payloads.
    """

    @classmethod
    def normalize(cls, raw_input: str | dict[str, Any]) -> CanonicalPatch:
        """
        Parse and normalize raw LLM output into a CanonicalPatch.

        Raises:
            ValidationException: When the input cannot be parsed or yields zero valid file operations.
        """
        data = cls._extract_dict(raw_input)
        if not isinstance(data, dict):
            raise ValidationException(
                message="LLM patch payload must be a valid JSON object"
            )

        files_to_create: list[dict[str, str]] = []
        files_to_modify: list[dict[str, str]] = []
        files_to_delete: list[str] = []

        # Validation of explicit multi-file keys if provided
        if "files_to_create" in data and data["files_to_create"] is not None and not isinstance(data["files_to_create"], list):
            raise ValidationException(message="files_to_create must be a list")
        if "files_to_modify" in data and data["files_to_modify"] is not None and not isinstance(data["files_to_modify"], list):
            raise ValidationException(message="files_to_modify must be a list")
        if "files_to_delete" in data and data["files_to_delete"] is not None and not isinstance(data["files_to_delete"], list):
            raise ValidationException(message="files_to_delete must be a list")

        # 1. Standard multi-file lists (CODE / general patch schema)
        raw_create = data.get("files_to_create")
        if isinstance(raw_create, list):
            for idx, item in enumerate(raw_create):
                norm_item = cls._normalize_create_item(item, idx)
                if norm_item:
                    files_to_create.append(norm_item)

        raw_modify = data.get("files_to_modify")
        if isinstance(raw_modify, list):
            for idx, item in enumerate(raw_modify):
                norm_item = cls._normalize_modify_item(item, idx)
                if norm_item:
                    files_to_modify.append(norm_item)

        raw_delete = data.get("files_to_delete")
        if isinstance(raw_delete, list):
            for idx, item in enumerate(raw_delete):
                norm_del = cls._normalize_delete_item(item, idx)
                if norm_del:
                    files_to_delete.append(norm_del)

        # 2. unit_tests array (found in CODE mode prompts)
        raw_tests = data.get("unit_tests")
        if isinstance(raw_tests, list):
            for idx, test_item in enumerate(raw_tests):
                norm_test = cls._normalize_create_item(test_item, idx, default_content_key="content")
                if norm_test:
                    # Avoid duplicate if already present in files_to_create
                    if not any(f["path"] == norm_test["path"] for f in files_to_create):
                        files_to_create.append(norm_test)

        # 3. DEBUG mode single-file schema: {"affected_file": "...", "patch": "..."}
        affected_file = (
            data.get("affected_file")
            or data.get("target_file")
            or data.get("file_path")
            or data.get("filename")
            or data.get("file")
        )
        patch_content = (
            data.get("patch")
            or data.get("fix")
            or data.get("code")
            or data.get("content")
            or data.get("fix_code")
        )

        if isinstance(affected_file, str) and affected_file.strip() and isinstance(patch_content, str) and patch_content.strip():
            clean_path = affected_file.strip().replace("\\", "/")
            if not any(f["path"] == clean_path for f in files_to_modify):
                files_to_modify.append({
                    "path": clean_path,
                    "patch": patch_content.strip(),
                })

        # 4. TEST mode schema: {"test_file_path": "...", "test_code": "..."}
        test_file_path = data.get("test_file_path") or data.get("test_path")
        test_code = data.get("test_code")
        if isinstance(test_file_path, str) and test_file_path.strip() and isinstance(test_code, str) and test_code.strip():
            clean_test_path = test_file_path.strip().replace("\\", "/")
            if not any(f["path"] == clean_test_path for f in files_to_create):
                files_to_create.append({
                    "path": clean_test_path,
                    "content": test_code.strip(),
                })

        # 5. Direct single-file modification: {"path": "...", "content": "..."} or {"path": "...", "patch": "..."}
        path_key = data.get("path")
        if isinstance(path_key, str) and path_key.strip():
            clean_p = path_key.strip().replace("\\", "/")
            if "content" in data and isinstance(data["content"], str) and data["content"].strip():
                if not any(f["path"] == clean_p for f in files_to_create) and not any(f["path"] == clean_p for f in files_to_modify):
                    files_to_create.append({"path": clean_p, "content": data["content"].strip()})
            elif "patch" in data and isinstance(data["patch"], str) and data["patch"].strip():
                if not any(f["path"] == clean_p for f in files_to_modify):
                    files_to_modify.append({"path": clean_p, "patch": data["patch"].strip()})

        # Canonical result
        canonical = CanonicalPatch(
            files_to_create=files_to_create,
            files_to_modify=files_to_modify,
            files_to_delete=files_to_delete,
        )

        if canonical.is_empty:
            raise ValidationException(
                message="LLM returned an empty patch with no actionable file operations (files_to_create, files_to_modify, files_to_delete, affected_file, or unit_tests were all empty or missing required code)"
            )

        return canonical

    @classmethod
    def _extract_dict(cls, raw_input: str | dict[str, Any]) -> dict[str, Any]:
        """Extract a Python dictionary from JSON string, markdown code fences, or dict."""
        if isinstance(raw_input, dict):
            return raw_input

        if not isinstance(raw_input, str):
            raise ValidationException(message="Patch payload must be a string or JSON dictionary")

        raw_text = raw_input.strip()
        if not raw_text:
            raise ValidationException(message="Patch payload is empty")

        # Check for fenced json code blocks
        fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw_text)
        candidate_str = fenced_match.group(1).strip() if fenced_match else raw_text

        # Extract outer braces
        start = candidate_str.find("{")
        end = candidate_str.rfind("}")
        if start != -1 and end != -1 and start <= end:
            json_str = candidate_str[start : end + 1]
        else:
            json_str = candidate_str

        try:
            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as exc:
            logger.error(f"JSON parsing error during patch normalization: {exc}")
            raise ValidationException(
                message=f"LLM returned an invalid JSON patch payload: {exc}"
            ) from exc

        raise ValidationException(message="Could not extract a valid JSON object from LLM patch output")

    @classmethod
    def _normalize_create_item(cls, item: Any, index: int, default_content_key: str = "content") -> dict[str, str]:
        """Validate and normalize a single file creation item."""
        if not isinstance(item, dict):
            raise ValidationException(
                message=f"Invalid item in files_to_create at index {index}: item must be a JSON object"
            )

        raw_path = item.get("path") or item.get("file") or item.get("filename")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValidationException(
                message=f"Invalid item in files_to_create at index {index}: 'path' must be a non-empty string"
            )

        content = item.get("content") or item.get(default_content_key) or item.get("code")
        if content is None or not isinstance(content, str):
            raise ValidationException(
                message=f"Invalid item in files_to_create at index {index} ('{raw_path}'): 'content' must be a string"
            )

        return {
            "path": raw_path.strip().replace("\\", "/"),
            "content": content,
        }

    @classmethod
    def _normalize_modify_item(cls, item: Any, index: int) -> dict[str, str]:
        """Validate and normalize a single file modification item."""
        if not isinstance(item, dict):
            raise ValidationException(
                message=f"Invalid item in files_to_modify at index {index}: item must be a JSON object"
            )

        raw_path = item.get("path") or item.get("file") or item.get("filename")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValidationException(
                message=f"Invalid item in files_to_modify at index {index}: 'path' must be a non-empty string"
            )

        patch = item.get("patch") or item.get("content") or item.get("diff") or item.get("fix")
        if patch is None or not isinstance(patch, str):
            raise ValidationException(
                message=f"Invalid item in files_to_modify at index {index} ('{raw_path}'): 'patch' or 'content' must be a string"
            )

        result: dict[str, str] = {
            "path": raw_path.strip().replace("\\", "/"),
        }
        if "patch" in item:
            result["patch"] = str(item["patch"])
        elif "content" in item:
            result["content"] = str(item["content"])
        else:
            result["patch"] = str(patch)

        return result

    @classmethod
    def _normalize_delete_item(cls, item: Any, index: int) -> str:
        """Validate and normalize a single file deletion item."""
        if isinstance(item, str) and item.strip():
            return item.strip().replace("\\", "/")

        if isinstance(item, dict):
            raw_path = item.get("path") or item.get("file")
            if isinstance(raw_path, str) and raw_path.strip():
                return raw_path.strip().replace("\\", "/")

        raise ValidationException(
            message=f"Invalid item in files_to_delete at index {index}: must be a non-empty relative file path string"
        )
