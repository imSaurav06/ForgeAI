import pytest
from fastapi.testclient import TestClient

from services.agent.app.core.events.event_bus import AgentEventBus
from services.agent.app.core.planner.agent_planner import AgentPlanner
from services.agent.app.core.sessions.session_store import get_agent_session_store
from services.agent.app.core.state_machine.states import AgentState, AgentStateMachine
from services.agent.app.core.workflows.orchestrator import AgentWorkflowOrchestrator
from services.agent.app.main import app
from shared.exceptions.handlers import ValidationException

client = TestClient(app)


def test_state_machine_transitions():
    """Verify 11 states and transition validation."""
    sm = AgentStateMachine(initial_state=AgentState.CREATED)
    assert sm.current_state == AgentState.CREATED
    assert sm.is_terminal() is False

    sm.transition_to(AgentState.ANALYZING)
    sm.transition_to(AgentState.RETRIEVING)
    sm.transition_to(AgentState.PLANNING)
    sm.transition_to(AgentState.CODING)
    sm.transition_to(AgentState.APPLYING)
    sm.transition_to(AgentState.TESTING)
    sm.transition_to(AgentState.COMPLETED)
    assert sm.is_terminal() is True

    # Invalid transition from COMPLETED to ANALYZING should raise ValidationException
    with pytest.raises(ValidationException):
        sm.transition_to(AgentState.ANALYZING)


def test_agent_planner():
    """Verify planner requirement decomposition and file impact estimation."""
    plan_code = AgentPlanner.decompose_requirements("Implement JWT validation", mode="CODE")
    assert len(plan_code.steps) >= 3
    assert plan_code.steps[0].tool == "retrieval_search"

    plan_ask = AgentPlanner.decompose_requirements("Where is settings defined?", mode="ASK")
    assert len(plan_ask.steps) == 2

    impact = AgentPlanner.estimate_file_impact("Implement auth middleware", ["services/gateway/main.py"])
    assert "services/gateway/main.py" in impact
    assert any("auth" in f for f in impact)


def test_agent_event_bus():
    """Verify event emission and subscriber retrieval."""
    bus = AgentEventBus()
    evt = bus.emit("run_test_bus", "agent.started", {"mode": "CODE"})
    assert evt.event_type == "agent.started"

    events = bus.get_events("run_test_bus")
    assert len(events) == 1
    assert events[0].payload["mode"] == "CODE"


@pytest.mark.asyncio
async def test_workflow_orchestrator_execution():
    """Verify workflow orchestrator execution for ASK and CODE modes."""
    store = get_agent_session_store()
    run = store.create_run(
        run_id="run_orch_1",
        project_id="proj_1",
        repository_id="repo_1",
        mode="ASK",
        instruction="How does logging work?",
    )

    orch = AgentWorkflowOrchestrator()

    # Stub remote microservices for isolated unit test
    async def mock_retrieve(repo_id: str, query: str) -> str:
        return "--- File: main.py ---\ndef main(): pass"

    async def mock_llm(instruction: str, mode: str, context: str, model_override: str | None = None) -> dict:
        return {
            "response": "Here is the answer.",
            "structured_data": {"steps": [{"step_id": "1", "task": "Explain logging", "tool": "none"}]},
            "model": "qwen2.5-coder:7b-instruct-q4_0",
        }

    orch._retrieve_context = mock_retrieve
    orch._call_llm = mock_llm

    completed_run = await orch.execute_run(run.run_id)
    assert completed_run.state == AgentState.COMPLETED
    assert len(completed_run.execution_plan) > 0


@pytest.mark.asyncio
async def test_self_correction_repair_loop():
    """Verify automatic self-correction repair loop on test failure."""
    store = get_agent_session_store()
    run = store.create_run(
        run_id="run_repair_1",
        project_id="proj_1",
        repository_id="repo_1",
        mode="CODE",
        instruction="Add new feature",
    )

    orch = AgentWorkflowOrchestrator()

    # Stub remote microservices for isolated unit test
    async def mock_retrieve(repo_id: str, query: str) -> str:
        return "--- File: main.py ---\ndef main(): pass"

    async def mock_llm(instruction: str, mode: str, context: str, model_override: str | None = None) -> dict:
        return {
            "response": "```json\n{\"files_to_create\": [{\"path\": \"new_file.py\", \"content\": \"x = 1\"}], \"files_to_modify\": [], \"files_to_delete\": []}\n```",
            "structured_data": {"steps": [{"step_id": "1", "task": "Write code", "tool": "code_writer"}]},
            "model": "qwen2.5-coder:7b-instruct-q4_0",
        }

    async def mock_apply(patch_data: str, repo_id: str) -> str:
        return "Applied patch successfully"

    # Mock pytest runner to fail on 1st attempt, pass on 2nd attempt
    attempts = 0

    async def mock_pytest(pytest_path: str | None = None, repository_id: str | None = None):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return {"passed": False, "error": "AssertionError: expected 200 got 500", "exit_code": 1}
        return {"passed": True, "error": None, "exit_code": 0}

    orch._retrieve_context = mock_retrieve
    orch._call_llm = mock_llm
    orch._apply_patch = mock_apply
    orch._execute_pytest = mock_pytest

    completed_run = await orch.execute_run(run.run_id)
    assert completed_run.state == AgentState.COMPLETED
    assert completed_run.repair_count >= 1


def test_agent_api_endpoints():
    """Verify Agent REST API endpoints."""
    from services.gateway.app.core.internal_auth import InternalAuthManager
    headers = {"X-Internal-Service-Token": InternalAuthManager().generate_internal_token("test-client")}

    # Create Run
    create_resp = client.post(
        "/v1/agent/runs",
        headers=headers,
        json={
            "project_id": "proj_api_1",
            "repository_id": "repo_api_1",
            "mode": "PLAN",
            "instruction": "Plan refactoring of gateway proxy",
        },
    )
    assert create_resp.status_code == 201
    run_id = create_resp.json()["data"]["run_id"]
    assert create_resp.json()["data"]["state"] in ("CREATED", "ANALYZING", "PLANNING", "COMPLETED")

    # Get Run Status
    get_resp = client.get(f"/v1/agent/runs/{run_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["run_id"] == run_id

    # Continue Run
    cont_resp = client.post(f"/v1/agent/runs/{run_id}/continue", headers=headers, json={"user_feedback": "Looks good"})
    assert cont_resp.status_code == 200

    # Get Steps
    steps_resp = client.get(f"/v1/agent/runs/{run_id}/steps", headers=headers)
    assert steps_resp.status_code == 200

    # Get Events
    events_resp = client.get(f"/v1/agent/runs/{run_id}/events", headers=headers)
    assert events_resp.status_code == 200
    assert len(events_resp.json()["data"]) > 0

    # Cancel Run
    cancel_resp = client.post(f"/v1/agent/runs/{run_id}/cancel", headers=headers)
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["data"]["state"] == "CANCELLED"
