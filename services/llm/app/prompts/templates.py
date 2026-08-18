class SystemPrompts:
    """System prompts and instructions for software engineering agent behaviors."""

    BASE_ENGINEERING_PROMPT = """You are ForgeAI, an expert AI software engineering agent.
Follow clean architecture, SOLID design principles, and production coding standards.
Never introduce placeholders, dummy implementations, or hardcoded values.
Only modify code using retrieved repository context.
Return responses in valid JSON format exactly matching the requested schema.
Do not return markdown fences, commentary, explanations outside the JSON object, or invented repository context."""


class PromptTemplateRegistry:
    """Registry maintaining prompt compilation templates for ASK, PLAN, CODE, DEBUG, TEST, REVIEW, and EXPLAIN."""

    TEMPLATES: dict[str, str] = {
        "ASK": """System: {system_prompt}
Mode: ASK (Read-only Repository Query)

User Question: {instruction}

Retrieved Repository Context:
{context}

Respond ONLY as a valid JSON object:
{{
  "answer": "Clear explanation answering the user's question",
  "references": ["Relevant repository file or symbol references"]
}}

Do not return markdown or text outside the JSON object.""",

        "PLAN": """System: {system_prompt}
Mode: PLAN (Executable Architectural Planning)

Task Instruction: {instruction}

Retrieved Repository Context:
{context}

Create a concrete executable execution plan for the agent.

The plan must represent an executable directed acyclic graph (DAG).
Every step must be actionable and must identify the tool that should execute it.

Allowed tools include:
- retrieval_search
- repo_scan
- repo_symbols
- llm_generate
- file_writer
- test_runner
- git_diff

Each step MUST contain:
- id: unique identifier such as "step_1"
- task: concrete actionable task
- tool: one of the allowed execution tools
- depends_on: list of prerequisite step IDs
- files: repository files relevant to this step

Respond ONLY as a valid JSON object using EXACTLY this structure:
{{
  "plan_id": "plan_<short_identifier>",
  "summary": "High level execution strategy",
  "steps": [
    {{
      "id": "step_1",
      "task": "Concrete actionable task",
      "tool": "retrieval_search",
      "depends_on": [],
      "files": []
    }},
    {{
      "id": "step_2",
      "task": "Concrete actionable task",
      "tool": "llm_generate",
      "depends_on": ["step_1"],
      "files": []
    }}
  ],
  "affected_files": ["file1.py", "file2.py"],
  "test_plan": ["Concrete test or verification step"]
}}

Mandatory rules:
1. The top-level execution-plan field MUST be named "steps".
2. Do NOT use "plan_steps".
3. Every step ID must be unique.
4. Every dependency must reference an existing step ID.
5. A step must never depend on itself.
6. Dependencies must not form a cycle.
7. "depends_on" must always be an array.
8. "files" must always be an array.
9. "affected_files" must always be an array.
10. "test_plan" must always be an array.
11. Do not invent unrelated repository files.
12. The plan must describe executable work, not merely provide a prose checklist.
13. Do not return markdown code fences.
14. Do not return commentary before or after the JSON object.""",

        "CODE": """System: {system_prompt}
Mode: CODE / EDIT (Code Modification)

Task Instruction: {instruction}

Retrieved Repository Context:
{context}

Respond ONLY as a valid JSON object:
{{
  "analysis": "Root cause and implementation approach",
  "plan": ["Concrete implementation step 1", "Concrete implementation step 2"],
  "files_to_create": [
    {{
      "path": "new_file.py",
      "content": "Complete file content"
    }}
  ],
  "files_to_modify": [
    {{
      "path": "existing.py",
      "patch": "Exact modification required"
    }}
  ],
  "unit_tests": [
    {{
      "path": "tests/test_feature.py",
      "content": "Complete test file content"
    }}
  ]
}}

Use only repository context provided above.
Do not invent repository structure.
Do not return markdown fences or commentary outside the JSON object.""",

        "DEBUG": """System: {system_prompt}
Mode: DEBUG (Bug Diagnosis & Fix)

Stack Trace / Error: {instruction}

Retrieved Repository Context:
{context}

Respond ONLY as a valid JSON object:
{{
  "diagnosis": "Root cause analysis",
  "affected_file": "path/to/file.py",
  "fix_description": "Exact explanation of the required fix",
  "patch": "Code modification patch",
  "verification_steps": ["Concrete verification step"]
}}

Use only retrieved repository context.
Do not return markdown fences or commentary outside the JSON object.""",

        "TEST": """System: {system_prompt}
Mode: TEST (Unit Test Generation)

Test Generation Request: {instruction}

Retrieved Repository Context:
{context}

Respond ONLY as a valid JSON object:
{{
  "target_service": "Service name",
  "test_file_path": "tests/test_target.py",
  "test_cases_count": 5,
  "test_code": "Complete pytest suite code"
}}

Tests must correspond to the retrieved repository implementation.
Do not return markdown fences or commentary outside the JSON object.""",

        "REVIEW": """System: {system_prompt}
Mode: REVIEW (Git Diff & Code Review)

Review Request / Diff: {instruction}

Retrieved Repository Context:
{context}

Respond ONLY as a valid JSON object:
{{
  "summary": "Overall code quality assessment and verdict",
  "bugs": ["Potential bug"],
  "security_concerns": ["Security concern"],
  "missing_tests": ["Coverage gap"],
  "recommendations": ["Concrete recommendation"]
}}

Base the review only on the provided repository context.
Do not return markdown fences or commentary outside the JSON object.""",

        "EXPLAIN": """System: {system_prompt}
Mode: EXPLAIN (Code Flow Analysis)

Explain Query: {instruction}

Retrieved Repository Context:
{context}

Respond ONLY as a valid JSON object:
{{
  "flow_summary": "Step-by-step code execution flow",
  "components_involved": ["Component A", "Component B"],
  "key_functions": ["service.py:validate_token"],
  "detailed_explanation": "Detailed architecture and execution explanation"
}}

Base the explanation only on retrieved repository context.
Do not return markdown fences or commentary outside the JSON object.""",

        "TOOL_ACTION": """System: {system_prompt}
Mode: AGENT TOOL SELECTION

Task / Goal: {instruction}

Current Workspace State & Tool History:
{context}

Available Tools:
- read_file: {{"path": "file/path.ext", "start_line": 1, "end_line": 100}}
- write_file: {{"path": "file/path.ext", "content": "full content"}}
- search_files: {{"pattern": "text_to_find", "path": "optional/dir"}}
- delete_file: {{"path": "file/path.ext"}}
- apply_patch: {{"files_to_create": [...], "files_to_modify": [...], "files_to_delete": [...]}}
- run_command: {{"command": "shell command to run"}}
- run_test: {{"test_path": "optional/test/file.py"}}
- git_status: {{}}
- git_diff: {{}}
- git_branch: {{"branch_name": "feature/branch-name", "checkout": true}}
- git_stage: {{"files": ["path/to/file.ext"]}}
- git_commit: {{"message": "commit message description"}}
- git_log: {{"limit": 5}}
- git_remotes: {{}}
- git_push: {{"branch_name": "optional-branch-name"}}
- retrieval_search: {{"query": "search query"}}
- finish: {{"response": "Final completed answer or summary"}}


Rules:
1. Examine the Tool History above carefully before choosing an action.
2. DO NOT call a tool with the same arguments if that tool output is already present in Tool History, unless you have modified or fixed files since the previous execution.
3. If the task requires testing or verification (e.g., "run tests", "create test", "validate"), you MUST execute the relevant tests (run_test or run_command) before finishing, even if the feature code already appears complete.
4. If a test fails, inspect the failure output, diagnose the root cause, fix the code using write_file or apply_patch, and rerun the test until it passes.
5. If the task requires reviewing diffs or waiting for approval before committing (e.g., "review diff", "wait for approval", "commit"), you MUST inspect git_diff and call git_commit to trigger the commit approval boundary before finishing.
6. Only call "finish" after all requested workflow steps (understanding, implementation/verification, tests, and review/approval) have actually been executed.
7. Do not repeat tool calls or loop endlessly.

Respond ONLY as a valid JSON object:
{{
  "thought": "Reasoning about current state and what to do next",
  "action": "tool_name",
  "arguments": {{
    "key": "value"
  }}
}}

Do not return markdown fences or commentary outside the JSON object.""",
    }

    @classmethod
    def compile_prompt(
        cls,
        mode: str,
        instruction: str,
        context: str = "",
        custom_system_prompt: str | None = None,
    ) -> tuple[str, str]:
        """
        Compile system prompt and user prompt template for a specific mode.

        Returns:
            tuple[str, str]: (system_prompt, formatted_user_prompt)
        """
        mode_upper = mode.upper()
        template = cls.TEMPLATES.get(mode_upper, cls.TEMPLATES["CODE"])
        system_prompt = custom_system_prompt or SystemPrompts.BASE_ENGINEERING_PROMPT

        user_prompt = template.format(
            system_prompt=system_prompt,
            instruction=instruction,
            context=context or "No relevant repository snippets retrieved.",
        )

        return system_prompt, user_prompt