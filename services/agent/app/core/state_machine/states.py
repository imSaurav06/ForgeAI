from enum import Enum

from shared.exceptions.handlers import ValidationException


class AgentState(str, Enum):
    """The 11 mandatory agent execution states."""

    CREATED = "CREATED"
    ANALYZING = "ANALYZING"
    RETRIEVING = "RETRIEVING"
    PLANNING = "PLANNING"
    CODING = "CODING"
    APPLYING = "APPLYING"
    TESTING = "TESTING"
    REVIEWING = "REVIEWING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentStateMachine:
    """
    Agent State Machine validating allowed state transitions during autonomous execution.
    """

    ALLOWED_TRANSITIONS: dict[AgentState, set[AgentState]] = {
        AgentState.CREATED: {AgentState.ANALYZING, AgentState.RETRIEVING, AgentState.CANCELLED},
        AgentState.ANALYZING: {AgentState.RETRIEVING, AgentState.PLANNING, AgentState.FAILED, AgentState.CANCELLED},
        AgentState.RETRIEVING: {AgentState.PLANNING, AgentState.CODING, AgentState.FAILED, AgentState.CANCELLED},
        AgentState.PLANNING: {AgentState.CODING, AgentState.APPLYING, AgentState.COMPLETED, AgentState.FAILED, AgentState.CANCELLED},
        AgentState.CODING: {AgentState.APPLYING, AgentState.TESTING, AgentState.COMPLETED, AgentState.FAILED, AgentState.CANCELLED},
        AgentState.APPLYING: {AgentState.TESTING, AgentState.REVIEWING, AgentState.FAILED, AgentState.CANCELLED},
        AgentState.TESTING: {
            AgentState.REVIEWING,
            AgentState.COMPLETED,
            AgentState.RETRIEVING,  # Self-correction repair loop transition
            AgentState.CODING,       # Self-correction patch generation transition
            AgentState.FAILED,
            AgentState.CANCELLED,
        },
        AgentState.REVIEWING: {AgentState.COMPLETED, AgentState.FAILED, AgentState.CANCELLED},
        AgentState.COMPLETED: set(),
        AgentState.FAILED: set(),
        AgentState.CANCELLED: set(),
    }

    def __init__(self, initial_state: AgentState = AgentState.CREATED) -> None:
        self.current_state = initial_state
        self.history: list[AgentState] = [initial_state]

    def transition_to(self, new_state: AgentState) -> AgentState:
        """Validate and execute state transition."""
        if new_state not in self.ALLOWED_TRANSITIONS[self.current_state]:
            raise ValidationException(
                message=f"Invalid state transition from {self.current_state.value} to {new_state.value}"
            )
        self.current_state = new_state
        self.history.append(new_state)
        return self.current_state

    def is_terminal(self) -> bool:
        """Check if state is terminal (COMPLETED, FAILED, CANCELLED)."""
        return self.current_state in {AgentState.COMPLETED, AgentState.FAILED, AgentState.CANCELLED}
