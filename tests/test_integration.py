"""End-to-end graph tests.

These exercise the full LangGraph pipeline — coordinator → parallel
(classifier ∥ reproducer) → delegator — on labelled bug reports.
Proves state is preserved across the whole walk and that the reducer
on `logs` actually merges the two workers' entries.
"""
from __future__ import annotations

import pytest

from core.graph import build_graph, MAX_ITERATIONS


@pytest.mark.llm
@pytest.mark.integration
class TestPipelineEndToEnd:

    def test_happy_path_populates_every_state_slot(self, empty_state):
        state = dict(empty_state)
        state["raw_issue"] = (
            "All checkout attempts fail with 'card declined' even on valid cards. "
            "Revenue has been zero since 09:00 UTC. Test cards from the gateway "
            "sandbox also fail."
        )
        app = build_graph()
        final = app.invoke(state)

        assert final["is_valid_bug"] is True
        assert final["title"]
        assert final["description"]
        assert final["severity"] in {"P0", "P1", "P2", "P3"}
        assert final["repro_steps"]
        assert final["assignee"]
        assert final["notification_message"]

        # All four agents must have contributed a log entry.
        agents_logged = {log["agent"] for log in final["logs"]}
        assert {"coordinator", "classifier", "reproducer", "delegator"} <= agents_logged, (
            f"missing agent logs: got {agents_logged}"
        )

    def test_feature_request_short_circuits_at_coordinator(self, empty_state):
        """A feature request should be rejected without running the workers."""
        state = dict(empty_state)
        state["raw_issue"] = (
            "Please add a CSV export button to the Orders page. Right now we "
            "copy rows by hand into a spreadsheet."
        )
        app = build_graph()
        final = app.invoke(state)

        assert final["is_valid_bug"] is False
        # Worker-owned fields should still be at their zero values.
        assert not final.get("notification_message")
        assert not final.get("assignee")

    def test_iteration_count_advances(self, empty_state):
        state = dict(empty_state)
        state["raw_issue"] = "Payment outage: card declined on every checkout."
        app = build_graph()
        final = app.invoke(state)
        assert 1 <= final["iteration_count"] <= MAX_ITERATIONS


@pytest.mark.integration
class TestReducerMergesParallelLogs:
    """Non-LLM proof that the operator.add reducer merges parallel updates."""

    def test_logs_field_is_append_only(self, empty_state):
        from core.state import TriageState
        from langgraph.graph import StateGraph, END

        def emit_a(state):
            return {"logs": [{"agent": "A", "timestamp": "", "input_prompt": "",
                              "user_input": "", "llm_raw_output": "",
                              "tool_called": None, "tool_output": None,
                              "latency_ms": 0}]}

        def emit_b(state):
            return {"logs": [{"agent": "B", "timestamp": "", "input_prompt": "",
                              "user_input": "", "llm_raw_output": "",
                              "tool_called": None, "tool_output": None,
                              "latency_ms": 0}]}

        def fan_out(state):
            return ["a", "b"]

        def join(state):
            return {}

        graph = StateGraph(TriageState)
        graph.add_node("start", lambda s: {})
        graph.add_node("a", emit_a)
        graph.add_node("b", emit_b)
        graph.add_node("join", join)
        graph.set_entry_point("start")
        graph.add_conditional_edges(
            "start", fan_out, {"a": "a", "b": "b"},
        )
        graph.add_edge("a", "join")
        graph.add_edge("b", "join")
        graph.add_edge("join", END)
        app = graph.compile()

        final = app.invoke(dict(empty_state))
        agents_seen = {log["agent"] for log in final["logs"]}
        assert agents_seen == {"A", "B"}, (
            "reducer must merge both parallel log entries; got " + repr(agents_seen)
        )
