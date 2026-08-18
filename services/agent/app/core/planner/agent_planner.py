from typing import Any

from services.agent.app.core.planner.execution_plan import (
    ExecutionPlan,
    ExecutionPlanStep,
)
from services.agent.app.core.planner.plan_validator import PlanValidator


class AgentPlanner:
    """
    Agent Planner performing requirement decomposition, task graph generation,
    file impact estimation, and tool selection strategy.
    """

    @classmethod
    def decompose_requirements(
        cls,
        instruction: str,
        mode: str,
    ) -> ExecutionPlan:
        """Decompose a task instruction into a validated execution plan."""
        mode_upper = mode.upper()

        if mode_upper == "ASK":
            steps = [
                ExecutionPlanStep(
                    id="step_1",
                    task="Search code symbols and definitions",
                    tool="retrieval_search",
                ),
                ExecutionPlanStep(
                    id="step_2",
                    task="Analyze codebase answers",
                    tool="llm_generate",
                    depends_on=["step_1"],
                ),
            ]

        elif mode_upper == "PLAN":
            steps = [
                ExecutionPlanStep(
                    id="step_1",
                    task="Scan repository tree and file structure",
                    tool="repo_scan",
                ),
                ExecutionPlanStep(
                    id="step_2",
                    task="Retrieve relevant context snippets",
                    tool="retrieval_search",
                    depends_on=["step_1"],
                ),
                ExecutionPlanStep(
                    id="step_3",
                    task="Construct architectural plan and affected files list",
                    tool="llm_generate",
                    depends_on=["step_2"],
                ),
            ]

        elif mode_upper in ("CODE", "DEBUG"):
            steps = [
                ExecutionPlanStep(
                    id="step_1",
                    task="Retrieve code context for target feature or bug",
                    tool="retrieval_search",
                ),
                ExecutionPlanStep(
                    id="step_2",
                    task="Generate code modification patch",
                    tool="llm_generate",
                    depends_on=["step_1"],
                ),
                ExecutionPlanStep(
                    id="step_3",
                    task="Apply file changes to workspace",
                    tool="file_writer",
                    depends_on=["step_2"],
                ),
                ExecutionPlanStep(
                    id="step_4",
                    task="Execute unit test suite and verify",
                    tool="test_runner",
                    depends_on=["step_3"],
                ),
            ]

        elif mode_upper == "TEST":
            steps = [
                ExecutionPlanStep(
                    id="step_1",
                    task="Inspect target service module",
                    tool="retrieval_search",
                ),
                ExecutionPlanStep(
                    id="step_2",
                    task="Generate complete unit test suite",
                    tool="llm_generate",
                    depends_on=["step_1"],
                ),
                ExecutionPlanStep(
                    id="step_3",
                    task="Execute pytest suite",
                    tool="test_runner",
                    depends_on=["step_2"],
                ),
            ]

        elif mode_upper == "REVIEW":
            steps = [
                ExecutionPlanStep(
                    id="step_1",
                    task="Fetch repository git diff",
                    tool="git_diff",
                ),
                ExecutionPlanStep(
                    id="step_2",
                    task="Analyze code diff for security and bug concerns",
                    tool="llm_generate",
                    depends_on=["step_1"],
                ),
            ]

        else:
            steps = [
                ExecutionPlanStep(
                    id="step_1",
                    task="Retrieve dependency graph and key symbols",
                    tool="repo_symbols",
                ),
                ExecutionPlanStep(
                    id="step_2",
                    task="Generate component architecture flow explanation",
                    tool="llm_generate",
                    depends_on=["step_1"],
                ),
            ]

        plan = ExecutionPlan(
            plan_id=f"plan_{mode_upper.lower()}",
            summary=f"{mode_upper} execution plan",
            steps=steps,
        )

        return PlanValidator.validate(plan)

    @classmethod
    def estimate_file_impact(
        cls,
        instruction: str,
        retrieved_files: list[str],
    ) -> list[str]:
        """Estimate file paths affected by task instruction."""
        impacted = list(retrieved_files)
        inst_lower = instruction.lower()

        if "auth" in inst_lower and not any(
            "auth" in f for f in impacted
        ):
            impacted.append(
                "services/gateway/app/api/middleware/auth.py"
            )

        if "setting" in inst_lower and not any(
            "setting" in f for f in impacted
        ):
            impacted.append(
                "shared/config/settings.py"
            )

        return impacted