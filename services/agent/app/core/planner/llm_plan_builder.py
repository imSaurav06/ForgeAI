from typing import Any

from services.agent.app.core.planner.execution_plan import (
    ExecutionPlan,
    ExecutionPlanStep,
)


class LLMPlanBuilder:
    """Build a validated execution plan from structured LLM output."""

    @classmethod
    def build(
        cls,
        structured_data: dict[str, Any],
        mode: str,
    ) -> ExecutionPlan:
        if not isinstance(structured_data, dict):
            raise ValueError("LLM structured output must be a JSON object")

        raw_steps = structured_data.get("steps")

        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError(
                "LLM structured output must contain a non-empty 'steps' list"
            )

        steps: list[ExecutionPlanStep] = []

        for index, raw_step in enumerate(raw_steps, start=1):
            if not isinstance(raw_step, dict):
                raise ValueError(
                    f"LLM plan step {index} must be a JSON object"
                )

            step_id = str(raw_step.get("id") or f"step_{index}")
            task = raw_step.get("task")
            tool = raw_step.get("tool")

            if not isinstance(task, str) or not task.strip():
                raise ValueError(
                    f"LLM plan step '{step_id}' is missing a valid task"
                )

            if not isinstance(tool, str) or not tool.strip():
                raise ValueError(
                    f"LLM plan step '{step_id}' is missing a valid tool"
                )

            depends_on = raw_step.get("depends_on", [])
            files = raw_step.get("files", [])
            metadata = raw_step.get("metadata", {})

            if not isinstance(depends_on, list):
                raise ValueError(
                    f"LLM plan step '{step_id}' has invalid depends_on"
                )

            if not isinstance(files, list):
                raise ValueError(
                    f"LLM plan step '{step_id}' has invalid files"
                )

            if not isinstance(metadata, dict):
                raise ValueError(
                    f"LLM plan step '{step_id}' has invalid metadata"
                )

            steps.append(
                ExecutionPlanStep(
                    id=step_id,
                    task=task.strip(),
                    tool=tool.strip(),
                    depends_on=depends_on,
                    files=files,
                    metadata=metadata,
                )
            )

        plan_id = str(
            structured_data.get("plan_id")
            or f"plan_{mode.lower()}"
        )

        summary = structured_data.get("summary", "")
        affected_files = structured_data.get("affected_files", [])
        test_plan = structured_data.get("test_plan", [])

        if not isinstance(summary, str):
            summary = str(summary)

        if not isinstance(affected_files, list):
            raise ValueError("LLM plan 'affected_files' must be a list")

        if not isinstance(test_plan, list):
            raise ValueError("LLM plan 'test_plan' must be a list")

        return ExecutionPlan(
            plan_id=plan_id,
            summary=summary,
            steps=steps,
            affected_files=affected_files,
            test_plan=test_plan,
            metadata={
                "source": "llm",
                "mode": mode.upper(),
            },
        )