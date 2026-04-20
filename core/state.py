"""Shared state schema for the bug triage multi-agent system.

This implements the 'State as a Graph' concept (Lecture 8) using
a LangGraph-compatible TypedDict with a reducer for parallel-safe
log appending (Lecture 9).
"""
from typing import TypedDict, Annotated, Literal
from operator import add


Severity = Literal["P0", "P1", "P2", "P3"]


class LogEntry(TypedDict):
    """Single execution trace entry per 'Tracing Execution Trees' (Lecture 9)."""
    timestamp: str
    agent: str
    input_prompt: str
    user_input: str
    llm_raw_output: str
    tool_called: str | None
    tool_output: str | None
    latency_ms: int


class TriageState(TypedDict):
    """Global state passed between agents.

    The 'logs' field uses a reducer (operator.add) so concurrent agent
    updates append rather than overwrite — this is the Reducer pattern
    from Lecture 9.
    """
    # === Input ===
    raw_issue: str
    issue_number: int | None
    repo: str | None

    # === Coordinator output ===
    is_valid_bug: bool
    title: str
    description: str
    tags: list[str]

    # === Classifier output ===
    severity: Severity | None
    severity_evidence: list[str]
    severity_confidence: float

    # === Reproducer output ===
    repro_steps: list[str]
    expected_behavior: str
    actual_behavior: str
    related_files: list[str]

    # === Delegator output ===
    assignee: str
    assignee_reason: str
    notification_message: str

    # === Observability (reducer-appended) ===
    logs: Annotated[list[LogEntry], add]

    # === Failsafe ===
    iteration_count: int
    errors: Annotated[list[str], add]
