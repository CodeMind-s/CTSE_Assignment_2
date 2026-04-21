"""GitHub public issue fetcher tool."""
import requests
from typing import TypedDict


class IssueResult(TypedDict):
    title: str
    body: str
    labels: list[str]
    state: str
    created_at: str
    error: str | None


def fetch_github_issue(issue_number: int, repo: str) -> IssueResult:
    """Fetch a public GitHub issue without authentication.

    Uses the public GitHub REST API (rate-limited to 60 req/hour unauthenticated,
    which is sufficient for our use case).

    Args:
        issue_number: The issue number to fetch (must be positive).
        repo: Repository in 'owner/name' format (e.g., 'microsoft/vscode').

    Returns:
        IssueResult dict with title, body, labels, state, created_at.
        On failure, returns dict with 'error' key containing a natural-language
        error string (per Lecture 9 'Graceful Tool Failure' pattern).

    Raises:
        Never raises — all failures are returned as error dicts.

    Example:
        >>> fetch_github_issue(1, "octocat/Hello-World")
        {'title': '...', 'body': '...', 'labels': [...], ...}
    """
    if not isinstance(issue_number, int) or issue_number <= 0:
        return {"error": "issue_number must be a positive integer. "
                         "Please provide a valid GitHub issue number.",
                "title": "", "body": "", "labels": [], "state": "", "created_at": ""}

    if "/" not in repo or repo.count("/") != 1:
        return {"error": "repo must be in 'owner/name' format. "
                         "Example: 'microsoft/vscode'",
                "title": "", "body": "", "labels": [], "state": "", "created_at": ""}

    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
    try:
        resp = requests.get(url, timeout=10,
                            headers={"Accept": "application/vnd.github.v3+json"})
        if resp.status_code == 404:
            return {"error": f"Issue #{issue_number} not found in {repo}. "
                             "Verify the repo name and issue number.",
                    "title": "", "body": "", "labels": [], "state": "", "created_at": ""}
        if resp.status_code == 403:
            return {"error": "GitHub API rate limit exceeded. "
                             "Try again in an hour or use fallback data.",
                    "title": "", "body": "", "labels": [], "state": "", "created_at": ""}
        resp.raise_for_status()
        data = resp.json()
        return {
            "title": data["title"],
            "body": data.get("body") or "",
            "labels": [lbl["name"] for lbl in data.get("labels", [])],
            "state": data["state"],
            "created_at": data["created_at"],
            "error": None,
        }
    except requests.Timeout:
        return {"error": "GitHub API request timed out after 10s. "
                         "Network may be slow — try again.",
                "title": "", "body": "", "labels": [], "state": "", "created_at": ""}
    except requests.RequestException as e:
        return {"error": f"Network error fetching issue: {str(e)[:200]}",
                "title": "", "body": "", "labels": [], "state": "", "created_at": ""}
