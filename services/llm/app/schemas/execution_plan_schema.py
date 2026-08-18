from typing import Any


EXECUTION_PLAN_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "plan_id",
        "summary",
        "steps",
        "affected_files",
        "test_plan",
    ],
    "properties": {
        "plan_id": {
            "type": "string",
        },
        "summary": {
            "type": "string",
        },
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "task",
                    "tool",
                    "depends_on",
                    "files",
                ],
                "properties": {
                    "id": {
                        "type": "string",
                    },
                    "task": {
                        "type": "string",
                    },
                    "tool": {
                        "type": "string",
                        "enum": [
                            "retrieval_search",
                            "repo_scan",
                            "repo_symbols",
                            "llm_generate",
                            "file_writer",
                            "test_runner",
                            "git_diff",
                        ],
                    },
                    "depends_on": {
                        "type": "array",
                        "items": {
                            "type": "string",
                        },
                    },
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "string",
                        },
                    },
                },
            },
        },
        "affected_files": {
            "type": "array",
            "items": {
                "type": "string",
            },
        },
        "test_plan": {
            "type": "array",
            "items": {
                "type": "string",
            },
        },
    },
}