"""JSONL execution tracer per Lecture 9 'Tracing Execution Trees'."""
import json
from datetime import datetime
from pathlib import Path
from typing import Any


LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def new_run_id() -> str:
    """Generate a unique run identifier based on timestamp."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def build_log_entry(
    agent: str,
    system_prompt: str,
    user_input: str,
    llm_output: str,
    tool_called: str | None = None,
    tool_output: Any = None,
    latency_ms: int = 0,
) -> dict:
    """Construct a single structured log entry.

    Captures the four things Lecture 9 requires:
        1. Exact system prompt and user input
        2. Raw LLM output
        3. Tool call output
        4. Latency in ms
    """
    return {
        "timestamp": datetime.now().isoformat(),
        "agent": agent,
        "input_prompt": system_prompt[:500],
        "user_input": user_input[:1000],
        "llm_raw_output": str(llm_output)[:2000],
        "tool_called": tool_called,
        "tool_output": str(tool_output)[:1000] if tool_output else None,
        "latency_ms": latency_ms,
    }


def persist_run(run_id: str, logs: list[dict]) -> Path:
    """Write all log entries for a run to a JSONL file."""
    path = LOG_DIR / f"run_{run_id}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for entry in logs:
            f.write(json.dumps(entry) + "\n")
    return path
