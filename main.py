"""CLI entry point for the bug triage multi-agent system.

Usage:
    python main.py --bug "Login button does nothing on Safari iOS"
    python main.py --issue 123 --repo octocat/Hello-World
"""
import argparse
import os
import sys
import time

from dotenv import load_dotenv

from core.graph import MAX_ITERATIONS, build_graph
from core.logger import new_run_id, persist_run
from tools.slack_notifier import post_to_slack


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Bug Triage Multi-Agent System")
    ap.add_argument("--bug", help="Raw bug description text")
    ap.add_argument("--issue", type=int, help="GitHub issue number")
    ap.add_argument("--repo", help="GitHub repo in 'owner/name' format")
    ap.add_argument("--post-to-slack", action="store_true",
                    help="Also POST the notification to SLACK_WEBHOOK_URL.")
    return ap.parse_args()


def _initial_state(bug: str | None, issue: int | None, repo: str | None) -> dict:
    return {
        "raw_issue": bug or "",
        "issue_number": issue,
        "repo": repo,
        "is_valid_bug": False,
        "title": "",
        "description": "",
        "tags": [],
        "severity": None,
        "severity_evidence": [],
        "severity_confidence": 0.0,
        "repro_steps": [],
        "expected_behavior": "",
        "actual_behavior": "",
        "related_files": [],
        "assignee": "",
        "assignee_reason": "",
        "notification_message": "",
        "logs": [],
        "iteration_count": 0,
        "errors": [],
    }


def main() -> None:
    load_dotenv()
    args = parse_args()
    if not args.bug and not (args.issue and args.repo):
        print("error: provide --bug OR (--issue AND --repo)", file=sys.stderr)
        sys.exit(2)

    app = build_graph()

    print("Running triage...", flush=True)
    t0 = time.time()
    t_last = t0
    final: dict = {}
    for mode, chunk in app.stream(
        _initial_state(args.bug, args.issue, args.repo),
        stream_mode=["updates", "values"],
    ):
        if mode == "updates":
            now = time.time()
            for node_name in chunk.keys():
                print(f"  [OK] {node_name:12s} ({now - t_last:5.1f}s)", flush=True)
            t_last = now
        elif mode == "values":
            final = chunk
    print(f"Total:    {time.time() - t0:.1f}s", flush=True)

    run_id = new_run_id()
    log_path = persist_run(run_id, final.get("logs", []))

    bar = "=" * 60
    print(bar)
    print(f"Title:     {final.get('title') or '(none)'}")
    print(f"Valid bug: {final.get('is_valid_bug')}")
    print(f"Severity:  {final.get('severity') or '(n/a)'}")
    print(f"Assignee:  {final.get('assignee') or '(unassigned)'}")
    print(f"Log file:  {log_path}")
    if final.get("errors"):
        print(f"Errors:    {final['errors']}")
    print(bar)
    msg = final.get("notification_message")
    if msg:
        print(msg)
    else:
        print("(no notification — bug was rejected by Coordinator)")

    if args.post_to_slack and msg:
        result = post_to_slack(msg)
        if result["posted"]:
            print(f"\n[slack] posted to webhook (HTTP {result['status_code']})")
        else:
            print(f"\n[slack] post failed: {result['error']}", file=sys.stderr)

    if not final.get("is_valid_bug") or final.get("iteration_count", 0) >= MAX_ITERATIONS:
        sys.exit(1)


if __name__ == "__main__":
    main()
