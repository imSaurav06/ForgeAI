import pytest
from services.agent.app.core.patching.patch_normalizer import CanonicalPatchNormalizer, CanonicalPatch
from shared.exceptions.handlers import ValidationException


class TestCanonicalPatchNormalizer:
    def test_normalize_standard_code_payload(self):
        payload = {
            "analysis": "Add new feature",
            "files_to_create": [{"path": "src/feature.py", "content": "print('hello')"}],
            "files_to_modify": [{"path": "src/main.py", "patch": "import feature"}],
            "files_to_delete": ["old.py"],
        }
        patch = CanonicalPatchNormalizer.normalize(payload)
        assert len(patch.files_to_create) == 1
        assert patch.files_to_create[0]["path"] == "src/feature.py"
        assert patch.files_to_create[0]["content"] == "print('hello')"
        assert len(patch.files_to_modify) == 1
        assert patch.files_to_modify[0]["path"] == "src/main.py"
        assert patch.files_to_modify[0]["patch"] == "import feature"
        assert len(patch.files_to_delete) == 1
        assert patch.files_to_delete[0] == "old.py"

    def test_normalize_code_payload_with_unit_tests(self):
        payload = {
            "analysis": "Add feature and test",
            "files_to_modify": [{"path": "src/utils.py", "patch": "def foo(): pass"}],
            "unit_tests": [{"path": "tests/test_utils.py", "content": "def test_foo(): pass"}],
        }
        patch = CanonicalPatchNormalizer.normalize(payload)
        assert len(patch.files_to_modify) == 1
        assert len(patch.files_to_create) == 1
        assert patch.files_to_create[0]["path"] == "tests/test_utils.py"
        assert patch.files_to_create[0]["content"] == "def test_foo(): pass"

    def test_normalize_debug_mode_payload(self):
        """Regression test for P0-1: DEBUG schema with affected_file and patch."""
        payload = {
            "diagnosis": "Division by zero on line 42",
            "affected_file": "services/calc.py",
            "fix_description": "Add denominator zero check",
            "patch": "if b == 0: return 0\nreturn a / b",
            "verification_steps": ["Run pytest tests/test_calc.py"],
        }
        patch = CanonicalPatchNormalizer.normalize(payload)
        assert len(patch.files_to_modify) == 1
        assert patch.files_to_modify[0]["path"] == "services/calc.py"
        assert "if b == 0" in patch.files_to_modify[0]["patch"]
        assert len(patch.files_to_create) == 0
        assert len(patch.files_to_delete) == 0

    def test_normalize_test_mode_payload(self):
        """Regression test for P0-1: TEST schema with test_file_path and test_code."""
        payload = {
            "target_service": "AuthService",
            "test_file_path": "tests/test_auth.py",
            "test_cases_count": 3,
            "test_code": "import pytest\ndef test_login(): assert True",
        }
        patch = CanonicalPatchNormalizer.normalize(payload)
        assert len(patch.files_to_create) == 1
        assert patch.files_to_create[0]["path"] == "tests/test_auth.py"
        assert "test_login" in patch.files_to_create[0]["content"]

    def test_normalize_fenced_markdown_json_string(self):
        raw_text = """Here is the fix:
```json
{
  "affected_file": "app/main.py",
  "patch": "def main(): return 0"
}
```
Hope this helps!"""
        patch = CanonicalPatchNormalizer.normalize(raw_text)
        assert len(patch.files_to_modify) == 1
        assert patch.files_to_modify[0]["path"] == "app/main.py"

    def test_fail_closed_on_empty_payload(self):
        with pytest.raises(ValidationException, match="no actionable file operations"):
            CanonicalPatchNormalizer.normalize({
                "analysis": "No changes needed",
                "files_to_create": [],
                "files_to_modify": [],
                "files_to_delete": [],
            })

    def test_fail_closed_on_invalid_json(self):
        with pytest.raises(ValidationException):
            CanonicalPatchNormalizer.normalize("Not a json string at all")


class TestAgentToolDispatcher:
    @pytest.mark.asyncio
    async def test_tool_dispatcher_unknown_tool_fails_closed(self):
        from services.agent.app.core.tools.tool_dispatcher import AgentToolDispatcher

        dispatcher = AgentToolDispatcher()
        with pytest.raises(ValidationException, match="Unknown or unsupported tool action"):
            await dispatcher.execute_tool(
                tool_name="unauthorized_backdoor_tool",
                repository_id="repo_123",
                arguments={},
            )

    @pytest.mark.asyncio
    async def test_tool_dispatcher_validates_empty_path(self):
        from services.agent.app.core.tools.tool_dispatcher import AgentToolDispatcher

        dispatcher = AgentToolDispatcher()
        with pytest.raises(ValidationException, match="path is required"):
            await dispatcher.read_file(
                repository_id="repo_123",
                path="",
            )

