"""Member 3 — Reproducer agent + codebase_searcher tool."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from agents import reproducer
from tools.codebase_searcher import codebase_searcher
from tests.llm_judge import judge


# =============================================================================
# Tier 1 — Tool: codebase_searcher
# =============================================================================

class TestCodebaseSearcher:

    def test_returns_hits_for_known_keyword(self, mock_codebase: str):
        r = codebase_searcher("login", directory=mock_codebase)
        assert r["error"] is None
        files = {m["file"] for m in r["matches"]}
        assert "auth.py" in files
        assert "ignored.txt" not in files, "non-code files must be skipped"

    def test_case_insensitive(self, mock_codebase: str):
        r = codebase_searcher("LOGIN", directory=mock_codebase)
        assert any("auth.py" in m["file"] for m in r["matches"])

    def test_short_keyword_rejected(self, mock_codebase: str):
        r = codebase_searcher("a", directory=mock_codebase)
        assert r["error"] is not None
        assert r["matches"] == []

    def test_missing_directory_returns_error(self):
        r = codebase_searcher("login", directory="no/such/dir")
        assert r["error"] is not None
        assert r["matches"] == []

    def test_non_string_keyword(self, mock_codebase: str):
        r = codebase_searcher(123, directory=mock_codebase)  # type: ignore[arg-type]
        assert r["error"] is not None

    @given(kw=st.text(alphabet=st.characters(blacklist_categories=("Cs",)),
                       min_size=3, max_size=20))
    @settings(max_examples=20, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_result_shape_is_stable(self, kw: str, mock_codebase: str):
        """Every call returns a dict with matches, total_files_scanned, error."""
        r = codebase_searcher(kw, directory=mock_codebase)
        assert set(r.keys()) >= {"matches", "total_files_scanned", "error"}
        assert isinstance(r["matches"], list)


# =============================================================================
# Tier 1 — Agent: Reproducer invariants (LLM stubbed)
# =============================================================================

def _stub_llm(response_content: str):
    class _StubLLM:
        def invoke(self, messages):
            class _Msg:
                content = response_content
            return _Msg()
    return patch("agents.reproducer.get_llm", return_value=_StubLLM())


class TestReproducerInvariants:

    def test_returns_at_least_two_repro_steps(self, make_state):
        state = make_state(title="Login crash", description="Login button crashes the tab.")
        with _stub_llm('{"repro_steps": ["Open app.", "Tap Login.", "Observe crash."], '
                       '"expected_behavior": "Login succeeds.", '
                       '"actual_behavior": "Tab crashes.", '
                       '"related_files": ["auth.py"], "missing_info": []}'):
            update = reproducer.run(state)
        assert len(update["repro_steps"]) >= 2

    def test_malformed_json_falls_back_to_default_steps(self, make_state):
        state = make_state(title="x", description="y")
        with _stub_llm("not JSON"):
            update = reproducer.run(state)
        assert len(update["repro_steps"]) >= 2
        assert update.get("errors")

    def test_related_files_include_searcher_hits(self, make_state):
        """discovered_files from the tool must be merged into related_files."""
        state = make_state(
            title="Login crash on mobile Safari",
            description="Login button fails.",
        )
        with _stub_llm('{"repro_steps": ["a", "b"], "expected_behavior": "", '
                       '"actual_behavior": "", "related_files": [], "missing_info": []}'):
            # Patch the codebase_searcher used inside reproducer to return a known file.
            with patch("agents.reproducer.codebase_searcher",
                       return_value={"matches": [{"file": "auth.py",
                                                  "line_number": 1,
                                                  "line_content": "login"}],
                                     "total_files_scanned": 1, "error": None}):
                update = reproducer.run(state)
        assert "auth.py" in update["related_files"]

    def test_log_captures_tool_call(self, make_state):
        state = make_state(title="t", description="d")
        with _stub_llm('{"repro_steps": ["1"], "expected_behavior": "", '
                       '"actual_behavior": "", "related_files": [], "missing_info": []}'):
            update = reproducer.run(state)
        log = update["logs"][0]
        assert log["agent"] == "reproducer"
        assert log["tool_called"] == "codebase_searcher"

    @given(desc=st.text(min_size=0, max_size=200))
    @settings(max_examples=10, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_never_raises(self, desc: str, empty_state):
        state = dict(empty_state)
        state["description"] = desc
        state["title"] = "probe"
        with _stub_llm('{"repro_steps": ["x"], "expected_behavior": "", '
                       '"actual_behavior": "", "related_files": [], "missing_info": []}'):
            with patch("agents.reproducer.codebase_searcher",
                       return_value={"matches": [], "total_files_scanned": 0,
                                     "error": None}):
                reproducer.run(state)  # must not raise


# =============================================================================
# Tier 2 — LLM-as-a-Judge
# =============================================================================

@pytest.mark.llm
class TestReproducerJudged:

    def test_judge_accepts_concrete_repro(self, make_state):
        state = make_state(
            title="Login page crashes on mobile Safari iOS 17",
            description=(
                "Tapping the Login button on Safari iOS 17 immediately crashes the "
                "tab. Login works on Chrome iOS and desktop Safari."
            ),
            tags=["auth", "mobile"],
        )
        update = reproducer.run(state)
        answer = (
            f"steps={update['repro_steps']}\n"
            f"expected={update['expected_behavior']}\n"
            f"actual={update['actual_behavior']}"
        )
        verdict = judge(
            question=f"{state['title']}\n{state['description']}",
            answer=answer,
            rubric=("Good repro steps are numbered, imperative, and specifically "
                    "mention Safari iOS 17 and tapping Login. Expected/actual should "
                    "contrast meaningfully. Score 4+ if steps are concrete and "
                    "on-topic, 5 if they also separate prerequisites from actions."),
        )
        assert verdict["score"] >= 3, f"judge rejected: {verdict['reasoning']}"


# =============================================================================
# Tier 3 — Golden dataset (member3-owned cases)
# =============================================================================

@pytest.mark.llm
class TestReproducerGolden:

    def test_member3_cases_emit_repro(self, golden_by_owner, make_state):
        cases = golden_by_owner["member3"]
        for case in cases:
            state = make_state(
                title=case["title"],
                description=case["description"],
                tags=case["tags"],
            )
            update = reproducer.run(state)
            assert update["repro_steps"], f"{case['id']}: no repro steps"
            assert isinstance(update["expected_behavior"], str)
            assert isinstance(update["actual_behavior"], str)
