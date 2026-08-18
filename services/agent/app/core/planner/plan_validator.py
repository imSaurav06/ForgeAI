from services.agent.app.core.planner.execution_plan import ExecutionPlan


class PlanValidator:
    """Validates execution plans as acyclic dependency graphs."""

    @staticmethod
    def validate(plan: ExecutionPlan) -> ExecutionPlan:
        PlanValidator._validate_duplicate_ids(plan)
        PlanValidator._validate_dependencies(plan)
        PlanValidator._validate_acyclic(plan)
        return plan

    @staticmethod
    def _validate_duplicate_ids(plan: ExecutionPlan) -> None:
        step_ids = [step.id for step in plan.steps]
        duplicates = {
            step_id
            for step_id in step_ids
            if step_ids.count(step_id) > 1
        }

        if duplicates:
            raise ValueError(
                f"Execution plan contains duplicate step IDs: {sorted(duplicates)}"
            )

    @staticmethod
    def _validate_dependencies(plan: ExecutionPlan) -> None:
        step_ids = {step.id for step in plan.steps}

        for step in plan.steps:
            if step.id in step.depends_on:
                raise ValueError(
                    f"Step '{step.id}' cannot depend on itself"
                )

            unknown = [
                dependency
                for dependency in step.depends_on
                if dependency not in step_ids
            ]

            if unknown:
                raise ValueError(
                    f"Step '{step.id}' contains unknown dependencies: {unknown}"
                )

    @staticmethod
    def _validate_acyclic(plan: ExecutionPlan) -> None:
        graph = {
            step.id: list(step.depends_on)
            for step in plan.steps
        }

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise ValueError(
                    f"Execution plan contains a circular dependency involving step '{step_id}'"
                )

            if step_id in visited:
                return

            visiting.add(step_id)

            for dependency in graph[step_id]:
                visit(dependency)

            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in graph:
            visit(step_id)