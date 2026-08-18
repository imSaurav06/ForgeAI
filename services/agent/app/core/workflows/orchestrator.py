from __future__ import annotations

import json
from typing import Any

import httpx

from services.agent.app.core.events.event_bus import get_agent_event_bus
from services.agent.app.core.patching.patch_normalizer import CanonicalPatchNormalizer
from services.agent.app.core.planner.llm_plan_builder import LLMPlanBuilder
from services.agent.app.core.planner.plan_validator import PlanValidator
from services.agent.app.core.sessions.session_store import AgentExecutionRun, get_agent_session_store
from services.agent.app.core.state_machine.states import AgentState, AgentStateMachine
from services.agent.app.core.tools.tool_dispatcher import AgentToolDispatcher
from services.gateway.app.core.internal_auth import InternalAuthManager
from shared.config.settings import get_settings
from shared.exceptions.handlers import ValidationException
from shared.logging.logger import logger


class AgentWorkflowOrchestrator:
    """
    Main Workflow Orchestrator driving autonomous agent runs across all 7 modes,
    validating state machine transitions, executing dynamic tool dispatching,
    canonical patch normalization, and automated self-correction repair loops.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.session_store = get_agent_session_store()
        self.event_bus = get_agent_event_bus()
        self.tool_dispatcher = AgentToolDispatcher()

    def _get_internal_headers(self) -> dict[str, str]:
        mgr = InternalAuthManager()
        token = mgr.generate_internal_token("agent-service")
        return {
            "X-Internal-Service-Token": token,
            "X-User-ID": "agent_system",
            "X-User-Role": "admin",
        }

    async def execute_run(self, run_id: str) -> AgentExecutionRun:
        """Execute full autonomous run workflow."""
        run = self.session_store.get_run(run_id)
        state_machine = AgentStateMachine(initial_state=run.state)

        # Emit agent.started
        self.event_bus.emit(run_id, "agent.started", {"mode": run.mode, "instruction": run.instruction})

        try:
            # Step 1: ANALYZING
            state_machine.transition_to(AgentState.ANALYZING)
            run.state = AgentState.ANALYZING
            self.session_store.update_run(run)
            self.event_bus.emit(run_id, "repository.searching", {"repository_id": run.repository_id})

            # Step 2: RETRIEVING
            state_machine.transition_to(AgentState.RETRIEVING)
            run.state = AgentState.RETRIEVING
            retrieved_context = await self._retrieve_context(run.repository_id, run.instruction)
            run.retrieved_context = retrieved_context
            self.event_bus.emit(run_id, "retrieval.completed", {"context_length": len(retrieved_context)})

            # Step 3: PLANNING
            state_machine.transition_to(AgentState.PLANNING)
            run.state = AgentState.PLANNING
            self.session_store.update_run(run)

            plan_llm_response = await self._call_llm(
                instruction=run.instruction,
                mode="PLAN",
                context=retrieved_context,
                model_override=run.selected_model,
            )

            structured_plan = plan_llm_response.get("structured_data")

            if not isinstance(structured_plan, dict):
                raise RuntimeError(
                    "LLM PLAN generation did not return structured execution-plan data"
                )

            execution_plan = LLMPlanBuilder.build(
                structured_data=structured_plan,
                mode="PLAN",
            )

            validated_plan = PlanValidator.validate(execution_plan)

            run.execution_plan = validated_plan.model_dump()
            self.session_store.update_run(run)

            self.event_bus.emit(
                run_id,
                "plan.created",
                {
                    "plan": validated_plan.model_dump(),
                    "model": plan_llm_response.get("model"),
                    "source": "llm",
                },
            )

            # Step 4: CODING / EXECUTION
            state_machine.transition_to(AgentState.CODING)
            run.state = AgentState.CODING
            self.event_bus.emit(run_id, "coding.started", {"mode": run.mode, "model": run.selected_model})
            llm_response = await self._call_llm(
                run.instruction, run.mode, retrieved_context, model_override=run.selected_model
            )
            run.steps.append({"step": "generate_patch", "output": llm_response})
            self.event_bus.emit(run_id, "coding.completed", {"response_length": len(llm_response.get("response", ""))})

            # Read-only modes conclude cleanly
            if run.mode in ("ASK", "PLAN", "REVIEW", "EXPLAIN"):
                state_machine.transition_to(AgentState.COMPLETED)
                run.state = AgentState.COMPLETED
                self.session_store.update_run(run)
                self.event_bus.emit(run_id, "agent.completed", {"status": "completed"})
                return run

            # Step 5: APPLYING (Canonical patch normalization)
            state_machine.transition_to(AgentState.APPLYING)
            run.state = AgentState.APPLYING
            patch_raw = llm_response.get("response", "") if isinstance(llm_response, dict) else str(llm_response)
            patch_status = await self._apply_patch(patch_raw, run.repository_id)
            self.event_bus.emit(run_id, "patch.created", {"status": patch_status})

            # Step 6: TESTING & SELF-CORRECTION LOOP
            state_machine.transition_to(AgentState.TESTING)
            run.state = AgentState.TESTING
            self.event_bus.emit(run_id, "testing.started", {"repository_id": run.repository_id})
            test_success = await self._run_tests_and_repair_loop(run, state_machine)

            if not test_success:
                state_machine.transition_to(AgentState.FAILED)
                run.state = AgentState.FAILED
                self.session_store.update_run(run)
                self.event_bus.emit(run_id, "agent.completed", {"status": "failed"})
                return run

            # Step 7: COMPLETED
            state_machine.transition_to(AgentState.COMPLETED)
            run.state = AgentState.COMPLETED
            self.session_store.update_run(run)
            self.event_bus.emit(run_id, "agent.completed", {"status": "completed"})
            return run

        except Exception as err:
            logger.error(f"Error during agent run execution '{run_id}': {err}")
            run.state = AgentState.FAILED
            self.session_store.update_run(run)
            self.event_bus.emit(run_id, "agent.completed", {"status": "failed", "error": str(err)})
            return run

    async def execute_dynamic_tool_loop(
        self,
        run_id: str,
        max_steps: int = 10,
    ) -> AgentExecutionRun:
        """
        Execute a dynamic multi-turn LLM -> Tool Action -> Execution -> Next Action loop.
        Every tool execution uses real microservices.
        """
        run = self.session_store.get_run(run_id)
        state_machine = AgentStateMachine(initial_state=run.state)
        self.event_bus.emit(run_id, "agent.started", {"mode": run.mode, "instruction": run.instruction})

        try:
            state_machine.transition_to(AgentState.ANALYZING)
            run.state = AgentState.ANALYZING
            self.session_store.update_run(run)

            # Gather baseline context
            base_context = await self._retrieve_context(run.repository_id, run.instruction)
            history_blocks: list[str] = [f"Initial Retrieved Context:\n{base_context}"]

            state_machine.transition_to(AgentState.RETRIEVING)
            run.state = AgentState.RETRIEVING
            state_machine.transition_to(AgentState.CODING)
            run.state = AgentState.CODING
            self.session_store.update_run(run)

            for step_idx in range(1, max_steps + 1):
                current_context = "\n\n".join(history_blocks)

                # Call LLM for next action decision
                action_response = await self._call_llm(
                    instruction=run.instruction,
                    mode="TOOL_ACTION",
                    context=current_context,
                    model_override=run.selected_model,
                )

                raw_resp = action_response.get("response", "")
                parsed_action = CanonicalPatchNormalizer._extract_dict(raw_resp) if raw_resp else {}

                thought = str(parsed_action.get("thought", ""))
                action_name = str(parsed_action.get("action", "")).strip().lower()
                arguments = parsed_action.get("arguments", {})
                if not isinstance(arguments, dict):
                    arguments = {}

                logger.info(f"Dynamic tool step {step_idx}/{max_steps}: action='{action_name}', thought='{thought}'")

                # Terminal action
                if action_name in ("finish", "complete", "done"):
                    final_text = str(arguments.get("response", thought or "Task completed successfully."))
                    run.steps.append({
                        "step": f"step_{step_idx}_finish",
                        "thought": thought,
                        "output": final_text,
                    })
                    state_machine.transition_to(AgentState.COMPLETED)
                    run.state = AgentState.COMPLETED
                    self.session_store.update_run(run)
                    self.event_bus.emit(run_id, "agent.completed", {"status": "completed", "response": final_text})
                    return run

                # Execute requested tool action
                if not action_name:
                    # If model returned direct patch format instead of action wrapper
                    try:
                        canonical = CanonicalPatchNormalizer.normalize(raw_resp)
                        state_machine.transition_to(AgentState.APPLYING)
                        apply_res = await self.tool_dispatcher.apply_patch(run.repository_id, canonical)
                        run.steps.append({
                            "step": f"step_{step_idx}_apply_patch",
                            "thought": "Applied generated patch",
                            "output": apply_res,
                        })
                        self.event_bus.emit(run_id, "patch.created", {"status": "Applied patch successfully"})
                        history_blocks.append(f"Step {step_idx} - Patch Applied: {json.dumps(apply_res)}")
                        continue
                    except Exception:
                        raise ValidationException(message=f"LLM produced invalid action output at step {step_idx}")

                # Emit step start
                self.event_bus.emit(run_id, "coding.started", {"step": step_idx, "tool": action_name, "thought": thought})

                try:
                    tool_output = await self.tool_dispatcher.execute_tool(
                        tool_name=action_name,
                        repository_id=run.repository_id,
                        arguments=arguments,
                    )
                except Exception as tool_err:
                    tool_output = {"error": str(tool_err), "status": "failed"}

                # Record step history
                run.steps.append({
                    "step": f"step_{step_idx}_{action_name}",
                    "thought": thought,
                    "arguments": arguments,
                    "output": tool_output,
                })
                self.session_store.update_run(run)

                # Format tool result block for next turn context
                out_str = json.dumps(tool_output, indent=2) if isinstance(tool_output, (dict, list)) else str(tool_output)
                if len(out_str) > 2000:
                    out_str = out_str[:2000] + "... [truncated]"

                history_blocks.append(
                    f"Step {step_idx} - Action: {action_name}\n"
                    f"Arguments: {json.dumps(arguments)}\n"
                    f"Result:\n{out_str}"
                )

                if action_name in ("apply_patch", "write_file", "delete_file"):
                    self.event_bus.emit(run_id, "patch.created", {"action": action_name, "status": "executed"})
                elif action_name in ("run_test", "pytest"):
                    if isinstance(tool_output, dict) and tool_output.get("passed"):
                        self.event_bus.emit(run_id, "tests.passed", {"step": step_idx})
                    else:
                        self.event_bus.emit(run_id, "tests.failed", {"step": step_idx, "output": tool_output})

            # Max steps reached
            state_machine.transition_to(AgentState.COMPLETED)
            run.state = AgentState.COMPLETED
            self.session_store.update_run(run)
            self.event_bus.emit(run_id, "agent.completed", {"status": "completed", "note": "Max tool steps reached"})
            return run

        except Exception as err:
            logger.error(f"Error in dynamic tool loop for run '{run_id}': {err}")
            run.state = AgentState.FAILED
            self.session_store.update_run(run)
            self.event_bus.emit(run_id, "agent.completed", {"status": "failed", "error": str(err)})
            return run

    async def _run_tests_and_repair_loop(
        self, run: AgentExecutionRun, state_machine: AgentStateMachine, max_repairs: int = 3
    ) -> bool:
        """Run tests and trigger automatic self-correction repair loop on failure."""
        run_id = run.run_id

        for attempt in range(1, max_repairs + 1):
            test_result = await self._execute_pytest(repository_id=run.repository_id)
            run.test_history.append({"attempt": attempt, "result": test_result})

            # Strict fail-closed evaluation: exit_code MUST be 0 and passed MUST be True
            if test_result.get("passed", False):
                self.event_bus.emit(run_id, "tests.passed", {"attempt": attempt})
                return True

            # Tests Failed: Trigger Self-Correction
            self.event_bus.emit(
                run_id, "tests.failed", {"attempt": attempt, "failure_output": test_result.get("error")}
            )

            if attempt >= max_repairs:
                logger.warning(f"Self-correction repair loop exceeded max attempts ({max_repairs}) for run '{run_id}'")
                return False

            # Execute Repair Iteration
            run.repair_count += 1
            self.event_bus.emit(run_id, "repair.started", {"repair_attempt": attempt})

            # Transition state machine through RETRIEVING -> CODING -> APPLYING -> TESTING
            state_machine.transition_to(AgentState.RETRIEVING)
            repair_context = await self._retrieve_context(
                run.repository_id, f"Fix test failure: {test_result.get('error')}"
            )
            run.retrieved_context += f"\n\nTest Failure Context:\n{repair_context}"

            state_machine.transition_to(AgentState.CODING)
            repair_patch = await self._call_llm(
                instruction=f"Fix test failure: {test_result.get('error')}",
                mode="DEBUG",
                context=run.retrieved_context,
                model_override=run.selected_model,
            )

            state_machine.transition_to(AgentState.APPLYING)
            repair_patch_raw = repair_patch.get("response", "") if isinstance(repair_patch, dict) else str(repair_patch)
            # Normalization handles DEBUG schema cleanly
            await self._apply_patch(repair_patch_raw, run.repository_id)

            state_machine.transition_to(AgentState.TESTING)

        return False

    async def _retrieve_context(self, repository_id: str, query: str) -> str:
        """Call the Retrieval Service over HTTP to assemble RAG context."""
        retrieval_url = self.settings.retrieval_service_url.rstrip("/")
        endpoint = f"{retrieval_url}/v1/search/semantic"

        payload = {
            "repository_id": repository_id,
            "query": query,
            "limit": 5,
        }

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    endpoint,
                    json=payload,
                    headers=self._get_internal_headers(),
                )

            if resp.status_code == 200:
                data = resp.json().get("data", [])
                context_parts = []
                for item in data:
                    fp = item.get("file_path", "unknown")
                    start_l = item.get("start_line", 1)
                    end_l = item.get("end_line", 1)
                    snip = item.get("snippet", "")
                    context_parts.append(f"--- File: {fp} (lines {start_l}-{end_l}) ---\n{snip}")
                return "\n\n".join(context_parts)
            logger.warning(f"Retrieval Service HTTP {resp.status_code}: {resp.text}")
            return "No repository context retrieved."
        except Exception as err:
            logger.warning(f"Could not retrieve context: {err}")
            return "No repository context retrieved."

    async def _call_llm(
        self,
        instruction: str,
        mode: str,
        context: str = "",
        model_override: str | None = None,
    ) -> dict[str, Any]:
        """Call the LLM Service over HTTP for text generation."""
        llm_url = self.settings.llm_service_url.rstrip("/")
        endpoint = f"{llm_url}/v1/generate"

        payload: dict[str, Any] = {
            "prompt": instruction,
            "mode": mode,
            "context": context,
        }

        if model_override:
            payload["model_override"] = model_override

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    endpoint,
                    json=payload,
                    headers=self._get_internal_headers(),
                )

            if resp.status_code == 200:
                data = resp.json()
                if "data" in data:
                    return data["data"]
                return data

            raise RuntimeError(f"LLM Service HTTP {resp.status_code}: {resp.text}")
        except Exception as err:
            logger.warning(f"Could not fetch LLM generation: {err}")
            raise

    async def _apply_patch(self, patch_data: Any, repository_id: str) -> str:
        """Apply an LLM-generated patch to the selected repository with canonical normalization."""
        if not repository_id:
            raise RuntimeError("repository_id is required to apply patch")

        tools_url = self.settings.tool_service_url.rstrip("/")

        # Step 1: Canonical normalization
        try:
            canonical_patch = CanonicalPatchNormalizer.normalize(patch_data)
        except Exception as exc:
            raise RuntimeError(f"Failed to parse patch data: {exc}") from exc

        payload = canonical_patch.to_dict(repository_id)

        # Step 2: Delegate to Tools Service
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{tools_url}/internal/v1/tools/apply-patch",
                    json=payload,
                    headers=self._get_internal_headers(),
                )

            response.raise_for_status()

            body = response.json()
            result = body.get("data", body)

            if isinstance(result, dict) and result.get("success") is False:
                raise RuntimeError(
                    result.get("message", "Tool patch application failed")
                )

            return "Applied patch successfully"

        except Exception as exc:
            logger.error(
                f"Could not apply patch to repository {repository_id}: {exc}",
                exc_info=True,
            )
            raise RuntimeError(
                f"Failed to apply patch to repository '{repository_id}': {exc}"
            ) from exc

    async def _execute_pytest(
        self,
        pytest_path: str | None = None,
        repository_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute pytest runner via Tools Service with strict fail-closed contract."""
        if not repository_id:
            logger.error("Test execution rejected: repository_id is required")
            return {
                "passed": False,
                "error": "repository_id is required for repository-scoped test execution",
                "exit_code": -1,
            }

        tools_url = self.settings.tool_service_url.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                payload: dict[str, Any] = {
                    "repository_id": repository_id,
                }
                if pytest_path:
                    payload["test_path"] = pytest_path
                    payload["path"] = pytest_path

                resp = await client.post(
                    f"{tools_url}/internal/v1/tools/run-test",
                    json=payload,
                    headers=self._get_internal_headers(),
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    passed = bool(data.get("exit_code") == 0 and data.get("passed") is True)
                    return {
                        "passed": passed,
                        "error": None if passed else (data.get("output") or data.get("stdout") or data.get("stderr") or "Test execution failed"),
                        "exit_code": data.get("exit_code"),
                        "output": data.get("output"),
                    }
                logger.error(
                    f"Tools Service returned non-200 for run-test: HTTP {resp.status_code} — {resp.text[:500]}"
                )
                return {
                    "passed": False,
                    "error": f"Tools Service HTTP {resp.status_code}: {resp.text[:500]}",
                    "exit_code": -1,
                }
        except Exception as err:
            logger.warning(f"Could not run tests: {err}")
            return {"passed": False, "error": f"Test execution exception: {err}", "exit_code": -1}
