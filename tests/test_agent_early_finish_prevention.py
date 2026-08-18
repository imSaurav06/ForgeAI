"""
Regression Test Suite for Stage 2B Agent Early-Finish Prevention
================================================================
Validates that in CODE mode (and other engineering execution modes),
the Agent cannot prematurely terminate with 'finish' merely because
a requested feature already exists on disk.

The Agent must establish complete verification evidence (e.g. executing tests,
reviewing git status/diff, and respecting commit approval boundaries).
"""

import pytest
from services.agent.app.core.sessions.session_store import AgentExecutionRun, get_agent_session_store
from services.agent.app.core.state_machine.states import AgentState
from services.agent.app.core.workflows.orchestrator import AgentWorkflowOrchestrator


class TestAgentEarlyFinishPrevention:
    """Test suite ensuring CODE mode does not equate 'feature already exists' with 'workflow complete'."""

    def test_validate_finish_rejects_untested_code_task(self):
        """
        GIVEN a CODE mode run with an instruction requesting implementation + test verification,
        AND the agent has only performed retrieval and read_file (feature already exists on disk),
        WHEN the agent attempts to call finish without running tests,
        THEN _validate_finish_action MUST return a validation requirement message and reject finish.
        """
        orch = AgentWorkflowOrchestrator()
        run = AgentExecutionRun(
            run_id="test_run_early_finish_1",
            project_id="proj_1",
            repository_id="repo_1",
            mode="CODE",
            instruction="Add /health endpoint, create tests, run the relevant tests and verify.",
            state=AgentState.CODING,
            steps=[
                {
                    "step": "step_1_retrieval_search",
                    "arguments": {"query": "health endpoint"},
                    "output": [{"file_path": "src/server.js"}],
                },
                {
                    "step": "step_2_read_file",
                    "arguments": {"path": "src/server.js"},
                    "output": {"content": "app.get('/health', ...)"},
                },
            ],
        )

        validation_err = orch._validate_finish_action(
            run=run,
            thought="Feature already exists, calling finish.",
            arguments={"response": "No changes needed."},
        )

        assert validation_err is not None
        assert "Validation Required" in validation_err
        assert "test" in validation_err.lower()

    def test_validate_finish_rejects_unreviewed_commit_task(self):
        """
        GIVEN a CODE mode run with an instruction requesting review / approval before commit,
        AND the agent has executed tests but not git_diff or git_commit,
        WHEN the agent attempts to call finish,
        THEN _validate_finish_action MUST return a review requirement message and reject finish.
        """
        orch = AgentWorkflowOrchestrator()
        run = AgentExecutionRun(
            run_id="test_run_early_finish_2",
            project_id="proj_1",
            repository_id="repo_1",
            mode="CODE",
            instruction="Add /health endpoint, run tests, review git diff and wait for approval.",
            state=AgentState.CODING,
            steps=[
                {
                    "step": "step_1_read_file",
                    "arguments": {"path": "src/server.js"},
                    "output": {"content": "app.get('/health', ...)"},
                },
                {
                    "step": "step_2_run_command",
                    "arguments": {"command": "npm test"},
                    "output": {"exit_code": 0, "stdout": "1 passed"},
                },
            ],
        )

        validation_err = orch._validate_finish_action(
            run=run,
            thought="Tests pass, calling finish.",
            arguments={"response": "Verified."},
        )

        assert validation_err is not None
        assert "Review Required" in validation_err

    def test_validate_finish_permits_finish_when_all_requirements_met(self):
        """
        GIVEN a CODE mode run where tests have run and diff/review has occurred,
        WHEN the agent calls finish,
        THEN _validate_finish_action MUST return None (finish permitted).
        """
        orch = AgentWorkflowOrchestrator()
        run = AgentExecutionRun(
            run_id="test_run_early_finish_3",
            project_id="proj_1",
            repository_id="repo_1",
            mode="CODE",
            instruction="Add /health endpoint, run tests, review git diff.",
            state=AgentState.CODING,
            steps=[
                {
                    "step": "step_1_read_file",
                    "arguments": {"path": "src/server.js"},
                    "output": {"content": "app.get('/health', ...)"},
                },
                {
                    "step": "step_2_run_test",
                    "arguments": {"test_path": "tests/test_server.js"},
                    "output": {"exit_code": 0, "passed": True},
                },
                {
                    "step": "step_3_git_diff",
                    "arguments": {},
                    "output": {"diff": ""},
                },
            ],
        )

        validation_err = orch._validate_finish_action(
            run=run,
            thought="All steps completed and verified.",
            arguments={"response": "Health endpoint verified and tests pass."},
        )

        assert validation_err is None

    def test_validate_finish_allows_read_only_query_modes_to_finish(self):
        """
        GIVEN read-only modes (ASK, PLAN, EXPLAIN),
        WHEN the agent calls finish after gathering evidence,
        THEN _validate_finish_action MUST return None (finish permitted immediately).
        """
        orch = AgentWorkflowOrchestrator()
        for mode in ("ASK", "PLAN", "EXPLAIN"):
            run = AgentExecutionRun(
                run_id=f"test_run_readonly_{mode}",
                project_id="proj_1",
                repository_id="repo_1",
                mode=mode,
                instruction="How does authentication work? Test if it is safe.",
                state=AgentState.CODING,
                steps=[
                    {
                        "step": "step_1_retrieval_search",
                        "arguments": {"query": "auth"},
                        "output": [{"file_path": "auth.py"}],
                    }
                ],
            )
            validation_err = orch._validate_finish_action(
                run=run,
                thought="Answer ready.",
                arguments={"response": "Auth explanation..."},
            )
            assert validation_err is None, f"Mode {mode} should not be blocked from finishing"

    @pytest.mark.asyncio
    async def test_dynamic_tool_loop_rejects_premature_finish_and_continues(self):
        """
        GIVEN a dynamic tool execution loop where the LLM initially attempts an early finish
        without running tests on an existing feature,
        WHEN the orchestrator encounters the finish action,
        THEN it MUST reject finish, record the validation requirement, and allow the agent
        to proceed to run tests and review before final completion.
        """
        store = get_agent_session_store()
        run = store.create_run(
            run_id="run_regression_loop_1",
            project_id="proj_1",
            repository_id="repo_1",
            mode="CODE",
            instruction="Understand server, add /health if needed, run tests to verify, review diff.",
        )

        orch = AgentWorkflowOrchestrator()

        # Simulate LLM turns:
        # Turn 1: read_file (discovers /health already exists)
        # Turn 2: premature finish ("No changes needed") -> Rejected by orchestrator!
        # Turn 3: run_command (executes tests)
        # Turn 4: git_diff (reviews changes)
        # Turn 5: finish (permitted!)
        turn = 0
        async def mock_call_llm(instruction: str, mode: str, context: str, model_override: str | None = None) -> dict:
            nonlocal turn
            turn += 1
            if turn == 1:
                return {
                    "response": '{"thought": "Read server file", "action": "read_file", "arguments": {"path": "src/server.js"}}',
                    "model": "qwen2.5-coder:7b-instruct-q4_0",
                }
            elif turn == 2:
                # Premature finish attempt
                return {
                    "response": '{"thought": "/health already exists. No changes needed.", "action": "finish", "arguments": {"response": "No changes needed."}}',
                    "model": "qwen2.5-coder:7b-instruct-q4_0",
                }
            elif turn == 3:
                # Responding to validation rejection by executing tests
                assert "Validation Required" in context or "finish [REJECTED" in context
                return {
                    "response": '{"thought": "Running tests as required", "action": "run_command", "arguments": {"command": "npm test"}}',
                    "model": "qwen2.5-coder:7b-instruct-q4_0",
                }
            elif turn == 4:
                return {
                    "response": '{"thought": "Reviewing git diff", "action": "git_diff", "arguments": {}}',
                    "model": "qwen2.5-coder:7b-instruct-q4_0",
                }
            else:
                return {
                    "response": '{"thought": "All validation complete", "action": "finish", "arguments": {"response": "Verified existing endpoint with passing tests."}}',
                    "model": "qwen2.5-coder:7b-instruct-q4_0",
                }

        # Mock tool dispatcher
        async def mock_execute_tool(tool_name: str, repository_id: str, arguments: dict) -> dict:
            if tool_name == "read_file":
                return {"path": "src/server.js", "content": "app.get('/health', ...)"}
            elif tool_name == "run_command":
                return {"command": "npm test", "exit_code": 0, "stdout": "Test Suite Passed (1 passed)", "stderr": ""}
            elif tool_name == "git_diff":
                return {"diff": "", "status": "clean"}
            return {"status": "ok"}

        async def mock_retrieve(r, i):
            return "Initial Context"

        orch._retrieve_context = mock_retrieve
        orch._call_llm = mock_call_llm
        orch.tool_dispatcher.execute_tool = mock_execute_tool

        completed_run = await orch.execute_dynamic_tool_loop(run.run_id)

        assert completed_run.state == AgentState.COMPLETED
        step_names = [s.get("step", "") for s in completed_run.steps]
        
        # Verify premature finish was rejected
        assert any("finish_rejected_validation_required" in s for s in step_names)
        # Verify tests were executed
        assert any("run_command" in s for s in step_names)
        # Verify review occurred
        assert any("git_diff" in s for s in step_names)
        # Verify final finish succeeded
        assert any(s.endswith("_finish") and "rejected" not in s for s in step_names)
