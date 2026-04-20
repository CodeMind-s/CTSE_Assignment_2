"""LangGraph wiring for the 4-agent CWD workflow.

Flow:
    START → coordinator → (is_valid_bug? )
                          ├─ no  → END (exit 1 in main.py)
                          └─ yes → [classifier ∥ reproducer] → delegator → END

Parallel fan-out from coordinator means classifier and reproducer execute
concurrently; their `logs` updates merge via the operator.add reducer
declared on TriageState.logs (Lecture 9 — Reducers and State Conflict
Management). The MAX_ITERATIONS gate guards against the 'Infinite Loops
and Token Exhaustion' failure mode from Lecture 8.
"""
from langgraph.graph import StateGraph, END

from core.state import TriageState
from agents import coordinator, classifier, reproducer, delegator


MAX_ITERATIONS = 5


def route_after_coordinator(state: TriageState) -> list[str] | str:
    """Decide whether to fan out to the workers, or short-circuit to END.

    Returning a list of node names triggers LangGraph's parallel fan-out —
    both workers run concurrently and their `logs` updates merge via the
    operator.add reducer on TriageState.logs.
    """
    if state.get("iteration_count", 0) >= MAX_ITERATIONS:
        return "end_failed"
    if not state.get("is_valid_bug", False):
        return "end_invalid"
    return ["classifier", "reproducer"]


def build_graph():
    """Construct and compile the triage graph."""
    graph = StateGraph(TriageState)

    graph.add_node("coordinator", coordinator.run)
    graph.add_node("classifier", classifier.run)
    graph.add_node("reproducer", reproducer.run)
    graph.add_node("delegator", delegator.run)

    graph.set_entry_point("coordinator")

    graph.add_conditional_edges(
        "coordinator",
        route_after_coordinator,
        {
            "classifier": "classifier",
            "reproducer": "reproducer",
            "end_invalid": END,
            "end_failed": END,
        },
    )

    # Both workers must complete before delegator runs.
    graph.add_edge("classifier", "delegator")
    graph.add_edge("reproducer", "delegator")
    graph.add_edge("delegator", END)

    return graph.compile()
